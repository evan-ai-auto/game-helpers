# games

## 当前定位

具体游戏适配层。第一款真实接入游戏为 **梦幻西游**。

## Game Agent Brain

当前链路已经从单一“命魂任务视觉闭环”升级为长期 Agent Brain：

```text
Game Screenshot
       │
       ├───────────────┐
       ↓               ↓
Global Vision       ROI Vision
       │               │
场景/角色/UI状态     OCR/数字/小目标
       │               │
       └───────┬───────┘
               ↓
      Semantic Observation
               ↓
        DreamGameState
               ↓
          GoalPlanner
       ├─ 场景确认
       ├─ 目标理解
       ├─ 导航
       ├─ 交互
       └─ 状态变化验证
               ↓
      Action → Result → Verification
               ↑                    │
               └── Memory / Recovery
```

## Vision 原则

**不要过度依赖模板。** 模板匹配只是小范围 UI 的兼容/兜底能力，不作为场景、玩家位置或经济状态的主要真值来源。

### 全局视觉

负责高层语义：

- 当前是否在游戏
- 当前场景
- 战斗 / 非战斗
- 对话 / 非对话
- 地图 / 副本
- UI 状态
- 是否发生传送

### ROI 视觉

负责高价值的小区域，并通过配置管理坐标：

- `player_location`：左上角场景 + 地图坐标
- `economy`：身上现金
- `task`：任务文本/状态
- `combat`：自动战斗/战斗状态
- `dialogue`：对话框/NPC 对话选项

ROI 定义位于 `data/assets/ui/vision_regions.json`。区域可以按参考分辨率自动缩放，最终分辨率以真实资产验证结果为准。

## 已实现

- `core.agent_brain`：通用 GoalPlanner、AgentMemory、RecoveryPolicy。
- `vision/regions.py`：可配置、可缩放 ROI 注册表。
- `vision/ocr.py`：可插拔 OCR 契约，以及场景坐标/数字解析器。
- `games/menghuanxiyou/perception.py`：全局视觉 + ROI OCR → Semantic Observation；保留模板匹配作为可选 fallback。
- `games/menghuanxiyou/scene.py`：场景识别器，优先使用显式视觉/OCR证据，不把未知场景猜成已知场景。
- `games/menghuanxiyou/navigation.py`：从场景知识构建传送点/导航图。
- `games/menghuanxiyou/recovery.py`：retry → reacquire → abort 的有界恢复策略。
- `DreamGameState`：保存场景、玩家动态坐标、现金及对应 confidence。
- `DreamAgent`：支持 `soul_task` 和 `transport:<target_id>` 两类目标，并通过 Runtime 回收执行/验证结果。
- `AgentRuntime`：每轮完成 post-action recapture，并把 VerificationResult 回传给 Agent Memory。

## 安全动作原则

导航和 NPC/传送点交互只允许使用当前 Observation 中**视觉确认的目标**。地图 JSON 中的坐标属于知识，不会自动变成盲点点击坐标；玩家 OCR 坐标也属于状态输入，不能直接当成屏幕点击坐标。

## 当前限制

当前 OCR backend 仍是可插拔契约，仓库没有绑定具体 OCR 引擎；真实场景、NPC、战斗、对话等全局视觉理解仍需要实际 Vision Adapter 和真实机器验证。现有模板资产继续作为旧任务 UI 的 fallback。
