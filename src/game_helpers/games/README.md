# games

## 当前定位

具体游戏适配层。第一款真实接入游戏为 **梦幻西游**。

## Game Agent Brain

当前链路已经从单一“命魂任务视觉闭环”升级为长期 Agent Brain：

```text
Capture / WGC
    ↓
Vision Observation
    ├─ UI 状态
    ├─ 场景识别（OCR/显式视觉证据接口）
    └─ NPC / 传送点视觉目标接口
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

## 已实现

- `core.agent_brain`：通用 GoalPlanner、AgentMemory、RecoveryPolicy。
- `games/menghuanxiyou/scene.py`：场景识别器，优先使用显式视觉/OCR证据，不把未知场景猜成已知场景。
- `games/menghuanxiyou/navigation.py`：从场景知识构建传送点/导航图。
- `games/menghuanxiyou/recovery.py`：retry → reacquire → abort 的有界恢复策略。
- `DreamAgent`：支持 `soul_task` 和 `transport:<target_id>` 两类目标，并通过 Runtime 回收执行/验证结果。
- `AgentRuntime`：每轮完成 post-action recapture，并把 VerificationResult 回传给 Agent Memory。

## 安全动作原则

导航和 NPC/传送点交互只允许使用当前 Observation 中**视觉确认的目标**。地图 JSON 中的坐标属于知识，不会自动变成盲点点击坐标。

## 当前限制

现有仓库的场景/NPC 视觉资产仍不完整，因此“场景识别 → NPC/传送点导航 → 传送 → 状态变化验证”已经有 Brain、状态机、导航图和恢复机制，但不能宣称已经完成真实 Windows 游戏实机验收。下一步应补齐真实游戏截图/目标模板（或接入 OCR/VLM Vision Adapter），再进行端到端验收。
