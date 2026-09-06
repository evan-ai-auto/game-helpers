# 人工扩展维护区

> **本节给人维护用。**  
> 日常加图标、加状态、加任务流程，只改这里列出的位置；尽量少改 `src/` 里的核心代码。

**当前开发基线：只做 800×600。**  
多分辨率目录已预留；等 800×600 功能全部完成、你再补其它分辨率资产并验证（见 [backlog.md](backlog.md) MULTI-RES）。

写新流程前先看：[capabilities.md](capabilities.md)。  
实机复验：[verification.md](verification.md)（以你本地日志为准）。

---

## 1. 模板 / 状态资产（按分辨率分目录）

推荐布局（已落地）：

```text
data/assets/ui/resolutions/
  800x600/     ← 当前维护
  1024x768/    ← 占位，以后再补
```

运行时用 `tasks.asset_resolution.resolve_resolution_asset(name, client_size)`  
按**当前子窗客户区**选文件夹；缺档直接报错，不会误用其它分辨率。

| 类型 | 800×600 路径 | 怎么扩 |
|---|---|---|
| 道具栏打开态 | `resolutions/800x600/item_panel_open.json` + **`item_panel_open.png`** | **请你上传正式模板替换该 PNG**（见 §1.4） |
| 道具栏切换 | `resolutions/800x600/item_bar_toggle.json` + `item_bar_icon.blob` | 可写 `click_client:[x,y]`；或靠模板 |
| 命魂已领取图标 | 现仍用 `ui/soul_task_claimed_icon.json`（副本在 `resolutions/800x600/`） | 目标分辨率重采 |
| NPC / 场景 | `npcs/`、`scenes/` | 坐标同样建议日后按分辨率分档 |
| 旧路径 | `visual_states/item_panel_open.json`、`ui/item_bar_toggle.json` | **已废弃**，勿再接流程 |

### 1.4 上传道具栏「打开态」800×600 模板

1. 游戏客户区 **800×600**，道具栏**打开**，截一张干净子窗图（或从 `diagnostic/workflow_runs/item_panel/after-*.png` 裁）  
2. 裁一块**稳定 chrome**（推荐底部页签如「加锁」，或标题栏固定字；避免人物头像、背包物品内容）  
3. 覆盖保存为：

```text
data/assets/ui/resolutions/800x600/item_panel_open.png
```

4. 如需改阈值，编辑同目录 `item_panel_open.json` 里 `anchors[0].threshold`（默认 `0.88`）  
5. 跑道具栏流程：关闭时应 `not_detected`，打开时应 `detected`；通过后把 JSON 的 `verification_status` 改为 `verified`，并同步 §1.3 台账  

当前仓库里的 `item_panel_open.png` 是临时裁剪（「加锁」），**以你上传的正式版为准**。

### 1.1 验证状态字段（必填）

| 字段 | 取值 | 含义 |
|---|---|---|
| `verification_status` | `pending` / `verified` / `failed` | 待验证 / 已验证 / 失败 |
| `verified_resolutions` | 如 `["800x600"]` | 仅 verified 时填写 |
| `verification_notes` | 字符串 | 可选说明 |

新资产默认 `pending`。流程优先只用 `verified`（诊断可临时用 pending）。

### 1.2 多分辨率策略（同意的推进方式）

1. **现在**：只实现 + 验收 **800×600**  
2. **资产**：按 `resolutions/{WxH}/` 分目录维护（比单 JSON 里塞多套 variants 更清晰、好对比）  
3. **以后**：你提供 1024×768 等素材 → 放入对应目录 → 单独验证 → 改 `verification_status`  
4. 缺分辨率资产时运行时报错，不静默缩放/挪用

### 1.3 当前资产台账

| 资产 | 路径 | status | 备注 |
|---|---|---|---|
| 命魂已领取图标 | `ui/soul_task_claimed_icon.json` | `verified` | V1；800×600 |
| 道具栏打开态（新） | `resolutions/800x600/item_panel_open.json` + `item_panel_open.png` | `pending` | 临时「加锁」裁剪已就位；**须在 800×600 上 V3 通过后再 verified**（现场曾扫到 1024×768 拒跑） |
| 道具栏切换（新） | `resolutions/800x600/item_bar_toggle.json` | `pending` | `click_client=[469,565]`；同上，等 V3 两轮通过 |
| 道具栏打开态（旧） | `visual_states/item_panel_open.json` | `failed` | 废弃 |
| 道具栏切换（旧） | `ui/item_bar_toggle.json` | `failed` | 废弃 |
| 女娲神使 / 场景 | `npcs/`、`scenes/` | `pending` | 未分分辨率 |

---

## 2. 任务流程定义

| 做什么 | 约定 |
|---|---|
| 流程内容 | 用已验证资产：检测 → 操作 → 再检测 |
| 执行入口 | `python -m game_helpers.tasks.task_workflow_cli` |
| 道具栏坐标 | 默认 `auto`（优先资产 `click_client`）；标定用 `--coord-source manual` |
| 单独采点 | `python -m game_helpers.tasks.manual_coordinate_cli` |

---

## 3. 维护检查清单

- [ ] 放进对应 `resolutions/{WxH}/`
- [ ] 写了 `verification_status`
- [ ] 在该分辨率实机验证过
- [ ] 台账已同步
- [ ] 未提交大图调试截图（除非必要）

---

## 4. 不要放这里的东西

- 核心捕获/点击驱动 → [agent-coding.md](agent-coding.md)
- 暂缓项 → [backlog.md](backlog.md)
