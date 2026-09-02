"""Window capture backends."""

from .models import Frame
from .printwindow import PrintWindowCapture

__all__ = ["Frame", "PrintWindowCapture"]
