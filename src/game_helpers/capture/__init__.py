"""Window capture backends."""

from .background_view import BackgroundViewCapture
from .models import Frame
from .png import save_png
from .printwindow import PrintWindowCapture
from .screen import ScreenCapture
from .wgc import WindowsGraphicsCapture

__all__ = [
    "BackgroundViewCapture",
    "Frame",
    "PrintWindowCapture",
    "ScreenCapture",
    "WindowsGraphicsCapture",
    "save_png",
]
