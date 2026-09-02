"""Logical game-instance views hosted inside a parent window."""

from __future__ import annotations

from dataclasses import dataclass

from .models import WindowInfo


@dataclass(frozen=True)
class GameView:
    """A game-rendering child window that can represent one account/view.

    ``index`` is the stable discovery order among matching child windows. It
    is not an account identifier; callers should bind their own account name
    after confirming which tab corresponds to which account.
    """

    index: int
    window: WindowInfo
    active: bool

    @property
    def hwnd(self) -> int:
        return self.window.hwnd


def discover_game_views(
    parent_hwnd: int,
    *,
    class_name: str = "WSGAME",
) -> list[GameView]:
    """Discover game-rendering child windows under a top-level window."""
    from .children import list_child_windows

    children = list_child_windows(parent_hwnd, visible_only=False)
    matches = [child for child in children if child.class_name.lower() == class_name.lower()]
    return [GameView(index=i, window=child, active=child.visible) for i, child in enumerate(matches, 1)]
