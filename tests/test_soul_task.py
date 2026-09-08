from game_helpers.games.menghuanxiyou.soul_task import (
    MilestoneState,
    SoulRoundStatus,
    SoulTaskLoop,
    SoulTaskRound,
    TaskExecutionResult,
    TaskExecutionStatus,
    TaskVerification,
)


class Verifier:
    def verify(self, result):
        return TaskVerification(result.task_id, result.status is TaskExecutionStatus.SUCCESS, "verified")


class Progress:
    def __init__(self, value):
        self.value = value

    def detect(self):
        return self.value


class Rewards:
    def __init__(self):
        self.claimed = []

    def claim(self, threshold):
        self.claimed.append(threshold)
        return True


class Refresh:
    def __init__(self):
        self.count = 0

    def refresh(self):
        self.count += 1
        return True


def make_loop(progress):
    rewards = Rewards()
    refresh = Refresh()
    loop = SoulTaskLoop(
        SoulTaskRound("round-001"), Verifier(), Progress(progress), rewards, refresh
    )
    return loop, rewards, refresh


def test_every_successful_task_type_uses_common_progress_pipeline():
    loop, rewards, refresh = make_loop(15)
    for task_type in ("give_item", "dialogue", "combat"):
        result = TaskExecutionResult(f"task-{task_type}", task_type, TaskExecutionStatus.SUCCESS)
        verification = loop.process_task(result)
        assert verification.verified
    assert rewards.claimed == [15]
    assert refresh.count == 1


def test_milestones_are_threshold_based_and_60_completes_without_opening_next_round():
    loop, rewards, refresh = make_loop(60)
    loop.process_task(TaskExecutionResult("task-1", "combat", TaskExecutionStatus.SUCCESS))
    assert rewards.claimed == [15, 30, 45, 60]
    assert refresh.count == 3
    assert loop.round.status is SoulRoundStatus.COMPLETED
    assert loop.snapshot()["auto_open_next_round"] is False
    assert loop.round.milestones[60].reward_type == "completion_reward"


def test_failed_task_does_not_advance_progress():
    loop, rewards, refresh = make_loop(30)
    verification = loop.process_task(
        TaskExecutionResult("task-1", "give_item", TaskExecutionStatus.FAILED)
    )
    assert not verification.verified
    assert loop.round.progress == 0
    assert rewards.claimed == []
    assert refresh.count == 0
