# 归因配置编译内置浏览器验收（2026-09-30）

环境：当前 linked worktree `D:/AIWork6/release_1.3.0`，分支 `release/release_1.3.0`。本地 5173、8000、8001 和一个使用 `local-DONGJINCHAO-release_1.3.0` 队列的 Worker。没有修改前端页面代码。

浏览器：Codex 内置浏览器，使用已登录账户在绑定工作空间 gig 的现有归因页面操作。

## 成功路径

创建并保存测试看板“归因编译验收-20260930”，图表“归因编译 · 次数验证”。

- 配置：用户主体、UserRegister 目标、UserLogin 触点、线性/当天/总次数、包含直接转化。
- 日期：2026-09-02 至 2026-09-29，最近可用业务日期窗口 28 天。
- 生成：625ms / 640ms，两个成功请求均 `llm_calls=0`、`http_attempts=0`、`network_retries=0`。
- 真实查询：64,501ms，成功返回 2 行和 8 个既有业务列。UserLogin 总触发数 1741，目标贡献为 0；直接转化目标数及贡献值 200，贡献度 100%，无真实触点，有效触发率 NULL。
- 配置变更后的重新生成：恢复线性/次数配置后成功，缓存预览 256ms。
- 应用到画布、保存成功、重新加载、从看板入口重开。重开后的服务端预览日志显示 `status=success, row_count=2, field_count=8, cache_hit=True, elapsed_ms=227`，图表显示相同两行。

保存的看板入口：`http://127.0.0.1:5173/#/dashboard/index?resourceId=8db1ddd67a4e4d4186890948d758a78d&dashboardMode=my`。

## 明确拒绝路径

- 首次归因：当前工作空间缺少稳定排序角色，编译明确拒绝。在现有“查看配置 Agent 建议”中可见 `metadata.event_id：首次/末次需要 event_id 或 event_sequence 稳定排序字段以处理同时间触点。`，141ms，`llm_calls=0`。
- 线性平均值：选择合法数值字段后，编译明确拒绝。在同一建议窗口可见 `attribution.targetMetric.aggregation：线性归因仅支持次数和求和；均值、极值及去重数没有配置分摊口径，请选择首次/末次归因。`，125ms，`llm_calls=0`。
- 首次/末次在具备稳定排序角色的数据集上的真实计算，由 PostgreSQL 和当前 MySQL 兼容引擎的合成数据用例验证；没有为了页面验收添加或伪造当前工作空间元数据。

## 证据与范围

- `.codex-runtime/attribution-browser-preview.png`：现有页面配置与数据预览。
- `.codex-runtime/attribution-browser-saved.png`：重开后的看板。
- `.codex-runtime/attribution-saved-preview.png`：保存后全屏表格。
- `.codex-runtime/attribution-linear-avg-error.png`：用户可见的线性指标限制提示。
- `.codex-runtime/backend-replicas/backend-8000.err.log`：运行记录；不提交运行日志。

编译耗时与数据库执行耗时分开记录；取消 LLM 并不使真实明细匹配查询变成常数时间操作。当前验收是单触点类型、无分组的页面链路；其他归因方式、聚合、关联属性、NULL 分组及微秒边界由自动化和真实引擎测试覆盖。

最终相关综合测试：675 passed、1 个此前已有的间隔模型测试失败。日志 `.codex-runtime/attribution-final-regression.log`。唯一失败：`test_property_sql_graph.py::test_workspace_filter_is_shared_by_manual_analysis_models[interval]`。

本地解析配置复核：`LLM_REQUEST_TIMEOUT=180`、`LLM_TASK_MAX_WAIT_SECONDS=900`、`LLM_MAX_RETRIES=1`。
