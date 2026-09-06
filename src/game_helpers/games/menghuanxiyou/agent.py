"""Game Agent Brain for 梦幻西游: planning, navigation, interaction, verification, recovery."""

from __future__ import annotations

from game_helpers.core.agent_brain import AgentMemory, GoalPlanner, PlanStep, RecoveryPolicy, state_key
from game_helpers.core.agent_protocol import AgentDecision, ActionResult, Observation, VerificationResult
from game_helpers.core.models import Action, ActionType

from .navigation import DreamNavigationGraph
from .recovery import DreamRecovery
from .state import DreamGameState


class DreamAgent:
    """Long-task policy with explicit milestones and bounded recovery.

    The default goal remains the existing soul-task status flow. A navigation
    goal can be supplied as ``transport:<id>``; movement is only executed when
    a matching visual target is present in the current Observation.
    """

    def __init__(self, *, navigation: DreamNavigationGraph | None = None, goal: str = "soul_task") -> None:
        self.navigation = navigation
        self.goal = goal
        self.memory = AgentMemory()
        self.recovery = RecoveryPolicy()
        self.recovery_actions = DreamRecovery()
        self.planner = GoalPlanner(self._steps_for(goal))
        self._last_decision: AgentDecision | None = None

    @staticmethod
    def _steps_for(goal: str) -> tuple[PlanStep, ...]:
        if goal.startswith("transport:"):
            return (
                PlanStep("recognize_scene", "确认当前场景"),
                PlanStep("locate_target", "理解目标 NPC/传送点"),
                PlanStep("navigate", "移动到目标"),
                PlanStep("interact", "执行交互"),
                PlanStep("verify_transition", "验证场景/状态变化"),
            )
        return (
            PlanStep("open_inventory", "打开道具栏"),
            PlanStep("inspect_task", "读取命魂任务状态"),
            PlanStep("verify_completion", "验证任务状态"),
        )

    def decide(self, state: DreamGameState, observation: Observation) -> AgentDecision:
        self.memory.observe_state(state_key(state))
        recovery = self.recovery_actions.decide(self.recovery.decide(self.memory))
        if recovery is not None:
            self._last_decision = recovery
            return recovery

        if self.goal.startswith("transport:"):
            decision = self._decide_transport(state, observation)
        else:
            decision = self._decide_soul_task(state, observation)
        self._last_decision = decision
        return decision

    def _decide_soul_task(self, state: DreamGameState, observation: Observation) -> AgentDecision:
        if state.soul_task_claimed:
            self.planner.advance_if(True)
            return AgentDecision(rationale="命魂任务已领取，目标完成", confidence=1.0)
        if not state.item_panel_open:
            target = observation.objects.get("item_bar_toggle")
            if target is None:
                return AgentDecision(actions=(Action(ActionType.WAIT, duration_ms=400),), rationale="等待道具栏视觉锚点", confidence=0.2)
            self.planner.advance_if(True)
            return AgentDecision(actions=(Action(ActionType.CLICK, target=target.center),), rationale="打开道具栏", confidence=0.9)
        self.planner.advance_if(True)
        return AgentDecision(actions=(Action(ActionType.WAIT, duration_ms=350),), rationale="等待命魂任务状态稳定", confidence=0.8)

    def _decide_transport(self, state: DreamGameState, observation: Observation) -> AgentDecision:
        if state.scene_confidence < 0.8:
            return AgentDecision(actions=(Action(ActionType.WAIT, duration_ms=500),), rationale="场景识别置信度不足，等待重新感知", confidence=state.scene_confidence)

        target_id = self.goal.removeprefix("transport:")
        target_key = f"transport:{target_id}"
        target = observation.objects.get(target_key)
        if target is None:
            return AgentDecision(actions=(Action(ActionType.WAIT, duration_ms=500),), rationale=f"未视觉确认目标 {target_id}，不执行盲点坐标", confidence=0.2)

        if state.interaction_target == target_id:
            self.planner.advance_if(True)
            return AgentDecision(actions=(Action(ActionType.CLICK, target=target.center),), rationale=f"交互目标 {target_id}", confidence=0.85, metadata={"expected_target": target_id})

        self.planner.advance_if(True)
        return AgentDecision(actions=(Action(ActionType.CLICK, target=target.center),), rationale=f"导航至 {target_id}", confidence=0.75, metadata={"navigation_target": target_id})

    def on_step_completed(self, results: tuple[ActionResult, ...], verification: VerificationResult) -> None:
        """Feed execution/verification outcomes back into memory for recovery."""
        self.memory.record_results(results, verification)
