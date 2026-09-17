# Agent 编码约定

先读 [requirements.md](requirements.md)。复用已验证能力看 [capabilities.md](capabilities.md)。人工加资产/流程看 [maintain.md](maintain.md)。

## 必守

1. 当前按 **800×600** 基线实现与验收；多分辨率见 backlog，勿顺手扩 scope。
2. 纯后台：`activate_before_switch=False`；禁止抢焦点 / 前台 Ctrl+Tab（除非需求写明）。
3. 根目录不新增散落文件；说明类文字放 `docs/`。
4. 代码在 `src/game_helpers/`；探针入口保持 `python -m game_helpers.tasks.*_probe`。
5. 资产与流程走可维护目录，勿把模板路径写死难扩展。
6. **新流程优先组合 [capabilities.md](capabilities.md) 里的稳定入口**，不要从探针里再抄一份。
7. 未请勿 commit；发现做不了的记 [backlog.md](backlog.md)。
8. **实机验收以用户本地跑为准**：改完后给出指令与期望日志字段即可；不要长时间挂机等待游戏条件/交互。用户贴日志后再分析调整。
9. 资产 JSON 必须带 `verification_status`（`pending`/`verified`/`failed`）；流程优先只用 `verified`。约定见 [maintain.md](maintain.md)。
10. **用户可见日志必须人工可读**：见下方「日志格式」。

## 日志格式（用户可见）

面向操作者/验收的控制台输出，必须让人直接判断：阶段、状态、坐标、结果、后续策略。

| 项 | 要求 |
|---|---|
| 一条一事 | 一行日志只表达一个事实；不要把多阶段拼成超长句 |
| 前缀 | 命魂相关用 `[命魂任务]` |
| 坐标 | 统一 `client=(x, y)`；禁止裸元组或混用屏幕坐标不标注 |
| 分数 | 统一 `score=0.856`（三位小数） |
| 布尔结果 | 用中文「成功/失败」「是/否」「未变化/已变化」等，勿直接打印 `True`/`False` 当主结论 |
| 失败日志 | 必须含：阶段、原因、关键坐标、关键分数、下一步策略 |
| 禁止 | 把 Python 对象、`Enum` 内部表示、长元组、嵌套 dict/list 直接 `print` 给用户 |

诊断字段需可区分（可用中文标签，勿只甩原始枚举）：

- `state_changed`：点击前后状态是否按预期变化
- `state_confident`：状态检测是否达到可信阈值
- `click_dispatch_success`：后台点击消息是否发送成功
- `verification_result`：本阶段校验结论（成功/失败及原因摘要）

视觉匹配位置与实际点击位置必须分离记录；主流程点击以标定/默认候选为准，不以模板匹配中心替代。

参考实现：`tasks/soul_task_logging.py`、`tasks/soul_task_flow.py`。回归场景见 [soul_task_regression.md](soul_task_regression.md)。

## 代码落点（短）

| 需求 | 优先看 |
|---|---|
| 已验证能力总表 | `docs/capabilities.md` |
| 窗口 / 子窗 / 切视图 | `core/` |
| 截图 | `capture/` + `tasks/verification_session.py` |
| 后台上下文恢复 | `tasks/background_context.py` |
| 角色 / 状态 / 流程 | `tasks/` |
| 命魂最小闭环 | `tasks/soul_task_flow.py`、`task_workflow_cli.py` |
| 点击 | `actions/background_input.py` |
| 人工采坐标（F8） | `tasks/manual_coordinate.py`、`manual_coordinate_cli.py` |
| 图标与状态资产 | `data/assets/ui/resolutions/{WxH}/` + `tasks/asset_resolution.py` |

切角色：先 `switch_surface_to`，再后台 `switch_to`，并确认前台未变（或用 `sync_selected_character` / `BackgroundRunGuard`）。
