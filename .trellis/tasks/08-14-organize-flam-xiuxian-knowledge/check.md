# 检查记录

## 数据核对

- 系统数据库只读查询：flam 16 条候选 Skill、85 个 SQL 块；修仙 12 条候选 Skill、45 个 SQL 块。
- 修仙日期契约 Skill `255` 单独审阅，包含 2 个 SQL 块，不计入业务候选。
- 业务候选合计 28 条 Skill、130 个 SQL 块；空白归一化后 115 个唯一 SQL。
- 发现 9 组重复组，覆盖 24 个 SQL 块。
- 130/130 个业务候选 SQL 按当前 MySQL 方言解析为单条查询；连同 Skill `255` 为 132/132。
- 业务候选中 111 个 SQL 使用参数，11 个含硬编码日期，91 个使用 JSON 访问表达式。

## 文档检查

- `git diff --check` 通过。
- 28 个候选 Skill ID 均出现在整理文档中。
- 未发现密码、Secret 或 API Key 赋值文本。
- 文档明确保留权限、数据源、日期、校验和图表输出约束在 Data Skill 中。
- 未修改数据库、运行时配置、前后端代码或用户已有文件。

## 交付物

- `docs/flam_xiuxian_business_terms_sql_inventory.md`
- `docs/knowledge-base/flam_business_terms_sql.md`
- `docs/knowledge-base/xiuxian_business_terms_sql.md`

## 知识库 Markdown 验证

- flam 文档包含 7 个 SQL 示例，7/7 按 MySQL 方言解析通过。
- 修仙文档包含 8 个 SQL 示例，8/8 按 MySQL 方言解析通过。
- 两份文档代码围栏均闭合，分别声明了数据源、产品标识、物理表、字段和 JSON Path。
- 两份文档未发现密码、Secret 或 API Key 赋值文本，也未跨数据源混用产品标识。
- 示例 SQL 使用看板参数，不含本次生成范围内的硬编码 `YYYYMMDD`。
- 两份知识库文档已改为编号 YAML 对象格式，编号仅保留在 Markdown 标题中，YAML 不包含冗余 `id` 字段。
- 每个对象包含 `term`、`aliases`、`definition`、`formula`、`constraints`、`related_objects`、`source_skills` 和 `examples`。
- 16 个 YAML 对象全部通过 YAML 解析；其中 flam 7 个、修仙 8 个 SQL 示例继续通过 MySQL 单查询解析。
