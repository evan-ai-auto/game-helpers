from game_helpers.tasks.basic_capabilities import (
    BASIC_CAPABILITIES,
    SHORTCUT_DIAGNOSTIC_CAPABILITY_IDS,
    get_basic_capability,
)
from game_helpers.tasks.basic_capability_flow import (
    _choose_dao_ju_lan_target,
    _run_basic_capability_session,
    _shortcut_state_label,
    run_basic_capability,
)
from game_helpers.tasks.soul_shortcut_diagnostic_flow import SHORTCUT_DIAGNOSTIC_CAPABILITIES
from pathlib import Path


def test_basic_capabilities_are_unique_and_independently_named():
    ids = [item.id for item in BASIC_CAPABILITIES]
    names = [item.name for item in BASIC_CAPABILITIES]
    assert ids
    assert len(ids) == len(set(ids))
    assert len(names) == len(set(names))
    assert callable(run_basic_capability)


def test_shortcut_flow_and_basic_capability_menu_share_the_same_registry():
    flow_ids = [item.id for item in SHORTCUT_DIAGNOSTIC_CAPABILITIES]
    assert flow_ids == list(SHORTCUT_DIAGNOSTIC_CAPABILITY_IDS)
    assert all(get_basic_capability(item_id).id == item_id for item_id in flow_ids)
    assert set(flow_ids).issubset({item.id for item in BASIC_CAPABILITIES})


def test_shortcut_state_result_has_human_readable_state():
    assert _shortcut_state_label(True) == "折叠"
    assert _shortcut_state_label(False) == "展开"
    assert _shortcut_state_label(None) == "未知"


def test_new_basic_capabilities_are_registered():
    assert get_basic_capability("demon_repellent_incense").name == "摄妖香相关"
    assert get_basic_capability("find_npc_and_interact").name == "寻找指定 NPC 角色并交互"
    assert "incense_capability_flow" in get_basic_capability("demon_repellent_incense").implementation


def test_incense_delegates_to_capability_flow(monkeypatch):
    captured = {}

    def fake_flow(parent_hwnd, selection, output_dir, **kwargs):
        captured["parent_hwnd"] = parent_hwnd
        captured["selection"] = selection
        captured["output_dir"] = output_dir
        return {"ok": True, "capability": "demon_repellent_incense", "subtask": "usage"}

    monkeypatch.setattr(
        "game_helpers.tasks.basic_capability_flow.run_demon_repellent_incense",
        fake_flow,
    )
    selection = object()
    result = run_basic_capability(123, selection, "demon_repellent_incense", "/tmp/incense")
    assert result["capability"] == "demon_repellent_incense"
    assert captured["parent_hwnd"] == 123
    assert captured["selection"] is selection
    assert captured["output_dir"] == "/tmp/incense"


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


def test_dao_ju_lan_delegates_to_existing_item_panel_flow(monkeypatch, tmp_path):
    captured = {}

    class FakeResult:
        def __init__(self):
            self.ok = True
            self.before = None
            self.after = None
            self.toggled = True
            self.toggle_verified = True
            self.message = "ok"
            self.foreground_unchanged = True
            self.restored_surface = True
            self.restored_tab = True
            self.click_client = (469, 565)
            self.error = None

    def fake_flow(parent_hwnd, selection, **kwargs):
        captured["parent_hwnd"] = parent_hwnd
        captured["selection"] = selection
        captured["output_dir"] = kwargs["output_dir"]
        captured["target_selector"] = kwargs["target_selector"]
        # Simulate flow writing evidence into the timestamped run dir.
        Path(kwargs["output_dir"]).mkdir(parents=True, exist_ok=True)
        (Path(kwargs["output_dir"]) / "before-character-1.png").write_bytes(b"x")
        return FakeResult()

    monkeypatch.setattr(
        "game_helpers.tasks.basic_capability_flow.run_item_panel_detect_and_toggle",
        fake_flow,
    )
    selection = object()
    result = run_basic_capability(123, selection, "dao_ju_lan", tmp_path)
    assert result["ok"] is True
    assert result["capability"] == "dao_ju_lan"
    assert "artifact_dir" in result
    run_dir = Path(result["artifact_dir"])
    assert run_dir.parent == tmp_path
    assert captured["output_dir"] == run_dir
    assert (run_dir / "result.json").is_file()
    assert (run_dir / "run.json").is_file()
    assert captured["parent_hwnd"] == 123
    assert captured["selection"] is selection
    assert callable(captured["target_selector"])
