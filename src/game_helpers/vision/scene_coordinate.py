"""Read the 800×600 player-location HUD from one full client screenshot.

The on-screen HUD is two separate lines: a scene name, then ``X:n Y:n``.
``地图名[x,y]`` is the assembled result, not the pixels sent to OCR.

Before either OCR call the full frame is:

1. converted to RGB;
2. cropped into the scene-name band and the coordinate band;
3. reduced to light glyph ink on a white page, which drops black outlines
   and the textured HUD background;
4. padded and enlarged, because Windows OCR returns empty text on a
   few-dozen-pixel strip.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from PIL import Image

from game_helpers.core.models import Rect
from game_helpers.vision.ocr import (
    OCRBackend,
    assemble_scene_coordinate,
    format_scene_coordinate,
    parse_hud_xy,
    parse_scene_name,
)

BASELINE_SIZE = (800, 600)
# Measured on an 800×600 capture: scene glyphs sit under the clock and above
# the coordinate bar; the coordinate glyphs sit above the mail/calendar buttons.
SCENE_NAME_BOX = (26, 14, 106, 34)
COORDINATE_BOX = (26, 62, 112, 80)
GLYPH_LUMINANCE = 185
OCR_PAD = 16
OCR_SCALE = 4
# Windows OCR reads this HUD's open-top 4 as Y (or r), or drops the X digits entirely.
_MISREAD_FOUR_RE = re.compile(
    r"(?P<head>X\s*[.:：]*\s*\d(?:\s*\d)*)(?P<gap>\s+)(?P<letter>[YyRr])(?P<tail>\s*[:：.])",
    re.IGNORECASE,
)
_BARE_X_RE = re.compile(
    r"(?P<head>X\s*[.:：]+)(?P<gap>\s*)(?P<rest>Y\s*[:：.].*)",
    re.IGNORECASE,
)
_X_NUMBER_RE = re.compile(
    r"(?P<head>X\s*[.:：]+\s*)(?P<digits>(?:\d\s*)*?)(?P<rest>Y\s*[:：.].*)",
    re.IGNORECASE,
)
_EIGHT_AS_E_RE = re.compile(
    r"(?P<head>Y\s*[:：.]\s*(?:\d\s*)*?)(?P<letter>[Ee])",
)
_Y_DIGITS_RE = re.compile(
    r"Y\s*[:：.]*\s*(?P<digits>(?:\d\s*)+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PreparedBand:
    name: str
    box: tuple[int, int, int, int]
    raw: Image.Image
    prepared: Image.Image


@dataclass(frozen=True)
class SceneCoordinateReading:
    scene_text: str
    coordinate_text: str
    scene_box: tuple[int, int, int, int]
    coordinate_box: tuple[int, int, int, int]
    parsed: tuple[str, int, int] | None
    formatted: str | None
    scene_ok: bool
    coordinate_ok: bool


def scale_box(
    box: tuple[int, int, int, int],
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    """Map an 800×600 client box onto the current full screenshot."""
    sx = width / BASELINE_SIZE[0]
    sy = height / BASELINE_SIZE[1]
    left, top, right, bottom = box
    return (
        max(0, min(width, round(left * sx))),
        max(0, min(height, round(top * sy))),
        max(0, min(width, round(right * sx))),
        max(0, min(height, round(bottom * sy))),
    )


def isolate_light_glyphs(image: Image.Image, *, threshold: int = GLYPH_LUMINANCE) -> Image.Image:
    """Keep near-white glyph fill as black ink on a white page."""
    rgb = image.convert("RGB")
    page = Image.new("L", rgb.size, 255)
    source = rgb.load()
    target = page.load()
    for y in range(rgb.height):
        for x in range(rgb.width):
            red, green, blue = source[x, y]
            if min(red, green, blue) >= threshold:
                target[x, y] = 0
    return page


def prepare_band(
    image: Image.Image,
    box: tuple[int, int, int, int],
    *,
    scale: int = OCR_SCALE,
    pad: int = OCR_PAD,
) -> PreparedBand:
    raw = image.convert("RGB").crop(box)
    ink = isolate_light_glyphs(raw)
    padded = Image.new("L", (ink.width + pad * 2, ink.height + pad * 2), 255)
    padded.paste(ink, (pad, pad))
    prepared = padded.resize(
        (padded.width * scale, padded.height * scale),
        Image.Resampling.LANCZOS,
    )
    return PreparedBand(name="", box=box, raw=raw, prepared=prepared)


def prepare_player_location(image: Image.Image) -> tuple[PreparedBand, PreparedBand]:
    """Crop and prepare the scene-name band and the coordinate band."""
    rgb = image.convert("RGB")
    scene_box = scale_box(SCENE_NAME_BOX, rgb.width, rgb.height)
    coordinate_box = scale_box(COORDINATE_BOX, rgb.width, rgb.height)
    scene = prepare_band(rgb, scene_box)
    coordinate = prepare_band(rgb, coordinate_box)
    return (
        PreparedBand("scene_name", scene.box, scene.raw, scene.prepared),
        PreparedBand("coordinate", coordinate.box, coordinate.raw, coordinate.prepared),
    )


def correct_scene_name(text: str, ink: Image.Image) -> str:
    """Turn a scene-name reading into the on-screen place name.

    Windows OCR splits this pixel font into spaced characters and may read
    朱 as 耒. A light UI fragment to the right of the name is not part of it,
    so only the character run is kept. 耒 is rewritten to 朱, 皋 to 寨, and 竟 to 境,
    only when the glyph still has that character's strokes. A dropped 唐 is
    inserted only when that unread cell sits between 大 and 官.
    """
    characters = re.findall(r"[\u4e00-\u9fff]", text)
    if not characters:
        return text
    glyphs = _scene_character_crops(ink.convert("L"))
    corrected: list[str] = []
    for index, character in enumerate(characters):
        if character == "耒" and index < len(glyphs) and _looks_like_zhu(glyphs[index]):
            corrected.append("朱")
        elif character == "皋" and index < len(glyphs) and _looks_like_zhai(glyphs[index]):
            corrected.append("寨")
        elif character == "竟" and index < len(glyphs) and _looks_like_jing(glyphs[index]):
            corrected.append("境")
        else:
            corrected.append(character)
    corrected = _insert_dropped_tang(corrected, glyphs)
    return "".join(corrected)


def _scene_character_crops(page: Image.Image) -> list[Image.Image]:
    """Character cells from the left, stopping before a distant UI fragment."""
    spans: list[tuple[int, int]] = []
    start: int | None = None
    for x in range(page.width + 1):
        has_ink = x < page.width and _column_has_ink(page, x)
        if has_ink and start is None:
            start = x
        elif not has_ink and start is not None:
            spans.append((start, x))
            start = None
    crops: list[Image.Image] = []
    previous_end: int | None = None
    for left, right in spans:
        if previous_end is not None and left - previous_end >= 8:
            break
        crops.append(page.crop((left, 0, right, page.height)))
        previous_end = right
    return crops


def _looks_like_zhu(crop: Image.Image) -> bool:
    """朱 has a stroke left of its first horizontal; 耒's first horizontal does not."""
    tight = _tight_crop(crop)
    if tight is None or tight.width < 8 or tight.height < 8:
        return False
    rows = _ink_rows(tight)
    bars = [
        index
        for index, cols in enumerate(rows)
        if cols
        and len(cols) >= tight.width * 0.45
        and cols[-1] - cols[0] + 1 == len(cols)
    ]
    if len(bars) < 2:
        return False
    first = bars[0]
    bar_left = min(rows[first])
    if bar_left < 2:
        return False
    stroke_continues = any(
        rows[index] and min(rows[index]) < bar_left
        for index in range(first + 1, min(tight.height, first + 4))
    )
    if not stroke_continues:
        return False
    return len(rows[bars[1]]) >= tight.width * 0.9


def _looks_like_zhai(crop: Image.Image) -> bool:
    """寨 has a roof bar and a 木 that spreads at the bottom; 皋 ends in a stem."""
    tight = _tight_crop(crop)
    if tight is None or tight.width < 8 or tight.height < 10:
        return False
    rows = _ink_rows(tight)
    ink_rows = [index for index, cols in enumerate(rows) if cols]
    if len(ink_rows) < 8:
        return False
    top = ink_rows[: max(1, len(ink_rows) // 3)]
    if not any(len(rows[index]) >= tight.width * 0.85 for index in top):
        return False
    last = rows[ink_rows[-1]]
    return min(last) <= tight.width * 0.3 and max(last) >= tight.width * 0.7


def _insert_dropped_tang(characters: list[str], glyphs: list[Image.Image]) -> list[str]:
    """Insert 唐 when OCR returned 大官府 and the second cell is that character."""
    if characters != ["大", "官", "府"] or len(glyphs) != 4:
        return characters
    if not _looks_like_tang(glyphs[1]):
        return characters
    return ["大", "唐", "官", "府"]


def _looks_like_jing(crop: Image.Image) -> bool:
    """境 keeps a straight 土 stem on the left. 竟 and 梦 do not."""
    tight = _tight_crop(crop)
    if tight is None or tight.width < 10 or tight.height < 10:
        return False
    rows = _ink_rows(tight)
    counts = [sum(x in cols for cols in rows) for x in range(tight.width)]
    for x in range(1, tight.width // 3):
        if counts[x] < tight.height * 0.7:
            continue
        if counts[x - 1] <= counts[x] * 0.4 and counts[x + 1] <= counts[x] * 0.4:
            return True
    return False


def _looks_like_tang(crop: Image.Image) -> bool:
    """唐 stacks indented bars beside the 广 stroke. 大, 官, and 府 do not."""
    tight = _tight_crop(crop)
    if tight is None or tight.width < 10 or tight.height < 10:
        return False
    rows = _ink_rows(tight)
    dense = [(index, min(cols)) for index, cols in enumerate(rows) if len(cols) >= tight.width * 0.65]
    if len(dense) < 4 or dense[0][1] < 2:
        return False
    return any(cols and min(cols) <= 2 and len(cols) < tight.width * 0.65 for cols in rows)


def restore_missing_x_digits(text: str, ink: Image.Image) -> str:
    """Fill X digits that OCR skipped when those glyphs are the open-top 4.

    ``X ： Y ： 2 2`` on an ``X:44 Y:22`` line becomes ``X ： 4 4 Y ： 2 2``.
    """
    match = _BARE_X_RE.search(text)
    if match is None:
        return text
    kinds = _x_digit_kinds(ink)
    if not kinds or any(kind != "four" for kind in kinds):
        return text
    digits = " ".join("4" for _ in kinds)
    return f"{match.group('head')} {digits} {match.group('rest')}"


def restore_leading_fours(text: str, ink: Image.Image) -> str:
    """Put dropped leading 4s back in front of the X digits OCR kept.

    ``X ： 6 Y ： 2 2`` on an ``X:46 Y:22`` line becomes ``X ： 4 6 Y ： 2 2``.
    A 4 that sits after a recognized digit is appended separately.
    """
    match = _X_NUMBER_RE.search(text)
    if match is None:
        return text
    kinds = _x_slot_kinds(ink)
    if not kinds:
        return text
    recognized = len(re.findall(r"\d", match.group("digits")))
    missing = len(kinds) - recognized
    if missing <= 0 or any(kind != "four" for kind in kinds[:missing]):
        return text
    inserted = " ".join("4" for _ in range(missing))
    return f"{match.group('head')}{inserted} {match.group('digits')}{match.group('rest')}"


def place_dropped_fours(text: str, ink: Image.Image) -> str:
    """Insert skipped 4s at the glyph slot where they sit, not at the end.

    ``X ： 1 2 Y ： 12`` on an ``X:142 Y:12`` line becomes ``X ： 1 4 2 Y ： 12``.
    """
    match = _X_NUMBER_RE.search(text)
    if match is None:
        return text
    kinds = _x_slot_kinds(ink)
    if not kinds or "four" not in kinds:
        return text
    digits = re.findall(r"\d", match.group("digits"))
    if len(kinds) == len(digits):
        return text
    if sum(kind != "four" for kind in kinds) != len(digits):
        return text
    placed: list[str] = []
    cursor = 0
    for kind in kinds:
        if kind == "four":
            placed.append("4")
        else:
            placed.append(digits[cursor])
            cursor += 1
    return f"{match.group('head')}{' '.join(placed)} {match.group('rest')}"


def place_dropped_y_fours(text: str, ink: Image.Image) -> str:
    """Insert a skipped 4 into the Y digits at its glyph slot.

    ``X ： 79 Y ： 2`` on an ``X:79 Y:24`` line becomes ``X ： 79 Y ： 2 4``.
    """
    match = _Y_DIGITS_RE.search(text)
    if match is None:
        return text
    crops = _crops_after_y(ink)
    if not crops:
        return text
    kinds = ["four" if _known_digit(crop) == "4" else "other" for crop in crops]
    digits = re.findall(r"\d", match.group("digits"))
    if "four" not in kinds or len(kinds) == len(digits):
        return text
    if sum(kind != "four" for kind in kinds) != len(digits):
        return text
    placed: list[str] = []
    cursor = 0
    for kind in kinds:
        if kind == "four":
            placed.append("4")
        else:
            placed.append(digits[cursor])
            cursor += 1
    return text[: match.start("digits")] + " ".join(placed) + text[match.end("digits") :]


def restore_trailing_fours(text: str, ink: Image.Image) -> str:
    """Append a 4 that OCR skipped after the X digits it kept.

    ``X ： 8 Y ： 8 7`` on an ``X:84 Y:87`` line becomes ``X ： 8 4 Y ： 8 7``.
    """
    match = _X_NUMBER_RE.search(text)
    if match is None:
        return text
    kinds = _x_slot_kinds(ink)
    if not kinds:
        return text
    recognized = len(re.findall(r"\d", match.group("digits")))
    if recognized >= len(kinds):
        return text
    if any(kind != "four" for kind in kinds[recognized:]):
        return text
    inserted = " ".join("4" for _ in kinds[recognized:])
    digits = match.group("digits")
    gap = "" if digits.endswith((" ", "：", ":")) or not digits else " "
    return f"{match.group('head')}{digits}{gap}{inserted} {match.group('rest')}"


def correct_misread_four(text: str, ink: Image.Image) -> str:
    """Rewrite a 4 that OCR emitted as Y when that 4 still sits before the real Y.

    ``X ： 5 Y ： 7 2`` on an ``X:54 Y:72`` line becomes ``X ： 5 4 ： 7 2``.
    A real ``X:5 Y:72`` has no 4-shaped glyph in the X digits, so it stays.
    """
    match = _MISREAD_FOUR_RE.search(text)
    if match is None:
        return text
    recognized = len(re.findall(r"\d", match.group("head")))
    digit_count, four_before_y = _x_digits_before_y(ink)
    if not four_before_y or digit_count is None or recognized + 1 != digit_count:
        return text
    return text[: match.start("letter")] + "4" + text[match.end("letter") :]


def correct_misread_eight(text: str, ink: Image.Image) -> str:
    """Rewrite an 8 that OCR emitted as E in the Y digits.

    ``X ： 29 Y ： 6E`` on an ``X:29 Y:68`` line becomes ``X ： 29 Y ： 68``.
    """
    match = _EIGHT_AS_E_RE.search(text)
    if match is None:
        return text
    crops = _crops_after_y(ink)
    recognized = len(re.findall(r"\d", match.group("head")))
    if recognized >= len(crops) or not _looks_like_eight(crops[recognized]):
        return text
    return text[: match.start("letter")] + "8" + text[match.end("letter") :]


def correct_misread_seven(text: str, ink: Image.Image) -> str:
    """Rewrite a 7 that OCR emitted as 1 in the Y digits.

    ``Y ： 31`` on a ``Y:37`` line becomes ``Y ： 37``.
    """
    match = _Y_DIGITS_RE.search(text)
    if match is None:
        return text
    crops = _crops_after_y(ink)
    spans = list(re.finditer(r"\d", match.group("digits")))
    if len(spans) != len(crops):
        return text
    chars = list(match.group("digits"))
    changed = False
    for span, crop in zip(spans, crops):
        if chars[span.start()] == "1" and _looks_like_seven(crop):
            chars[span.start()] = "7"
            changed = True
    if not changed:
        return text
    return text[: match.start("digits")] + "".join(chars) + text[match.end("digits") :]


def restore_missing_y(text: str, ink: Image.Image) -> str:
    """Append a Y value when OCR stopped after X and the Y glyphs are readable.

    ``X ： 6`` on an ``X:6 Y:8`` line becomes ``X ： 6 Y ： 8``.
    """
    if re.search(r"Y", text, re.IGNORECASE):
        return text
    if re.search(r"X\s*[.:：]", text, re.IGNORECASE) is None:
        return text
    digits = [_known_digit(crop) for crop in _crops_after_y(ink)]
    if not digits or any(digit is None for digit in digits):
        return text
    return text.rstrip() + " Y ： " + " ".join(digits)


def trim_coordinate_noise(text: str) -> str:
    """Drop the icon fragment OCR places before the X label."""
    match = re.search(r"X\s*[.:：]", text, re.IGNORECASE)
    if match is None or match.start() == 0:
        return text
    return text[match.start() :]


def restore_blank_y_digits(text: str, ink: Image.Image) -> str:
    """Fill Y digits when the label was read and the number was not.

    ``X ： 50 Y ：`` on an ``X:50 Y:47`` line becomes ``X ： 50 Y ： 4 7``.
    """
    if re.search(r"Y\s*[:：.]*\s*\d", text, re.IGNORECASE):
        return text
    match = re.search(r"(?P<head>Y\s*[:：.])\s*$", text, re.IGNORECASE)
    if match is None:
        return text
    digits = [_known_digit(crop) for crop in _crops_after_y(ink)]
    if not digits or any(digit is None for digit in digits):
        return text
    return f"{text[: match.end('head')]} {' '.join(digits)}"


def drop_trailing_bare_y(text: str) -> str:
    """Drop a second ``Y ：`` that OCR appended after the digits were recovered."""
    if re.search(r"Y\s*[:：.]*\s*\d", text, re.IGNORECASE) is None:
        return text
    return re.sub(r"\s*Y\s*[:：.]\s*$", "", text, flags=re.IGNORECASE)


def _known_digit(crop: Image.Image) -> str | None:
    if _looks_like_eight(crop):
        return "8"
    if _looks_like_seven(crop):
        return "7"
    if _looks_like_three(crop):
        return "3"
    if _looks_like_nine(crop):
        return "9"
    tight = _tight_crop(crop)
    if tight is not None and _is_open_four(tight):
        return "4"
    return None


def _looks_like_nine(crop: Image.Image) -> bool:
    """9 keeps a loop on top and a right stem under it. 0, 4, 6, and 8 do not."""
    tight = _tight_crop(crop)
    if tight is None or tight.width < 4 or tight.height < 8:
        return False
    rows = _ink_rows(tight)
    ink_rows = [index for index, cols in enumerate(rows) if cols]
    if len(ink_rows) < 8 or _is_horizontal_bar(rows[ink_rows[-1]], tight.width):
        return False
    if rows[ink_rows[0]] and min(rows[ink_rows[0]]) >= tight.width * 0.35:
        return False
    top = ink_rows[: len(ink_rows) // 2]
    if not any(_has_split_right(rows[index], tight.width) for index in top):
        return False
    midpoint = ink_rows[len(ink_rows) // 2]
    stems = [
        index
        for index in ink_rows
        if index > midpoint
        and rows[index]
        and min(rows[index]) >= tight.width * 0.45
        and max(rows[index]) >= tight.width * 0.65
    ]
    return len(stems) >= 2


def restore_non_digit_y(text: str, ink: Image.Image) -> str:
    """Replace a Y value that OCR read as a character when the glyphs are digits.

    ``X ： 80 Y ： 四`` on an ``X:80 Y:49`` line becomes ``X ： 80 Y ： 4 9``.
    """
    digits = [_known_digit(crop) for crop in _crops_after_y(ink)]
    if not digits or any(digit is None for digit in digits):
        return text
    match = re.search(r"(?P<head>Y\s*[:：.]*)(?P<tail>.*)$", text, re.IGNORECASE)
    if match is None:
        return text
    found = re.sub(r"\s+", "", match.group("tail"))
    if found == "".join(digits) or found.isdigit():
        return text
    return f"{text[: match.end('head')]} {' '.join(digits)}"


def _looks_like_seven(crop: Image.Image) -> bool:
    """7 has a top bar and a right-hand stem. 1 keeps a bar at the bottom."""
    tight = _tight_crop(crop)
    if tight is None or tight.width < 3 or tight.height < 8:
        return False
    rows = _ink_rows(tight)
    ink_rows = [index for index, cols in enumerate(rows) if cols]
    if len(ink_rows) < 8:
        return False
    top = rows[ink_rows[0]]
    bottom = rows[ink_rows[-1]]
    top_is_bar = len(top) >= tight.width * 0.7 and top[-1] - top[0] + 1 == len(top)
    bottom_is_bar = len(bottom) >= tight.width * 0.7
    return top_is_bar and not bottom_is_bar and min(bottom) >= tight.width * 0.4


def _looks_like_three(crop: Image.Image) -> bool:
    """3 has top and bottom bars and a short middle stroke on the right."""
    tight = _tight_crop(crop)
    if tight is None or tight.width < 4 or tight.height < 8:
        return False
    rows = _ink_rows(tight)
    ink_rows = [index for index, cols in enumerate(rows) if cols]
    if len(ink_rows) < 8:
        return False

    def is_bar(cols: list[int]) -> bool:
        return bool(cols) and len(cols) >= tight.width * 0.55 and cols[-1] - cols[0] + 1 == len(cols)

    if not is_bar(rows[ink_rows[0]]) or not is_bar(rows[ink_rows[-1]]):
        return False
    middle = ink_rows[len(ink_rows) // 3 : len(ink_rows) * 2 // 3]
    return any(
        rows[index]
        and len(rows[index]) <= tight.width * 0.5
        and min(rows[index]) >= tight.width * 0.3
        for index in middle
    )


def _crops_after_y(ink: Image.Image) -> list[Image.Image]:
    page = ink.convert("L")
    spans: list[tuple[int, int]] = []
    start: int | None = None
    for x in range(page.width + 1):
        has_ink = x < page.width and _column_has_ink(page, x)
        if has_ink and start is None:
            start = x
        elif not has_ink and start is not None:
            spans.append((start, x))
            start = None
    kinds: list[str] = []
    crops: list[Image.Image] = []
    for left, right in spans:
        crop = page.crop((left, 0, right, page.height))
        kind = _classify_glyph(crop)
        if kind == "noise":
            continue
        kinds.append(kind)
        crops.append(crop)
    y_index = next((index for index, kind in enumerate(kinds) if kind == "y"), None)
    if y_index is None:
        return []
    return [crops[index] for index in range(y_index + 1, len(crops)) if kinds[index] != "colon"]


def _looks_like_eight(crop: Image.Image) -> bool:
    """8 has three bars and a split right side between the middle and bottom bars."""
    tight = _tight_crop(crop)
    if tight is None or tight.width < 4 or tight.height < 8:
        return False
    rows = _ink_rows(tight)
    bars = [index for index, cols in enumerate(rows) if _is_horizontal_bar(cols, tight.width)]
    if len(bars) < 3:
        return False
    middle, bottom = bars[1], bars[-1]
    return any(_has_split_right(rows[index], tight.width) for index in range(middle + 1, bottom))


def _is_horizontal_bar(cols: list[int], width: int) -> bool:
    return bool(cols) and len(cols) >= width * 0.6 and cols[-1] - cols[0] + 1 == len(cols)


def _has_split_right(cols: list[int], width: int) -> bool:
    if len(cols) < 2:
        return False
    split = any(cols[index + 1] - cols[index] >= 2 for index in range(len(cols) - 1))
    return split and min(cols) <= width * 0.4 and max(cols) >= width * 0.6


def _x_slot_kinds(ink: Image.Image) -> list[str] | None:
    """Glyphs between the X colon and Y, including a wide digit read as X."""
    glyphs = _segment_glyphs(ink.convert("L"))
    y_index = next((index for index, kind in enumerate(glyphs) if kind == "y"), None)
    if y_index is None:
        return None
    colon_index = next((index for index, kind in enumerate(glyphs[:y_index]) if kind == "colon"), None)
    if colon_index is None:
        return None
    return [kind for kind in glyphs[colon_index + 1 : y_index] if kind != "colon"]


def _x_digit_kinds(ink: Image.Image) -> list[str] | None:
    glyphs = _segment_glyphs(ink.convert("L"))
    y_index = next((index for index, kind in enumerate(glyphs) if kind == "y"), None)
    if y_index is None:
        return None
    x_index = next((index for index, kind in enumerate(glyphs[:y_index]) if kind == "x"), None)
    start = x_index + 1 if x_index is not None else 0
    return [kind for kind in glyphs[start:y_index] if kind in {"digit", "four"}]


def _x_digits_before_y(ink: Image.Image) -> tuple[int | None, bool]:
    kinds = _x_digit_kinds(ink)
    if kinds is None:
        return None, False
    return len(kinds), "four" in kinds


def _segment_glyphs(page: Image.Image) -> list[str]:
    kinds: list[str] = []
    start: int | None = None
    for x in range(page.width + 1):
        has_ink = x < page.width and _column_has_ink(page, x)
        if has_ink and start is None:
            start = x
        elif not has_ink and start is not None:
            kind = _classify_glyph(page.crop((start, 0, x, page.height)))
            if kind != "noise":
                kinds.append(kind)
            start = None
    return kinds


def _column_has_ink(page: Image.Image, x: int) -> bool:
    return any(page.getpixel((x, y)) == 0 for y in range(page.height))


def _classify_glyph(crop: Image.Image) -> str:
    tight = _tight_crop(crop)
    if tight is None:
        return "noise"
    if _is_colon(tight):
        return "colon"
    if _is_y_letter(tight):
        return "y"
    if _is_x_letter(tight):
        return "x"
    if _is_open_four(tight):
        return "four"
    return "digit"


def _tight_crop(crop: Image.Image) -> Image.Image | None:
    pixels = [
        (x, y)
        for y in range(crop.height)
        for x in range(crop.width)
        if crop.getpixel((x, y)) == 0
    ]
    if len(pixels) < 6:
        return None
    xs = [x for x, _ in pixels]
    ys = [y for _, y in pixels]
    return crop.crop((min(xs), min(ys), max(xs) + 1, max(ys) + 1))


def _ink_rows(crop: Image.Image) -> list[list[int]]:
    return [
        [x for x in range(crop.width) if crop.getpixel((x, y)) == 0]
        for y in range(crop.height)
    ]


def _is_colon(crop: Image.Image) -> bool:
    if crop.width > 3:
        return False
    bands = 0
    in_band = False
    for y in range(crop.height):
        ink = any(crop.getpixel((x, y)) == 0 for x in range(crop.width))
        if ink and not in_band:
            bands += 1
            in_band = True
        elif not ink:
            in_band = False
    return bands == 2


def _is_y_letter(crop: Image.Image) -> bool:
    """Y forks at the top, then stays a center stem. X flares again at the bottom."""
    if crop.width < 6:
        return False
    rows = _ink_rows(crop)
    ink_rows = [index for index, cols in enumerate(rows) if cols]
    if len(ink_rows) < 6:
        return False
    if not (
        _has_side(rows[ink_rows[0]], crop.width, "left")
        and _has_side(rows[ink_rows[0]], crop.width, "right")
    ):
        return False
    midpoint = ink_rows[len(ink_rows) // 2]
    stem = 0
    flared = 0
    for index in ink_rows:
        if index < midpoint:
            continue
        cols = rows[index]
        left = _has_side(cols, crop.width, "left")
        right = _has_side(cols, crop.width, "right")
        if left and right:
            flared += 1
        elif not left and not right:
            stem += 1
    return stem >= 2 and flared == 0


def _is_x_letter(crop: Image.Image) -> bool:
    if crop.width < 6:
        return False
    rows = _ink_rows(crop)
    ink_rows = [index for index, cols in enumerate(rows) if cols]
    if len(ink_rows) < 6 or _row_coverage(rows[ink_rows[0]], crop.width) >= 0.92:
        return False
    top = ink_rows[: max(2, len(ink_rows) // 3)]
    bottom = ink_rows[-max(2, len(ink_rows) // 3) :]
    return all(
        any(
            _has_side(rows[index], crop.width, "left") and _has_side(rows[index], crop.width, "right")
            for index in band
        )
        for band in (top, bottom)
    )


def _is_open_four(crop: Image.Image) -> bool:
    rows = _ink_rows(crop)
    ink_rows = [index for index, cols in enumerate(rows) if cols]
    if len(ink_rows) < 6:
        return False
    top = ink_rows[: max(2, len(ink_rows) // 3)]
    bottom = ink_rows[-max(2, len(ink_rows) // 4) :]
    if any(rows[index] and min(rows[index]) < crop.width * 0.35 for index in top):
        return False
    if not any(len(rows[index]) >= crop.width * 0.7 for index in ink_rows):
        return False
    return not any(rows[index] and min(rows[index]) < crop.width * 0.4 for index in bottom)


def _row_coverage(cols: list[int], width: int) -> float:
    return len(cols) / width if width else 0.0


def _has_side(cols: list[int], width: int, side: str) -> bool:
    if side == "left":
        return any(x < width * 0.35 for x in cols)
    return any(x > width * 0.65 for x in cols)


def _read_prepared(backend: OCRBackend, band: PreparedBand) -> str:
    region = Rect(0, 0, band.prepared.width, band.prepared.height)
    results = backend.read(band.prepared, region=region)
    return " ".join(result.text.strip() for result in results if result.text.strip())


def read_player_location(image: Image.Image, backend: OCRBackend) -> SceneCoordinateReading:
    """OCR the two HUD lines from one full screenshot and assemble ``地图名[x,y]``."""
    scene, coordinate = prepare_player_location(image)
    scene_ink = isolate_light_glyphs(scene.raw)
    scene_text = correct_scene_name(_read_prepared(backend, scene), scene_ink)
    coordinate_ink = isolate_light_glyphs(coordinate.raw)
    coordinate_text = _read_prepared(backend, coordinate)
    coordinate_text = trim_coordinate_noise(coordinate_text)
    coordinate_text = place_dropped_fours(coordinate_text, coordinate_ink)
    coordinate_text = place_dropped_y_fours(coordinate_text, coordinate_ink)
    coordinate_text = restore_leading_fours(coordinate_text, coordinate_ink)
    coordinate_text = restore_trailing_fours(coordinate_text, coordinate_ink)
    coordinate_text = restore_missing_x_digits(coordinate_text, coordinate_ink)
    coordinate_text = correct_misread_four(coordinate_text, coordinate_ink)
    coordinate_text = correct_misread_eight(coordinate_text, coordinate_ink)
    coordinate_text = correct_misread_seven(coordinate_text, coordinate_ink)
    coordinate_text = restore_missing_y(coordinate_text, coordinate_ink)
    coordinate_text = restore_blank_y_digits(coordinate_text, coordinate_ink)
    coordinate_text = drop_trailing_bare_y(coordinate_text)
    coordinate_text = restore_non_digit_y(coordinate_text, coordinate_ink)
    parsed = assemble_scene_coordinate(scene_text, coordinate_text)
    return SceneCoordinateReading(
        scene_text=scene_text,
        coordinate_text=coordinate_text,
        scene_box=scene.box,
        coordinate_box=coordinate.box,
        parsed=parsed,
        formatted=format_scene_coordinate(*parsed) if parsed else None,
        scene_ok=parse_scene_name(scene_text) is not None,
        coordinate_ok=parse_hud_xy(coordinate_text) is not None,
    )
