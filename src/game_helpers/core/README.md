# core

## 当前定位

GUI Agent Core 的基础抽象层。

## 当前职责

- 窗口生命周期管理
- 游戏视图抽象
- 会话上下文管理
- 基础模型定义

## 不应该包含

- 游戏规则
- AI 决策逻辑
- 具体游戏操作流程

## 架构关系

Platform Layer → Core → Vision/State/Agent

## 后续方向

稳定接口，作为整个 GUI Agent 的运行基础。