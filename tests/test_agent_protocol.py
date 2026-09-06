from dataclasses import dataclass

from game_helpers.core import (
    Action,
    ActionResult,
    ActionStatus,
    ActionType,
    AgentDecision,
    Observation,
    Rect,
    VerificationResult,
)


@dataclass(frozen=True)
class FakeFrame:
    window: object
    width: int = 1280
    height: int = 720
    data: bytes = b""
    captured_at: float = 1.0
    backend: str = "test"


def test_observation_accepts_capture_frame_contract():
    frame = FakeFrame(window=object())
    observation = Observation(
        frame=frame,
        observation_id="obs-1",
        objects={"button": Rect(0, 0, 10, 10)},
        text=("Play",),
    )

    assert observation.frame is frame
    assert observation.observation_id == "obs-1"
    assert observation.text == ("Play",)


def test_action_result_exposes_execution_status():
    action = Action(ActionType.CLICK)
    result = ActionResult(action, ActionStatus.SUCCESS, 1.0, 1.1)

    assert result.action is action
    assert result.succeeded
    assert result.error is None


def test_decision_and_verification_are_independent_data_contracts():
    action = Action(ActionType.WAIT, duration_ms=100)
    decision = AgentDecision(actions=(action,), rationale="wait for UI")
    verification = VerificationResult(verified=True, reason="expected state reached")

    assert decision.actions == (action,)
    assert decision.rationale == "wait for UI"
    assert verification.verified
