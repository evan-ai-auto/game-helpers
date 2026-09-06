# Agent 编码约定

先读 [requirements.md](requirements.md)。复用已验证能力看 [capabilities.md](capabilities.md)。人工加资产/流程看 [maintain.md](maintain.md)。

## 必守

1. 当前按 **800×600** 基线实现与验收；多分辨率见 backlog，勿顺手扩 scope。
2. 纯后台：`activate_before_switch=False`；禁止抢焦点 / 前台 Ctrl+Tab（除非需求写明）。
3. 根目录不新增散落文件；说明类文字放 `docs/`。
4. 代码在 `src/game_helpers/`；探针入口保持 `python -m game_helpers.tasks.*_probe`。
5. 资产与流程走可维护目录，勿把模板路径写死难扩展。
6. **新流程优先组合 [capabilities.md](capabilities.md) 里的稳定入口**，不要从探针里再抄一份。
7. 未请勿 commit；发现做不了的记 [backlog.md](backlog.md)。

## 代码落点（短）

| 需求 | 优先看 |
|---|---|
| 已验证能力总表 | `docs/capabilities.md` |
| 窗口 / 子窗 / 切视图 | `core/` |
| 截图 | `capture/` + `tasks/verification_session.py` |
| 后台上下文恢复 | `tasks/background_context.py` |
| 角色 / 状态 / 流程 | `tasks/` |
| 命魂最小闭环 | `tasks/soul_task_flow.py`、`task_workflow_cli.py` |
| 点击 | `actions/background_input.py` |
| 图标与状态资产 | `data/assets/`（人工维护） |

切角色：先 `switch_surface_to`，再后台 `switch_to`，并确认前台未变（或用 `sync_selected_character` / `BackgroundRunGuard`）。
