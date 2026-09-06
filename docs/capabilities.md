# 已验证可复用能力（800×600 最小链路）

> 来自「发现窗口 → 选角色 → 命魂领取状态检测」实机通过的能力点。  
> **写新流程时优先复用这里的 API**，不要再复制一份探针逻辑。

基线：子窗 **800×600**；默认纯后台。

---

## 能力清单 → 稳定入口

| # | 能力 | 稳定入口 | 说明 |
|---|---|---|---|
| 1 | 发现游戏窗口 | `core.window.find_window` | 按标题找主窗 |
| 1 | 扫描角色/登录信息 | `tasks.accounts.scan_game_accounts` | 含登录态、角色名、client 尺寸 |
| 1 | 筛已登录 / 选角色 | `tasks.character_selection.logged_in_accounts` / `select_character` | 按 view_index 选实例 |
| 3+4 | 后台切角色（Surface+Tab） | `tasks.character_selection.sync_selected_character` | 不抢焦点；失败则抛错 |
| 3 | 后台运行上下文（保存/恢复） | `tasks.background_context.BackgroundRunGuard` | 记录前台+视图，结束后恢复 |
| 4 | 多子窗切换原语 | `core.view_manager.GameViewManager.switch_surface_to` / `switch_to` | `activate_before_switch=False` |
| 2 | 后台点击 | `actions.background_input.BackgroundInput.click_sync` / `click_and_verify` | 子窗客户区坐标 |
| 6 | 按分辨率解析 UI 资产 | `tasks.asset_resolution.resolve_resolution_asset` | `resolutions/{WxH}/`；缺档报错 |
| 6 | 人工协助采坐标（F8） | `tasks.manual_coordinate.collect_client_coordinate` | **标定专用** |
| 6 | 采坐标 CLI | `python -m game_helpers.tasks.manual_coordinate_cli` | 不写回文件 |
| 5 | 道具栏开/关检测 | `resolutions/800x600/item_panel_open.json` | 新「加锁」模板；`pending` 待你确认 |
| 5+2 | 道具栏检测+反转 | `item_panel_flow` + `item_bar_toggle.json` | 默认用 `click_client`；`--coord-source` 可选 |
| 2+5 | 父窗截图并裁子窗 | `tasks.verification_session.VerificationSession.capture_frame` | WGC 抓父窗再 crop |
| 5 | 命魂面板折叠检测 | `tasks.soul_task.detect_soul_task_panel_collapsed` | 基于子窗帧 |
| 5 | 命魂已领取图标检测 | `tasks.soul_task.detect_soul_task_claimed_icon` | 模板资产见 maintain |
| 6 | 命魂 UI 坐标/模板配置 | `tasks.soul_task.DEFAULT_SOUL_TASK_UI` + `data/assets/ui/` | 人工维护资产 |
| 7 | 流程目录 | `tasks.workflows.TaskWorkflowRegistry` | 选流程元数据 |
| 7 | 命魂最小闭环编排 | `tasks.soul_task_flow.run_soul_task_claim_diagnosis` | 组合以上能力 |
| 7 | 人机入口 | `python -m game_helpers.tasks.task_workflow_cli` | 选角色+流程并执行诊断 |

---

## 推荐组合方式（新流程）

```text
find_window
  → scan_game_accounts / select_character
  → BackgroundRunGuard.begin(manager)
  → sync_selected_character
  → VerificationSession.capture_frame
  → 状态检测 / BackgroundInput 点击（按需）
  → guard.finish()  # 恢复视图 + 检查前台未变
```

命魂领取状态检测已封装为 `run_soul_task_claim_diagnosis`，一般直接调用即可。

---

## 不要当稳定能力用的

| 项 | 原因 |
|---|---|
| 前台 Ctrl+Tab / `activate_before_switch=True` | 违反纯后台约束 |
| `SetWindowPos` 硬扩宿主 | 游戏常锁死；多分辨率暂缓 |
| 各未整理的 `*_probe` 临时代码 | 诊断用；采坐标请改用 `manual_coordinate` |
| 师门/自定义流程执行 | 尚未实现，仅可选目录项 |

---

## 人工维护关系

- 改图标/模板/坐标资产 → [maintain.md](maintain.md)
- 改产品需求 → [requirements.md](requirements.md)
- Agent 写代码约定 → [agent-coding.md](agent-coding.md)
