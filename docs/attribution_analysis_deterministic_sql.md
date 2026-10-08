# 归因分析固定 SQL 模板与配置编译器

归因沿用现有前端页面、DashboardAiSqlGenerateRequest 与 attribution_table 结果协议。既有 `/api/v1/dashboard/ai_sql_generate` 和 `/api/v1/dashboard/sql_compile` 均进入同一确定性编译图，不创建模型、不构造模型提示词、不检索 Data Skills 或 embedding，也不在失败时调用 LLM 修复。

## 计算范围

- 首次、末次支持 count、sum、avg、max、min、count_distinct；后四种按获选目标原值聚合，贡献度分母从参与归因的目标明细独立聚合，各行贡献度不保证相加为 100%。
- 按本次用户确认，线性仅支持 count、sum；非可加指标明确拒绝，不推断分摊公式。
- 每条目标独立匹配同一主体的先前触点；当天按业务自然日计算，时长窗口以精确时间计算。触点扫描起点向前扩展，日期分区边界同步扩展，目标日期范围保持原配置。
- 查询内目标与触点编号在关联前创建，保留每次实际事件。排序包含影响匹配/聚合的值，完全相同的重复明细仍是独立事件。
- 首次/末次需要已授权的 event_sequence 或 event_id 排序元数据。重复排序键、空排序键或范围内空事件时间触发原子错误，不返回部分成功数据。
- 目标/触点分组分别解析，NULL 分组使用空值安全关联。总触点统计独立于归因获选统计，保留零贡献行。关联属性为每个触点事件独立的类型列，任何一侧 NULL 均不匹配。
- 分母只按目标侧分组，从目标明细计算，避免被触点多对多关联或触点分组放大。
- 直接转化只包含无合格触点的目标，触发计数为零，有效触发率为 NULL。

## 模块职责

| 模块 | 职责 |
|---|---|
| attribution_sql_plan.py | 严格输入、事件字典与授权元数据解析、类型/窗口/分组验证 |
| attribution_sql_compiler.py | 固定 CTE、方言时间表达式、独立触点/贡献/分母及数据冲突检测 |
| attribution_sql_validation.py | 固定模板 AST 等价与最终输出列验证 |
| attribution_execution_contract.py | SQL 签名、工作空间与数据源边界、元数据版本、日期/时区/输出校验 |
| ai_sql_generator.py | 编译图和旧接口接入、失败关闭、沿用结果配置 |
| analysis_execution_contract.py | 共用预览、查询及保存执行协议派发 |

SQL 包含签名执行协议与内部 `__attribution_data_error` 列。公共执行器验证后剥离该列，页面仍收到既有 8 个业务列及所配置的 group_N 列。编辑 SQL 使它偏离编译结构时明确要求重新生成。

## 当前能力边界

- 事件使用当前工作空间单一授权事件表；缺少跨表角色配置时明确拒绝，不猜测关联。
- PostgreSQL 支持事件 epoch 秒/毫秒、有时区时间戳及声明源时区的无时区时间戳。无时区源在查询范围含夏令时切换时拒绝；检查范围包含向前扩展的窗口。
- MySQL 及本地已验证的 MySQL 兼容引擎支持事件 epoch 秒/毫秒和自然日 date/yyyymmdd 参数。使用显式 CONVERT_TZ 和秒级自然日边界，事件匹配保留十进制秒精度。暂不支持 MySQL 时间戳范围参数和非 epoch 事件时间。
- 时区转换能力在同一查询连接验证。显式转换查询无需读写会话时区；依赖原生 MySQL TIMESTAMP 会话语义的其他分析查询继续使用 UTC 会话约束。
- 未验证的方言、非法配置、字段权限、JSON 映射、关联类型和排序元数据错误均明确拒绝，没有 LLM 或字段替换回退。

## 验证

新增测试覆盖编译器、生成图、真实 PostgreSQL VALUES 计算、实际 MySQL 兼容引擎的合成 CTE、签名执行协议及公共执行链。数据库验证没有创建或修改业务表。

2026-09-30 最终相关综合回归：675 passed、1 failed（235 条依赖/环境警告）。唯一失败为已有 `test_property_sql_graph.py::test_workspace_filter_is_shared_by_manual_analysis_models[interval]`，间隔配置被输入校验拒绝后测试仍访问 filters；本次未修改该用例或间隔配置逻辑。不是全仓库测试结果。

日志位于 `.codex-runtime/attribution-final-regression.log`；浏览器记录见 `docs/attribution_compiler_browser_test_20260930.md`。本轮没有修改前端页面代码。
