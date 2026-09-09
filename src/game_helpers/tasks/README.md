# tasks

## 当前定位

Agent 工作流描述层。

## 当前职责

- 定义任务流程
- 管理执行步骤
- 提供任务运行抽象

## 不应该包含

- 游戏特定逻辑
- 底层输入实现

## 架构关系

Agent Planner → Task → Action

## 后续方向

逐步从助手流程迁移为 Agent Workflow 系统。

## 800×600 道具坐标 + 后台点击验证实验

运行：

```powershell
python -m game_helpers.tasks.item_panel_coordinate_calibration
```

该实验现在不是“只采点”，而是一个最小闭环：

1. 操作员把鼠标悬停到真实“道具”图标，确认 `道具 (Alt+E)` tooltip 后按 F8。
2. 程序把真实屏幕坐标转换为选中 WSGAME 的 client 坐标，并按 `800x600` 写入 `diagnostic/calibration/item_panel_coordinates.json`。
3. 程序使用刚采集的**同一个 client 坐标**，通过现有 `BackgroundInput.click_and_verify()` 发送 `PostMessageW` 后台鼠标点击。
4. 点击后连续检测道具栏视觉状态，验证是否真的发生状态切换。
5. 如果开始时道具栏已经打开，则先用同一坐标关闭，再用同一坐标重新打开，最终成功标准固定为“关闭 → 打开”。
6. `before.png`、`after-close.png`、`after-open.png` 保存在 `diagnostic/calibration/item_panel_click/`，失败时可直接用于判断命中区、HWND/input surface 或消息通道问题。

当前实验仅接受 `800×600`。它的目标就是回答两个问题：

- **坐标是否有效**：人工采点后，实际点击该坐标能否改变道具栏状态。
- **后台点击是否有效**：该坐标在当前选中 WSGAME HWND 上通过 `PostMessageW` 是否能触发道具栏打开。

实验成功后，才有依据把该坐标继续沉淀到正式的 800×600 道具栏自动化配置中；失败则保留现场截图，不把未经验证的坐标写进正式自动化资产。
