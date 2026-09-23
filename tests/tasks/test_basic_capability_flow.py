from game_helpers.tasks.basic_capabilities import get_basic_capability
from game_helpers.tasks.basic_capability_flow import _run_basic_capability_session


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
