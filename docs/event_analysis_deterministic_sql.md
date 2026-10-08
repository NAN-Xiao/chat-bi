# 事件分析确定性 SQL 编译

2026-10-06。工作树 `D:/AIWork6/release_1.3.0`，分支 `release/release_1.3.0`。保留此前其他模型的未提交改动，本任务未提交或推送。

事件模型现在使用结构化配置、授权工作空间元数据和封闭模板生成 SQL。旧 `/dashboard/ai_sql_generate` 接口在后端转入编译，`/dashboard/sql_compile` 及直接服务调用同样支持事件模型。缺省模型沿用事件请求语义，明确的未知模型拒绝处理。

成功、配置失败、编译失败、结构校验失败均不调用 LLM；不读取模型配置，不构造生成 prompt，不召回 Data Skill 或 embedding。编译使用独立的 60 秒生命周期，并保留取消、断连和请求 Session 排空处理。其他分析模型的生成策略保持原有行为。

## 实现边界

- `event_sql_plan.py`：原始配置校验，事件字典、字段权限、JSON 来源和物理类型解析，不可变查询计划。
- `event_sql_time.py`：DATE、YYYYMMDD 数值/文本及有明确编码和时区的 timestamp 边界，日/周/月分桶。
- `event_sql_compiler.py`：每个基础指标独立过滤与聚合，完整维度组合并集，日期骨架，空值安全连接及外层公式。
- `event_sql_validation.py`：完整模板 AST、日期 token 对照；复用独立度量来源检查，并独立检查事实谓词和聚合粒度。即使模板生成函数被错误改写，独立检查仍能识别聚合、事件筛选及粒度错误。
- `ai_sql_generator.py`、`dashboard_api.py`：编译上下文、计划和编排接入；关闭事件 LLM 生成/修复；保留已有响应字段及图表类型。
- `sql_engine_executor.py`：`origin_column=True` 时保留驱动返回的明确输出列名，避免给 `adinfo.mediaSource` 等别名额外添加短名。该修复统一适用于要求原始列名的执行入口。
- `dashboard_service.py`：预览缓存增加结果格式版本，避免旧缓存继续带回重复短名列；旧键自然过期。

原有通用公式解析默认校验保持不变。事件图编排只在可信计划随后负责字段校验时使用公式语法解析；JSON 表达式由服务端授权映射构造，客户端无需提交表达式，提交时必须与可信映射一致。

## 统计和结果契约

1. 支持 COUNT、COUNT DISTINCT、SUM、AVG、MIN、MAX。COUNT 统计事件行数，不改为某个字段非空数。
2. 指标和公式原子指标独立聚合后再连接，保留相同金额的真实重复明细，不连接原始事件明细造成乘积。
3. 日期、工作空间强制条件、全局条件和指标内条件作用于每个输入。用户 OR 条件不能绕过工作空间条件。
4. 分组域来自选中指标有效输入的完整元组并集；不从其他事件补类别，不把各维度独立去重后做无依据的组合。
5. 有日期且无分组时补齐日期；有分组时只为存在的合法组合补齐日期。完全没有分组样本时返回空结果。NULL 分组使用空值安全连接。
6. COUNT/COUNT DISTINCT 缺桶为 0；其他聚合缺桶或全 NULL 样本保留 NULL。公式在聚合后计算，以 `NULLIF` 保护零分母，按配置小数位 ROUND。
7. 原始日期/分区列直接按对应参数过滤；timestamp 使用半开边界。趋势结果日期统一输出真实 DATE，参数采用 YYYYMMDD 不代表结果维度也应输出数值。输出列名称仍遵循配置。
8. 指标卡不输出日期维度，已配置日期范围仍约束事实。仅常量公式无分组时可输出日期序列或单值；无基础输入却配置分组时明确拒绝。
9. 保留日期、分组、指标、公式列名、展示名和图表类型。编译器直接生成最终列，不经过 LLM 输出键绑定。
10. 不支持的方言、近似模式、跨表关联、缺失/歧义事件、非法字段映射或无明确时间编码均明确报错，不调用模型兜底。

## 验证

- 最新全后端测试：**3415 passed、175 skipped、5 failed**。五个失败在修改前模块基线中复现，详见下方。
- 原始列名与缓存修复后的定向测试 **155 passed**；日期输出修复另有 **44 passed**，包括真实 PostgreSQL DATE 结果类型和只读 VALUES 数值测试。最终全后端运行已包含这些改动。
- 测试覆盖成功及失败零 LLM、两个 API、缺省模型、取消/超时、六种聚合、公式原子指标、JSON 权限、重复 ID、SQL 篡改、日期类型、空值和维度组合。
- 前端 805 个非忽略文件的路径/SHA256 核对：**0 个改动、0 个新增**。
- 内置浏览器及独立明细对账见 `docs/event_compiler_browser_test_20261006.md`。证据位于 `.codex-runtime/event-20261006/`。
- 用户提供账号后的最终重启复测已完成：真实 DATE 折线正常，双分组 336 格和折线单分组 280 格独立对账通过；保存重开后 SQL 逐字一致。本轮 3 次生成零 LLM 调用，无需追加产品代码修改。

既有失败：

```text
test_dashboard_platform_template_snapshot.py::test_materialize_platform_template_canvas_view_info_stores_query_snapshot
test_data_skill_sql_validation.py::test_check_sql_raises_shared_structured_validation_error
test_embedding_auto_backfill.py::test_ai_table_schema_uses_workspace_dictionary_without_cached_field_fallback
test_embedding_model_config.py::test_default_embedding_model_is_authorized_remote_model
test_property_sql_graph.py::test_workspace_filter_is_shared_by_manual_analysis_models[interval]
```

PostgreSQL 和当前授权 MySQL 兼容数据源进行了真实只读执行。StarRocks/Doris 仅有模板构造及方言解析验证。MySQL TIMESTAMP 缺少可确认会话时区执行协议时明确拒绝；不会猜测时区。历史保存 SQL 不批量改写，重新生成时使用新模板。
