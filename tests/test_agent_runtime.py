from dataclasses import dataclass
import json

import pytest

from game_helpers.capture.models import Frame
from game_helpers.core import Action, ActionStatus, ActionType, AgentDecision, Observation, VerificationResult, WindowInfo
from game_helpers.runtime.agent_runtime import AgentRuntime, RuntimeStatus, RuntimePaused


@dataclass
class FakeExecutor:
    executed: list

    def execute(self, action):
        self.executed.append(action)


class FakeAgent:
    def __init__(self, *, pause: bool = False):
        self.pause = pause

    def decide(self, state, observation):
        metadata = {"pause": True, "pause_reason": "unknown task state"} if self.pause else {}
        return AgentDecision(actions=(Action(ActionType.WAIT, duration_ms=0),), rationale="test", metadata=metadata)


class FakeVerifier:
    def __init__(self, *, pause: bool = False):
        self.pause = pause

    def verify(self, previous, current, decision, results):
        metadata = {"pause": True, "pause_reason": "verification requires human"} if self.pause else {}
        return VerificationResult(bool(all(r.succeeded for r in results)), "verified", current, metadata)


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
    assert runtime.status is RuntimeStatus.RUNNING


def test_runtime_hard_stops_before_any_action_when_agent_requests_user():
    executor = FakeExecutor([])
    frames = iter((make_frame(1.0),))
    runtime = AgentRuntime(lambda: next(frames), FakeAgent(pause=True), executor=executor, checkpoint_dir=None)

    with pytest.raises(RuntimePaused) as exc_info:
        runtime.step()

    assert runtime.status is RuntimeStatus.PAUSED_USER_REQUEST
    assert runtime.checkpoint is exc_info.value.checkpoint
    assert exc_info.value.checkpoint.reason == "unknown task state"
    assert executor.executed == []


def test_runtime_run_returns_without_retrying_after_pause():
    executor = FakeExecutor([])
    frames = iter((make_frame(1.0),))
    runtime = AgentRuntime(lambda: next(frames), FakeAgent(pause=True), executor=executor, checkpoint_dir=None)

    steps = runtime.run()

    assert steps == []
    assert runtime.status is RuntimeStatus.PAUSED_USER_REQUEST
    assert executor.executed == []


def test_runtime_hard_stops_after_verification_pause():
    executor = FakeExecutor([])
    frames = iter((make_frame(1.0), make_frame(2.0)))
    runtime = AgentRuntime(lambda: next(frames), FakeAgent(), executor=executor, verifier=FakeVerifier(pause=True), checkpoint_dir=None)

    with pytest.raises(RuntimePaused) as exc_info:
        runtime.step()

    assert runtime.status is RuntimeStatus.PAUSED_USER_REQUEST
    assert exc_info.value.checkpoint.reason == "verification requires human"
    assert len(executor.executed) == 1


def test_runtime_writes_json_checkpoint(tmp_path):
    executor = FakeExecutor([])
    frames = iter((make_frame(1.0),))
    runtime = AgentRuntime(lambda: next(frames), FakeAgent(pause=True), executor=executor, checkpoint_dir=tmp_path)

    runtime.run()

    checkpoint = tmp_path / "latest.json"
    assert checkpoint.exists()
    data = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert data["reason"] == "unknown task state"
    assert data["decision"]["metadata"]["pause"] is True
