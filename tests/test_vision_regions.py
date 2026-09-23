from PIL import Image

from game_helpers.core.models import Rect
from game_helpers.vision.ocr import parse_integer, parse_scene_coordinate
from game_helpers.vision.regions import VisionRegion


def test_parse_scene_coordinate():
    assert parse_scene_coordinate("四方城[34,44]") == ("四方城", 34, 44)
    assert parse_scene_coordinate("四方城 [34，44]") == ("四方城", 34, 44)


def test_assemble_scene_coordinate_from_separate_hud_lines():
    from game_helpers.vision.ocr import assemble_scene_coordinate, format_scene_coordinate, parse_hud_xy, parse_scene_name

    assert parse_scene_name("泾河府") == "泾河府"
    assert parse_hud_xy("X:71 Y:34") == (71, 34)
    assert parse_hud_xy("X：71 Y：34") == (71, 34)
    assert parse_hud_xy("X.: 7 1 Y ： 3 4") == (71, 34)
    assert parse_hud_xy("X ： 5 4 ： 7 2") == (54, 72)
    assert parse_hud_xy("X ： 4 4 Y ： 2 2") == (44, 22)
    assert parse_hud_xy("X ： 29 Y ： 68") == (29, 68)
    assert parse_hud_xy("X ： 4 6 Y ： 2 2") == (46, 22)
    assert parse_hud_xy("X ： 6 Y ： 8") == (6, 8)
    assert parse_hud_xy("X ： 8 4 Y ： 8 7") == (84, 87)
    assert parse_hud_xy("X ： 1 4 2 Y ： 12") == (142, 12)
    assert parse_hud_xy("X ： 76 Y ： 37") == (76, 37)
    assert parse_hud_xy("X ： 79 Y ： 2 4") == (79, 24)
    assert parse_hud_xy("X ： 50 Y ： 4 7") == (50, 47)
    assert parse_hud_xy("X ： 139 Y 4 3") == (139, 43)
    assert parse_hud_xy("X ： 80 Y ： 4 9") == (80, 49)
    assert parse_hud_xy("X ： 80 Y ： 四") is None
    assert assemble_scene_coordinate("泾河府", "X:71 Y:34") == ("泾河府", 71, 34)
    assert format_scene_coordinate("泾河府", 71, 34) == "泾河府[71,34]"


def test_prepare_player_location_splits_a_full_frame():
    from game_helpers.vision.scene_coordinate import COORDINATE_BOX, SCENE_NAME_BOX, prepare_player_location

    image = Image.new("RGB", (800, 600), (20, 40, 40))
    scene, coordinate = prepare_player_location(image)
    assert scene.box == SCENE_NAME_BOX
    assert coordinate.box == COORDINATE_BOX
    assert scene.prepared.width > scene.raw.width
    assert coordinate.prepared.mode == "L"


def _stamp(page: Image.Image, origin: int, rows: tuple[str, ...]) -> None:
    pixels = page.load()
    for y, row in enumerate(rows):
        for x, cell in enumerate(row):
            if cell == "#":
                pixels[origin + x, y] = 0


def test_correct_misread_four_keeps_a_real_single_digit_x():
    from game_helpers.vision.scene_coordinate import correct_misread_four

    page = Image.new("L", (40, 12), 255)
    _stamp(
        page,
        0,
        (
            "###.###",
            ".#...#.",
            "..#.#..",
            "...#...",
            "..#.#..",
            "..#.#..",
            ".#...#.",
            "###..##",
        ),
    )
    _stamp(
        page,
        16,
        (
            "###.###",
            ".#...#.",
            "..#.#..",
            "...#...",
            "...#...",
            "...#...",
            "...#...",
            "..###..",
        ),
    )
    assert correct_misread_four("X:5 Y:72", page) == "X:5 Y:72"


def test_correct_misread_four_restores_the_dropped_digit():
    from game_helpers.vision.scene_coordinate import correct_misread_four

    page = Image.new("L", (48, 12), 255)
    _stamp(
        page,
        0,
        (
            "###.###",
            ".#...#.",
            "..#.#..",
            "...#...",
            "..#.#..",
            "..#.#..",
            ".#...#.",
            "###..##",
        ),
    )
    _stamp(
        page,
        10,
        (
            "#####",
            "#....",
            "#....",
            "####.",
            "#...#",
            "....#",
            "....#",
            "#...#",
            "#...#",
            ".###.",
        ),
    )
    _stamp(
        page,
        18,
        (
            "...#.",
            "...#.",
            "..##.",
            ".#.#.",
            ".#.#.",
            "#..#.",
            "#####",
            "...#.",
            "...#.",
            "..###",
        ),
    )
    _stamp(
        page,
        28,
        (
            "###.###",
            ".#...#.",
            "..#.#..",
            "...#...",
            "...#...",
            "...#...",
            "...#...",
            "..###..",
        ),
    )
    assert correct_misread_four("X ： 5 Y ： 7 2", page) == "X ： 5 4 ： 7 2"


def test_restore_missing_x_digits_fills_open_fours():
    from game_helpers.vision.scene_coordinate import restore_missing_x_digits

    page = Image.new("L", (48, 12), 255)
    _stamp(
        page,
        0,
        (
            "###.###",
            ".#...#.",
            "..#.#..",
            "...#...",
            "..#.#..",
            "..#.#..",
            ".#...#.",
            "###..##",
        ),
    )
    four = (
        "...#.",
        "...#.",
        "..##.",
        ".#.#.",
        ".#.#.",
        "#..#.",
        "#####",
        "...#.",
        "...#.",
        "..###",
    )
    _stamp(page, 12, four)
    _stamp(page, 20, four)
    _stamp(
        page,
        30,
        (
            "###.###",
            ".#...#.",
            "..#.#..",
            "...#...",
            "...#...",
            "...#...",
            "...#...",
            "..###..",
        ),
    )
    assert restore_missing_x_digits("X ： Y ： 2 2", page) == "X ： 4 4 Y ： 2 2"
    assert restore_missing_x_digits("X ： 5 Y ： 7 2", page) == "X ： 5 Y ： 7 2"


def test_restore_leading_four_before_a_kept_digit():
    from game_helpers.vision.scene_coordinate import restore_leading_fours

    page = Image.new("L", (56, 12), 255)
    _stamp(
        page,
        0,
        (
            "###.###",
            ".#...#.",
            "..#.#..",
            "...#...",
            "..#.#..",
            "..#.#..",
            ".#...#.",
            "###..##",
        ),
    )
    _stamp(page, 10, ("##", "##", "....", "##", "##"))
    _stamp(
        page,
        16,
        (
            "...#.",
            "...#.",
            "..##.",
            ".#.#.",
            ".#.#.",
            "#..#.",
            "#####",
            "...#.",
            "...#.",
            "..###",
        ),
    )
    _stamp(
        page,
        24,
        (
            "..##..",
            ".#..#.",
            "#.....",
            "#.###.",
            "##...#",
            "#....#",
            "#....#",
            "#....#",
            ".#...#",
            "..###.",
        ),
    )
    _stamp(
        page,
        36,
        (
            "###.###",
            ".#...#.",
            "..#.#..",
            "...#...",
            "...#...",
            "...#...",
            "...#...",
            "..###..",
        ),
    )
    assert restore_leading_fours("X ： 6 Y ： 2 2", page) == "X ： 4 6 Y ： 2 2"
    assert restore_leading_fours("X ： 46 Y ： 22", page) == "X ： 46 Y ： 22"


def test_restore_trailing_four_after_a_kept_digit():
    from game_helpers.vision.scene_coordinate import restore_trailing_fours

    page = Image.new("L", (56, 12), 255)
    _stamp(
        page,
        0,
        (
            "###.###",
            ".#...#.",
            "..#.#..",
            "...#...",
            "..#.#..",
            "..#.#..",
            ".#...#.",
            "###..##",
        ),
    )
    _stamp(page, 10, ("##", "##", "....", "##", "##"))
    _stamp(
        page,
        16,
        (
            ".####.",
            "#....#",
            "#....#",
            "#....#",
            ".####.",
            ".#..#.",
            "#....#",
            "#....#",
            "#....#",
            ".####.",
        ),
    )
    _stamp(
        page,
        26,
        (
            "...#.",
            "...#.",
            "..##.",
            ".#.#.",
            ".#.#.",
            "#..#.",
            "#####",
            "...#.",
            "...#.",
            "..###",
        ),
    )
    _stamp(
        page,
        36,
        (
            "###.###",
            ".#...#.",
            "..#.#..",
            "...#...",
            "...#...",
            "...#...",
            "...#...",
            "..###..",
        ),
    )
    assert restore_trailing_fours("X ： 8 Y ： 8 7", page) == "X ： 8 4 Y ： 8 7"
    assert restore_trailing_fours("X ： 8 4 Y ： 8 7", page) == "X ： 8 4 Y ： 8 7"


def test_place_dropped_four_between_kept_digits():
    from game_helpers.vision.scene_coordinate import place_dropped_fours

    page = Image.new("L", (64, 12), 255)
    _stamp(
        page,
        0,
        (
            "###.###",
            ".#...#.",
            "..#.#..",
            "...#...",
            "..#.#..",
            "..#.#..",
            ".#...#.",
            "###..##",
        ),
    )
    _stamp(page, 10, ("##", "##", "....", "##", "##"))
    _stamp(
        page,
        16,
        (
            "..#..",
            "###..",
            "..#..",
            "..#..",
            "..#..",
            "..#..",
            "..#..",
            "..#..",
            "..#..",
            "#####",
        ),
    )
    _stamp(
        page,
        24,
        (
            "...#.",
            "...#.",
            "..##.",
            ".#.#.",
            ".#.#.",
            "#..#.",
            "#####",
            "...#.",
            "...#.",
            "..###",
        ),
    )
    _stamp(
        page,
        32,
        (
            ".###.",
            "#...#",
            "#...#",
            "....#",
            "...#.",
            "...#.",
            "..#..",
            ".#...",
            "#...#",
            "#####",
        ),
    )
    _stamp(
        page,
        42,
        (
            "###.###",
            ".#...#.",
            "..#.#..",
            "...#...",
            "...#...",
            "...#...",
            "...#...",
            "..###..",
        ),
    )
    assert place_dropped_fours("X ： 1 2 Y ： 12", page) == "X ： 1 4 2 Y ： 12"
    assert place_dropped_fours("X ： 1 4 2 Y ： 12", page) == "X ： 1 4 2 Y ： 12"


def test_place_dropped_four_after_the_y_digit():
    from game_helpers.vision.scene_coordinate import place_dropped_y_fours

    page = Image.new("L", (48, 12), 255)
    _stamp(
        page,
        0,
        (
            "###.###",
            ".#...#.",
            "..#.#..",
            "...#...",
            "...#...",
            "...#...",
            "...#...",
            "..###..",
        ),
    )
    _stamp(
        page,
        12,
        (
            ".###.",
            "#...#",
            "#...#",
            "....#",
            "...#.",
            "...#.",
            "..#..",
            ".#...",
            "#...#",
            "#####",
        ),
    )
    _stamp(
        page,
        20,
        (
            "...#.",
            "...#.",
            "..##.",
            ".#.#.",
            ".#.#.",
            "#..#.",
            "#####",
            "...#.",
            "...#.",
            "..###",
        ),
    )
    assert place_dropped_y_fours("X ： 79 Y ： 2", page) == "X ： 79 Y ： 2 4"
    assert place_dropped_y_fours("X ： 79 Y ： 2 4", page) == "X ： 79 Y ： 2 4"


def test_restore_blank_y_digits_reads_four_and_seven():
    from game_helpers.vision.scene_coordinate import restore_blank_y_digits, trim_coordinate_noise

    page = Image.new("L", (40, 12), 255)
    _stamp(
        page,
        0,
        (
            "###.###",
            ".#...#.",
            "..#.#..",
            "...#...",
            "...#...",
            "...#...",
            "...#...",
            "..###..",
        ),
    )
    _stamp(
        page,
        12,
        (
            "...#.",
            "...#.",
            "..##.",
            ".#.#.",
            ".#.#.",
            "#..#.",
            "#####",
            "...#.",
            "...#.",
            "..###",
        ),
    )
    _stamp(
        page,
        20,
        (
            "####",
            "#...",
            "...#",
            "...#",
            "...#",
            "..#.",
            "..#.",
            "..#.",
            "..#.",
            "..#.",
        ),
    )
    assert trim_coordinate_noise("， ： X ： 50 Y ：") == "X ： 50 Y ："
    assert restore_blank_y_digits("X ： 50 Y ：", page) == "X ： 50 Y ： 4 7"
    assert restore_blank_y_digits("X ： 50 Y ： 47", page) == "X ： 50 Y ： 47"


def test_restore_blank_y_digits_reads_four_and_three():
    from game_helpers.vision.scene_coordinate import drop_trailing_bare_y, place_dropped_y_fours, restore_blank_y_digits

    page = Image.new("L", (40, 12), 255)
    _stamp(
        page,
        0,
        (
            "###.###",
            ".#...#.",
            "..#.#..",
            "...#...",
            "...#...",
            "...#...",
            "...#...",
            "..###..",
        ),
    )
    _stamp(
        page,
        12,
        (
            "...#.",
            "...#.",
            "..##.",
            ".#.#.",
            ".#.#.",
            "#..#.",
            "#####",
            "...#.",
            "...#.",
            "..###",
        ),
    )
    _stamp(
        page,
        20,
        (
            ".###.",
            "#...#",
            "#...#",
            "....#",
            "..##.",
            "....#",
            "#...#",
            "#...#",
            ".###.",
        ),
    )
    assert place_dropped_y_fours("X ： 139 Y 3", page) == "X ： 139 Y 4 3"
    assert restore_blank_y_digits("X ： 139 Y ：", page) == "X ： 139 Y ： 4 3"
    assert drop_trailing_bare_y("X ： 139 Y 4 3 Y ：") == "X ： 139 Y 4 3"


def test_correct_misread_seven_rewrites_a_y_one():
    from game_helpers.vision.scene_coordinate import correct_misread_seven

    page = Image.new("L", (40, 12), 255)
    _stamp(
        page,
        0,
        (
            "###.###",
            ".#...#.",
            "..#.#..",
            "...#...",
            "...#...",
            "...#...",
            "...#...",
            "..###..",
        ),
    )
    _stamp(page, 12, ("#####", "#...#", ".###.", "#...#", "#####"))
    _stamp(
        page,
        20,
        (
            "####",
            "#...",
            "...#",
            "...#",
            "...#",
            "..#.",
            "..#.",
            "..#.",
            "..#.",
            "..#.",
        ),
    )
    assert correct_misread_seven("《 X ： 76 Y ： 31", page) == "《 X ： 76 Y ： 37"

    one = Image.new("L", (36, 12), 255)
    _stamp(
        one,
        0,
        (
            "###.###",
            ".#...#.",
            "..#.#..",
            "...#...",
            "...#...",
            "...#...",
            "...#...",
            "..###..",
        ),
    )
    _stamp(one, 12, ("#####", "#...#", ".###.", "#...#", "#####"))
    _stamp(
        one,
        20,
        (
            "..#..",
            "###..",
            "..#..",
            "..#..",
            "..#..",
            "..#..",
            "..#..",
            "..#..",
            "..#..",
            "#####",
        ),
    )
    assert correct_misread_seven("X ： 76 Y ： 31", one) == "X ： 76 Y ： 31"


def test_correct_misread_eight_rewrites_the_y_digit():
    from game_helpers.vision.scene_coordinate import correct_misread_eight

    page = Image.new("L", (40, 12), 255)
    _stamp(
        page,
        0,
        (
            "###.###",
            ".#...#.",
            "..#.#..",
            "...#...",
            "...#...",
            "...#...",
            "...#...",
            "..###..",
        ),
    )
    _stamp(page, 12, ("#####", "#...#", "#####"))
    _stamp(
        page,
        20,
        (
            ".####",
            "#....",
            "#....",
            "#....",
            ".####",
            ".#..#",
            "#....",
            "#....",
            "#....",
            ".####",
        ),
    )
    assert correct_misread_eight("X ： 29 Y ： 6E", page) == "X ： 29 Y ： 68"

    plain = Image.new("L", (32, 10), 255)
    _stamp(
        plain,
        0,
        (
            "###.###",
            ".#...#.",
            "..#.#..",
            "...#...",
            "...#...",
            "...#...",
            "...#...",
            "..###..",
        ),
    )
    _stamp(plain, 10, ("#####", "#...#", "#####"))
    _stamp(
        plain,
        18,
        (
            "#####",
            "#....",
            "#....",
            "#####",
            "#....",
            "#....",
            "#####",
        ),
    )
    assert correct_misread_eight("X ： 29 Y ： 6E", plain) == "X ： 29 Y ： 6E"


def test_correct_scene_name_rewrites_zhu_and_drops_the_side_fragment():
    from game_helpers.vision.scene_coordinate import correct_scene_name

    page = Image.new("L", (80, 16), 255)
    _stamp(
        page,
        0,
        (
            "......#......",
            "...#..#......",
            "...#..#......",
            "...########..",
            "..#...#......",
            ".#....#......",
            "......#......",
            "#############",
            ".....###.....",
            "....#.#.#....",
            "...#..#..#...",
            "..#...#...#..",
            "##....#....##",
            "......#......",
        ),
    )
    _stamp(page, 16, ("#####", "#...#", "#####"))
    _stamp(page, 24, ("#####", "#...#", "#####"))
    _stamp(page, 48, ("#", "#", "#####"))
    assert correct_scene_name("耒 紫 国 L", page) == "朱紫国"


def test_correct_scene_name_keeps_lei_without_the_zhu_stroke():
    from game_helpers.vision.scene_coordinate import correct_scene_name

    page = Image.new("L", (40, 12), 255)
    _stamp(
        page,
        0,
        (
            "#############",
            "......#......",
            "......#......",
            "#############",
            "......#......",
        ),
    )
    assert correct_scene_name("耒 紫 国", page) == "耒紫国"
    assert correct_scene_name("泾 河 府", page) == "泾河府"


def test_correct_scene_name_rewrites_zhai():
    from game_helpers.vision.scene_coordinate import correct_scene_name

    page = Image.new("L", (40, 16), 255)
    _stamp(page, 0, ("#####", "#...#", "#####", "#...#", "#####"))
    _stamp(page, 8, ("#####", "#...#", "#####", "#...#", "#####"))
    _stamp(
        page,
        16,
        (
            "......#......",
            "#############",
            "#...#...#...#",
            "..#########..",
            "....#...#....",
            "..#########..",
            "....#...#....",
            "#############",
            "...#.....#...",
            "..#...#...#..",
            "##.#######.##",
            "......#......",
            "...#..#..#...",
            "..#..##...#..",
        ),
    )
    assert correct_scene_name("魔王皋", page) == "魔王寨"

    stem = Image.new("L", (16, 12), 255)
    _stamp(
        stem,
        0,
        (
            "......#.....",
            ".##########.",
            "......#.....",
            "......#.....",
            "......#.....",
        ),
    )
    assert correct_scene_name("皋", stem) == "皋"


def test_restore_missing_y_appends_a_readable_eight():
    from game_helpers.vision.scene_coordinate import restore_missing_y

    page = Image.new("L", (36, 12), 255)
    _stamp(
        page,
        0,
        (
            "###.###",
            ".#...#.",
            "..#.#..",
            "...#...",
            "...#...",
            "...#...",
            "...#...",
            "..###..",
        ),
    )
    _stamp(
        page,
        12,
        (
            ".####.",
            "#....#",
            "#....#",
            "#....#",
            ".####.",
            ".#..#.",
            "#....#",
            "#....#",
            "#....#",
            ".####.",
        ),
    )
    assert restore_missing_y("X ： 6", page) == "X ： 6 Y ： 8"
    assert restore_missing_y("X ： 6 Y ： 8", page) == "X ： 6 Y ： 8"


def test_insert_dropped_tang_between_da_and_guan():
    from game_helpers.vision.scene_coordinate import correct_scene_name

    page = Image.new("L", (52, 16), 255)
    block = ("#####", "#...#", "#####", "#...#", "#####")
    _stamp(page, 0, block)
    _stamp(
        page,
        10,
        (
            "......#......",
            ".......#.....",
            "..###########",
            "..#....#.....",
            "..#.########.",
            "..#....#...#.",
            "..###########",
            "..#....#...#.",
            "..#.########.",
            "..#....#.....",
            "..#.########.",
            ".#..#......#.",
            ".#..#......#.",
            "#...########.",
        ),
    )
    _stamp(page, 26, block)
    _stamp(page, 34, block)
    assert correct_scene_name("大官府", page) == "大唐官府"
    assert correct_scene_name("大唐官府", page) == "大唐官府"

    plain = Image.new("L", (40, 8), 255)
    _stamp(plain, 0, block)
    _stamp(plain, 8, block)
    _stamp(plain, 16, block)
    _stamp(plain, 24, block)
    assert correct_scene_name("大官府", plain) == "大官府"


def test_correct_scene_name_rewrites_jing():
    from game_helpers.vision.scene_coordinate import correct_scene_name

    page = Image.new("L", (36, 16), 255)
    _stamp(page, 0, ("#####", "#...#", "#####", "#...#", "#####"))
    _stamp(
        page,
        10,
        (
            "..#.....#....",
            "..#..#######.",
            "..#...#...#..",
            "..#....#.#...",
            "####.########",
            "..#..........",
            "..#..#######.",
            "..#..#.....#.",
            "..#..#######.",
            "..#..#.....#.",
            "..##.#######.",
            "##.....#.#...",
            "......#..#..#",
            "....##....###",
        ),
    )
    assert correct_scene_name("梦竟", page) == "梦境"

    plain = Image.new("L", (20, 12), 255)
    _stamp(
        plain,
        0,
        (
            "..###########",
            "....#.....#..",
            "###############",
            "...#########.",
            "...#.......#.",
            "...#########.",
        ),
    )
    assert correct_scene_name("竟", plain) == "竟"


def test_correct_scene_name_rewrites_di():
    from game_helpers.vision.scene_coordinate import correct_scene_name

    page = Image.new("L", (36, 16), 255)
    # 地: left 土 stem + crossbar, right 也-like body
    _stamp(
        page,
        0,
        (
            "..#.....#....",
            "..#..#######.",
            "#####.#...#..",
            "..#....#.#...",
            "..#.....#....",
            "..#....##....",
            "..#...#.#....",
            "..#..#..#....",
            "..#.#...#..#.",
            "..##....#.#..",
            "..#.....#....",
            "..#.....#...#",
            "..#......####",
            ".............",
        ),
    )
    _stamp(page, 16, ("#####", "#...#", "#...#", "#####", "#...#", "#...#", "#####"))
    assert correct_scene_name("也府", page) == "地府"

    plain = Image.new("L", (16, 14), 255)
    # plain 也: no isolated left 土 stem
    _stamp(
        plain,
        0,
        (
            ".#######.",
            "#.....#..",
            ".....#...",
            "....#....",
            "...##....",
            "..#.#....",
            ".#..#..#.",
            "#...#.#..",
            "....#....",
            "....#...#",
            ".....####",
        ),
    )
    assert correct_scene_name("也", plain) == "也"


def test_restore_non_digit_y_reads_four_and_nine():
    from game_helpers.vision.scene_coordinate import _known_digit, restore_non_digit_y

    page = Image.new("L", (48, 12), 255)
    _stamp(
        page,
        0,
        (
            "###.###",
            ".#...#.",
            "..#.#..",
            "...#...",
            "...#...",
            "...#...",
            "...#...",
            "..###..",
        ),
    )
    _stamp(
        page,
        12,
        (
            "...#.",
            "...#.",
            "..##.",
            ".#.#.",
            ".#.#.",
            "#..#.",
            "#####",
            "...#.",
            "...#.",
            "..###",
        ),
    )
    nine = Image.new("L", (6, 10), 255)
    _stamp(
        nine,
        0,
        (
            ".###..",
            "#...#.",
            "#....#",
            "#....#",
            "#...##",
            ".###.#",
            ".....#",
            ".....#",
            ".#..#.",
            "..##..",
        ),
    )
    page.paste(nine, (22, 0))
    zero = Image.new("L", (6, 10), 255)
    _stamp(
        zero,
        0,
        (
            "..##..",
            ".#..#.",
            "#....#",
            "#....#",
            "#....#",
            "#....#",
            "#....#",
            "#....#",
            ".#..#.",
            "..##..",
        ),
    )
    assert _known_digit(nine) == "9"
    assert _known_digit(zero) is None
    assert restore_non_digit_y("X ： 80 Y ： 四", page) == "X ： 80 Y ： 4 9"
    assert restore_non_digit_y("X ： 80 Y ： 4 9", page) == "X ： 80 Y ： 4 9"


def test_parse_integer():
    assert parse_integer("现银 87,199") == 87199
    assert parse_integer("87199") == 87199


def test_region_scales_from_reference_resolution():
    region = VisionRegion("location", (0, 0, 150, 70), 1024, 768)
    assert region.resolve(800, 600) == Rect(0, 0, 117, 55)
