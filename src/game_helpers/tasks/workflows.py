"""Human-selectable task workflow definitions for 梦幻西游."""
from __future__ import annotations

from dataclasses import dataclass

from .models import TaskCategory, TaskRecipe


@dataclass(frozen=True)
class TaskWorkflow:
    id: str
    name: str
    recipe: TaskRecipe
    description: str = ""


class TaskWorkflowRegistry:
    def __init__(self, workflows: tuple[TaskWorkflow, ...] | None = None) -> None:
        self._workflows = workflows or default_workflows()
        self._by_id = {workflow.id: workflow for workflow in self._workflows}
        self._by_name = {workflow.name: workflow for workflow in self._workflows}

    def all(self):
        return self._workflows

    def get(self, workflow_id: str):
        return self._by_id[workflow_id]

    def get_by_name(self, name: str):
        return self._by_name[name]


def default_workflows():
    return (
        TaskWorkflow(id="minghun", name="命魂任务", description="执行领取状态检测（800×600 基线）；不自动领取。", recipe=TaskRecipe(id="minghun", name="命魂任务", category=TaskCategory.GENERAL, metadata={"game": "梦幻西游", "diagnosis_only": True, "status_detector": "soul_task", "baseline_client": "800x600"})),
        TaskWorkflow(id="minghun_coordinate", name="命魂任务坐标采集", description="保留原有单次 F9 坐标采集与单次后台点击确认流程。", recipe=TaskRecipe(id="minghun_coordinate", name="命魂任务坐标采集", category=TaskCategory.GENERAL, metadata={"game": "梦幻西游", "diagnosis_only": True, "calibration": "shortcut_panel_toggle", "baseline_client": "800x600"})),
        TaskWorkflow(id="minghun_coordinate_continuous", name="命魂快捷图标开关连续坐标验证", description="连续 F9 采点并后台点击；仅人工确认有效的坐标计入样本，ESC 结束，不覆盖默认坐标。", recipe=TaskRecipe(id="minghun_coordinate_continuous", name="命魂快捷图标开关连续坐标验证", category=TaskCategory.GENERAL, metadata={"game": "梦幻西游", "diagnosis_only": True, "calibration": "shortcut_panel_toggle_continuous", "baseline_client": "800x600"})),
        TaskWorkflow(id="minghun_detection_coordinate", name="命魂快捷图标检测与点击坐标联合验证", description="先保存完整截图并裁剪 ROI，再输出匹配坐标、采集人工有效点击点并逐点验证；不覆盖默认坐标。", recipe=TaskRecipe(id="minghun_detection_coordinate", name="命魂快捷图标检测与点击坐标联合验证", category=TaskCategory.GENERAL, metadata={"game": "梦幻西游", "diagnosis_only": True, "calibration": "shortcut_panel_detection_and_click_coordinate", "baseline_client": "800x600"})),
        TaskWorkflow(id="minghun_shortcut_diagnostic", name="阻塞 - 命魂快捷图标完整闭环 - 覆盖窗口画面刷新问题阻塞，进入后按需求分层验证", description="用户视角入口；进入后按需求验收目标选择分层验证。底层仍组合运动、OCR、Hover、PostMessageW、Click、覆盖捕获新鲜度等实现能力，不修改生产默认配置。", recipe=TaskRecipe(id="minghun_shortcut_diagnostic", name="命魂快捷图标 Hover / 运动 / 后台输入分层验证", category=TaskCategory.GENERAL, metadata={"game": "梦幻西游", "diagnosis_only": True, "calibration": "shortcut_panel_layered_diagnostic", "baseline_client": "800x600", "subtypes": ["full", "motion", "ocr_roi_compare", "hover", "postmessage_hover", "click_hotspot", "background_capture_freshness"]})),
        TaskWorkflow(id="daoju_panel", name="道具栏状态检测", description="检测道具栏开/关并后台反转；默认模板定位，可用 --coord-source manual 人工采点（800×600）。", recipe=TaskRecipe(id="daoju_panel", name="道具栏状态检测", category=TaskCategory.GENERAL, metadata={"game": "梦幻西游", "baseline_client": "800x600", "status_detector": "item_panel_open", "supports_toggle": True})),
        TaskWorkflow(id="shimen", name="师门任务", description="师门任务诊断流程（当前仅选择流程，不执行任务）。", recipe=TaskRecipe(id="shimen", name="师门任务", category=TaskCategory.GENERAL, metadata={"game": "梦幻西游", "diagnosis_only": True})),
        TaskWorkflow(id="custom", name="自定义任务流程", description="用于后续接入用户自定义任务步骤的诊断入口。", recipe=TaskRecipe(id="custom", name="自定义任务流程", category=TaskCategory.GENERAL, metadata={"game": "梦幻西游", "diagnosis_only": True})),
    )
