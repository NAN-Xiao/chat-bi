# 检查记录

## 只读来源核对

- 当前系统数据库 `custom_prompt` 中修仙工作空间活动 Skill 为 `255`、`257`、`269-279`，均绑定 `datasource_ids=[6]`。
- 业务 Skill `257`、`269-279` 共 45 个 SQL 代码块；日期契约 Skill `255` 单独保留，不作为业务术语整体迁移。
- 文档中的每个 `source_skills` 均能在系统数据库中解析到对应活动 Skill，示例 SQL 与来源 Skill 有可识别对象/字段/事件重合。

## 知识库 Markdown 验证

- `docs/knowledge-base/xiuxian_business_terms_sql.md` 包含 8 个 YAML 业务对象和 8 条代表性 SQL 示例。
- 8/8 YAML 对象可解析；每个对象包含 `term`、`aliases`、`definition`、`formula`、`constraints`、`related_objects`、`source_skills`、`examples`。
- 8/8 SQL 按 MySQL 方言解析为单条 `SELECT`/`WITH` 查询；日期使用看板参数占位符。
- 未发现密码、Secret、API Key 或用户数据；文档明确 `datasource_id=6`、产品过滤和 Data Skill 优先级边界。
- `git diff --check` 通过。

## 本轮审查修复

- 修复“英雄养成” SQL 缺少 `prod = 110000047` 的产品边界，避免同一数据源中其他产品事件混入。
- 修复“实时充值人数” SQL 使用 `UTC_TIMESTAMP()` 绕过看板日期参数的问题，改为 `{{dashboard_end_yyyymmdd}}`，并明确当前自然日实时语义由调用方日期上下文保证。
- 将 8 个 YAML 对象的 `related_objects` 合并为“表 + fields + json_paths”单一对象，避免解析后表、字段和 JSON Path 之间失去关联；英雄对象同时补充 SQL 实际使用的 `prod` 字段。

## 最终验证

- YAML：8/8 对象通过 PyYAML 解析；字段齐全，`related_objects` 结构可表达表字段和 JSON Path 关联。
- SQL：8/8 按 MySQL 方言解析为单条 `SELECT`/`WITH` 只读查询；均使用看板日期参数、允许的修仙表和 `prod = 110000047`。
- 来源边界：Skill `255`、`257`、`269-279` 均为活动记录且 `specific_ds=true`、`datasource_ids=[6]`。
- 凭证/跨数据源：未发现密码、Secret、API Key、flam/SLG 或基础设施地址；文档仅声明 `datasource_id=6`。
- `git diff --check`：通过（仅有 Git 的 LF/CRLF 转换提示）。
- Lint/TypeCheck/Tests：本次仅修改 Markdown 知识库和 Trellis 检查记录，无运行时代码、类型或测试目标；不适用。
