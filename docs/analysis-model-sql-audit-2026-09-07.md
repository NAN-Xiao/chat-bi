# 分析模型 SQL 生成检查（2026-09-07）

检查版本：`85d9a9ad`，分支 `release/release_1.6.0`，目录 `D:/AIWork5/chat-bi`。
本轮只读检查应用代码，新增本报告；依据 AGENTS.md 的文档例外未创建 linked worktree。未修改应用代码、配置、业务数据或服务。

## 结论

确认 3 类生成/校验问题。它们是通过人工构造 SQL、调用生产校验函数和执行合成数据查询复现的缺陷，不代表观察到了线上模型生成这些 SQL 的频率。

1. **9 个模型没有核验最终 SELECT 的真实输出列。** 属性、留存、漏斗、分布、间隔、路径、收入、排行榜和热力地图使用整段 SQL 的列名正则匹配。必需列仅在内部 CTE 中出现、最终只返回 `wrong_output`，仍然 `success=true`、`issues=[]`。前端随后按固定结果配置绑定列，存在生成成功但结果无法正常绑定的风险。归因模型已有最终 SELECT 输出检查；事件模型没有同一固定列协议，不计入这 9 个。
2. **排行榜校验未落实用户选定的排名规则。** 默认规则下，合法的 `ROW_NUMBER() OVER (ORDER BY ranking_value DESC, ranking_entity)` 被拒绝；配置 `dense + desc` 时，`RANK + DESC` 和 `DENSE_RANK + ASC` 却均被放行。原因是只检查全文包含 `RANK` 或 `DENSE_RANK` 和 `OVER`，没有检查输出 `rank` 的实际窗口函数、方向及次级排序。
3. **间隔分析混淆普通 MySQL 与 AnalyticDB 的函数能力。** 提示词和校验器都强制普通 MySQL 使用 `APPROX_PERCENTILE`。MySQL 8.4 标准内置函数没有该函数，AnalyticDB 提供它；普通 MySQL 会因此生成不可执行的查询，正确的其他实现又无法通过当前校验。此项通过代码与官方文档确认，未连接原生 MySQL 实测。

## 模型覆盖

后端注册 11 个模型；前端当前下拉框提供其中 10 个，热力地图未列入选项。

| 模型 | 本轮生产校验函数探针 | SQL 实际执行证据 | 页面控件/图表 |
| --- | --- | --- | --- |
| event / 事件 | 现有事件与公式回归通过，未发现新增问题 | 未调用在线 LLM、未执行真实业务 SQL | 未交互验证 |
| property / 属性 | 最终缺列未拦截 | SQLite 合成数据返回仅 `wrong_output` | 未交互验证 |
| retention / 留存 | 最终缺列未拦截 | SQLite 合成数据返回仅 `wrong_output` | 未交互验证 |
| funnel / 漏斗 | 最终缺列未拦截 | SQLite 合成数据返回仅 `wrong_output` | 未交互验证 |
| distribution / 分布 | 最终缺列未拦截 | SQLite 合成数据返回仅 `wrong_output` | 未交互验证 |
| interval / 间隔 | 最终缺列未拦截；MySQL 函数规则错误 | PostgreSQL 17.10 合成数据返回仅 `wrong_output` | 未交互验证 |
| path / 路径 | 最终缺列未拦截 | SQLite 合成数据返回仅 `wrong_output` | 未交互验证 |
| revenue / 收入 | 最终缺列未拦截 | SQLite 合成数据返回仅 `wrong_output` | 未交互验证 |
| attribution / 归因 | 专项结构与 SQL 等价性测试 64 项通过 | 现有 SQLite 等价性测试 | 未交互验证 |
| ranking / 排行榜 | 最终缺列未拦截；正确 SQL 误拒；错误排序规则漏检 | SQLite 合成排名结果见下 | 未交互验证 |
| heatmap / 热力地图 | 最终缺列未拦截 | SQLite 合成数据返回仅 `wrong_output` | 下拉入口当前未列出 |

## 最小复现

生产入口均为 `backend/apps/dashboard/crud/ai_sql_generator.py` 中的 `_node_validate_sql`。探针隔离检查 SQL 校验阶段，没有绕过业务权限去执行业务查询；合成 SQL 只读取 CTE 常量。

### 最终输出缺列

漏斗示例：

```sql
WITH detail AS (
    SELECT 1 AS step_order, 'step' AS step_name, 1 AS step_count,
           1.0 AS step_rate, 1.0 AS step_conversion_rate,
           0.0 AS step_dropoff_rate
)
SELECT COUNT(*) AS wrong_output FROM detail;
```

用 `normalized_config={"analysis_model":"funnel"}` 和 `sql_dialect="postgres"` 调用 `_node_validate_sql`，应报告漏斗必需结果列缺失，当前却成功。其他 8 个模型以同样方式在 CTE 内保留必需列和相关聚合/窗口函数，而外层不输出这些列。

间隔模型的 PostgreSQL 实测使用以下完整查询：

```sql
WITH sample AS (SELECT 1 AS entity_id, 5 AS interval_seconds),
detail AS (
    SELECT CURRENT_DATE AS interval_date,
           COUNT(DISTINCT entity_id) AS entity_count,
           COUNT(*) AS interval_count,
           MAX(interval_seconds) AS max_interval_seconds,
           PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY interval_seconds) AS p75_interval_seconds,
           PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY interval_seconds) AS median_interval_seconds,
           PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY interval_seconds) AS p25_interval_seconds,
           MIN(interval_seconds) AS min_interval_seconds,
           AVG(interval_seconds) AS avg_interval_seconds
    FROM sample
)
SELECT COUNT(*) AS wrong_output FROM detail;
```

校验结果：`success=true, issues=[]`；真实结果：列 `wrong_output`，行 `[(1,)]`。

### 排名配置不一致

输入主体值为 `a=10, b=10, c=5`，先按主体 SUM 后进行窗口排名：

| 用户配置 | 实际窗口表达式 | 当前校验 | 实际名次 |
| --- | --- | --- | --- |
| default / desc | `ROW_NUMBER() OVER (ORDER BY ranking_value DESC, ranking_entity)` | 拒绝：必须使用窗口函数生成名次 | a=1、b=2、c=3，符合稳定默认排序 |
| dense / desc | `RANK() OVER (ORDER BY ranking_value DESC)` | 成功 | a=1、b=1、c=3，不符合连续名次 |
| dense / desc | `DENSE_RANK() OVER (ORDER BY ranking_value ASC)` | 成功 | c=1、a=2、b=2，方向反了 |

## 代码定位与修正层级

- 结果列：`ai_sql_generator.py:3649` 起的各模型 `_xxx_sql_result_issues`。应统一基于当前方言解析最终结果投影，包括合法的 CTE、子查询与星号展开；不要以全文字符串出现代替结果协议验证。
- 排行榜：`ai_sql_generator.py:4060`；配置规则来自 `ai_sql_generator.py:3183`。应追踪输出 `rank` 的表达式并与 `tieHandling`、`direction` 及稳定次级排序一致校验。
- 间隔方言：`ai_sql_generator.py:2960` 与 `ai_sql_generator.py:3912` 附近。应按真实引擎能力统一驱动提示词和校验，不把 MySQL 协议兼容视为函数兼容。
- 前端消费：`frontend/src/views/dashboard/common/DashboardSqlEditor.vue:6108` 附近按 `result_config` 设置固定字段；本轮没有声称实际观察到空白图表。

## 回归结果及命令

后端合计 **464 通过，1 失败**：

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_dashboard_ai_sql_generator.py backend/tests/test_dashboard_revenue_analysis.py backend/tests/test_analysis_assistant_sql_generation.py backend/tests/test_analysis_assistant_permissions.py backend/tests/test_analysis_assistant_time_policy.py -q -p no:cacheprovider
.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_dashboard_attribution_validation.py backend/tests/test_attribution_sql_equivalence.py -q -p no:cacheprovider --disable-warnings
```

唯一失败为 `test_ranking_prompt_plan_and_result_contract_keep_rank_semantics`，第 2637 行仍要求旧提示词片段 `attribution/ranking 字段信息`。这是旧文本断言失配，本身不构成 SQL 执行失败证据。该测试中的后续断言未运行。

前端 **21 通过，13 失败**（在 frontend 目录运行）：

```powershell
node --test src/views/dashboard/common/DashboardSqlEditor.analysis-model.test.mjs tests/dashboard-sql-builder-persistence.test.mjs tests/analysisEntityDefault.test.ts
```

失败集中在匹配组件源码的测试：测试仍只读取 `DashboardSqlEditor.vue`，但模型表单已拆至 `DashboardAnalysisModelForm.vue`，并且热力地图已不在模型选项中。不能把这 13 项直接解释为 13 个运行时 SQL 缺陷。配置持久化和分析主体初始化相关测试通过。

## 执行条件与未覆盖项

- SQL 执行使用 SQLite 内存合成数据，以及配置的系统 PostgreSQL 上只读事务中的常量 CTE；PostgreSQL 设置 `default_transaction_read_only=on` 与 5 秒语句超时，没有读取业务表或修改数据。
- 本地 SLG 演示库的已知凭据连接失败（密码认证失败），未尝试其他随机凭据。它没有参与本次业务数据验收。
- 未选择具体用户/工作空间/业务数据源，未重新调用在线 LLM，未逐模型点击页面，未执行真实业务 SQL，未验证保存/复制后的真实图表；没有浏览器截图或 trace。
- 权限结论限于现有自动化测试，不代表完成了真实账号的接口权限验收。
- 本报告确认的是生成规则和校验边界缺陷；其他业务口径错误、特定引擎错误和真实模型生成稳定性仍需在明确的数据源上下文中端到端验证。

## 方言核对来源

- [MySQL 8.4 官方聚合函数表](https://dev.mysql.com/doc/refman/8.4/en/aggregate-functions.html)
- [AnalyticDB 官方 APPROX_PERCENTILE 文档](https://www.alibabacloud.com/help/doc-detail/2579571.html)
