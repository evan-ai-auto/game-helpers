# game_helpers 总览

Windows 游戏 GUI 自动化 / GUI Agent 核心包。当前基线：**子窗 800×600**、默认**纯后台**（不抢前台）。

产品与验收文档见仓库根目录 [`docs/`](../../docs/README.md)。

---

## 架构总览图

```text
                    ┌─────────────────────────────────────┐
                    │  docs / data/assets（人工维护资产）   │
                    └─────────────────┬───────────────────┘
                                      │
┌──────────────┐   ┌──────────────┐   ▼   ┌──────────────┐   ┌──────────────┐
│   accounts   │   │    games     │       │    tasks     │   │    agent     │
│  账号扩展层   │   │  游戏适配层   │       │  工作流/编排  │   │  决策规划层   │
└──────┬───────┘   └──────┬───────┘       └──────┬───────┘   └──────┬───────┘
       │                  │                      │                  │
       └──────────────────┴──────────┬───────────┴──────────────────┘
                                     ▼
              ┌──────────────────────────────────────────┐
              │                 core                       │
              │     窗口 / 视图 / Tab·Surface / 会话模型      │
              └───────────────┬──────────────────────────┘
                              │
         ┌────────────────────┼────────────────────┐
         ▼                    ▼                    ▼
┌────────────────┐   ┌────────────────┐   ┌────────────────┐
│    capture     │   │     vision     │   │     state      │
│   截图 / 帧     │──▶│  感知 / 匹配    │──▶│  结构化状态     │
└────────────────┘   └────────────────┘   └────────┬───────┘
                                                   │
                                                   ▼
                                          ┌────────────────┐
                                          │    actions     │
                                          │  后台键鼠执行   │
                                          └────────────────┘
```

主链路（已落地的编排习惯）：

```text
find_window
  → scan / select character
  → BackgroundRunGuard + sync_selected_character
  → VerificationSession.capture_frame
  → visual_state / soul_task 检测 或 BackgroundInput 点击
  → guard.finish()
```

稳定入口表见 [`docs/capabilities.md`](../../docs/capabilities.md)。

---

## 子目录一览

| 目录 | 定位（摘要） | 说明 |
|---|---|---|
| [core/](core/README.md) | 基础抽象：窗口、视图、会话、模型 | Platform → **Core** → Vision/State/Agent |
| [capture/](capture/README.md) | 输入采集：截图、WGC、帧模型 | Window → **Capture** → Vision |
| [actions/](actions/README.md) | 动作执行：后台鼠标/键盘与验证接口 | Agent → **Action** → Platform |
| [tasks/](tasks/README.md) | 工作流：选角、状态检测、流程 CLI、探针 | Planner → **Task** → Action |
| [accounts/](accounts/README.md) | 应用层账号能力（偏扩展） | Game Adapter / Extension |
| [vision/](vision/README.md) | 视觉理解：检测 / OCR / 匹配（规划层） | Capture → **Vision** → State |
| [state/](state/README.md) | 游戏状态模型（规划层） | Vision → **State** → Agent |
| [agent/](agent/README.md) | AI 决策：规划 / 记忆 / 恢复（规划层） | State → **Agent** → Action |
| [games/](games/README.md) | 具体游戏适配（规划层） | Core → **Game Adapter** |

各目录的「当前职责 / 不应该包含 / 后续方向」以对应 `README.md` 为准；本文件只做总览索引。

---

## 实现现状（简）

| 层 | 现状 |
|---|---|
| core / capture / actions / tasks | **已有大量可运行代码**（窗口发现、后台切 Surface/Tab、WGC 截图、后台点击、命魂/道具栏诊断流程等） |
| vision / state / agent / games | **以架构说明为主**，能力大多仍落在 `tasks` + `data/assets` 的实用路径上，后续再分层迁入 |

---

## 常用入口

```powershell
# 选角色 + 选流程（命魂 / 道具栏等）
.\.venv\Scripts\python.exe -m game_helpers.tasks.task_workflow_cli

# 多子窗 Surface 区分验证
.\.venv\Scripts\python.exe -m game_helpers.tasks.instance_surface_cli
```

人工复验步骤：[`docs/verification.md`](../../docs/verification.md)。  
资产维护：[`docs/maintain.md`](../../docs/maintain.md)。
