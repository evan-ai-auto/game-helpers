# 人工复验清单

**验收节奏**：你本地执行并把控制台日志/截图结论反馈给 Agent → Agent 分析改代码 → 你再验。  
Agent **不**长时间挂机等待游戏前台交互或未满足条件的循环。

基线：子窗 **800×600**；纯后台（不要把游戏点到最前）。  
资产是否可用以 JSON 的 `verification_status` 为准，台账见 [maintain.md](maintain.md)。

---

## 立刻要做（最短路径）

1. 客户区保持 **800×600**（已确认可扫到）。
2. **退出战斗 / 关闭自动战斗与挡脸对话框**，站到空闲场景（不要在排队入队、剧情框、战斗回合中验 V3）。
3. （可选）覆盖正式打开态模板：`data/assets/ui/resolutions/800x600/item_panel_open.png`。
4. 再跑 V3（关→开、开→关各一轮），贴完整日志。
5. 通过后告诉 Agent：资产标 `verified`，并确认 V2。

```powershell
.\.venv\Scripts\python.exe -m game_helpers.tasks.task_workflow_cli
```

**Agent 最新冒烟（800×600）**

- 基线分辨率检查：**通过**
- `coord_source=stored_click` / 模板中心点击 / `click_sync` / `Alt+E`：**均未稳定打开道具栏**
- 截图显示当时有 **自动战斗**，且点击后进入 **战斗/对话** 态；此状态下 V3 不可信
- 资产保持 `pending`，**未标 verified**
- V2 此前冒烟仍为 PASSED（与道具栏无关）

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
| Agent 冒烟 | **再确认通过**（`surfaces_distinct=True`，`foreground_unchanged=True`，`result=PASSED`） |
| 你的确认 | 待你过目截图后确认 |

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

截图：`diagnostic/instance_surfaces_verify/surface-*.png`

---

## V3 — 道具栏状态检测 + 反向切换（待你确认）

| 项 | 内容 |
|---|---|
| 覆盖能力 | 1 选角 · 2 后台点击 · 5 打开态检测 · 存储 click_client · 7 流程 |
| Agent | 资产与流程已接好；800×600 冒烟因**战斗/自动战斗态**未稳定打开道具栏 |
| 你的确认 | 待确认（须空闲非战斗态复验） |

**阻塞**

- ~~客户区 1024×768~~：已改回 800×600。  
- **当前阻塞**：角色处于自动战斗 / 战斗或剧情对话框时，后台点击道具栏不可靠；须空闲态再验。  
- 打开态 / 切换资产仍为 `verification_status=pending`。

**前置条件**

- 客户区 **800×600**
- 打开态模板：`resolutions/800x600/item_panel_open.png`（可先用临时裁剪，建议你再上传正式版）
- 切换坐标默认：`click_client=[469,565]`（`coord_source=stored_click`）
- 执行期间游戏保持**后台**

**推荐复验**

```powershell
.\.venv\Scripts\python.exe -m game_helpers.tasks.task_workflow_cli
```

选角色 → 选「道具栏状态检测」。关→开、开→关各一轮；跑前/跑后肉眼确认。

仍要人工采点：`--coord-source manual`（会临时前台，属预期）。

**通过标准**

- `resolution_key=800x600`
- before/after 与肉眼一致且相反
- `result=PASSED`
- `coord_source_used=stored_click`（或 `manual`）
- 自动段尽量 `foreground_unchanged=True`

**请反馈**：完整控制台日志。

---

## 下一项预告（V3 你确认 + V2 过目后再做）

仍锁 **800×600 / 纯后台**，不要展开 MULTI-RES。优先二选一：

1. **命魂未领取 → 后续步骤骨架**（可不自动点 NPC，先做路由与异常提示）
2. **再做一个可复用 UI 状态**（同道具栏模式：`resolutions/800x600` 资产 → 检测 → 可选点击）

实现时继续组合 [capabilities.md](capabilities.md) 稳定入口，勿从 `*_probe` 再抄一份。
