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
