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

---

## 快捷图标分层诊断

> **Flow 首屏依赖总览**：本节先列出当前 Flow 引用的基础能力；能力 ID、用户名称和当前实现绑定统一维护在 `basic_capabilities.py`。后续再说明执行顺序、验收证据与实机回归。底层实现拆分保持独立，Flow 负责组合，不要求能力归核。

### 基础能力依赖（首屏）

| 基础能力 | 实现文件 | 核心函数/入口 | Flow 用途 |
|---|---|---|---|
| Host WGC 捕获 | `src/game_helpers/capture/wgc.py` | `WindowsGraphicsCapture.capture` | 获取宿主窗口画面 |
| WSGAME 裁剪 | `src/game_helpers/tasks/verification_session.py` | `VerificationSession.capture_frame` | 从 Host Frame 取得选中 800×600 GameView |
| GameView / Surface 管理 | `src/game_helpers/core/view_manager.py` | `GameViewManager` | 选择目标游戏视图并支持 Surface 切换 |
| 后台运行上下文 | `src/game_helpers/tasks/background_context.py` | `BackgroundRunGuard` | 保存/恢复前台窗口、Surface 与标签 |
| 角色选择同步 | `src/game_helpers/tasks/character_selection.py` | `sync_selected_character` | 诊断开始时同步目标角色 |
| 人工坐标采集 | `src/game_helpers/tasks/manual_coordinate.py` | `collect_client_coordinate` | Hover / Click 目标点采集 |
| 后台鼠标输入 | `src/game_helpers/actions/background_input.py` | `BackgroundInput` | PostMessageW Hover / Background Click |
| Shortcut 状态 / Hotspot 视觉检测 | `src/game_helpers/tasks/shortcut_panel_vision.py` | `detect_shortcut_panel_state` | 一级状态与点击后状态确认 |
| 场景 / 地图坐标 OCR | `src/game_helpers/vision/scene_coordinate.py` | `read_player_location` | OCR 与 Motion 的场景坐标证据 |
| Windows OCR 后端 | `src/game_helpers/vision/windows_ocr.py` | `WindowsNativeOCRBackend` | 执行 Windows.Media.Ocr 识别 |
| 800×600 基线 | `src/game_helpers/tasks/soul_task.py` | `SOUL_TASK_BASELINE_SIZE` | 诊断前置分辨率约束 |
| Frame / PIL 转换 | `src/game_helpers/tasks/soul_task_match.py` | `as_pil_image` | 图像差分、ROI 与截图处理 |
| Surface 刷新辅助 | `src/game_helpers/tasks/background_item_panel_open_probe_visual.py` | `refresh_surface_for_capture` | Motion / Freshness 刷新尝试 |
| 覆盖捕获新鲜度 | `src/game_helpers/tasks/background_capture_freshness.py` | `run_background_capture_freshness` | E7：covered / refresh 分层验证 |

### Flow 入口与执行说明

用户入口名称：「阻塞 - 命魂快捷图标完整闭环 - 覆盖窗口画面刷新问题阻塞，进入后按需求分层验证」。入口与验收看板见 [commands.md](commands.md)。

进入后提供：

1. 完整验证流程（运动 + Hover / PostMessageW / Click；不含 OCR 对照）
2. 角色运动状态验证
3. 800×600 OCR 多 ROI 对照验证（场景名条 + 坐标条分段 OCR）
4. Hover 二级 ROI 隔离验证
5. PostMessageW Hover 验证
6. 后台 Click + Hotspot 验证
7. 后台覆盖捕获新鲜度分层验证（covered / refresh）

子实验与需求的对应关系以 [commands.md](commands.md)「需求—子实验对应关系」为唯一维护来源；本页只保留当前执行顺序，不另行维护映射表。

诊断输出独立写入 `diagnostic/workflow_runs/soul_shortcut_diagnostic/<subtype>/`（含 `background_capture_freshness/`），不修改生产默认坐标 `client=(14, 122)`、生产模板或现有后台点击实现。

Windows OCR 依赖：Windows 环境通过 `windows` extra 安装 `winsdk>=1.0.0b10`。运动状态与 OCR 对照子实验均走 `scene_coordinate.read_player_location`（整图裁场景名条 / 坐标条后分段识别）；OCR 原文、解析坐标与状态会写入诊断报告。Windows OCR 当前 binding 未提供稳定的 confidence 字段，因此报告中的 `ocr_confidence=0.0` 表示“未提供”，不表示识别置信度为零。

### 快捷图标诊断：当前引用文件

以最小可组合子功能组合验证流；流程编排文件不应重复实现这些子功能。下表保留完整直接依赖清单，首屏摘要见上方「基础能力依赖（首屏）」。（含子类型 7 专用实现）。

| 文件 | 功能 | 在诊断中的作用 |
|---|---|---|
| `src/game_helpers/tasks/soul_shortcut_diagnostic_flow.py` | 诊断流程编排、子类型路由、报告输出 | 入口与组合层 |
| `src/game_helpers/tasks/verification_session.py` | Host WGC 捕获后按选中 WSGAME 几何裁剪 | 统一 800×600 GameView |
| `src/game_helpers/capture/wgc.py` | Windows Graphics Capture | Host Frame |
| `src/game_helpers/core/view_manager.py` | GameView / Surface 管理 | 选中游戏视图 |
| `src/game_helpers/tasks/background_context.py` | 后台运行上下文 | 保存/恢复前台与 Surface/标签 |
| `src/game_helpers/tasks/character_selection.py` | 角色选择与同步 | 诊断开始时同步角色 |
| `src/game_helpers/tasks/manual_coordinate.py` | 人工坐标采集 | Hover / Click 目标点 |
| `src/game_helpers/actions/background_input.py` | 后台鼠标消息 | PostMessageW Hover / Click |
| `src/game_helpers/tasks/shortcut_panel_vision.py` | Shortcut 状态 / Hotspot 视觉检测 | 一级状态与点击确认 |
| `src/game_helpers/vision/scene_coordinate.py` | 场景名、地图坐标 ROI 与解析 | OCR / Motion 证据 |
| `src/game_helpers/vision/windows_ocr.py` | Windows.Media.Ocr 后端 | OCR 识别 |
| `src/game_helpers/tasks/soul_task.py` | 800×600 基线定义 | 分辨率前置约束 |
| `src/game_helpers/tasks/soul_task_match.py` | Frame / PIL 转换 | 诊断图像输入 |
| `src/game_helpers/tasks/background_item_panel_open_probe_visual.py` | Surface 刷新辅助 | Motion / Freshness 刷新尝试 |
| `src/game_helpers/tasks/background_capture_freshness.py` | 后台覆盖新鲜度分层验证 | 子类型 7 |

验证工具（非流程 import，人工常用）：`tools/verify_background_capture_freshness.py`。

维护规则以 [commands.md](commands.md)「维护规则」为准；本表变更时同步更新，暂不要求能力归核。


## 基础能力列表 Flow

基础能力列表是独立的人工/开发诊断入口，用于逐项验证最小可复用能力。它通过 `basic_capability_flow.py` 作为薄适配层调用现有实现，不复制基础能力逻辑、不修改现有 Flow 的调用方式。

### 单项能力清单

| 能力 | 现有实现 | 测试入口 |
|---|---|---|
| 获取宿主窗口画面 | `capture/wgc.py:WindowsGraphicsCapture.capture` | `host_capture` |
| 获取选中游戏画面 | `verification_session.py:VerificationSession.capture_frame` | `game_view_capture` |
| 检查游戏画面 Surface | `verification_session.py:VerificationSession.health` | `surface_health` |
| 读取场景与地图坐标 | `scene_coordinate.py:read_player_location` | `scene_coordinate_ocr` |
| 识别 Shortcut 当前状态 | `shortcut_panel_vision.py:detect_shortcut_panel_state` | `shortcut_state_vision` |
| 识别 UI 图标（依赖 Shortcut 状态） | `ui_icon_vision.py:detect_ui_icon_with_shortcut_gate` | `ui_icon_vision` |
| 执行图像差分 | `soul_shortcut_diagnostic_flow.py:image_diff` | `image_diff` |
| 执行 Surface 刷新 | `soul_shortcut_diagnostic_flow.py:_refresh_capture_surface` | `surface_refresh` |
| 发送后台鼠标移动 | `platform/windows/input.py:BackgroundInput.mouse_move` | `background_mouse_move` |
| 暂未验证通过 验证捕获新鲜度 | `background_capture_freshness.py:run_background_capture_freshness` | `capture_freshness` |

**复用隔离规则**：能力注册表只描述能力契约和当前实现绑定，不承载测试编排；基础能力菜单与任务 Flow 共用注册表，但任务 Flow 不依赖菜单入口。删除基础能力菜单不会影响任何任务执行；替换底层实现时优先更新注册表绑定并执行受影响 Flow 的重新验收。
