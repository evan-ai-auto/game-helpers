"""Windows native OCR backend using Windows.Media.Ocr.

The backend is optional and intended for Windows diagnostics/perception.
It keeps the public OCRBackend contract synchronous while using the Windows
Runtime async APIs internally.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile

from PIL import Image

from game_helpers.core.models import Rect
from game_helpers.vision.ocr import OCRBackend, OCRResult

try:
    from winsdk.windows.graphics.imaging import BitmapDecoder
    from winsdk.windows.media.ocr import OcrEngine
    from winsdk.windows.storage import StorageFile
except ImportError:  # pragma: no cover - exercised on non-Windows/minimal installs
    BitmapDecoder = None
    OcrEngine = None
    StorageFile = None


class WindowsNativeOCRBackend:
    """Synchronous OCRBackend backed by Windows.Media.Ocr."""

    def __init__(self, *, language: str | None = None) -> None:
        if OcrEngine is None:
            raise RuntimeError(
                "Windows 原生 OCR 需要安装 Windows 依赖 winsdk>=1.0.0b10。"
            )
        # winsdk's current binding accepts the user-profile language factory
        # reliably; direct string arguments to try_create_from_language are
        # not compatible with the installed binding.
        self._engine = OcrEngine.try_create_from_user_profile_languages()
        if self._engine is None:
            raise RuntimeError("无法创建 Windows 原生 OCR 引擎。")
        detected_language = self._engine.recognizer_language.language_tag
        if language and detected_language.lower() != language.lower():
            raise RuntimeError(
                f"Windows OCR 当前语言={detected_language}，不满足要求={language}。"
            )
        self.language = detected_language

    def read(self, image: Image.Image, *, region: Rect) -> tuple[OCRResult, ...]:
        if region.width <= 0 or region.height <= 0:
            return ()
        roi = image.convert("RGBA").crop(
            (region.left, region.top, region.right, region.bottom)
        )
        return tuple(asyncio.run(self._recognize(roi)))

    async def _recognize(self, image: Image.Image) -> tuple[OCRResult, ...]:
        if BitmapDecoder is None or StorageFile is None:
            raise RuntimeError("Windows 原生 OCR 运行时组件不可用。")

        with tempfile.TemporaryDirectory(prefix="game_helpers_ocr_") as temp_dir:
            path = Path(temp_dir) / "roi.png"
            image.save(path, format="PNG")
            file = await StorageFile.get_file_from_path_async(str(path))
            stream = await file.open_read_async()
            decoder = await BitmapDecoder.create_async(stream)
            bitmap = await decoder.get_software_bitmap_async()
            result = await self._engine.recognize_async(bitmap)

        # Windows.Media.Ocr exposes text at line level in this binding, but
        # does not provide a stable confidence value here. Keep confidence at
        # the contract default rather than inventing a score.
        return tuple(
            OCRResult(line.text.strip(), 0.0)
            for line in result.lines
            if line.text.strip()
        )


__all__ = ["WindowsNativeOCRBackend"]
