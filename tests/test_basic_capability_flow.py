from game_helpers.tasks.basic_capabilities import (
    BASIC_CAPABILITIES,
    SHORTCUT_DIAGNOSTIC_CAPABILITY_IDS,
    get_basic_capability,
)
from game_helpers.tasks.basic_capability_flow import run_basic_capability
from game_helpers.tasks.soul_shortcut_diagnostic_flow import SHORTCUT_DIAGNOSTIC_CAPABILITIES


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
