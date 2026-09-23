# 指令入口

> 人工操作统一从本页开始。上方是**需求验收看板**；下方是可执行入口（命令 / 菜单 / 子实验 / 输出）。
> 命令树按业务需求命名；实现方式仅作说明。验收状态只表示业务人工验收结果，不因代码变更自动改变。

## 需求验收看板

### 状态定义

- **已验收通过**：业务人工验收通过；临时人工验收通过也视为通过。
- **部分完成**：已有实现或局部验证，但尚未完成业务人工验收。
- **验收失败**：业务验收未达到要求，或既有验收结论已被后续证据推翻。
- **待确认**：已有实验结果，但证据不足以完成业务验收。
- **未验收**：尚未进行有效业务人工验收。
- **阻塞**：存在前置问题，当前无法继续有效验收。

### 命魂快捷图标需求树

| ID | 状态 | 需求 | 当前实现方式 | 备注 |
|---|---|---|---|---|
| R1 | 阻塞 | Shortcut 功能能够完整闭环 | 完整诊断流程 | 被 R7 验收失败挡住 |
| R2 | 部分完成 | 能够可靠识别角色是否移动 | Playfield 图像差分 + OCR + RightEdge | 未过点：窗口被覆盖时主画面常判「画面未刷新」 |
| R3 | 部分完成 | 能够可靠识别场景与地图坐标 | 800×600 多 ROI + Windows.Media.Ocr + 字符纠错 | 未过点：开顶 `4` / CJK「四」漏读或错位、缺 `X` 标签、场景名右侧 UI 碎片、`9`/`0` 易被当成 `X` |
| R4 | 部分完成 | 鼠标悬停能够触发并识别 Shortcut 二级状态 | 真实鼠标 Hover + 二级 ROI 隔离 | |
| R5 | 部分完成 | 后台消息能够触发并识别 Shortcut 悬停状态 | PostMessageW Hover | |
| R6 | 部分完成 | 后台点击能够触发并确认 Shortcut 状态变化 | Background Click + Hotspot | |
| R7 | 验收失败 | 窗口被覆盖时仍能获得持续刷新的游戏画面 | WGC Host/WSGAME Crop + Surface 切换 + RedrawWindow | 子实验 E7；证据见 `background_capture_freshness/` |

> **需求—子实验对应关系（本表为单一维护来源）**：R1 ← E1、E2、E4、E5、E6；R2 ← E2；R3 ← E3；R4 ← E4；R5 ← E5；R6 ← E6；R7 ← E7。需求名称与 R 编号保持稳定；子实验实现方式可变更时，只更新本表及对应子实验说明。

```text
任务流程
├── 命魂相关任务
├── 阻塞 - 命魂快捷图标完整闭环 - 覆盖窗口画面刷新问题阻塞，进入后按需求分层验证
│   ├── [阻塞] Shortcut 功能能够完整闭环
│   ├── [部分完成] 能够可靠识别角色是否移动
│   ├── [部分完成] 能够可靠识别场景与地图坐标
│   ├── [部分完成] 鼠标悬停能够触发并识别 Shortcut 二级状态
│   ├── [部分完成] 后台消息能够触发并识别 Shortcut 悬停状态
│   ├── [部分完成] 后台点击能够触发并确认 Shortcut 状态变化
│   └── [验收失败] 窗口被覆盖时仍能获得持续刷新的游戏画面
└── 道具栏检测与切换
```

> 子实验名称是人工入口；上表需求才是验收对象。实现方式被推翻或替换时，优先改「当前实现方式 / 备注」，不随意改需求名称。若已验收结论被后续证据推翻，应记录方案/结论变化，而不是静默覆盖历史。

### 维护规则

1. **需求与实现分离**：`状态 - 需求名称` + `实现：当前方式`；需求回答「要证明什么」，实现回答「现在怎么证明」。
2. **最小可组合子功能**：子功能文件可被多任务/验证流复用；流程文件只做编排组合。
3. **引用清单**：快捷图标诊断涉及的文件新增、删除、替换或职责变化时，同步更新 [soul_task_regression.md](soul_task_regression.md) 的「快捷图标诊断：当前引用文件」。
4. 验收状态仅由业务人工验收结果或后续证据推动。

---

## 1. 通用任务入口

在仓库根目录、已激活项目虚拟环境的 PowerShell 中执行：

```powershell
python -m game_helpers.tasks.task_workflow_cli
```

默认会依次进入：

```text
查找游戏主窗口
  ↓
扫描已登录角色
  ↓
选择角色
  ↓
选择任务流程
  ↓
按任务要求执行
```

默认游戏窗口标题：

```text
梦幻西游 ONLINE
```

如窗口标题不同，可传入标题：

```powershell
python -m game_helpers.tasks.task_workflow_cli "梦幻西游 ONLINE"
```

默认诊断输出目录：

```text
diagnostic/workflow_runs
```

如需指定输出根目录：

```powershell
python -m game_helpers.tasks.task_workflow_cli --output-dir diagnostic/workflow_runs
```

## 2. 当前任务菜单

任务菜单由代码中的任务注册表生成，因此实际编号以运行时显示为准。当前诊断分支包含：

| 任务 | 任务用途 | 菜单路径 |
|---|---|---|
| [未验收] 命魂任务 - 执行领取状态检测 | 命魂领取/检测流程 | 进入任务菜单后选择对应命魂任务 |
| 阻塞 - 命魂快捷图标完整闭环 - 覆盖窗口画面刷新问题阻塞，进入后按需求分层验证 | 快捷图标诊断 | 任务菜单 → 选择该任务 → 按需求选择分层验证 |
| [未验收] 基础能力列表 - 单项测试最基础可复用能力 | 单独测试各项最基础可复用能力 | 任务菜单 → 基础能力列表 → 选择基础能力单项测试 |\n| [未验收] 道具栏状态检测 - 检测开关状态并后台反转 | 道具栏状态检测与切换 | 任务菜单 → 选择道具栏任务 |

**不要把这里的数字编号当作固定 API。** 任务注册表发生变化时，菜单编号可能变化；优先按任务名称选择。

## 3. 命魂快捷图标分层诊断

入口命令仍然是：

```powershell
python -m game_helpers.tasks.task_workflow_cli
```

菜单路径：

```text
任务流程
  ↓
阻塞 - 命魂快捷图标完整闭环 - 覆盖窗口画面刷新问题阻塞，进入后按需求分层验证
  ↓
按需求选择分层验证
```

当前子实验与需求对应关系：

| 子实验 ID | 用户菜单名称 | 实现子类型 | 对应需求 | 用途 |
|---|---|---|---|
| E1 | [阻塞] Shortcut 功能能够完整闭环 | `full` | R1、R2、R4、R5、R6 | 依次跑运动检测 + Hover / PostMessageW / Click 分层阶段（不含 OCR 对照） |
| E2 | [部分完成] 能够可靠识别角色是否移动 | `motion` | R2 | 约 3s 内每 0.25s 采样；坐标 + 主画面/右侧条差分，并报告首次变化帧 |
| E3 | [部分完成] 能够可靠识别场景与地图坐标 | `ocr_roi_compare` | R3 | 一张整图裁场景名条与坐标条，分段 OCR 后组装 `地图名[x,y]` |
| E4 | [部分完成] 鼠标悬停能够触发并识别 Shortcut 二级状态 | `hover` | R4 | 验证目标图标自身 Hover 变化 |
| E5 | [部分完成] 后台消息能够触发并识别 Shortcut 悬停状态 | `postmessage_hover` | R5 | 验证后台鼠标移动消息是否触发 Hover |
| E6 | [部分完成] 后台点击能够触发并确认 Shortcut 状态变化 | `click_hotspot` | R6 | 逐点验证后台点击与实际热区 |
| E7 | [验收失败] 窗口被覆盖时仍能获得持续刷新的游戏画面 | `background_capture_freshness` | R7 | 对比窗口被覆盖时的 Host / WSGAME / Playfield / RightEdge 刷新情况，并验证 Surface/RedrawWindow 刷新是否有效 |

**维护约束：**
- R1–R7 是稳定的需求 ID；E1–E7 是稳定的子实验 ID。
- 新增、删除或拆分需求/子实验时，先更新上面的对应关系，再同步各章节的命令说明。
- 任何子实验变更都必须明确它覆盖哪个需求；需求状态仍以“当前需求验收状态”表为准。

诊断输出：

```text
diagnostic/workflow_runs/soul_shortcut_diagnostic/
├── full/
├── motion/
├── ocr_roi_compare/
├── hover/
├── postmessage_hover/
├── click_hotspot/
└── background_capture_freshness/
    ├── covered/
    └── refresh/
```

### 角色运动状态验证

菜单路径：

```text
阻塞 - 命魂快捷图标完整闭环 - 覆盖窗口画面刷新问题阻塞，进入后按需求分层验证
  → 2. 角色运动状态验证
```

该实验在约 3 秒内按 0.25s 连采多帧（约 13 帧），对首帧做基准差分，并对首/末帧分段 OCR：

```text
第 1..N 帧（间隔 0.25s，总时长约 3.0s）
  ↓
开采前 / 主画面仍冻结时中途：后台切换 Surface 刷新画面
  ↓
每帧相对第 1 帧：主画面差 + 右侧条差
  ↓
记录主画面/右侧条「首次超过阈值」的帧号与耗时
  ↓
首末帧分段 OCR → 地图名[x,y]
  ↓
坐标不同 → 移动
坐标相同且主画面变化明显 → 同格运动候选
主画面冻住但右侧条在变 → 画面未刷新
坐标相同且两侧都静 → 静止候选
任一侧 OCR 失败且无冻结证据 → 未知
```

截图会写入 `motion-sample-01.png` … `motion-sample-NN.png`；`motion-sample-1.png` / `motion-sample-2.png` 仍指向首帧与末帧。

Windows 环境依赖：

```powershell
python -m pip install -e ".[windows]"
```

该安装方式会安装项目声明的 Windows 依赖，包括 `winsdk`。

## 4. 800×600 前置条件

当前命魂诊断链路以 **800×600 客户区**为基线。

运行任务前确认游戏客户区为：

```text
800x600
```

如果 CLI 提示当前角色不是基线分辨率，应先调整窗口/客户区，不要继续诊断。

## 5. 输出与证据

诊断任务原则上不会修改生产配置。

常见证据包括：

- 完整截图
- ROI 截图
- OCR 原文
- OCR 解析坐标
- Hover 前后截图
- 点击前后状态
- JSON validation report

不要只根据终端最后的 `result=PASSED` 判断某个视觉结论正确；它表示该诊断流程本身完成。

## 6. 相关文档

- [docs/verification.md](verification.md)：逐项复验步骤与通过标准
- [docs/maintain.md](maintain.md)：资产和流程维护
- [docs/capabilities.md](capabilities.md)：已验证可复用能力
- [docs/soul_task_regression.md](soul_task_regression.md)：命魂领取回归 + 快捷图标诊断引用清单
- [docs/agent-coding.md](agent-coding.md)：Agent 编码约定

## 7. 新增任务时的文档要求

新增用户可执行任务时，同时更新本文件，至少记录：

1. 入口命令
2. 任务菜单名称
3. 子实验/子菜单
4. 前置条件
5. 输出目录
6. 通过标准
7. 常见失败处理

需求验收状态变更时，只改本页「需求验收看板」；引用文件变更时，改 [soul_task_regression.md](soul_task_regression.md) 对应表。

这样执行任务时不需要依赖聊天记录记忆命令。


## 基础能力列表

> 本菜单只提供基础能力的**单项测试入口**。`basic_capabilities.py` 是基础能力注册表：定义稳定的能力 ID、用户名称、契约说明和当前实现绑定；菜单测试与任务 Flow 共用这份注册表。注册表不承载具体实现，因此切换底层实现时保持能力 ID 稳定，不会复制测试逻辑。

| # | 基础能力 | 实现来源 | 单项测试目的 |
|---|---|---|---|
| 1 | 获取宿主窗口画面 | `capture/wgc.py` | 验证单次 Host WGC 捕获 |
| 2 | 获取选中游戏画面 | `tasks/verification_session.py` | 验证 Host 捕获 + WSGAME 裁剪 |
| 3 | 检查游戏画面 Surface | `core/surface.py` / `verification_session.py` | 验证当前 Surface 捕获条件 |
| 4 | 读取场景与地图坐标 | `vision/scene_coordinate.py` + `vision/windows_ocr.py` | 单独验证 OCR |
| 5 | 识别 Shortcut 当前状态 | `tasks/shortcut_panel_vision.py` | 单独验证 Shortcut 视觉状态识别；结果明确输出「折叠 / 展开 / 未知」 |
| 6 | 执行图像差分 | `tasks/soul_shortcut_diagnostic_flow.py:image_diff` | 单独验证基础差分能力 |
| 7 | 执行 Surface 刷新 | `tasks/soul_shortcut_diagnostic_flow.py:_refresh_capture_surface` | 单独验证现有刷新尝试 |
| 8 | 发送后台鼠标移动 | `actions/background_input.py` | 仅发送 WM_MOUSEMOVE，不执行点击 |
| 9 | 暂未验证通过 验证捕获新鲜度 | `tasks/background_capture_freshness.py` | 单独验证 Host / WSGAME / Playfield / RightEdge 新鲜度 |

基础能力输出统一写入 `diagnostic/workflow_runs/basic_capabilities/<capability-id>/<run-id>/`，每次执行独立落盘，不覆盖历史证据。运行时至少保存：
- `run.json`：基础能力 ID、名称、当前实现绑定、证据文件清单
- `capture.png`：本次基础能力测试使用的游戏画面
- `result.json`：本次结构化测试结果
- Shortcut 状态识别额外保存 `shortcut-toggle-roi.png`：实际识别 ROI 原图

目录示例：

```text
diagnostic/workflow_runs/basic_capabilities/
├── host_capture/
├── game_view_capture/
├── surface_health/
├── scene_coordinate_ocr/
├── shortcut_state_vision/
│   └── <run-id>/
│       ├── capture.png
│       ├── shortcut-toggle-roi.png
│       ├── result.json
│       └── run.json
├── image_diff/
├── surface_refresh/
├── background_mouse_move/
└── capture_freshness/
```

这些运行证据允许提交到 Git，用于人工复盘、问题定位和后续视觉算法回归；它们不属于生产配置。


能力注册表：`src/game_helpers/tasks/basic_capabilities.py`。命魂 Shortcut Flow 通过 `SHORTCUT_DIAGNOSTIC_CAPABILITY_IDS` 声明其基础能力依赖；单项测试菜单直接使用同一注册表，因此“Flow 实际依赖什么”与“菜单测试什么”不会形成两套能力清单。


### 顶层任务菜单命名规则

所有人工任务入口统一采用 **状态 - 需求名称 - 说明**。状态表示业务人工验收状态，不表示代码是否能运行；未发生有效业务人工验收的任务使用「未验收」。实现技术名只进入 Flow/子实验说明，不作为顶层任务名称。
