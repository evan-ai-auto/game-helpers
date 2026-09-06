"""Deterministic first policy for the 梦幻西游 baseline task."""

from __future__ import annotations

from game_helpers.core.agent_protocol import AgentDecision, Observation
from game_helpers.core.models import Action, ActionType

from .state import DreamGameState


class DreamAgent:
    """Closed-loop policy for the currently supported soul-task check.

    The policy is deliberately deterministic: it uses visual evidence to open
    the item panel, then waits for the verified soul-task icon. This gives the
    first game a real perception -> decision -> action -> verification loop
    without pretending that unverified game coordinates are reliable.
    """

    def decide(self, state: DreamGameState, observation: Observation) -> AgentDecision:
        if state.soul_task_claimed:
            return AgentDecision(rationale="命魂任务已领取，目标完成", confidence=1.0)

        if not state.item_panel_open:
            target = observation.objects.get("item_bar_toggle")
            if target is None:
                return AgentDecision(
                    actions=(Action(ActionType.WAIT, duration_ms=400),),
                    rationale="未检测到道具栏入口，等待下一帧恢复视觉锚点",
                    confidence=0.2,
                )
            return AgentDecision(
                actions=(Action(ActionType.CLICK, target=target.center),),
                rationale="打开道具栏以读取命魂任务状态",
                confidence=0.9,
            )

        return AgentDecision(
            actions=(Action(ActionType.WAIT, duration_ms=350),),
            rationale="道具栏已打开，等待命魂任务图标稳定检测",
            confidence=0.8,
        )
