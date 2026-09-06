"""Game-specific recovery actions for the first Dream Agent."""

from __future__ import annotations

from game_helpers.core.agent_brain import RecoveryDecision
from game_helpers.core.agent_protocol import AgentDecision
from game_helpers.core.models import Action, ActionType


class DreamRecovery:
    """Translate generic recovery modes into safe, observable actions."""

    def decide(self, recovery: RecoveryDecision | None) -> AgentDecision | None:
        if recovery is None:
            return None
        if recovery.mode == "abort":
            return AgentDecision(rationale=recovery.reason, confidence=1.0, metadata={"recovery": "abort"})
        if recovery.mode == "reacquire":
            return AgentDecision(
                actions=(Action(ActionType.WAIT, duration_ms=600),),
                rationale=recovery.reason,
                confidence=0.5,
                metadata={"recovery": "reacquire"},
            )
        return AgentDecision(
            actions=(Action(ActionType.WAIT, duration_ms=450),),
            rationale=recovery.reason,
            confidence=0.5,
            metadata={"recovery": "retry"},
        )
