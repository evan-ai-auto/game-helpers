from game_helpers.core.game_view import GameView, discover_game_views
from game_helpers.core.models import Rect, WindowInfo


def test_discover_game_views_filters_by_class(monkeypatch):
    children = [
        WindowInfo(10, "Tab", "SysTabControl32", Rect(0, 0, 10, 10), True),
        WindowInfo(11, "Game", "WSGAME", Rect(0, 10, 100, 110), False),
        WindowInfo(12, "Game", "wsgame", Rect(0, 10, 100, 110), True),
    ]
    monkeypatch.setattr(
        "game_helpers.core.children.list_child_windows",
        lambda _hwnd, visible_only=False: children,
    )

    views = discover_game_views(99)

    assert [view.hwnd for view in views] == [11, 12]
    assert [view.index for view in views] == [1, 2]
    assert [view.active for view in views] == [False, True]
