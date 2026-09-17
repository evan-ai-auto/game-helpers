"""命魂任务人工可读日志格式化。

约定：一条日志只表达一个事实；坐标用 client=(x, y)；分数用 score=0.856；
禁止把枚举内部表示、长元组或 Python 对象直接打给操作者。
"""
from __future__ import annotations

from .soul_task_models import SoulTaskPanelObservation, SoulTaskStatus


LOG_PREFIX = "[命魂任务]"


def format_client(point: tuple[int, int] | None) -> str:
    if point is None:
        return "无"
    return f"client=({point[0]}, {point[1]})"


def format_xy(point: tuple[int, int] | None) -> str:
    if point is None:
        return "无"
    return f"({point[0]}, {point[1]})"


def format_score(score: float | None) -> str:
    if score is None:
        return "无"
    return f"score={float(score):.3f}"


def format_bool_cn(ok: bool) -> str:
    return "成功" if ok else "失败"


def panel_state_text(collapsed: bool | None) -> str:
    if collapsed is True:
        return "折叠"
    if collapsed is False:
        return "已展开"
    return "未知"


def claim_status_text(status: SoulTaskStatus) -> str:
    mapping = {
        SoulTaskStatus.CLAIMED: "已领取",
        SoulTaskStatus.NOT_CLAIMED: "未领取",
        SoulTaskStatus.UNKNOWN: "未知",
        SoulTaskStatus.CLAIM_FAILED: "领取失败",
    }
    return mapping.get(status, "未知")


def log_soul(message: str) -> None:
    print(f"{LOG_PREFIX} {message}")


def visual_match_point(panel: SoulTaskPanelObservation) -> tuple[int, int] | None:
    """Prefer the visual match center; fall back to match origin."""
    if panel.click_location is not None:
        return panel.click_location
    return panel.match_location


def log_panel_state(stage: str, panel: SoulTaskPanelObservation) -> None:
    log_soul(f"{stage}状态：{panel_state_text(panel.collapsed)}")


def log_panel_evidence(stage: str, panel: SoulTaskPanelObservation) -> None:
    template = panel.matched_template or "无"
    score_value = panel.match_score if panel.matched_template is not None else None
    log_soul(
        f"{stage}证据：模板={template}；{format_score(score_value)}；"
        f"匹配位置={format_xy(visual_match_point(panel))}"
    )


def log_expand_failure(
    *,
    reason: str,
    click: tuple[int, int] | None,
    click_dispatch_success: bool,
    panel_after: SoulTaskPanelObservation,
    strategy: str,
) -> None:
    log_soul("展开结果：失败")
    log_soul(f"失败原因：{reason}")
    log_soul(f"点击位置：{format_client(click)}")
    log_soul(f"点击发送：{format_bool_cn(click_dispatch_success)}")
    best = panel_after.matched_template or "无"
    log_soul(f"点击后最佳模板：{best}；{format_score(panel_after.match_score if panel_after.matched_template else None)}")
    second = panel_after.second_template or "无"
    second_score = panel_after.second_score if panel_after.second_template is not None else None
    log_soul(f"点击后次佳模板：{second}；{format_score(second_score)}")
    log_soul(f"处理策略：{strategy}")
