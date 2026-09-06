# 人工复验清单

**验收节奏**：你本地执行并把控制台日志/截图结论反馈给 Agent → Agent 分析改代码 → 你再验。  
Agent **不**长时间挂机等待游戏前台交互或未满足条件的循环。

基线：子窗 **800×600**；纯后台（不要把游戏点到最前）。  
资产是否可用以 JSON 的 `verification_status` 为准，台账见 [maintain.md](maintain.md)。

---

## V1 — 命魂领取状态检测（最小闭环）

| 项 | 内容 |
|---|---|
| 覆盖能力 | 1 窗口/角色 · 3 纯后台 · 4 切子窗 · 5 状态检测 · 7 流程入口 |
| Agent 冒烟 | 已通过（`result=PASSED`，`not_claimed`，前台未变） |
| 你的确认 | 已确认通过 |

**前置条件**

- 游戏「梦幻西游 ONLINE」已开
- 至少 1 个已登录角色，客户区 **800×600**
- 在项目根目录，已激活 `.venv`

**执行指令**

```powershell
.\.venv\Scripts\python.exe -m game_helpers.tasks.task_workflow_cli
```

**操作步骤**

1. 按提示输入已登录角色编号（如 `1`）
2. 选择任务流程 `1`（命魂任务）
3. 看控制台输出，不要切换游戏到前台

**通过标准**

- `client_size=(800, 600)`（或打印的 client 为 800x600）
- `soul_task_status` 为 `claimed` / `not_claimed` / `unknown` 之一
- `foreground_unchanged=True`
- `restored_surface=True`、`restored_tab=True`
- `result=PASSED`（检测逻辑跑完且上下文恢复成功）

---

## V2 — 多子窗口后台切换

| 项 | 内容 |
|---|---|
| 覆盖能力 | 3 纯后台 · 4 多子窗口切换 · 父窗截图区分实例 |
| Agent 冒烟 | 已通过 |
| 你的确认 | 待确认（或已确认后改这里） |

**前置条件**

- 游戏主窗口已开
- **至少 2 个** WSGAME 子实例（多开账号页即可；不必都登录）
- 项目根目录 + `.venv`
- 复验期间尽量不要手动点游戏窗抢焦点

**执行指令**

```powershell
.\.venv\Scripts\python.exe -m game_helpers.tasks.instance_surface_cli --output-dir diagnostic/instance_surfaces_verify
```

（无交互，直接跑完。）

**通过标准**

- `surfaces_distinct=True`
- `foreground_unchanged=True`
- `restored=True`
- `result=PASSED`

---

## V3 — 道具栏状态检测 + 反向切换（待你确认）

| 项 | 内容 |
|---|---|
| 覆盖能力 | 1 选角 · 2 后台点击 · 5 打开态检测（800×600 新模板）· 存储 click_client · 7 流程 |
| Agent | 已换 `resolutions/800x600` 资产；打开态 offline 可区分 before/after |
| 你的确认 | **请再跑一轮**（建议先默认 `auto`，用已存 `(469,565)`） |

**已知问题修正**

1. **抢前台**：Surface 切换改为 `SetWindowPos(SWP_NOACTIVATE)`；`BackgroundRunGuard` 结束时若前台被抢走会尝试恢复。默认 `--coord-source auto` **不会**为采点拉前台（只有 `manual` / 回退才会）。  
2. **打开态模板**：请把正式 800×600 图覆盖到  
   `data/assets/ui/resolutions/800x600/item_panel_open.png`（步骤见 [maintain.md](maintain.md) §1.4）。

**推荐复验（无需再 F8）**

```powershell
.\.venv\Scripts\python.exe -m game_helpers.tasks.task_workflow_cli
```

选角色 → 选道具栏。默认 `auto` 会用资产里的 `click_client=[469,565]`。

关→开、开→关各一轮；跑前/跑后肉眼确认。

仍要人工采点时加：`--coord-source manual`

**通过标准**

- `resolution_key=800x600`  
- before/after 与肉眼一致且相反  
- `result=PASSED`  
- `coord_source_used=stored_click`（默认）或 `manual`  

**请反馈**：完整控制台日志。---

## 下一项预告（V3 你确认后再做）

预计继续其它状态检测或任务步骤能力。
