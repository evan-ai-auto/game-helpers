# 指令入口

> 人工操作统一从本页开始。需要执行任务时，先查“任务菜单路径”，再复制入口命令。

## 当前需求验收状态

命令树以业务需求命名，实现方式仅作为说明。状态只表示业务人工验收状态：

- **已验收通过**：业务人工验收通过；临时人工验收通过也视为通过。
- **部分完成**：已有实现或局部验证，但尚未完成业务人工验收。
- **验收失败**：业务验收未达到要求，或既有验收结论已被后续证据推翻。
- **待确认**：已有实验结果，但证据不足以完成业务验收。
- **未验收**：尚未进行有效业务人工验收。
- **阻塞**：存在前置问题，当前无法继续有效验收。

### 命魂快捷图标需求树

| 状态 | 需求 | 当前实现方式 |
|---|---|---|
| 部分完成 | Shortcut 功能能够完整闭环 | 完整诊断流程 |
| 部分完成 | 能够可靠识别角色是否移动 | Playfield 图像差分 + OCR + RightEdge |
| 部分完成 | 能够可靠识别场景与地图坐标 | 800×600 多 ROI + Windows.Media.Ocr + 字符纠错 |
| 部分完成 | 鼠标悬停能够触发并识别 Shortcut 二级状态 | 真实鼠标 Hover + 二级 ROI 隔离 |
| 部分完成 | 后台消息能够触发并识别 Shortcut 悬停状态 | PostMessageW Hover |
| 部分完成 | 后台点击能够触发并确认 Shortcut 状态变化 | Background Click + Hotspot |
| 验收失败 | 窗口被覆盖时仍能获得持续刷新的游戏画面 | WGC Host/WSGAME Crop + Surface 切换 + RedrawWindow |

> 验收状态不会因为代码文件变更自动改变；只有业务人工验收结果或后续证据才能推动状态变化。若已验收结论被后续证据推翻，应记录方案/结论变化，而不是静默覆盖历史。

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
| 命魂领取相关任务 | 命魂领取/检测流程 | 进入任务菜单后选择对应命魂任务 |
| 命魂快捷图标 Hover / 运动 / 后台输入分层验证 | 快捷图标诊断 | 任务菜单 → 选择该任务 → 选择子实验 |
| 道具栏检测与切换 | 道具栏状态检测与切换 | 任务菜单 → 选择道具栏任务 |

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
命魂快捷图标 Hover / 运动 / 后台输入分层验证
  ↓
选择子实验
```

当前子实验：

| 子实验 | 用途 |
|---|---|
| 1. 完整验证流程 | 依次跑运动检测 + Hover / PostMessageW / Click 分层阶段（不含 OCR 对照） |
| 2. 角色运动状态验证 | 约 3s 内每 0.25s 采样；坐标 + 主画面/右侧条差分，并报告首次变化帧 |
| 3. 800×600 OCR 多 ROI 对照验证 | 一张整图裁场景名条与坐标条，分段 OCR 后组装 `地图名[x,y]` |
| 4. Hover 二级 ROI 隔离验证 | 验证目标图标自身 Hover 变化 |
| 5. PostMessageW Hover 验证 | 验证后台鼠标移动消息是否触发 Hover |
| 6. 后台 Click + Hotspot 验证 | 逐点验证后台点击与实际热区 |
| 7. 后台覆盖捕获新鲜度分层验证 | 对比窗口被覆盖时的 Host / WSGAME / Playfield / RightEdge 刷新情况，并验证 Surface/RedrawWindow 刷新是否有效 |

诊断输出：

```text
diagnostic/workflow_runs/soul_shortcut_diagnostic/
├── full/
├── motion/
├── ocr_roi_compare/
├── hover/
├── postmessage_hover/
└── click_hotspot/
```

### 角色运动状态验证

菜单路径：

```text
命魂快捷图标 Hover / 运动 / 后台输入分层验证
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
- [docs/soul_task_regression.md](soul_task_regression.md)：命魂回归与诊断矩阵
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

这样执行任务时不需要依赖聊天记录记忆命令。
