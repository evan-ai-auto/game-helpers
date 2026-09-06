from game_helpers.core.agent_brain import AgentMemory, GoalPlanner, PlanStep, RecoveryPolicy
from game_helpers.core.agent_protocol import ActionResult, ActionStatus, AgentDecision, VerificationResult
from game_helpers.core.models import Action, ActionType


def result(success: bool) -> ActionResult:
    action = Action(ActionType.WAIT, duration_ms=1)
    return ActionResult(action, ActionStatus.SUCCESS if success else ActionStatus.FAILED, 1.0, 2.0)


def test_goal_planner_advances_semantic_milestones():
    planner = GoalPlanner((PlanStep("a", "A"), PlanStep("b", "B")))
    assert planner.current.name == "a"
    planner.advance_if(True)
    assert planner.current.name == "b"
    planner.advance_if(True)
    assert planner.completed


def test_memory_escalates_after_failed_steps():
    memory = AgentMemory()
    policy = RecoveryPolicy(max_retries=2, stall_seconds=999)
    memory.record_results((result(False),), VerificationResult(False, "bad", None))
    assert policy.decide(memory).mode == "retry"
    memory.record_results((result(False),), VerificationResult(False, "bad again", None))
    assert policy.decide(memory).mode == "abort"
