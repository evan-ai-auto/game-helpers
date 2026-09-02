"""Window capture backends."""

from .models import Frame
from .png import save_png
from .printwindow import PrintWindowCapture
from .screen import ScreenCapture
from .wgc import WindowsGraphicsCapture

__all__ = [
    "Frame",
    "PrintWindowCapture",
    "ScreenCapture",
    "WindowsGraphicsCapture",
    "save_png",
]
