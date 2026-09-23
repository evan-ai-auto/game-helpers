from game_helpers.tasks.basic_capabilities import BASIC_CAPABILITIES, get_basic_capability
from game_helpers.tasks.basic_capability_flow import _choose_dao_ju_lan_target, _run_basic_capability_session, run_basic_capability


def test_new_basic_capabilities_are_registered():
    assert get_basic_capability("demon_repellent_incense").name == "摄妖香相关"
    assert get_basic_capability("find_npc_and_interact").name == "寻找指定 NPC 角色并交互"


def test_incense_placeholder_returns_standard_result():
    result = _run_basic_capability_session(None, "demon_repellent_incense", "/tmp", None)
    assert result["ok"] is True
    assert result["capability"] == "demon_repellent_incense"
    assert result["status"] == "not_implemented"
    assert "尚在路上" in result["message"]


def test_npc_placeholder_returns_standard_result():
    result = _run_basic_capability_session(None, "find_npc_and_interact", "/tmp", None)
    assert result["ok"] is True
    assert result["capability"] == "find_npc_and_interact"
    assert result["status"] == "not_implemented"
    assert "尚在路上" in result["message"]


def test_dao_ju_lan_is_inserted_before_incense_and_npc():
    ids = [item.id for item in BASIC_CAPABILITIES]
    assert ids[9:13] == [
        "capture_freshness",
        "dao_ju_lan",
        "demon_repellent_incense",
        "find_npc_and_interact",
    ]
    assert get_basic_capability("dao_ju_lan").name == "道具栏相关"


def test_dao_ju_lan_menu_maps_open_and_close(monkeypatch):
    class Before:
        open = False

    answers = iter(["1", "2", "0"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    assert _choose_dao_ju_lan_target(Before()) is True
    assert _choose_dao_ju_lan_target(Before()) is False
    assert _choose_dao_ju_lan_target(Before()) is None


def test_dao_ju_lan_delegates_to_existing_item_panel_flow(monkeypatch):
    captured = {}

    def fake_flow(parent_hwnd, selection, **kwargs):
        captured["parent_hwnd"] = parent_hwnd
        captured["selection"] = selection
        captured["target_selector"] = kwargs["target_selector"]
        return {"ok": True, "capability": "dao_ju_lan"}

    monkeypatch.setattr("game_helpers.tasks.basic_capability_flow.run_item_panel_detect_and_toggle", fake_flow)
    selection = object()
    result = run_basic_capability(123, selection, "dao_ju_lan", "/tmp")
    assert result["capability"] == "dao_ju_lan"
    assert captured["parent_hwnd"] == 123
    assert captured["selection"] is selection
    assert callable(captured["target_selector"])
