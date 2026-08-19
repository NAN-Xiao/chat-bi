# 检查记录

## 平台 Skill 核查

- 系统库只读查询得到 16 条活动 `PLATFORM_PUBLIC` Data Skill。
- 12 条为 SQL/分析通用约束：`170-173、185-188、190、281-283`。
- 4 条为 ChatMon MCP 工具能力：`248-251`。
- 16 条均为 `specific_ds=false`、`datasource_ids=[]`，且不包含 SQL 代码块。

## 文档验证

- 文档逐条登记全部 16 个平台 Skill，并区分通用 SQL/分析约束与 MCP 工具能力。
- 未为无 SQL 来源的平台 Skill 人为生成 SQL；现有修仙 SQL 继续由工作空间口径提供。
- 8/8 YAML 对象解析通过，均不包含 `source_skills`。
- 8/8 SQL 按 MySQL 方言解析为单条 `SELECT`/`WITH` 查询。
- `git diff --check` 通过，仅有工作区换行符提示。
