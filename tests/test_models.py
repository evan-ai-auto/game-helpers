from game_helpers.core.models import Action, ActionType, Point, Rect


def test_rect_geometry() -> None:
    rect = Rect(10, 20, 110, 80)
    assert rect.width == 100
    assert rect.height == 60
    assert rect.center == Point(60, 50)


def test_action_is_serializable_as_plain_data() -> None:
    action = Action(ActionType.CLICK, target=Point(12, 34))
    assert action.type.value == "click"
    assert action.target == Point(12, 34)
