"""Background screenshot snapshot for the selected 梦幻西游 instance."""

from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path

from ..capture import Frame, WindowsGraphicsCapture, save_png
from ..core.view_manager import GameViewManager
from .character_selection import CharacterSelectionResult
from .render_binding import BindingStatus, verify_render_binding


@dataclass(frozen=True)
class GameStateSnapshot:
    """A capture-only snapshot; it intentionally contains no task execution."""

    status: str
    view_index: int
    hwnd: int
    process_id: int | None
    character_name: str
    identity: str | None
    window_title: str
    surface_index: int
    tab_index: int
    foreground_hwnd_before: int
    foreground_hwnd_after: int
    width: int
    height: int
    backend: str
    frame_sha256: str
    screenshot_path: str | None


def capture_selected_game_state(
    parent_hwnd: int,
    selection: CharacterSelectionResult,
    *,
    output_path: str | Path | None = None,
    settle_delay: float = 0.25,
) -> GameStateSnapshot:
    """Select, verify binding, and capture one background game-state snapshot.

    This function does not OCR, infer task state, or execute any game action.
    """
    if sys.platform != "win32":
        raise RuntimeError("game state snapshot requires Windows")

    import ctypes

    manager = GameViewManager(parent_hwnd, timeout=2.0)
    foreground_before = int(ctypes.windll.user32.GetForegroundWindow())
    binding = verify_render_binding(
        parent_hwnd,
        selection.view_index,
        identity=selection.account.identity,
        settle_delay=settle_delay,
    )
    if binding.status != BindingStatus.VERIFIED:
        raise RuntimeError(f"render binding is not verified: {binding.status}")

    # verify_render_binding already captured a frame. Capture again here so the
    # snapshot owns the exact frame represented by its saved PNG and hash.
    frame: Frame = WindowsGraphicsCapture().capture(parent_hwnd)
    frame_sha = hashlib.sha256(frame.data).hexdigest()
    if frame_sha != binding.frame_sha256:
        raise RuntimeError("render changed between binding verification and snapshot capture")

    if output_path is not None:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        save_png(frame, str(output))
        saved_path = str(output)
    else:
        saved_path = None

    foreground_after = int(ctypes.windll.user32.GetForegroundWindow())
    surface = manager.current_surface_index()
    tab = manager.current_index()
    if surface != selection.view_index or tab != selection.view_index:
        raise RuntimeError("selected character Surface/Tab is no longer synchronized")
    if foreground_after != foreground_before:
        raise RuntimeError("foreground window changed during game-state snapshot")

    return GameStateSnapshot(
        status="captured",
        view_index=selection.view_index,
        hwnd=selection.hwnd,
        process_id=selection.process_id,
        character_name=selection.character_name,
        identity=selection.account.identity,
        window_title=selection.account.metadata.get("title", "") or "",
        surface_index=surface,
        tab_index=tab,
        foreground_hwnd_before=foreground_before,
        foreground_hwnd_after=foreground_after,
        width=frame.width,
        height=frame.height,
        backend=frame.backend,
        frame_sha256=frame_sha,
        screenshot_path=saved_path,
    )
