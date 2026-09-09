"""Closed-loop runtime for the GUI Game Agent."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import json
from pathlib import Path
from time import time
from typing import Any, Callable, Mapping, Protocol

from ..actions.executor import ActionExecutor
from ..capture.models import Frame
from ..core.agent_protocol import ActionResult, ActionStatus, AgentDecision, Observation, VerificationResult
from ..core.models import GameState


class ObservationBuilder(Protocol):
    def build(self, frame: Frame) -> Observation: ...


class GameAdapter(Protocol):
    def to_state(self, observation: Observation) -> GameState: ...


class Agent(Protocol):
    def decide(self, state: GameState, observation: Observation) -> AgentDecision: ...


class Verifier(Protocol):
    def verify(self, previous: GameState, current: GameState, decision: AgentDecision, results: tuple[ActionResult, ...]) -> VerificationResult: ...


class AgentRuntimeStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED_USER_REQUEST = "paused_user_request"
    COMPLETED = "completed"
    FAILED = "failed"


# Backward-compatible name for callers that imported the runtime-local status.
RuntimeStatus = AgentRuntimeStatus


class RuntimePaused(RuntimeError):
    """Raised when the current run must stop and wait for a new program run."""

    def __init__(self, checkpoint: "RuntimeCheckpoint") -> None:
        self.checkpoint = checkpoint
        super().__init__(checkpoint.reason)


@dataclass(frozen=True)
class RuntimeCheckpoint:
    """Serializable context captured immediately before a user-request halt."""

    timestamp: float
    reason: str
    rationale: str
    state: Mapping[str, Any]
    observation: Mapping[str, Any]
    decision: Mapping[str, Any]
    results: tuple[Mapping[str, Any], ...] = ()
    verification: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class AgentStep:
    """One Capture -> Observation -> State -> Decide -> Execute -> Verify transition."""

    observation: Observation
    state: GameState
    decision: AgentDecision
    results: tuple[ActionResult, ...]
    next_observation: Observation
    next_state: GameState
    verification: VerificationResult


class DefaultObservationBuilder:
    def build(self, frame: Frame) -> Observation:
        return Observation(frame=frame, timestamp=frame.captured_at, metadata={"capture_backend": frame.backend})


class MetadataGameAdapter:
    def to_state(self, observation: Observation) -> GameState:
        return GameState(window=observation.frame.window, screenshot_available=True, detected_text=list(observation.text), targets=dict(observation.objects), metadata=dict(observation.metadata))


class AgentRuntime:
    """Execute the agent loop and hard-stop when user intervention is required.

    A user-request halt is deliberately terminal for the current process run:
    no automatic retry, recovery, capture, planning, or action is performed
    after the checkpoint is written. A later run starts from the latest code.
    """

    def __init__(
        self,
        capture: Callable[[], Frame],
        agent: Agent,
        *,
        observation_builder: ObservationBuilder | None = None,
        game_adapter: GameAdapter | None = None,
        executor: ActionExecutor | None = None,
        verifier: Verifier | None = None,
        checkpoint_dir: str | Path | None = "data/runtime/checkpoints",
    ) -> None:
        self.capture = capture
        self.agent = agent
        self.observation_builder = observation_builder or DefaultObservationBuilder()
        self.game_adapter = game_adapter or MetadataGameAdapter()
        self.executor = executor or ActionExecutor()
        self.verifier = verifier or DefaultVerifier()
        self.checkpoint_dir = Path(checkpoint_dir) if checkpoint_dir is not None else None
        self._state: GameState | None = None
        self._status = AgentRuntimeStatus.IDLE
        self._checkpoint: RuntimeCheckpoint | None = None

    @property
    def state(self) -> GameState | None:
        return self._state

    @property
    def status(self) -> AgentRuntimeStatus:
        return self._status

    @property
    def checkpoint(self) -> RuntimeCheckpoint | None:
        return self._checkpoint

    def step(self) -> AgentStep:
        self._status = AgentRuntimeStatus.RUNNING
        frame = self.capture()
        observation = self.observation_builder.build(frame)
        state = self.game_adapter.to_state(observation)
        previous = self._state or state
        decision = self.agent.decide(state, observation)
        if self._requires_user_pause(decision.metadata):
            raise self._pause(
                reason=str(decision.metadata.get("pause_reason", "agent requested user intervention")),
                rationale=decision.rationale,
                state=state,
                observation=observation,
                decision=decision,
            )
        results = tuple(self._execute(action) for action in decision.actions)
        next_frame = self.capture()
        next_observation = self.observation_builder.build(next_frame)
        next_state = self.game_adapter.to_state(next_observation)
        verification = self.verifier.verify(previous, next_state, decision, results)
        self._state = verification.state or next_state
        if self._requires_user_pause(verification.metadata):
            raise self._pause(
                reason=str(verification.metadata.get("pause_reason", verification.reason or "verification requires user intervention")),
                rationale=decision.rationale,
                state=self._state,
                observation=next_observation,
                decision=decision,
                results=results,
                verification=verification,
            )
        callback = getattr(self.agent, "on_step_completed", None)
        if callback is not None:
            callback(results, verification)
        return AgentStep(observation, state, decision, results, next_observation, self._state, verification)

    def run(self, *, max_steps: int | None = None) -> list[AgentStep]:
        steps: list[AgentStep] = []
        self._status = AgentRuntimeStatus.RUNNING
        while max_steps is None or len(steps) < max_steps:
            try:
                step = self.step()
            except RuntimePaused:
                return steps
            steps.append(step)
            if step.next_state.task_completed or step.decision.metadata.get("goal_completed"):
                self._status = AgentRuntimeStatus.COMPLETED
                break
            if step.decision.metadata.get("recovery") == "abort":
                self._status = AgentRuntimeStatus.FAILED
                break
        return steps

    def _pause(
        self,
        *,
        reason: str,
        rationale: str,
        state: GameState,
        observation: Observation,
        decision: AgentDecision,
        results: tuple[ActionResult, ...] = (),
        verification: VerificationResult | None = None,
    ) -> RuntimePaused:
        checkpoint = RuntimeCheckpoint(
            timestamp=time(),
            reason=reason,
            rationale=rationale,
            state=_json_safe(asdict(state)),
            observation=_json_safe({"timestamp": observation.timestamp, "metadata": dict(observation.metadata), "text": list(observation.text), "objects": {k: asdict(v) for k, v in observation.objects.items()}}),
            decision=_json_safe(asdict(decision)),
            results=tuple(_json_safe(asdict(result)) for result in results),
            verification=_json_safe(asdict(verification)) if verification is not None else None,
        )
        self._checkpoint = checkpoint
        self._status = AgentRuntimeStatus.PAUSED_USER_REQUEST
        self._write_checkpoint(checkpoint)
        return RuntimePaused(checkpoint)

    def _write_checkpoint(self, checkpoint: RuntimeCheckpoint) -> None:
        if self.checkpoint_dir is None:
            return
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        path = self.checkpoint_dir / "latest.json"
        path.write_text(json.dumps(_json_safe(asdict(checkpoint)), ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _requires_user_pause(metadata: Mapping[str, Any]) -> bool:
        return bool(metadata.get("pause") or metadata.get("requires_user_intervention"))

    def _execute(self, action) -> ActionResult:
        started = time()
        try:
            self.executor.execute(action)
        except Exception as exc:
            return ActionResult(action, ActionStatus.FAILED, started, time(), str(exc))
        return ActionResult(action, ActionStatus.SUCCESS, started, time())


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return _json_safe(asdict(value))
    if hasattr(value, "__dict__") and not isinstance(value, (str, bytes, bytearray)):
        return _json_safe(vars(value))
    return value


class DefaultVerifier:
    """Conservative verifier: execution must succeed and post-action state is retained."""

    def verify(self, previous, current, decision, results):
        if any(not result.succeeded for result in results):
            return VerificationResult(False, "action execution failed", current)
        return VerificationResult(True, "post-action observation accepted", current)
