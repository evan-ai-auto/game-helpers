from game_helpers.tasks.basic_capability_flow import BASIC_CAPABILITIES, run_basic_capability


def test_basic_capabilities_are_unique_and_independently_named():
    ids = [item.id for item in BASIC_CAPABILITIES]
    names = [item.name for item in BASIC_CAPABILITIES]
    assert ids
    assert len(ids) == len(set(ids))
    assert len(names) == len(set(names))
    assert callable(run_basic_capability)
