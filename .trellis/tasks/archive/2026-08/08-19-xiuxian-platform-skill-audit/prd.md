# 补充修仙知识库平台级 Skill

## Goal

核对全部平台公共 Data Skill，并将平台 SQL/分析执行约束和 MCP 能力边界写入修仙知识库文档。

## Requirements

- 只读查询全部活动 `PLATFORM_PUBLIC` Data Skill，不修改系统数据库。
- 将平台 SQL/分析通用约束的完整清单和对修仙 SQL 示例的影响写入文档。
- 登记 ChatMon MCP 平台 Skill，但明确其为工具调用能力，不将其混入业务 SQL 口径。
- 平台 Skill 没有 SQL 代码块时不得人为编造 SQL 示例。

## Acceptance Criteria

- [x] 16 条平台公共活动 Skill 均已登记。
- [x] 12 条 SQL/分析约束和 4 条 MCP 工具能力已分类。
- [x] 文档业务 YAML 不恢复 `source_skills` 字段，现有 SQL/YAML 继续通过解析。

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
