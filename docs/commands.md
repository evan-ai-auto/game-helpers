# 指令入口

> 人工操作统一从本页开始。需要执行任务时，先查“任务菜单路径”，再复制入口命令。

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
| 1. 完整验证流程 | 按顺序执行全部诊断阶段 |
| 2. 角色运动状态验证 | 两次识别角色场景坐标，判断静止候选/移动/未知 |
| 3. 800×600 OCR 多 ROI 对照验证 | 对比 117×55、150×70、180×80、100×38 精准 ROI，以及精准 ROI 4×放大 OCR |
| 4. Hover 二级 ROI 隔离验证 | 验证目标图标自身 Hover 变化 |
| 5. PostMessageW Hover 验证 | 验证后台鼠标移动消息是否触发 Hover |
| 6. 后台 Click + Hotspot 验证 | 逐点验证后台点击与实际热区 |

诊断输出：

```text
diagnostic/workflow_runs/soul_shortcut_diagnostic/
├── full/
├── motion/
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

该实验当前使用 Windows 原生 OCR：

```text
player_location ROI
  ↓
Windows.Media.Ocr
  ↓
parse_scene_coordinate()
  ↓
P1 / P2
  ↓
静止候选 / 移动 / 未知
```

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
