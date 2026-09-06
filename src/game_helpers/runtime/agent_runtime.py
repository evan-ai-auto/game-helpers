"""Closed-loop runtime for the GUI Game Agent."""

from __future__ import annotations

from dataclasses import dataclass
from time import time
from typing import Callable, Protocol

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
    def verify(
        self,
        previous: GameState,
        current: GameState,
        decision: AgentDecision,
        results: tuple[ActionResult, ...],
    ) -> VerificationResult: ...


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
    """Turn a capture Frame into the protocol-level Observation."""

    def build(self, frame: Frame) -> Observation:
        return Observation(frame=frame, timestamp=frame.captured_at, metadata={"capture_backend": frame.backend})


class MetadataGameAdapter:
    """Bootstrap adapter; real games replace this with Vision + game semantics."""

    def to_state(self, observation: Observation) -> GameState:
        return GameState(
            window=observation.frame.window,
            screenshot_available=True,
            detected_text=list(observation.text),
            targets=dict(observation.objects),
            metadata=dict(observation.metadata),
        )


class AgentRuntime:
    """Execute the AI Game Agent closed loop one step at a time."""

    def __init__(
        self,
        capture: Callable[[], Frame],
        agent: Agent,
        *,
        observation_builder: ObservationBuilder | None = None,
        game_adapter: GameAdapter | None = None,
        executor: ActionExecutor | None = None,
        verifier: Verifier | None = None,
    ) -> None:
        self.capture = capture
        self.agent = agent
        self.observation_builder = observation_builder or DefaultObservationBuilder()
        self.game_adapter = game_adapter or MetadataGameAdapter()
        self.executor = executor or ActionExecutor()
        self.verifier = verifier or DefaultVerifier()
        self._state: GameState | None = None

    @property
    def state(self) -> GameState | None:
        return self._state

    def step(self) -> AgentStep:
        frame = self.capture()
        observation = self.observation_builder.build(frame)
        state = self.game_adapter.to_state(observation)
        previous = self._state or state
        decision = self.agent.decide(state, observation)
        results = tuple(self._execute(action) for action in decision.actions)

        next_frame = self.capture()
        next_observation = self.observation_builder.build(next_frame)
        next_state = self.game_adapter.to_state(next_observation)
        verification = self.verifier.verify(previous, next_state, decision, results)
        self._state = verification.state or next_state
        return AgentStep(observation, state, decision, results, next_observation, self._state, verification)

    def run(self, *, max_steps: int | None = None) -> list[AgentStep]:
        steps: list[AgentStep] = []
        while max_steps is None or len(steps) < max_steps:
            step = self.step()
            steps.append(step)
            if step.next_state.task_completed:
                break
        return steps

    def _execute(self, action) -> ActionResult:
        started = time()
        try:
            self.executor.execute(action)
        except Exception as exc:
            return ActionResult(action, ActionStatus.FAILED, started, time(), str(exc))
        return ActionResult(action, ActionStatus.SUCCESS, started, time())


class DefaultVerifier:
    """Conservative verifier: execution must succeed and post-action state is retained."""

    def verify(self, previous, current, decision, results):
        failed = [result for result in results if not result.succeeded]
        if failed:
            return VerificationResult(False, "action execution failed", current)
        return VerificationResult(True, "post-action observation accepted", current)
