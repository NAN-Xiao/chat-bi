# 补充修仙工作空间级 Data Skill 核查

## Goal

核对修仙租户全部活动 Data Skill 的可见性与数据源绑定，并把工作空间级覆盖范围补充到知识库文档。

## Requirements

- 只读查询修仙租户 `7482727237662281728` 的 `custom_prompt`，不修改数据库。
- 说明 `ADMIN_PUBLIC`、`USER_PRIVATE` 和平台公共 Skill 的边界。
- 明确文档已覆盖修仙工作空间公开 Skill `255、257、269-279`；不复制私有 Skill `256、280`。

## Acceptance Criteria

- [x] 工作空间公开 Skill 与 datasource 6 绑定关系已核对。
- [x] 私有 Skill 排除原因已写入文档。
- [x] 文档 SQL/YAML 结构保持可解析，`source_skills` 字段不恢复。

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
