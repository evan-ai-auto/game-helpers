from dataclasses import dataclass

from game_helpers.capture.models import Frame
from game_helpers.core import Action, ActionStatus, ActionType, AgentDecision, Observation, VerificationResult, WindowInfo
from game_helpers.runtime.agent_runtime import AgentRuntime


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
        return VerificationResult(bool(all(r.succeeded for r in results)), "verified", current)


def make_frame(timestamp):
    return Frame(WindowInfo(1, "game", "Game"), 2, 2, bytes(16), timestamp, "test")


def test_runtime_executes_closed_loop_step():
    executor = FakeExecutor([])
    frames = iter((make_frame(1.0), make_frame(2.0)))
    runtime = AgentRuntime(lambda: next(frames), FakeAgent(), executor=executor, verifier=FakeVerifier())

    step = runtime.step()

    assert isinstance(step.observation, Observation)
    assert step.state.screenshot_available
    assert step.decision.rationale == "test"
    assert step.results[0].status is ActionStatus.SUCCESS
    assert step.next_observation.timestamp == 2.0
    assert step.next_state.screenshot_available
    assert step.verification.verified
    assert len(executor.executed) == 1
