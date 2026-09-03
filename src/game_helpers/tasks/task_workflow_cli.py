"""Interactive MVP-4 CLI: select a character and a task workflow only."""

from __future__ import annotations

import argparse

from ..core.window import find_window
from .accounts import scan_game_accounts
from .character_selection import logged_in_accounts, select_character
from .diagnosis import CharacterSelection
from .workflows import TaskWorkflowRegistry


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Select a 梦幻西游 character and task workflow without executing the task."
    )
    parser.add_argument("title", nargs="?", default="梦幻西游 ONLINE")
    args = parser.parse_args()

    print("[验证] 1/6 查找游戏主窗口")
    parent = find_window(args.title)
    if parent is None:
        print(f"parent window not found: {args.title!r}")
        return 2
    print(f"parent hwnd={parent.hwnd}")

    print("[验证] 2/6 扫描已登录角色")
    scan = scan_game_accounts(parent.hwnd)
    accounts = logged_in_accounts(scan)
    print(f"logged_in characters={len(accounts)}")
    if not accounts:
        print("未发现已登录角色，无法创建任务诊断请求。")
        return 3
    for option, account in enumerate(accounts, start=1):
        print(
            f"  [{option}] {account.character_name!r} | "
            f"实例=#{account.view_index} | identity={account.identity!r}"
        )

    print("[验证] 3/6 选择角色")
    try:
        choice = int(input("请选择角色编号：").strip())
    except (EOFError, ValueError):
        print("角色编号无效。")
        return 4
    if not 1 <= choice <= len(accounts):
        print(f"角色编号必须在 1 到 {len(accounts)} 之间。")
        return 4
    selected = select_character(scan, accounts[choice - 1].view_index)
    selection = CharacterSelection(
        character_name=selected.character_name,
        view_index=selected.view_index,
        hwnd=selected.hwnd,
    )
    print(
        f"selected character={selection.character_name!r} "
        f"view_index={selection.view_index} hwnd={selection.hwnd}"
    )

    print("[验证] 4/6 选择任务流程名称")
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

    print("[验证] 5/6 生成 TaskDiagnosisRequest")
    print(f"character={selection.character_name}")
    print(f"view_index={selection.view_index}")
    print(f"hwnd={selection.hwnd}")
    print(f"workflow_id={workflow.id}")
    print(f"workflow_name={workflow.name}")
    print("diagnosis_only=True")
    print("task_execution_started=False")

    print("[验证] 6/6 结果")
    print("result=PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
