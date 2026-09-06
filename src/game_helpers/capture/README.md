# capture

## 当前定位

GUI Agent 的输入采集层。

## 当前职责

- 窗口截图
- 帧数据获取
- Windows 捕获能力封装

## 不应该包含

- 图像理解
- 游戏状态判断
- AI 决策

## 架构关系

Window → Capture → Vision → State

## 后续方向

提供稳定、高性能的视觉输入来源。