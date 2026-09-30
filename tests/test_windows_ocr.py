from __future__ import annotations

import game_helpers.vision.windows_ocr as windows_ocr


def test_windows_ocr_module_imports_without_required_runtime() -> None:
    assert hasattr(windows_ocr, "WindowsNativeOCRBackend")


def test_windows_ocr_reports_missing_runtime(monkeypatch) -> None:
    monkeypatch.setattr(windows_ocr, "OcrEngine", None)
    try:
        windows_ocr.WindowsNativeOCRBackend()
    except RuntimeError as exc:
        assert "winsdk" in str(exc)
    else:
        raise AssertionError("missing winsdk runtime should be reported")
