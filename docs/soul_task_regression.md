# 命魂主流程回归记录

基线：子窗 **800×600**；纯后台。入口：

```powershell
.\.venv\Scripts\python.exe -m game_helpers.tasks.task_workflow_cli
```

相关能力：单次 F9 坐标采集（`minghun_coordinate`）、连续坐标验证（`minghun_coordinate_continuous`）、主流程（`minghun`）。

## 坐标约定

| 项 | 说明 |
|---|---|
| 历史误点 | `fixed_coordinates.json` 曾写入 `shortcut_panel_toggle` **client=(34, 92)**（过时标定） |
| 现行默认点击候选 | **client=(14, 122)**（`DEFAULT_SHORTCUT_PANEL_CLICK` + 已更新的 `fixed_coordinates.json`） |
| 视觉匹配 | 仅诊断：记录模板、分数、匹配位置 |
| 实际点击 | 仅用标定/默认候选；**禁止**用视觉匹配中心替代生产点击 |
| 容差 ROI | `shortcut_panel_vision.SHORTCUT_PANEL_TOGGLE_REGION`（约 client x∈[0,40)、y∈[80,128)） |

## 回归清单

本地实机逐项打勾；Agent 不挂机等待游戏。

| # | 场景 | 期望要点 |
|---|---|---|
| 1 | 单次 F9 坐标采集 | 采到客户区坐标；日志含 `client=(x, y)`；不覆盖错误默认除非人工确认 |
| 2 | 连续坐标验证 | 仅人工确认有效点计入样本；ESC 结束；不覆盖默认坐标 |
| 3 | 主流程·折叠态展开 | 点击前保存 `character-N-panel-before-click.png`；展开前状态=折叠；执行展开点击 `client=(14, 122)`；消息发送=成功；展开后=已展开；展开结果=成功；失败时仍保留 `panel-failure.png` |
| 4 | 主流程·已展开态 | 不点击；展开结果=成功；继续领取检测 |
| 5 | 点击后状态变化成功 | `状态变化=成功`；`校验结论=展开成功` |
| 6 | 点击后低置信度 | 展开结果=失败；失败原因含「无法可靠确认」；含最佳/次佳模板与分数；策略=停止不自动重试 |
| 7 | 模板缺失或匹配失败 | 展开前即失败或状态未知；含阶段/原因/策略；不误点 |
| 8 | 前台/界面/标签恢复 | 日志：前台窗口=未变化；Surface 恢复=成功；标签恢复=成功 |

## 成功日志样例

```text
[命魂任务] 展开前状态：折叠
[命魂任务] 展开前证据：模板=right_gray；score=0.856；匹配位置=(14, 122)
[命魂任务] 执行展开点击：client=(14, 122)；消息发送=成功
[命魂任务] 展开后状态：已展开
[命魂任务] 展开后证据：模板=left_light；score=0.841；匹配位置=(14, 122)
[命魂任务] 展开结果：成功
```

## 失败日志样例

```text
[命魂任务] 展开结果：失败
[命魂任务] 失败原因：点击后状态无法可靠确认
[命魂任务] 点击位置：client=(14, 122)
[命魂任务] 点击发送：成功
[命魂任务] 点击后最佳模板：right_gray；score=0.774
[命魂任务] 点击后次佳模板：left_light；score=0.755
[命魂任务] 处理策略：停止，不自动重试
```

## 记录区（实机）

| 日期 | 场景# | 结果 | 备注 |
|---|---|---|---|
| （待填） |  |  |  |


## 当前主流程引用文件

当前“命魂快捷图标 Hover / 运动 / 后台输入分层验证”主流程以最小可组合子功能组合验证流；流程编排文件不应重复实现这些子功能。

| 文件 | 功能 | 在主流程中的作用 |
|---|---|---|
| `src/game_helpers/tasks/soul_shortcut_diagnostic_flow.py` | 诊断流程编排、子类型路由、报告输出 | 主流程入口与组合层 |
| `src/game_helpers/tasks/verification_session.py` | Host WGC 捕获后按选中 WSGAME 几何裁剪 | 为各验证流提供统一 800×600 GameView |
| `src/game_helpers/capture/wgc.py` | Windows Graphics Capture | 获取 Host HWND 的 Frame |
| `src/game_helpers/core/view_manager.py` | GameView/Surface 管理 | 解析并管理选中游戏视图 |
| `src/game_helpers/tasks/background_context.py` | 后台运行上下文 | 保存/恢复前台窗口与 Surface/标签 |
| `src/game_helpers/tasks/character_selection.py` | 角色选择与同步 | 在诊断开始时同步选中角色 |
| `src/game_helpers/tasks/manual_coordinate.py` | 人工坐标采集 | Hover/Click 验证的人工目标点采集 |
| `src/game_helpers/actions/background_input.py` | 后台鼠标消息 | PostMessageW Hover 与后台 Click |
| `src/game_helpers/tasks/shortcut_panel_vision.py` | Shortcut 状态/Hotspot 视觉检测 | 一级状态与点击前后状态确认 |
| `src/game_helpers/vision/scene_coordinate.py` | 场景名、地图坐标 ROI 与解析 | OCR / Motion 的状态证据 |
| `src/game_helpers/vision/windows_ocr.py` | Windows.Media.Ocr 后端 | OCR 实际识别 |
| `src/game_helpers/tasks/soul_task.py` | 800×600 基线定义 | 主流程分辨率前置约束 |
| `src/game_helpers/tasks/soul_task_match.py` | Frame/PIL 图像转换 | 诊断图像处理输入 |
| `src/game_helpers/tasks/background_item_panel_open_probe_visual.py` | Surface 刷新辅助 | Motion/Freshness 中的刷新尝试 |
| `src/game_helpers/tasks/background_capture_freshness.py` | 后台覆盖新鲜度分层验证 | 子类型 7 的独立验证实现 |

维护规则：

1. 主流程新增、删除、替换或改变上述文件职责时，同步更新本表。
2. 新能力优先作为最小子功能实现，再由任务类型/手动验证流组合。
3. 验收状态属于业务人工验收结果，不因代码文件变更自动改变。
4. 若某实现方式被后续证据推翻，保留需求名称，更新当前实现方式并记录方案历史。
5. 暂不进行能力归核；当前只要求最小可组合子功能与主流程引用可追踪。

---

## 快捷图标分层诊断任务

新增单一任务类型「命魂快捷图标 Hover / 运动 / 后台输入分层验证」，进入后提供：
1. 完整验证流程（运动 + Hover / PostMessageW / Click；不含 OCR 对照）
2. 角色运动状态验证
3. 800×600 OCR 多 ROI 对照验证（场景名条 + 坐标条分段 OCR）
4. Hover 二级 ROI 隔离验证
5. PostMessageW Hover 验证
6. 后台 Click + Hotspot 验证

诊断输出独立写入 `diagnostic/workflow_runs/soul_shortcut_diagnostic/<subtype>/`，不修改生产默认坐标 `client=(14, 122)`、生产模板或现有后台点击实现。

Windows OCR 依赖：Windows 环境通过 `windows` extra 安装 `winsdk>=1.0.0b10`。运动状态与 OCR 对照子实验均走 `scene_coordinate.read_player_location`（整图裁场景名条 / 坐标条后分段识别）；OCR 原文、解析坐标与状态会写入诊断报告。Windows OCR 当前 binding 未提供稳定的 confidence 字段，因此报告中的 `ocr_confidence=0.0` 表示“未提供”，不表示识别置信度为零。
