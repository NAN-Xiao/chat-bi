# 留存分析确定性 SQL 编译

界面约束更新（2026-09-29）：按用户要求保留原有前端界面，撤回分组入口隐藏、按钮及等待文案调整；后端确定性编译、接口调用和数据处理修复保留。下方浏览器记录为当时的历史验收证据。

## 行为

看板留存分析使用 `RetentionSqlPlan` 和固定 Cohort CTE 模板生成 SQL。
生成成功、输入错误、编译错误、SQL 校验失败均不创建 LLM；修复路由及修复节点均关闭留存的模型调用。
其他模型的生成策略不变。既有 SQL 明细编辑/执行和已保存图表保留。

- 每个自然日发生初始事件的主体组成该日 Cohort，不自动解释为历史首次。
- 输出 `cohort_date, cohort_size, day_0 ... day_7`，比例为 0–100。
- 观察截止来自看板日期参数；未成熟为 NULL，成熟无回访为 0。
- 初始事件先按日期、主体及启用的关联键去重；分母独立统计。
- 关联属性只匹配时，在最终主体粒度再次去重；作为分组时输出 `related_property`。
- NULL 关联属性不互相匹配，但不删除初始 Cohort；结果维度连接保留 NULL 分组。
- 同时展示只连接去重后的回访资格键；原始事件明细不去重。COUNT/SUM/AVG/MIN/MAX/COUNT DISTINCT 在最终 Cohort 粒度计算，避免累加日均值或每日去重数。
- 初始、回访筛选各自生效；强制表筛选按事件来源分别应用。用户全局筛选引用不兼容的跨表字段时明确拒绝，不猜测字段映射。
- 事件、JSON 属性、主体/时间角色均由当前工作空间授权元数据解析。跨表必须配置明确主体角色与 event_time 映射。
- 留存分组使用关联属性的分组开关；普通分组配置明确拒绝，前端保留原有分组入口及错误提示流程。

## 模块

- `backend/apps/dashboard/crud/retention_sql_plan.py`：原始输入检查、元数据解析、类型化不可变计划。
- `backend/apps/dashboard/crud/retention_sql_compiler.py`：封闭 SQL 模板、方言日期表达式、分母和同时展示聚合。
- `backend/apps/dashboard/crud/retention_sql_validation.py`：完整 AST 和原始日期占位符契约检查。
- `ai_sql_generator.py`：接入当前权限/元数据流程，保留公共只读、安全、字段、方言检查。
- 前端沿用原有按钮、等待状态与“配置 Agent 建议”界面文案；文案不改变后端零 LLM 编译策略。

复用现有属性编译器的授权字段/筛选解析器与事件属性类型规范化；没有加入业务表、事件名或指标口径特例。

## 独立编译接口与上下文（2026-09-29 补充）

为消除上下文阶段的远程 Embedding，属性、间隔、留存现在直接调用
`POST /api/v1/dashboard/sql_compile`。保持现有图表请求/响应字段，前端不再先请求 AI 生成时限。

内部链路为：

```text
sql_compile → compile_dashboard_sql
            → BusinessSqlContextService.build_for_compilation
            → get_compilation_table_schema
            → 配置计划 / 编译 / 校验
```

编译入口不接受 embedding 或模式开关，也不调用 `get_ai_table_schema`、`find_data_skills` 或 Tracking 提示拼装。
通过共享权限检查、工作空间字典校验和缓存 Schema 渲染保留数据源、工作空间、表、字段边界。
旧 AI 入口仅用于仍需模型生成的分析类型，其语义检索能力保留。
编译 API 只接受三个确定性模型；显式附加 Data Skill 返回配置错误，不静默忽略。

接口独立时限 60 秒，客户端 65 秒且不自动重放请求。取消后阻止后续节点；已经开始的同步元数据读取先安全收尾，再释放请求数据库会话，避免后台线程继续使用已关闭 Session。
页面沿用原有等待文案，查询预览是后续独立阶段。

本轮相关后端 364 passed，前端 API/生命周期 28 passed，`vue-tsc -b` 通过。
全量后端 2674 passed、35 skipped、7 failed，失败仍为下文已记录的既有项（本轮未提供 PostgreSQL 夹具 DSN，因此对应实际执行测试跳过；上一轮已实测）。

内置浏览器确认 HTTP `POST /api/v1/dashboard/sql_compile` 为 200：

- 上下文读取 148ms。
- SQL 生成与全部校验总计 328ms，LLM 调用 0。
- 数据预览 1530ms，20 行、12 列，未命中结果缓存。
- 此次启动后的请求日志无 `/embeddings` 请求。

证据截图 `.codex-runtime/compiler-api-browser.png`；测试日志 `.codex-runtime/compiler-final-focused.log`、`.codex-runtime/compiler-api-tests.log`、`.codex-runtime/compiler-api-full-suite.log`。

## 验证（2026-09-29）

工作树 `D:/AIWork6/release_1.3.0`，分支 `release/release_1.3.0`。

相关后端回归：409 passed。覆盖留存、执行图、既有看板生成/契约、属性与间隔编译。
前端生命周期、关联属性选项、主体默认值测试：36 passed；`npx vue-tsc -b` 通过。

PostgreSQL 实际 SQL 测试使用 READ ONLY 事务和 VALUES CTE，不创建或修改业务表；覆盖重复事件、六种聚合、关联分组、全局/事件筛选、四种日期类型、跨年、闰日、epoch 秒/毫秒和 timestamptz。
连接由显式 `RETENTION_TEST_POSTGRES_DSN` 提供；不设置时这部分测试跳过。

支持 PostgreSQL/MySQL/StarRocks/Doris 编译及解析。实际执行验证覆盖 PostgreSQL 和内置浏览器当前 gig 数据源；MySQL、Doris 未在各自独立实例执行，不能把解析通过当成实机验证。

### 全量回归的既有问题

从仓库根目录运行 `python -m pytest backend/tests -q --disable-warnings --tb=short`：2680 passed、12 skipped、7 failed。
其中以下 6 项使用 HEAD 版本生成器替换当前生成器后均复现：

1. `test_dashboard_platform_template_snapshot.py::test_materialize_platform_template_canvas_view_info_stores_query_snapshot`：测试会话替身缺少 exec。
2. `test_dashboard_revenue_analysis.py::test_revenue_prompt_plan_and_result_contract_keep_cohort_semantics`：旧收入 SQL 夹具缺少成熟窗口。
3. `test_dashboard_revenue_analysis.py::test_revenue_prompt_and_validation_require_displayable_cohort_date`：同类收入成熟窗口夹具。
4. `test_data_skill_sql_validation.py::test_check_sql_raises_shared_structured_validation_error`：预期异常未抛出。
5. `test_embedding_auto_backfill.py::test_ai_table_schema_uses_workspace_dictionary_without_cached_field_fallback`：JSON 表达式文本断言不一致。
6. `test_embedding_model_config.py::test_default_embedding_model_is_authorized_remote_model`：预期模型名与当前明确配置 text-embedding-v4 不一致。

另 `test_sync_xiuxian_sql_repair_skills.py::test_psycopg_backend_cas_and_verify_cover_description` 在全量运行中报凭据解密错误；该文件单独运行 22 passed，属全量运行状态相关问题，未声称已修复。

前端 `DashboardSqlEditor.analysis-model.test.mjs` 有 13 项旧源码断言失败。将其和所读取组件复制为 HEAD 版本后仍为相同 13 项失败；主要仍在父组件中寻找已拆到 `DashboardAnalysisModelForm.vue` 的模板。不扩展本次任务修改这些无关断言。

运行日志保留在 `.codex-runtime/retention-*.log`，不提交运行数据。

### 内置浏览器验证

在当前用户的 gig 工作空间创建独立验证看板：`留存编译器验证-20260929`，ID `fc40c5059b954939a70e7ea06896d1e7`。未改动已有业务看板。

已通过页面操作验证：

| 条件 | 观察结果 |
| --- | --- |
| 缺少初始事件 | 显示明确必填错误，不生成 SQL |
| 相同初始/回访事件 | 生成及执行成功；7 天 Cohort 数据，D0 为 100 |
| 同时展示 COUNT | 成功输出额外计数；不改变分母 |
| AVG 未选择属性 | 明确要求选择计算字段，清除旧预览 |
| AVG JSON 数值属性 | SQL 使用数值 JSON 提取及 AVG，实际执行成功 |
| 关联属性缺失 | 明确要求配置初始/回访属性 |
| 关联属性仅匹配、不分组 | SQL 含关联键，最终分母仍按主体去重，执行成功 |
| 关联属性作为分组 | 输出 related_property，按媒体来源拆分 Cohort，执行成功 |
| 回访事件过滤 | Organic 仅限制回访，其他组保留分母且成熟留存为 0 |
| 关联分组＋回访过滤＋JSON COUNT DISTINCT | 生成及执行成功；20 行、12 列，空匹配计数为 0 |
| 日期从过去7天切换上周 | 重新执行成功，结果起日变为 2026-09-21，成熟窗口随截止变化 |
| 应用、保存、重新打开 | 页面提示保存成功；重新打开仍显示组合图表、上周范围和实际数据 |

浏览器读取的生成 SQL 保存在 `.codex-runtime/retention-browser-generated.sql`。
已保存看板截图：`.codex-runtime/retention-browser-saved.png`。内置浏览器保留该验证看板页。

前端基线失败的完整测试名：

- `renders the analysis model selector before event metrics`
- `keeps property analysis isolated with property metrics, filters, and grouping`
- `keeps simultaneous and related-property controls while removing the red-box options`
- `reuses event metric aggregation behavior for simultaneous retention metrics`
- `adds rename and reused event-filter controls to both retention events`
- `provides ordered funnel steps with window and related-property controls`
- `keeps distribution analysis configuration and controls isolated from other models`
- `keeps distribution simultaneous event and aggregation on the same row`
- `keeps interval analysis isolated and exposes the reference controls`
- `keeps path analysis isolated and exposes event split and session controls`
- `keeps revenue analysis isolated with cohort, metric, cost, and observation controls`
- `keeps ranking analysis isolated with rank, tie, metric, and property controls`
- `keeps heatmap analysis isolated with event coordinates and map metadata`
