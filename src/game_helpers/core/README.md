# core

## 当前定位

GUI Agent Core 的基础契约与平台无关模型层。

## 当前职责

- `Point` / `Rect` / `WindowInfo` 等基础 GUI 模型
- `GameView` 等宿主游戏视图抽象
- Surface geometry / health 等与平台实现解耦的基础判断
- 为 Capture / Actions / Vision / State / Agent 提供稳定契约

## 明确边界

Core 不负责：

- Win32 API 调用、窗口枚举、子窗口枚举
- 鼠标键盘消息投递
- Capture backend 实现
- View switching / Session orchestration
- 游戏规则与 AI 决策

这些实现分别位于 `platform/windows/`、`capture/` 与 `runtime/`。

## 兼容策略

历史入口仍通过 lazy compatibility exports 保留，但新代码应直接依赖对应的 `platform` / `runtime` 模块，避免把平台实现重新带回 Core。

## 目标依赖

```text
Core contracts
    ↑
Platform / Capture / Actions / Runtime
    ↑
Vision / State / Agent / Games
```

## 当前迁移状态

第一阶段已完成：Win32 window/child discovery、tab switching、background input 和 view/session orchestration 已从 Core 实现中下沉到 platform/runtime；`core.surface` 不再运行时依赖 `capture.models.Frame`。
