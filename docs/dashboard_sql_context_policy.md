# 图表配置生成 SQL 的上下文策略

图表配置通过 `/dashboard/ai_sql_generate` 生成 SQL 时，仅采用平台级（`PLATFORM_PUBLIC`）Data Skill。工作空间级、个人级 Data Skill 和知识库文档不参与该流程。

## 生效范围

- 上下文收集：使用当前用户有权限的数据源、表字段元数据、事件字典、图表配置和平台级 Data Skill，不加载知识库。
- SQL 生成与修复：共用上述上下文，不注入知识库正文或知识库优先级规则。
- SQL 校验：保留结果契约、字段映射、方言和只读校验，不调用知识库冲突裁决；JSON 路径与当前配置冲突时明确报错。

平台级 Data Skill 仍受原有启用状态、可见性、用户停用偏好、工作空间排除列表、数据源范围、所需表权限和使用场景限制。“仅平台级”不表示无条件加载所有平台 Skill。

平台 Skill 可以通过 `<!-- data-skill-analysis-models: ["funnel"] -->` 声明适用的分析模型。检索服务在相关性排序、显式 Skill 选择和 Schema 构建之前完成模型过滤：完全未出现保留元数据名的 Skill 仍为通用 Skill；出现保留名时必须且只能有一个完整、合法的 JSON 数组声明，否则关闭该 Skill 并记录告警；合法数组只对命中的模型可见；缺少当前模型时不加载。显式 `data_skill_id` 不能绕过模型范围。已组装提示词进入模型前还会执行一次相同过滤，防止调用方漏传模型上下文；命中当前模型的专用 Skill 会完整保留，通用 Skill 单独使用提示词字符预算。

作用域过滤在相关性排序和同名 Skill 覆盖处理之前执行，避免工作空间或个人规则替换平台规则。调用方传入非平台 Skill ID 时，该条目不会进入上下文，也不会自动替换成其他 Skill。没有匹配的平台 Skill 时，继续依据显式图表配置和授权元数据处理，不回退到知识库或其他作用域 Skill。

## 维护入口

- `backend/apps/chat/curd/custom_prompt.py`：`find_data_skills(..., platform_only=True)` 在召回前限定条目作用域。
- `backend/apps/datasource/crud/sql_engine.py`：`BusinessSqlContextService.build(..., platform_data_skills_only=True, analysis_model=...)` 将平台作用域与模型范围传给共享 Skill 服务。
- `backend/apps/dashboard/crud/ai_sql_generator.py`：图表配置入口固定启用平台级限制，并传入当前 `analysisModel`。

共享服务的默认策略仍允许当前用户可用的其他作用域 Skill。智能问数、分析助手等入口的知识库及 Data Skill 策略保持原有行为。

## 配置驱动的 SQL 契约

图表生成的必需规则不依赖 Data Skill。`sql_generation_rules.py` 根据实际方言和明确的时间配置构建 `sql_plan.sql_rules`，与完整的图表结果契约一起提供给首次生成和每轮修复。这些规则不经过 Data Skill 的文本截断。

- 事件分析契约包括配置的事件、来源表、聚合函数、计算字段、指标内/全局筛选、分组、输出名称及公式 IR；校验沿结果列血缘检查聚合和筛选，防止其他指标或可选连接来源的条件冒充当前指标的条件。
- 分组维度域取已应用配置事件、时间和筛选条件的指标输入并集；不能从同表其他事件扩大用户或其他维度集合。集合查询的每个分支都参与来源校验，避免无关零值组合膨胀并触发预览行数上限。
- 事件分析的模型输出使用生成前声明的内部列键（例如 `chart_metric_1`）；`sql_output_bindings.py` 只在键集合完整且唯一时，通过 AST 将外层输出绑定到用户配置的名称，并按方言引用标识符。不会按位置、相似名称或空格归一化猜测字段。字段绑定后仍须通过完整语义校验；内部来源列和字符串字面量保持原义。
- `event_grain_validation.py` 检查指标的事实聚合粒度及日期/维度连接键，禁止将全区间总量重复填入每天，或增加未配置分组。前端不再用 SQL 字符串中的 COUNT/SUM 正则代替后端契约校验；明确的后端失败结果不会进入预览。
- 日粒度的 MySQL 兼容源和 PostgreSQL 使用程序构建的非递归日期骨架，动态覆盖起止日期。事件/属性趋势必须保留骨架定义及日期行，不能改成固定 15/31 天、添加结果 LIMIT，或通过 INNER JOIN/外层事实筛选丢失无数据日期。
- 日期骨架目前支持 `date`、`yyyymmdd_number`、`yyyymmdd_text`。其他方言、timestamp 和其他粒度保留原有生成路径，并明确提供能力说明，不能静默转换配置。
- 语法解析失败时只报告解析位置及原因；解析成功后才检查事件、字段和结果语义。独立错误合并反馈；相同 SQL 和相同错误再次出现时停止无效自动修复。
- MySQL 兼容源的裸 `ORDER BY` 项可引用唯一输出别名，即使输入连接中有同名列；此规则不扩展到 WHERE、GROUP BY、聚合参数或重复输出别名，真实来源歧义仍会被拦截。
- 未配置的业务表、事件、产品、默认时间窗口和指标口径不得写入公共规则。工作空间 Data Skill 不会因生成或修复失败而自动启用。

## 其他分析模型的结果正确性

- 工作空间明确配置的字段角色与字段自身角色，在授权字段过滤后合并到共享 Schema，并保留时间编码。角色冲突明确报错；不根据字段名猜测事件时间。
- 留存、收入的 `day_N` 必须以看板结束参数判断成熟窗口。未成熟返回 NULL，已成熟且没有行为或金额时才返回真实零。
- 同期群在关联后续事件前，按同期群日期、主体及配置分组/关联属性形成唯一粒度。收入不能用支付明细去重或 `SUM(DISTINCT 金额)` 掩盖关联放大。
- 漏斗以配置的真实事件时间和主体逐步匹配，时长窗口始终锚定首步；当天窗口使用同一自然日，不能用分区日期代替滚动时长。
- 漏斗模型会收到平台级 AnalyticDB `window_funnel` 参考 Skill。只有数据源明确支持该函数且未启用关联属性时才使用原生实现；其他情况继续生成等价逐步 CTE。原生实现按配置主体的精确粒度计算最大完成深度，真实事件时间、主体、步骤事件和分区范围必须来自同一次事件扫描；事件步骤必须是正向等值条件。逐步 CTE 必须为每个候选首步保留独立窗口，不能先按主体 `MIN(event_time)` 压缩为唯一最早首步，再在后续步骤按 `entity_id + first_step_time` 匹配并按主体取最大深度。主体最大深度聚合层不得通过 `HAVING`、`QUALIFY`、`LIMIT` 或 `OFFSET` 裁剪主体。第 N 步人数必须由最终 `step_count` 血缘中的 `COUNT(CASE WHEN max_depth >= N THEN 1 END)` 产生；`step_counts` 必须使用 `UNION ALL` 完整保留每个配置步骤，集合节点、计数分支和后续投影不得通过额外连接、筛选、限行或分组改变主体或步骤粒度。MySQL/AnalyticDB 不在该聚合结果上使用 `MAX/LAG ... OVER` 值窗口函数，而以 `step_counts` 标量子查询或等价单行关联取得第一步与上一步人数。窗口秒数来自当前配置；timestamp 必须解析到 Schema 的 `role=event_time` 字段并提供 BIGINT 秒值，毫秒字段除以 1000 后显式转为整数，TIMESTAMP/DATETIME 转换必须使用全体事件共享的固定起点。YYYYMMDD 日期字段必须在同一事件扫描上同时受起止看板参数约束，条件可位于 WHERE 或必然生效的 INNER JOIN ON 中，不能由旁路扫描或无关 CTE 代为满足。最外层 SELECT 必须按固定顺序输出六列，步骤编号与计数保持同一血缘；第一步人数为 0 时三个比率均返回 NULL。Skill 同时提供正向可执行模板和反向错误示例；其中 `event.uid/event.event/event.time/event.dt/event.prod`、产品值和事件名只是可替换示例，不是平台硬编码口径。
- 路径在会话内按完整事件时间生成一次步骤序号，后续相邻边复用该序号，防止并列时间记录被重新排列。名称排序、倒序或常量排序不满足事件顺序协议。只有第1步匹配配置初始事件的会话才能参与结果，筛选必须按完整主体、会话及配置分组键连接到实际边数据，不能仅在无关CTE或事件集合中出现配置事件。
- 间隔日期沿实际时差起点的事件行传递，跨午夜配对仍归到起点日。相邻自连接、LAG/LEAD 和不同事件配对均检查日期与起点的来源一致性。
- 日期来源校验区分数值来源与排序/条件依赖。按日期排序得到的行号、日期计数和条件聚合值是数值；原始 YYYYMMDD 经别名、窗口或 CASE 返回后，仍禁止直接进行日期加减。

真实页面回归除了生成和执行，还须与独立明细计算比较；预览非空不能证明统计口径正确。隐藏模型须单独报告后端测试范围，不计作浏览器通过。

## 请求时限与取消

`sql_generation_lifecycle.py` 使用请求级上下文与单调时钟落实 `LLM_TASK_MAX_WAIT_SECONDS` 总预算。前端从认证接口 `/dashboard/ai_sql_generation_limits` 获取预算，设置为总预算加 5 秒的网络等待时间，不再固定为 180 秒。`LLM_REQUEST_TIMEOUT=120`、`LLM_TASK_MAX_WAIT_SECONDS=900`、`LLM_MAX_RETRIES=1` 的本地配置不变。

关闭编辑器、取消或开始新的操作会中止旧操作；操作身份和 AbortSignal 持续覆盖生成、预览和草稿写回，防止旧结果污染新图表。后端在请求体解析后直接等待 ASGI 断连消息，适用于应用中的多层 `BaseHTTPMiddleware`。已进入同步线程的驱动 I/O 无法由 asyncio 强行终止，但取消后不会继续启动修复或写回页面。

日志区分模型轮次 `llm_calls`、可观测 OpenAI 客户端 HTTP 请求数 `http_attempts` 和 SDK 重试数 `network_retries`；均携带 `request_id`。未暴露 OpenAI HTTP 客户端的其他模型只统计模型轮次，不将其零个可观测 HTTP 请求解释为未调用模型。SQL 校验通过不等同于数据库执行通过。

## 回归验证

对应测试覆盖自动召回、显式 Skill ID、同名覆盖、模型选择、数据源和工作空间排除条件，以及 SQL 生成、修复和校验不使用知识库。

在 `backend` 目录运行：

```text
python -m pytest tests/test_custom_prompt_datasource_scope.py tests/test_sql_engine_context.py tests/test_dashboard_ai_sql_generator.py tests/test_dashboard_sql_contract.py tests/test_dashboard_sql_output_bindings.py tests/test_event_grain_validation.py tests/test_dashboard_sql_generation_rules.py tests/test_dashboard_sql_generation_lifecycle.py tests/test_dashboard_sql_generation_api.py tests/test_dashboard_sql_telemetry.py tests/test_sql_repair.py tests/test_knowledge_authority.py -q
```

在 `frontend` 目录运行：

```text
node --test src/views/dashboard/common/DashboardSqlEditor.generation-lifecycle.test.mjs tests/dashboard-sql-generation-api.test.mjs
npx vue-tsc -b --pretty false
```

日期骨架测试通过 SQLGlot 解析并在本地 SQLite 适配日期函数后执行，覆盖缺失日期补零、跨月、跨年、闰年及长于 31 天的范围。此测试不能代替各实际数据源的兼容性验证。
