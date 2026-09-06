"""Generic GUI Agent Core contracts and platform-independent models."""

from .agent_brain import AgentMemory, GoalPlanner, PlanStep, RecoveryDecision, RecoveryPolicy
from .agent_protocol import ActionResult, ActionStatus, AgentDecision, FrameLike, Observation, VerificationResult
from .diagnostics import WindowDiagnostics, diagnose_window
from .game_view import GameView, discover_game_views
from .models import Action, ActionType, GameState, Point, Rect, WindowInfo
from .surface import SurfaceGeometry, SurfaceHealth, inspect_surface, query_surface_geometry

__all__ = [
    "Action", "ActionResult", "ActionStatus", "ActionType", "AgentDecision", "AgentMemory", "FrameLike",
    "GameState", "GameView", "GoalPlanner", "Observation", "PlanStep", "Point", "Rect", "RecoveryDecision",
    "RecoveryPolicy", "SurfaceGeometry", "SurfaceHealth", "VerificationResult", "WindowDiagnostics", "WindowInfo",
    "diagnose_window", "discover_game_views", "inspect_surface", "query_surface_geometry",
]


def __getattr__(name: str):
    """Load legacy adapters only when an old API is explicitly requested."""
    if name == "list_child_windows":
        from ..platform.windows.children import list_child_windows
        return list_child_windows
    if name in {"current_tab_index", "find_tab_control", "select_tab", "GameViewTabSession"}:
        from ..platform.windows import tabs
        return getattr(tabs, name)
    if name == "GameViewManager":
        from ..runtime.view_manager import GameViewManager
        return GameViewManager
    if name == "BackgroundGameSession":
        from ..runtime.session import BackgroundGameSession
        return BackgroundGameSession
    if name in {"find_window", "list_windows", "get_window_info"}:
        from ..platform.windows import window
        return getattr(window, name)
    raise AttributeError(name)
