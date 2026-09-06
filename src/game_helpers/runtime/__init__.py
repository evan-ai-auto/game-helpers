"""Runtime orchestration for GUI Agent sessions."""

from .session import BackgroundGameSession
from .view_manager import GameViewManager

__all__ = ["BackgroundGameSession", "GameViewManager"]
