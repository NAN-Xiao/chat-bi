# 实施计划

1. 在独立 linked worktree 和 `codex/fix-thinking-process-flicker` 分支中实施，保持主检出已有改动不动。
2. 扩展记录生成态纯函数：活动 `task_id` 优先于“最后一条记录”限制，同时保留新记录启动窗口。
3. 调整 `index.vue` 调用方并统一任务完成/失败后的会话 typing 状态同步，避免仍有任务时提前解锁。
4. 将 `ChartAnswer` 的轮询 loading 改为组件本地可写状态，并与外部记录生成态组合后传给 `BaseAnswer`。
5. 增加回归测试：非最后活动任务、无 task_id 启动窗口、终态残留 task_id、交错完成和 loading 组合。
6. 运行聚焦测试与 `npm run build`，检查 diff 无无关生成文件。
7. 重启或切换 `5173` 到修复 worktree，真实复现重叠任务场景；验证思考入口连续、输入锁正确、完成后收起且入口保留，并检查控制台和横向溢出。
8. 记录检查结果；若该状态所有权规则具有复用价值，更新前端规范后再提交。

## 实施日志

### 2026-08-25

- 扩展 `shouldMarkRecordTyping`：未终态记录拥有活动 `task_id` 时独立保持生成态；无任务的新记录仍仅通过“最后一条 + 页面发送中”覆盖启动窗口。
- `index.vue` 的页面恢复改为扫描全部记录；新增统一会话状态同步，在 Smart Q&A 完成、失败和任务启动失败后重新扫描未完成记录，避免交错完成时提前释放输入锁。
- `ChartAnswer` 新增组件本地 loading，并与父级记录生成态组合后传给 `BaseAnswer`，不再依赖父级未监听的更新事件才能保持轮询状态。
- 新增非最后活动任务、页面恢复、终态残留 `task_id`、会话锁同步及 loading 组合回归测试。
- 已通过：`node --test tests/chatTypingState.test.ts tests/chat-thinking-state-contract.test.mjs`（7 项）、`git diff --check`。
- 未在本 worktree 运行依赖 TypeScript 的历史测试和生产构建：`frontend/node_modules` 未安装；直接运行分别因找不到 `typescript` 与 `vue-tsc` 依赖失败。未启动或停止共享本地服务，浏览器回归留给后续质量检查阶段。
- 质量检查阶段复用锁文件一致的现有依赖目录完成验证：相关回归测试 15/15 通过，`npm run build` 通过；临时依赖 junction 已删除，源依赖目录保持不变。
- 独立检查统一了 `shouldMarkChatTypingOnRestore`：页面恢复、运行时输入锁均扫描全部记录，并新增“旧任务仍运行、最新记录已完成”和“终态残留 task_id”用例。
- 在隔离端口 `5187` 用真实 `BaseAnswer` 和真实记录 typing 判定做桌面/390px 浏览器回归：后续记录出现后旧任务占位持续，首个 reasoning 连续显示，完成后正文收起但入口保留；无控制台错误或横向溢出。临时夹具和服务均已清理。
