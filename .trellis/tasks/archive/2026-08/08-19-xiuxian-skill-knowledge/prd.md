# 整理修仙空间 Data Skill 口径对应 SQL 示例知识库

## Goal

基于当前系统数据库中修仙工作空间（`datasource_id=6`）的活动 Data Skill，生成一份可上传到知识库的“业务术语与 SQL 示例”Markdown，按业务口径提供代表性 MySQL 查询示例。

## Requirements

- 只读核对 Skill `255`、`257`、`269-279` 的来源范围，不修改系统数据库或运行时配置。
- 将稳定业务概念拆成独立 BUSINESS YAML 对象，保留术语、别名、定义、公式、约束、关联表/字段/JSON Path、来源 Skill 和示例问题/SQL。
- SQL 使用看板日期参数，占位符不包含凭证或用户数据；每条示例必须是 MySQL 单条 SELECT/WITH 查询。
- 明确知识库内容仅为参考，不能覆盖当前数据源、权限、Schema、事件/JSON 映射或 Data Skill 执行约束；日期骨架和按日补零规则继续由 Skill `255` 执行。
- 文档不得跨数据源复用 flam 的表、产品标识或 SQL。

## Acceptance Criteria

- [x] 生成修仙专属 Markdown，覆盖 8 个代表性业务口径和 8 条 SQL 示例。
- [x] 8 个 YAML 对象均包含 `term`、`aliases`、`definition`、`formula`、`constraints`、`related_objects`、`source_skills`、`examples`。
- [x] 所有 SQL 按 MySQL 解析为单条只读查询，文档通过凭证/边界检查。
- [x] 记录修仙 Skill 来源和 `datasource_id=6`，不修改数据库记录。

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
