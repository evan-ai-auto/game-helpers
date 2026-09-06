# 人工复验清单

Agent 先实机冒烟，再把本页步骤给你；**你本地确认通过后**，我们再开下一项。

基线：子窗 **800×600**；纯后台（不要把游戏点到最前）。

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

## V2 — 多子窗口后台切换（待你确认）

| 项 | 内容 |
|---|---|
| 覆盖能力 | 3 纯后台 · 4 多子窗口切换 · 父窗截图区分实例 |
| Agent 冒烟 | **已通过**（6/6 实例画面可区分，前台未变，已恢复） |
| 你的确认 | 待确认 |

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

**操作步骤**

1. 执行上面命令
2. 观察控制台：是否逐个 `Surface #N` 且 `foreground` 不变
3. 可选：打开 `diagnostic/instance_surfaces_verify/surface-*.png`，看各实例画面是否不同
4. 结束后看游戏是否回到原先可见页签/画面（命令会恢复 original surface）

**通过标准**

- `WSGAME instances` ≥ 2
- 每个 `Surface #N: visible_surface=N`
- `unique_surface_frames` 等于实例数（或 `surfaces_distinct=True`）
- `foreground_unchanged=True`
- `restored=True`
- `result=PASSED`

**失败时请告诉我**

- 完整控制台尾部（含 `result=`）
- 当时前台窗口是否被切到游戏
- `instances` 数量

---

## 下一项预告（V2 你确认后再做）

预计 **V3 — 后台选角同步（Surface+Tab）**：`character_selection_cli`（需交互选角色）。
