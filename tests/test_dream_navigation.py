from dataclasses import dataclass

from game_helpers.core.agent_protocol import Observation
from game_helpers.core.models import ActionType, Rect, WindowInfo
from game_helpers.games.menghuanxiyou import DreamAgent, DreamGameAdapter
from game_helpers.games.menghuanxiyou.navigation import DreamNavigationGraph


@dataclass(frozen=True)
class FakeFrame:
    window: WindowInfo
    width: int = 800
    height: int = 600
    data: bytes = b""
    captured_at: float = 1.0
    backend: str = "fake"


def test_transport_goal_requires_visual_target():
    adapter = DreamGameAdapter(asset_root="data/assets")
    navigation = DreamNavigationGraph(adapter.scenes)
    obs = Observation(
        frame=FakeFrame(WindowInfo(hwnd=1, title="梦幻西游")),
        metadata={"game": "梦幻西游", "resolution": "800x600", "scene_id": "scene_changan", "scene_confidence": 1.0},
    )
    state = adapter.to_state(obs)
    decision = DreamAgent(navigation=navigation, goal="transport:tp_changan_yizhan_laoban").decide(state, obs)
    assert decision.actions[0].type is ActionType.WAIT


def test_transport_goal_clicks_detected_target():
    adapter = DreamGameAdapter(asset_root="data/assets")
    navigation = DreamNavigationGraph(adapter.scenes)
    obs = Observation(
        frame=FakeFrame(WindowInfo(hwnd=1, title="梦幻西游")),
        objects={"transport:tp_changan_yizhan_laoban": Rect(270, 35, 290, 55)},
        metadata={"game": "梦幻西游", "resolution": "800x600", "scene_id": "scene_changan", "scene_confidence": 1.0},
    )
    state = adapter.to_state(obs)
    decision = DreamAgent(navigation=navigation, goal="transport:tp_changan_yizhan_laoban").decide(state, obs)
    assert decision.actions[0].type is ActionType.CLICK
    assert decision.metadata["navigation_target"] == "tp_changan_yizhan_laoban"
