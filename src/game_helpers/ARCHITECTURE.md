# game_helpers 架构总览

> 本文描述 `src/game_helpers` 的实际依赖边界。游戏是第一个应用场景，长期目标是可复用的 GUI Agent Core。

## 1. 整体架构

```text
Platform Layer
    ↓
GUI Agent Core
    ↓
Capture / Actions
    ↓
Vision → State → Agent → Runtime
                     ↑        ↓
               Game Adapter  Verify
                     ↑        ↓
                 Game Adapter ← Capture
```

关键原则：**Core 是契约和基础模型，不是 Windows 实现的容器。** Windows API、输入投递和宿主 View 切换分别由 `platform/windows/` 与 `runtime/` 承担。

## 2. Agent 数据闭环

```text
Capture / WGC
    ↓
FrameLike
    ↓
Observation
    ↓
Vision + Game Adapter
    ↓
GameState
    ↓
Agent
    ↓
AgentDecision
    ↓
Actions Executor
    ↓
ActionResult
    ↓
下一帧 Capture
    ↓
Observation → GameState
    ↓
VerificationResult
    └──────────────→ 下一轮 Agent
```

对应实现集中在 `core/agent_protocol.py` 与 `runtime/agent_runtime.py`。

| 数据对象 | 作用 |
|---|---|
| `FrameLike` | Capture 输出给上层所需的最小帧契约 |
| `Observation` | 将一帧及其视觉/文本结果规范化为 Agent 输入 |
| `GameState` | 当前可消费的结构化游戏状态 |
| `AgentDecision` | Planner/Agent 输出的动作序列、置信度和解释信息 |
| `Action` | 可执行的原子动作 |
| `ActionResult` | 动作执行状态、耗时、错误和执行元数据 |
| `VerificationResult` | 使用动作后的新 Observation/State 判断是否达到预期 |

这套协议刻意不携带具体游戏类型或具体 AI SDK，规则 Agent、LLM Agent、视觉模型 Agent 可以共享同一 Runtime 数据面。

## 3. AI Game Agent Runtime

`runtime/agent_runtime.py` 现在提供真正的单步闭环：

1. 从 `capture()` 获取当前 `Frame`。
2. `ObservationBuilder` 将 Frame 变成 `Observation`。
3. `GameAdapter` 将 Observation 变成 `GameState`。
4. `Agent.decide()` 产生 `AgentDecision`。
5. `ActionExecutor` 执行每个 `Action` 并记录 `ActionResult`。
6. **执行后重新 Capture**，生成下一份 `Observation` / `GameState`。
7. `Verifier` 对比动作结果与动作后的 State，产出 `VerificationResult`。
8. Runtime 保存验证后的 State，并进入下一轮。

`BackgroundGameSession.build_agent_runtime()` 将现有 Windows + WGC Session 直接绑定到该 Runtime，因此真实运行路径为：

```text
BackgroundGameSession
        ↓
WindowsGraphicsCapture
        ↓
AgentRuntime
        ↓
Vision / Game Adapter
        ↓
Agent
        ↓
ActionExecutor → platform/windows input
        ↓
WindowsGraphicsCapture
        ↺
```

Runtime 的 `ObservationBuilder`、`GameAdapter`、`Agent`、`Verifier` 都是可注入协议；默认实现只用于启动/测试，不冒充具体游戏 AI。

## 4. 模块职责

| 模块 | 职责 | 状态 |
|---|---|---|
| `core/` | 通用数据契约、几何、GameView、Surface；Agent 数据协议 | 已建立 |
| `platform/windows/` | Win32 window / child / tab / desktop input / background input | 已迁移 |
| `capture/` | Screen / PrintWindow / WGC 等 Frame 获取 | 已有实现 |
| `actions/` | ActionExecutor 与动作执行 | 已接入 Runtime |
| `runtime/` | Session、View switching、Agent closed loop | **已建立** |
| `vision/` | 从 Frame 提取结构化视觉信息 | 通过 `ObservationBuilder` 接入点待填充 |
| `state/` | 保存/演进 Agent 可消费的结构化状态 | 通过 `GameAdapter` 接入点待填充 |
| `agent/` | 规划、策略、恢复、记忆 | 通过 `Agent` 接入点待填充 |
| `games/` | 第一款游戏的专属适配 | 通过 `GameAdapter` 接入点待填充 |
| `tasks/` | Agent 工作流与高层任务 | 待 Agent 化 |

## 5. 依赖边界

```text
Capture ──→ Observation ──→ State ──→ Agent ──→ Action
                                                  ↓
                                             ActionResult
                                                  ↓
                                        next Capture / State
                                                  ↓
                                          VerificationResult
                                                  ↓
                                               Agent
```

实际边界：

1. `core/` 不依赖 `capture.models`、`actions`、`agent` 或具体游戏。
2. `core/agent_protocol.py` 只依赖 Core 自身模型和最小 `FrameLike` Protocol。
3. `capture/` 只负责采集，不解释画面。
4. `actions/` 负责执行，不决定策略；Win32 输入在 `platform/windows/`。
5. `runtime/` 可以组合 Core、Capture、Actions，但不是 Core 的一部分。
6. `vision/` 不直接执行输入；其输出逐步归一到 `Observation`。
7. `state/` 不负责底层截图；其状态逐步归一到 `GameState`。
8. `agent/` 不直接调用 Win32 API；其决策输出归一到 `AgentDecision`。
9. `games/<target_game>/` 可以依赖通用能力，但通用层不能反向依赖游戏。

## 6. 本轮实际落地

本轮已完成 Runtime 数据面与执行闭环：

- 新增 `runtime/agent_runtime.py`
- `BackgroundGameSession` 增加 `build_agent_runtime()`
- Capture → Observation → State → AgentDecision → Action → ActionResult 已连通
- **Action 后重新 Capture**，再进入 Observation → State → Verification
- 所有核心节点均可注入，便于接入真实 Vision、Game Adapter 和 AI Agent
- 新增 `tests/test_agent_runtime.py`，覆盖执行后重新采集这一闭环语义

注意：当前默认 `MetadataGameAdapter` 和 `DefaultVerifier` 是 Runtime 骨架实现；它们不包含具体游戏规则。下一步应实现第一款目标游戏的 Vision + Game Adapter + Agent Policy。

**游戏是第一个应用场景；GUI Agent Core 才是长期产品核心。**
