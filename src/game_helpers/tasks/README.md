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

## 800×600 道具坐标标定

运行：

```powershell
python -m game_helpers.tasks.item_panel_coordinate_calibration
```

该实验只做人工坐标采集，不发送后台点击，也不修改游戏状态。操作员把鼠标悬停到“道具”图标、确认 `道具 (Alt+E)` tooltip 后按 F8，程序将真实屏幕坐标转换为选中 WSGAME 的 client 坐标，并按分辨率写入 `diagnostic/calibration/item_panel_coordinates.json`。

当前实验仅接受 `800×600`，坐标按 `800x600` 独立保存，为后续固定坐标后台点击验证提供校准数据。
