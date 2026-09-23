"""Registry of the smallest reusable diagnostic capabilities.

The registry is the shared vocabulary between user-facing capability tests and
task Flows. It records the capability contract and current implementation
binding without moving the implementation into this module.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BasicCapability:
    id: str
    name: str
    description: str
    implementation: str


BASIC_CAPABILITIES = (
    BasicCapability("host_capture", "获取宿主窗口画面", "单次 Host WGC 捕获。", "capture.wgc:WindowsGraphicsCapture.capture"),
    BasicCapability("game_view_capture", "获取选中游戏画面", "Host 捕获后按选中 WSGAME 几何裁剪。", "tasks.verification_session:VerificationSession.capture_frame"),
    BasicCapability("surface_health", "检查游戏画面 Surface", "检查当前选中 WSGAME Surface 是否具备捕获条件。", "tasks.verification_session:VerificationSession.health"),
    BasicCapability("scene_coordinate_ocr", "读取场景与地图坐标", "读取场景名称与 X/Y 坐标。", "vision.scene_coordinate:read_player_location"),
    BasicCapability("shortcut_state_vision", "识别 Shortcut 当前状态", "识别 Shortcut 折叠/展开状态。", "tasks.shortcut_panel_vision:detect_shortcut_panel_state"),
    BasicCapability("image_diff", "执行图像差分", "比较连续画面的像素变化。", "tasks.soul_shortcut_diagnostic_flow:image_diff"),
    BasicCapability("surface_refresh", "执行 Surface 刷新", "调用现有 Surface 切换/RedrawWindow 刷新能力。", "tasks.soul_shortcut_diagnostic_flow:_refresh_capture_surface"),
    BasicCapability("background_mouse_move", "发送后台鼠标移动", "仅发送 WM_MOUSEMOVE，不执行点击。", "actions.background_input:BackgroundInput.mouse_move"),
    BasicCapability("capture_freshness", "暂未验证通过 验证捕获新鲜度", "验证 Host/WSGAME/Playfield/RightEdge 分层新鲜度。", "tasks.background_capture_freshness:run_background_capture_freshness"),
)


BASIC_CAPABILITY_BY_ID = {item.id: item for item in BASIC_CAPABILITIES}


# The Shortcut diagnostic Flow's declared dependencies. The Flow still owns
# orchestration; this registry only prevents the menu and documentation from
# drifting to a different capability vocabulary.
SHORTCUT_DIAGNOSTIC_CAPABILITY_IDS = (
    "host_capture",
    "game_view_capture",
    "surface_health",
    "scene_coordinate_ocr",
    "shortcut_state_vision",
    "image_diff",
    "surface_refresh",
    "background_mouse_move",
    "capture_freshness",
)


def get_basic_capability(capability_id: str) -> BasicCapability:
    try:
        return BASIC_CAPABILITY_BY_ID[capability_id]
    except KeyError as exc:
        raise KeyError(f"unknown basic capability: {capability_id}") from exc
