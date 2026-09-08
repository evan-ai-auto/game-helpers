# 梦幻西游命魂/铸魂任务公共闭环

任务类型只负责完成当前任务；所有任务类型完成后统一进入同一条公共闭环。

```text
给物品 ─┐
对话   ─┼→ TaskExecutionResult
战斗   ─┘          ↓
                TaskVerification
                     ↓
                ProgressDetection
                     ↓
          ┌──────────┼──────────┐
          15         30         45        60
           ↓          ↓          ↓         ↓
          领奖        领奖        领奖      完成
           ↓          ↓          ↓         ↓
          刷新        刷新        刷新    Round Complete
                                              ↓
                                     暂不自动开新轮
```

## 规则

- `give_item`、`dialogue`、`combat` 等任务类型共享任务验证与进度推进。
- 15/30/45 使用 `reward_chest`，进度达到阈值即进入领奖处理；领取成功后刷新任务列表。
- 判断采用 `progress >= threshold`，而不是只判断精确等于阈值。
- 60 使用独立的 `completion_reward` 语义，不把它当作普通宝箱；领取/点击成功后标记 Round Complete。
- 60 完成后当前版本不会自动开启下一轮。
- 任何任务验证失败不会推进进度。
- 领奖或刷新失败会将轮次置为 `BLOCKED`，等待上层恢复/人工处理。

## 接口边界

`SoulTaskLoop` 只编排公共闭环，通过协议注入：

- `TaskVerifier`：验证当前任务是否真正完成。
- `ProgressDetector`：从最新视觉/语义状态读取当前 0~60 进度。
- `RewardClaimer`：点击/领取对应里程碑奖励并验证动作成功。
- `TaskRefresher`：领奖后的任务列表刷新。

因此具体任务执行器可以独立实现，不需要重复实现里程碑逻辑。
