from dataclasses import dataclass

from game_helpers.core.agent_protocol import Observation
from game_helpers.core.models import ActionType, Rect, WindowInfo
from game_helpers.games.menghuanxiyou import DreamAgent, DreamGameAdapter


@dataclass(frozen=True)
class FakeFrame:
    window: WindowInfo
    width: int = 800
    height: int = 600
    data: bytes = b""
    captured_at: float = 1.0
    backend: str = "fake"


def observation(objects: dict[str, Rect]) -> Observation:
    return Observation(
        frame=FakeFrame(WindowInfo(hwnd=1, title="梦幻西游")),
        objects=objects,
        metadata={"game": "梦幻西游", "resolution": "800x600"},
    )


def test_adapter_projects_real_game_state():
    obs = observation({"item_panel_open": Rect(1, 2, 10, 20), "soul_task_claimed": Rect(5, 6, 15, 16)})
    state = DreamGameAdapter(asset_root="data/assets").to_state(obs)
    assert state.item_panel_open
    assert state.soul_task_claimed
    assert state.task_completed
    assert state.game == "梦幻西游"


def test_agent_opens_item_panel_from_detected_anchor():
    obs = observation({"item_bar_toggle": Rect(460, 560, 478, 578)})
    state = DreamGameAdapter(asset_root="data/assets").to_state(obs)
    decision = DreamAgent().decide(state, obs)
    assert decision.actions[0].type is ActionType.CLICK
    assert decision.actions[0].target == Rect(460, 560, 478, 578).center


def test_agent_stops_when_soul_task_is_claimed():
    obs = observation({"item_panel_open": Rect(1, 2, 10, 20), "soul_task_claimed": Rect(5, 6, 15, 16)})
    state = DreamGameAdapter(asset_root="data/assets").to_state(obs)
    decision = DreamAgent().decide(state, obs)
    assert decision.actions == ()
    assert state.task_completed
