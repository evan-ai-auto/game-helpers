from dataclasses import dataclass

from game_helpers.core import Action, ActionResult, ActionStatus, ActionType, AgentDecision, Observation, WindowInfo
from game_helpers.runtime.agent_runtime import AgentRuntime
from game_helpers.capture.models import Frame


@dataclass
class FakeExecutor:
    executed: list

    def execute(self, action):
        self.executed.append(action)


class FakeAgent:
    def decide(self, state, observation):
        return AgentDecision(actions=(Action(ActionType.WAIT, duration_ms=0),), rationale="test")


class FakeVerifier:
    def verify(self, previous, current, decision, results):
        from game_helpers.core import VerificationResult
        return VerificationResult(bool(all(r.succeeded for r in results)), "verified", current)


def make_frame():
    return Frame(WindowInfo(1, "game", "Game"), 2, 2, bytes(16), 1.0, "test")


def test_runtime_executes_closed_loop_step():
    executor = FakeExecutor([])
    runtime = AgentRuntime(
        lambda: make_frame(),
        FakeAgent(),
        executor=executor,
        verifier=FakeVerifier(),
    )

    step = runtime.step()

    assert isinstance(step.observation, Observation)
    assert step.state.screenshot_available
    assert step.decision.rationale == "test"
    assert step.results[0].status is ActionStatus.SUCCESS
    assert step.verification.verified
    assert len(executor.executed) == 1
