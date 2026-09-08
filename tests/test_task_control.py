from game_helpers.runtime.task_control import (
    AssignmentConflict,
    MultiCharacterRuntime,
    RunMode,
    RuntimeStatus,
)


def make_runtime():
    runtime = MultiCharacterRuntime()
    runtime.characters.register("a", "角色A", login_status="logged_in")
    runtime.characters.register("b", "角色B", login_status="logged_in")
    runtime.characters.register("c", "角色C", login_status="logged_in")
    return runtime


def test_first_task_can_start_multiple_characters():
    runtime = make_runtime()
    task, decisions = runtime.create_task("soul_task", ["a", "b"], run_mode=RunMode.BACKGROUND)

    assert task.task_type == "soul_task"
    assert all(d.accepted for d in decisions)
    assert runtime.characters.get("a").current_task_id == task.task_id
    assert runtime.characters.get("b").current_task_id == task.task_id


def test_second_task_sees_existing_character_context_and_requires_choice():
    runtime = make_runtime()
    first, _ = runtime.create_task("soul_task", ["a", "b"])

    second, decisions = runtime.create_task("ghost", ["b", "c"])
    b_decision = next(d for d in decisions if d.character_id == "b")
    c_decision = next(d for d in decisions if d.character_id == "c")

    assert runtime.character_context()[1].current_task_id == first.task_id
    assert b_decision.conflict is True
    assert b_decision.accepted is False
    assert c_decision.accepted is True
    assert runtime.characters.get("b").task_type == "soul_task"
    assert runtime.characters.get("c").task_type == "ghost"


def test_conflict_keep_existing_only_keeps_conflicting_character():
    runtime = make_runtime()
    first, _ = runtime.create_task("soul_task", ["a", "b"])
    second, decisions = runtime.create_task("ghost", ["b", "c"], conflict=AssignmentConflict.KEEP_EXISTING)

    assert next(d for d in decisions if d.character_id == "b").reason == "kept_existing_task"
    assert runtime.characters.get("b").current_task_id == first.task_id
    assert runtime.characters.get("c").current_task_id == second.task_id


def test_conflict_overwrite_stops_old_session_before_starting_new_one():
    runtime = make_runtime()
    first, _ = runtime.create_task("soul_task", ["a", "b"])
    old_session_id = runtime.characters.get("b").current_session_id

    second, decisions = runtime.create_task("ghost", ["b", "c"], conflict=AssignmentConflict.OVERWRITE)
    b_decision = next(d for d in decisions if d.character_id == "b")

    assert b_decision.accepted is True
    assert b_decision.replaced_task_id == first.task_id
    assert runtime.characters.get("b").current_task_id == second.task_id
    assert runtime.characters.get("b").task_type == "ghost"
    assert runtime.characters.get("b").current_session_id != old_session_id
    assert next(s for s in runtime.scheduler.sessions() if s.session_id == old_session_id).status == RuntimeStatus.STOPPED


def test_stop_character_does_not_stop_other_characters():
    runtime = make_runtime()
    runtime.create_task("soul_task", ["a", "b"])
    assert runtime.stop_character("a") is True

    assert runtime.characters.get("a").status == RuntimeStatus.STOPPED
    assert runtime.characters.get("b").status == RuntimeStatus.RUNNING


def test_stop_all_stops_all_character_sessions():
    runtime = make_runtime()
    runtime.create_task("soul_task", ["a", "b"])
    runtime.create_task("ghost", ["c"])
    runtime.stop_all_sessions()

    assert all(c.status == RuntimeStatus.STOPPED for c in runtime.characters.all())
