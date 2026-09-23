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
        TaskWorkflow(id="minghun_basic_capabilities", name="基础能力列表", description="单独测试各项最基础可复用能力；仅调用现有实现，不修改能力实现本身。", recipe=TaskRecipe(id="minghun_basic_capabilities", name="基础能力列表", category=TaskCategory.GENERAL, metadata={"game": "梦幻西游", "diagnosis_only": True, "baseline_client": "800x600"})),
        TaskWorkflow(id="minghun", name="[未验收] 命魂任务 - 执行领取状态检测", description="800×600 基线；不自动领取。业务人工验收状态：未验收。", recipe=TaskRecipe(id="minghun", name="[未验收] 命魂任务 - 执行领取状态检测", category=TaskCategory.GENERAL, metadata={"game": "梦幻西游", "diagnosis_only": True, "status_detector": "soul_task", "baseline_client": "800x600"})),
        TaskWorkflow(id="minghun_coordinate", name="[未验收] 命魂任务坐标采集 - 单次 F9 坐标采集与后台点击确认", description="保留原有流程。业务人工验收状态：未验收。", recipe=TaskRecipe(id="minghun_coordinate", name="[未验收] 命魂任务坐标采集 - 单次 F9 坐标采集与后台点击确认", category=TaskCategory.GENERAL, metadata={"game": "梦幻西游", "diagnosis_only": True, "calibration": "shortcut_panel_toggle", "baseline_client": "800x600"})),
        TaskWorkflow(id="minghun_coordinate_continuous", name="[未验收] 命魂快捷图标开关连续坐标验证 - 连续采点与后台点击", description="仅人工确认有效点计入样本，ESC 结束，不覆盖默认坐标。业务人工验收状态：未验收。", recipe=TaskRecipe(id="minghun_coordinate_continuous", name="[未验收] 命魂快捷图标开关连续坐标验证 - 连续采点与后台点击", category=TaskCategory.GENERAL, metadata={"game": "梦幻西游", "diagnosis_only": True, "calibration": "shortcut_panel_toggle_continuous", "baseline_client": "800x600"})),
        TaskWorkflow(id="minghun_detection_coordinate", name="[未验收] 命魂快捷图标检测与点击坐标联合验证 - 视觉检测与人工点击点验证", description="保存完整截图并裁剪 ROI；不覆盖默认坐标。业务人工验收状态：未验收。", recipe=TaskRecipe(id="minghun_detection_coordinate", name="[未验收] 命魂快捷图标检测与点击坐标联合验证 - 视觉检测与人工点击点验证", category=TaskCategory.GENERAL, metadata={"game": "梦幻西游", "diagnosis_only": True, "calibration": "shortcut_panel_detection_and_click_coordinate", "baseline_client": "800x600"})),
        TaskWorkflow(id="minghun_shortcut_diagnostic", name="阻塞 - 命魂快捷图标完整闭环 - 覆盖窗口画面刷新问题阻塞，进入后按需求分层验证", description="用户视角入口；进入后按需求验收目标选择分层验证。底层仍组合运动、OCR、Hover、PostMessageW、Click、覆盖捕获新鲜度等实现能力，不修改生产默认配置。", recipe=TaskRecipe(id="minghun_shortcut_diagnostic", name="阻塞 - 命魂快捷图标完整闭环 - 覆盖窗口画面刷新问题阻塞，进入后按需求分层验证", category=TaskCategory.GENERAL, metadata={"game": "梦幻西游", "diagnosis_only": True, "calibration": "shortcut_panel_layered_diagnostic", "baseline_client": "800x600", "subtypes": ["full", "motion", "ocr_roi_compare", "hover", "postmessage_hover", "click_hotspot", "background_capture_freshness"]})),
        TaskWorkflow(id="daoju_panel", name="[未验收] 道具栏状态检测 - 检测开关状态并后台反转", description="默认模板定位，可用 --coord-source manual 人工采点（800×600）。业务人工验收状态：未验收。", recipe=TaskRecipe(id="daoju_panel", name="[未验收] 道具栏状态检测 - 检测开关状态并后台反转", category=TaskCategory.GENERAL, metadata={"game": "梦幻西游", "baseline_client": "800x600", "status_detector": "item_panel_open", "supports_toggle": True})),
        TaskWorkflow(id="shimen", name="[未验收] 师门任务 - 当前仅选择流程，不执行任务", description="业务人工验收状态：未验收。", recipe=TaskRecipe(id="shimen", name="[未验收] 师门任务 - 当前仅选择流程，不执行任务", category=TaskCategory.GENERAL, metadata={"game": "梦幻西游", "diagnosis_only": True})),
        TaskWorkflow(id="custom", name="[未验收] 自定义任务流程 - 用户自定义任务步骤诊断入口", description="业务人工验收状态：未验收。", recipe=TaskRecipe(id="custom", name="[未验收] 自定义任务流程 - 用户自定义任务步骤诊断入口", category=TaskCategory.GENERAL, metadata={"game": "梦幻西游", "diagnosis_only": True})),
    )
