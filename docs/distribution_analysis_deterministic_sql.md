# 分布分析确定性 SQL 编译

实施日期：2026-09-29。工作树 `D:/AIWork6/release_1.3.0`，分支 `release/release_1.3.0`。本次未提交、推送或重启服务。

后续更新：用户要求内置浏览器测试国家主体 + UserRegister 后，已按 runbook 重启本地栈并完成三种区间的实际生成、执行、保存及重载，修复了日期元数据 `yyyyMMdd` 大小写校验问题。详见 `distribution_country_browser_test_20260929.md`。下文未重启/未联调的描述是首次实施阶段的历史记录。

## 接口与现有页面

新增 `POST /api/v1/dashboard/distribution/sql_compile`，请求沿用 `DashboardAiSqlGenerateRequest`：datasource、context、chart_type、title、intent、data_skill_id。context 必须明确指定 `analysisModel: distribution` 或等价的现有 analysis_model 字段；其他模型返回 400。附加 data_skill_id 在配置编译上下文中被拒绝。

响应沿用 `DashboardAiSqlGenerateResponse` 和既有 distribution_table 的 result_config，不新增前端必传版本字段或保存要求。

现有页面继续调用 `/api/v1/dashboard/ai_sql_generate`，由后端对 distribution 分流到同一个编译服务；通用 `/api/v1/dashboard/sql_compile` 同样支持 distribution。所有路径共享权限检查、60 秒编译预算和取消收尾，编译失败不进入模型修复。独立服务函数为 `compile_distribution_dashboard_sql`，它及旧生成服务入口也不会绕回 LLM。

前端仍可读取 AI limits；这是读取已有配置，不是调用模型。本次没有修改任何前端文件。实施前后比较全部 805 个受跟踪/非忽略的前端文件，内容一致，无新增或删除。

## 模块与行为

| 文件 | 职责 |
| --- | --- |
| `backend/apps/dashboard/crud/distribution_sql_plan.py` | 原始输入、授权字段、事件字典、JSON 映射、日期/事件时间、强制筛选与不可变计划 |
| `backend/apps/dashboard/crud/distribution_sql_aggregates.py` | 每主体聚合、连续分位数、总体方差/标准差、同时展示的可合并统计及按桶去重 |
| `backend/apps/dashboard/crud/distribution_sql_compiler.py` | 固定 CTE、全窗口分桶、日期/分组分母、既有结果列 |
| `backend/apps/dashboard/crud/distribution_sql_validation.py` | 完整计划 AST 与精确参数契约、独立 population_issues 检查 |
| `backend/apps/dashboard/crud/ai_sql_generator.py` | 接入共同上下文、graph、禁止模型回退、维持旧响应 |
| `backend/apps/dashboard/api/dashboard_api.py` | 新专用路由、旧接口后端分流、共用生命周期 |

首版仅使用当前工作空间授权默认事件表、日粒度和分布表输出。主体仅来自 entityField，分组仅来自 groups；不根据 uid、country 等字段名推断额外维度。工作空间元数据、表强制条件和执行时权限检查保持现有边界。

主链路先按日期+全部分组+主体聚合，再计算该分区主体总数，再进行分桶。主体为 NULL 的明细不参与；NULL 分组可保留并正常匹配。

- auto：全查询窗口统一 min/max，差值小于 12 逐值分桶，否则 12 个等宽桶；所有值的桶序号限制在 1–12，末桶包含最大值。
- discrete：每个不同数值一个桶，统一排序，不将小数取整。
- custom：2–20 个有限、递增的数字边界，保留下溢/上溢桶，使用左闭右开边界，末边界归上溢桶。
- 主属性聚合全 NULL 时保留“无有效值”桶；count_distinct 全 NULL 为 0。未参与事件者不进入人群。
- 方差和标准差是总体统计；分位数采用连续线性插值；重复值保留其频次。
- 同时展示均值按有效事件条数加权；同时展示去重数在桶内对实际值去重，不相加各主体去重数。
- 主 eventFilters 仅用于主事件，全局条件与工作空间强制筛选作用于两个事件源；不可解析或越权时明确失败。

结果列保持：`distribution_date, group_1...group_n, total_entities, interval_order, interval_label, entity_count, entity_rate[, simultaneous_value]`。entity_rate 为 0–100 百分数，分母由每主体一行的完整分区计算。

## 验证记录

本次进行了配置、元数据、聚合数值、分桶、AST 篡改、graph、三个服务/API 入口、真实 ASGI HTTP 请求、权限拒绝和取消测试。取消测试覆盖同步元数据读取完成前不释放请求会话；LLM/提示/Embedding/Skill 依赖使用调用即失败的替身验证。

PostgreSQL 17.10 使用授权连接，在 READ ONLY 事务中执行内联 VALUES，不创建或修改业务表。45 项原生测试覆盖全部界面属性聚合、NULL、日期与分组、同时展示、epoch 秒/毫秒、无时区/带时区时间、不同会话时区、结束边界与高精度边界。

独立只读审查发现并修复两个问题，5 项原生回归先失败后通过：

1. integer/bigint 的桶跨度及分位数插值中间减法溢出：在减法前提升计算类型。
2. 浮点值略小于最大值仍因舍入进入第 13 桶：约束整个等宽桶表达式的上限，末桶标签与序号一致。

前端只读运行原有 Node 回归，40 项通过；文件内容快照验证保持一致。

相关后端回归包括全部 `test_distribution*.py`，以及 dashboard AI generator、SQL contract/API、compilation context、SQL engine context 和 property/retention/funnel/interval graph。最终为 **611 passed、12 skipped、1 个已存在失败**（另有 235 条依赖/环境警告）。这不是全仓库测试套件。结果记录于本任务 `.superpowers/sdd/2026-09-29-distribution-sql-compiler/final-combined.log`。

其中存在一个本次实施前已有的失败：`test_property_sql_graph.py::test_workspace_filter_is_shared_by_manual_analysis_models[interval]`，`KeyError: filters`。已使用实施前 ai_sql_generator.py 副本单独复现，未修改该无关测试或间隔实现。

可重复执行：

```powershell
# DISTRIBUTION_TEST_POSTGRES_DSN 需显式设置为授权只读测试连接，不在命令记录中输出凭据。
.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_distribution_sql_plan.py backend/tests/test_distribution_sql_aggregates.py backend/tests/test_distribution_sql_compiler.py backend/tests/test_distribution_sql_validation.py backend/tests/test_distribution_window_population.py backend/tests/test_distribution_sql_graph.py backend/tests/test_distribution_sql_compile_api.py backend/tests/test_distribution_existing_client_contract.py backend/tests/test_distribution_sql_postgres.py backend/tests/test_distribution_sql_engine_integration.py -q --disable-warnings --tb=short

# 在 frontend 目录，只运行原有测试，不写前端源码。
node --test tests/distributionTable.test.ts tests/dashboard-sql-generation-api.test.mjs src/views/dashboard/common/DashboardSqlEditor.generation-lifecycle.test.mjs src/views/dashboard/common/DashboardSqlEditor.distribution-pivot.test.mjs
```

## 能力限制与保留事项

- MySQL/AnalyticDB、StarRocks、Doris 有编译/解析覆盖；本次没有配置原生测试 DSN，12 项相应执行测试跳过，不能视为已实测这些引擎。
- 非 PostgreSQL 原生 TIMESTAMP 会随执行会话时区变化，而当前分布执行链路没有专属会话时区契约，因此明确拒绝。可使用元数据明确的 DATETIME/epoch；不能猜测连接时区。与字段声明冲突的日期/时间编码同样拒绝。
- 前端发送前已默认化或删除的原值，后端无法恢复；现有动态表把非计数同时展示 NULL 显示成 0 的行为也保留。SQL/API 保持 NULL，不以文本或伪列绕过页面。
- 公共执行层结果行数上限及完整性标记问题仍是已有限制；本次不以隐藏 LIMIT 或删减主体规避。
- 未指定业务数据源，未执行实际业务规模 EXPLAIN/性能验收；所有数据库验证均为有界合成样本。
- 未重启现有本地栈，因此没有宣称运行中的后台已加载新接口，也未完成浏览器新旧保存图表的现场联调。已完成注册路由的 ASGI HTTP 验证和既有前端行为测试；运行环境需要在按仓库 runbook 重启后验证。
- 工作树包含其他任务的未提交修改。本次保留这些修改，不执行整体暂存、提交、合并或清理工作树。
