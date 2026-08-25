# 思考过程闪烁诊断

## 结论

根因是前端把生成态建模为“全局 `isTyping` 且记录必须是当前会话最后一条”，但后端和任务存储允许同一会话存在多个仍在运行的记录。旧任务一旦不再是最后一条，就会被临时判定为非生成态；如果此时尚未收到首个 reasoning 分片，`BaseAnswer` 的 `thinkingActive` 与 `hasReasoning` 同时为 false，整个思考入口消失。首个 reasoning 分片到达后 `hasReasoning` 变为 true，入口重新出现。

## 真实时间线

截图对应会话为 `chat.id=878`（沙盘出征事件明细）。数据库只读取了记录时间和 reasoning 长度，没有读取完整提示词或推理内容。

- `record 2907` 创建于 `17:09:56.334`，完成于 `17:11:05.877`。
- 下一条 `record 2908` 创建于 `17:10:10.263`，此时 `record 2907` 仍在运行。
- `record 2907` 的 SQL reasoning 日志从 `17:10:11.310` 才开始，晚于下一条记录创建约 1.05 秒。
- 在这约 1 秒窗口内，`record 2907` 已不是最后一条记录，且还没有 reasoning 内容，满足思考入口完全隐藏的条件。
- reasoning 分片开始到达后，`record 2907.sql_answer` 被流式更新，`hasReasoning` 变为 true，入口重新出现。
- 同一会话还存在其他重叠任务：`record 2909` 创建于 `17:10:58.734`，而 `record 2907` 到 `17:11:05.877` 才结束。

## 代码证据

- `frontend/src/views/chat/chatTypingState.ts:12`：`shouldMarkRecordTyping` 要求 `recordIndex === lastRecordIndex`。
- `frontend/src/views/chat/index.vue:631`：每条消息的 `isTyping` 由全局 `isTyping`、最后一条索引和 unfinished 状态共同决定。
- `frontend/src/views/chat/answer/BaseAnswer.vue:95`：思考入口仅在 `thinkingActive || hasReasoning` 时渲染。
- `frontend/src/views/chat/answer/ChartAnswer.vue:340`：首个 `sql-result` 到达后才把 reasoning 追加到 `sql_answer`，使 `hasReasoning` 变为 true。
- `frontend/src/views/chat/index.vue:1337`：`sendMessage` 本身没有检查已有生成任务，只依赖输入框/按钮的外层禁用态；它不能覆盖多标签页、快速重复调用或其他并发入口。

## 次要缺陷

`c5acc2f1` 曾尝试把 `loading` 计入思考活动态，但当前链路没有提供独立 loading 状态：

- `ChartAnswer.vue:104` 的 `_loading` 只是 `props.loading` 的 computed 包装，setter 仅发出 `update:loading`。
- 父组件在 `index.vue:243` 只使用单向 `:loading="message.isTyping"`，没有 `v-model:loading` 或 `@update:loading`。
- `BaseAnswer.vue:35` 实际拿到的是同一个 `message.isTyping` 两次，无法覆盖 `isTyping` 短暂为 false、任务仍在运行的窗口。

现有 `thinkingVisibility.test.ts` 只验证纯函数布尔组合，没有覆盖多记录并发、任务所有权或父子 loading 绑定，因此没有发现该缺口。

## 排除项

- 后端不会在 reasoning 日志之前完成任务：SQL/图表阶段通过 `end_log` 提交 reasoning，工作流 finally 才调用 `service.finish` 写 `ChatRecord.finish=true`。
- 实际记录的 reasoning 日志均早于对应 `finish_time`，没有证据表明数据库先返回终态空 reasoning、随后才补写。
- 45 秒流式采样中，SQL reasoning 连续输出时思考入口稳定存在。
- 任务完成时展开内容会被主动收起，这是 `62f6918b` 引入的既定行为；实测约 76.5 秒时按钮从“思考中”切换为“思考过程”，按钮本身仍存在。这与并发窗口导致的整块隐藏是两个不同现象。

## 建议修复方向

1. 以记录自身的任务状态作为 `thinkingActive` 权威来源，而不是“全局 isTyping + 必须是最后一条记录”。每个未终态 `task_id` 对应的记录都应保持生成态，直到该任务成功、失败或停止。
2. 明确同一会话是否允许并发提问。如果禁止，应在 `sendMessage` 的核心入口和后端任务创建边界统一拒绝重复提交，不能只依赖按钮禁用；如果允许，必须完整支持每条记录独立的 loading、停止和恢复状态。
3. 移除或修正无效的 `_loading` 双向包装，使 `BaseAnswer` 接收真正独立、可追踪的任务 loading 状态。
4. 增加回归测试：旧记录仍在运行时追加新记录、首个 reasoning 到达前的空窗口、两个任务交错完成、页面恢复/多标签页，以及完成时仅收起内容但入口不消失。
