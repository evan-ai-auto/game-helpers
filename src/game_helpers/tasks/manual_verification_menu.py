"""Interactive menu for independently verifying task flows."""
from __future__ import annotations
import sys
from .soul_task_toggle_auto_probe import main as verify_soul_toggle
from .background_item_panel_open_probe import main as verify_item_panel

OPTIONS = {
    "1": ("命魂任务面板：自动识别并切换折叠/展开", verify_soul_toggle),
    "2": ("道具栏：验证当前开关状态并执行反向切换", verify_item_panel),
}

def main() -> int:
    title = sys.argv[1] if len(sys.argv) > 1 else "梦幻西游 ONLINE"
    print("\n可选手动验证流程：")
    for key, (label, _) in OPTIONS.items(): print(f"  {key}. {label}")
    print("  q. 退出")
    choice = input("请选择验证流程：").strip().lower()
    if choice == "q": return 0
    entry = OPTIONS.get(choice)
    if entry is None: print("无效选项。"); return 1
    # The selected probe may still ask for character selection; it must not ask
    # for a desired UI direction in automatic soul-toggle mode.
    sys.argv = [sys.argv[0], title]
    return entry[1]()

if __name__ == "__main__": raise SystemExit(main())
