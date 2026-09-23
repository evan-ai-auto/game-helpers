"""Interactive CLI: select character + workflow; run supported diagnosis flows."""
from __future__ import annotations

import argparse

from ..core.window import find_window
from .accounts import scan_game_accounts
from .character_selection import logged_in_accounts, select_character
from .basic_capability_flow import BASIC_CAPABILITIES, run_basic_capability
from .item_panel_flow import run_item_panel_detect_and_toggle
from .soul_shortcut_diagnostic_flow import (
    SHORTCUT_DIAGNOSTIC_SUBTYPES,
    run_soul_shortcut_diagnostic,
)
from .soul_task import SOUL_TASK_BASELINE_SIZE
from .soul_task_coordinate_flow import (
    run_soul_task_coordinate_collection,
    run_soul_task_coordinate_continuous_verification,
)
from .soul_task_detection_coordinate_flow import run_soul_task_detection_coordinate_validation
from .soul_task_flow import run_soul_task_claim_diagnosis
from .workflows import TaskWorkflowRegistry


def _choose_basic_capability() -> str | None:
    print("[基础能力] 请选择基础能力单项测试")
    for option, capability in enumerate(BASIC_CAPABILITIES, start=1):
        print(f"  [{option}] {capability.name} | {capability.description}")
    print("  [0] 返回")
    try:
        choice = int(input("请选择基础能力编号：").strip())
    except (EOFError, ValueError):
        print("[基础能力] 编号无效")
        return None
    if choice == 0:
        return None
    if not 1 <= choice <= len(BASIC_CAPABILITIES):
        print(f"[基础能力] 编号必须在 1 到 {len(BASIC_CAPABILITIES)} 之间")
        return None
    return BASIC_CAPABILITIES[choice - 1].id


def _choose_soul_shortcut_subtype() -> str | None:
    print("[命魂诊断] 请选择子实验")
    for option, (_, name) in enumerate(SHORTCUT_DIAGNOSTIC_SUBTYPES, start=1):
        print(f"  [{option}] {name}")
    print("  [0] 返回")
    try:
        choice = int(input("请选择子实验编号：").strip())
    except (EOFError, ValueError):
        print("[命魂诊断] 子实验编号无效")
        return None
    if choice == 0:
        return None
    if not 1 <= choice <= len(SHORTCUT_DIAGNOSTIC_SUBTYPES):
        print(f"[命魂诊断] 子实验编号必须在 1 到 {len(SHORTCUT_DIAGNOSTIC_SUBTYPES)} 之间")
        return None
    return SHORTCUT_DIAGNOSTIC_SUBTYPES[choice - 1][0]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="选择角色与任务流程（800×600 基线）：命魂领取检测 / 坐标采集 / 快捷图标分层诊断 / 道具栏状态检测与切换。"
    )
    parser.add_argument("title", nargs="?", default="梦幻西游 ONLINE")
    parser.add_argument("--output-dir", default="diagnostic/workflow_runs")
    parser.add_argument(
        "--coord-source",
        default="auto",
        choices=("auto", "manual", "auto_then_manual"),
        help="道具栏流程的点击坐标来源。",
    )
    args = parser.parse_args()

    print("[链路] 1/6 查找游戏主窗口")
    parent = find_window(args.title)
    if parent is None:
        print(f"未找到游戏主窗口: {args.title!r}")
        return 2
    print(f"parent hwnd={parent.hwnd}")

    print("[链路] 2/6 扫描已登录角色")
    scan = scan_game_accounts(parent.hwnd)
    accounts = logged_in_accounts(scan)
    print(f"logged_in characters={len(accounts)}")
    if not accounts:
        print("未发现已登录角色，无法继续。")
        return 3
    for option, account in enumerate(accounts, start=1):
        resolution = account.expected_resolution
        res_text = f"{resolution[0]}x{resolution[1]}" if resolution else "unknown"
        print(f"  [{option}] {account.character_name!r} | 实例=#{account.view_index} | client={res_text} | identity={account.identity!r}")

    print("[链路] 3/6 选择角色")
    try:
        choice = int(input("请选择角色编号：").strip())
    except (EOFError, ValueError):
        print("角色编号无效。")
        return 4
    if not 1 <= choice <= len(accounts):
        print(f"角色编号必须在 1 到 {len(accounts)} 之间。")
        return 4
    selected = select_character(scan, accounts[choice - 1].view_index)
    resolution = selected.account.expected_resolution
    res_text = f"{resolution[0]}x{resolution[1]}" if resolution else "unknown"
    print(f"selected character={selected.character_name!r} view_index={selected.view_index} hwnd={selected.hwnd} client={res_text}")
    if resolution != SOUL_TASK_BASELINE_SIZE:
        print(f"当前角色分辨率不是基线 {SOUL_TASK_BASELINE_SIZE[0]}x{SOUL_TASK_BASELINE_SIZE[1]}，请先统一到 800×600 后再跑本链路（多分辨率后续优化）。")
        return 8

    print("[链路] 4/6 选择任务流程")
    registry = TaskWorkflowRegistry()
    workflows = registry.all()
    for option, workflow in enumerate(workflows, start=1):
        print(f"  [{option}] {workflow.name} | {workflow.description}")
    try:
        workflow_choice = int(input("请选择任务流程编号：").strip())
    except (EOFError, ValueError):
        print("任务流程编号无效。")
        return 5
    if not 1 <= workflow_choice <= len(workflows):
        print(f"任务流程编号必须在 1 到 {len(workflows)} 之间。")
        return 5
    workflow = workflows[workflow_choice - 1]
    print(f"workflow_id={workflow.id} workflow_name={workflow.name}")

    print("[链路] 5/6 执行流程")
    if workflow.id == "minghun_basic_capabilities":
        capability_id = _choose_basic_capability()
        if capability_id is None:
            print("[链路] 6/6 结果")
            print("result=SKIPPED")
            return 0
        print(f"[基础能力] 单项测试={dict((item.id, item.name) for item in BASIC_CAPABILITIES)[capability_id]}")
        print("task_execution_started=True")
        try:
            result = run_basic_capability(
                parent.hwnd,
                selected,
                capability_id,
                f"{args.output_dir}/basic_capabilities/{capability_id}",
            )
        except RuntimeError as exc:
            print(f"[基础能力] 阶段=执行；原因={exc}")
            print("[链路] 6/6 结果")
            print("result=FAILED")
            return 1
        print(f"[基础能力] result={result}")
        print("[链路] 6/6 结果")
        print("result=PASSED")
        return 0

    if workflow.id == "minghun_shortcut_diagnostic":
        subtype = _choose_soul_shortcut_subtype()
        if subtype is None:
            print("[链路] 6/6 结果")
            print("result=SKIPPED")
            return 0
        print(f"[命魂诊断] 子实验={dict(SHORTCUT_DIAGNOSTIC_SUBTYPES)[subtype]}")
        print("task_execution_started=True")
        try:
            run_soul_shortcut_diagnostic(
                parent.hwnd,
                selected,
                subtype=subtype,
                output_dir=f"{args.output_dir}/soul_shortcut_diagnostic",
            )
        except RuntimeError as exc:
            print(f"[命魂诊断] 阶段=执行；原因={exc}；下一步策略=保持生产配置不变并根据诊断报告调整实验")
            print("[链路] 6/6 结果")
            print("result=FAILED")
            return 1
        print("[链路] 6/6 结果")
        print("result=PASSED")
        return 0

    if workflow.id == "minghun_coordinate":
        print("task_execution_started=True")
        run_soul_task_coordinate_collection(parent.hwnd, selected, output_dir=f"{args.output_dir}/soul_task")
        print("[链路] 6/6 结果")
        print("result=PASSED")
        return 0

    if workflow.id == "minghun_coordinate_continuous":
        print("task_execution_started=True")
        run_soul_task_coordinate_continuous_verification(parent.hwnd, selected, output_dir=f"{args.output_dir}/soul_task_continuous")
        print("[链路] 6/6 结果")
        print("result=PASSED")
        return 0

    if workflow.id == "minghun_detection_coordinate":
        print("task_execution_started=True")
        run_soul_task_detection_coordinate_validation(parent.hwnd, selected, output_dir=f"{args.output_dir}/soul_task_detection_coordinate")
        print("[链路] 6/6 结果")
        print("result=PASSED")
        return 0

    if workflow.id == "minghun":
        print("task_execution_started=True")
        result = run_soul_task_claim_diagnosis(parent.hwnd, selected, output_dir=f"{args.output_dir}/soul_task", require_baseline=True)
        print(f"[命魂任务] 客户区：{result.client_size[0]}x{result.client_size[1]}" if result.client_size else "[命魂任务] 客户区：未知")
        print(f"[命魂任务] 领取状态：{result.status.value}")
        if result.observation is not None:
            print(f"[命魂任务] 领取分数：score={result.observation.confidence:.3f}")
        if result.screenshot_path:
            print(f"[命魂任务] 截图：{result.screenshot_path}")
        if result.state_changed is not None:
            print(f"[命魂任务] 状态变化标志：{'是' if result.state_changed else '否'}")
        if result.state_confident is not None:
            print(f"[命魂任务] 状态可信标志：{'是' if result.state_confident else '否'}")
        if result.click_dispatch_success is not None:
            print(f"[命魂任务] 点击发送标志：{'是' if result.click_dispatch_success else '否'}")
        if result.verification_result:
            print(f"[命魂任务] 校验结论：{result.verification_result}")
        print(result.message)
        if result.error:
            print(f"[命魂任务] 错误摘要：{result.error}")
        print("[链路] 6/6 结果")
        return 0 if result.ok else 1

    if workflow.id == "daoju_panel":
        print("task_execution_started=True")
        result = run_item_panel_detect_and_toggle(parent.hwnd, selected, output_dir=f"{args.output_dir}/item_panel", require_baseline=True, coord_source=args.coord_source)
        if result.before is not None:
            print(f"item_panel_before_open={result.before.open}")
        if result.after is not None:
            print(f"item_panel_after_open={result.after.open}")
        print(f"toggled={result.toggled}")
        print(f"toggle_verified={result.toggle_verified}")
        print(f"coord_source_requested={result.coord_source_requested}")
        print(f"coord_source_used={result.coord_source_used}")
        print(f"resolution_key={result.resolution_key}")
        print(f"click_client={result.click_client}")
        print(f"icon_match_score={result.icon_match_score}")
        print(f"foreground_unchanged={result.foreground_unchanged}")
        print(f"restored_surface={result.restored_surface}")
        print(f"restored_tab={result.restored_tab}")
        print(result.message)
        if result.error:
            print(f"error={result.error}")
        print("[链路] 6/6 结果")
        return 0 if result.ok else 1

    print(f"「{workflow.name}」尚未实现执行。")
    print("task_execution_started=False")
    print("result=SKIPPED")
    return 9


if __name__ == "__main__":
    raise SystemExit(main())
