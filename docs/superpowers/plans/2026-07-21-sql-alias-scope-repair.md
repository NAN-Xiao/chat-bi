# SQL 别名作用域最小修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Smart Q&A 降低生成越界别名 SQL 的概率，并在数据库明确返回 `Column ... cannot be resolved` 时进入现有 SQL 修复再生成流程。

**Architecture:** 保持现有 SQL 修复图不变，只扩展执行错误文本分类器的精确模式；同时在基础 SQL 模板增加查询块别名作用域规则。两个行为分别由独立回归测试约束。

**Tech Stack:** Python、pytest、正则表达式、YAML 提示词模板。

## Global Constraints

- 不将整个数据库错误码 `1815` 归类为可修复错误。
- 不实现 AST 校验或 SQL 自动改写。
- 不改变 SQL 修复次数、权限、连接和超时策略。
- 所有规则保持领域无关、数据源无关。

---

### Task 1: 精确分类无法解析的限定列

**Files:**
- Modify: `backend/tests/test_sql_repair.py:109`
- Modify: `backend/apps/chat/task/sql_repair.py:58`

**Interfaces:**
- Consumes: `classify_execute_sql_error(error: Exception) -> SqlRepairReason | None`
- Produces: `Column '<alias>.<column>' cannot be resolved` 被分类为 `SqlRepairReason.DATABASE_SYNTAX_OR_DIALECT`

- [x] **Step 1: 写入失败测试**

在 `test_execute_error_accepts_explicit_syntax_or_dialect_text` 的参数中加入：

```python
"Column 'e.time' cannot be resolved",
```

并加入负向测试，证明非列解析错误不会被误分类：

```python
def test_execute_error_rejects_unrelated_cannot_be_resolved_text() -> None:
    error = _MysqlError("storage backend cannot be resolved", 1815)
    assert classify_execute_sql_error(error) is None
```

- [x] **Step 2: 运行测试并确认按预期失败**

Run: `D:\\AIWork3\\chat-bi\\backend\\.venv\\Scripts\\python.exe -m pytest backend/tests/test_sql_repair.py::test_execute_error_accepts_explicit_syntax_or_dialect_text backend/tests/test_sql_repair.py::test_execute_error_rejects_unrelated_cannot_be_resolved_text -q`

Expected: 新增正向参数失败，实际结果为 `None`；负向测试通过。

- [x] **Step 3: 写入最小实现**

在 `_EXECUTE_SYNTAX_OR_DIALECT_PATTERNS` 中增加精确模式：

```python
re.compile(
    r"\bcolumn\s+['\"`]?[^'\"`\s]+['\"`]?\s+cannot be resolved\b",
    re.IGNORECASE,
),
```

- [x] **Step 4: 运行测试并确认通过**

Run: `D:\\AIWork3\\chat-bi\\backend\\.venv\\Scripts\\python.exe -m pytest backend/tests/test_sql_repair.py -q`

Expected: `backend/tests/test_sql_repair.py` 全部通过。

- [x] **Step 5: 提交错误分类修复**

```powershell
git add -- backend/apps/chat/task/sql_repair.py backend/tests/test_sql_repair.py
git commit -m "修复无法解析列时的SQL再生成"
```

### Task 2: 增加通用查询块别名作用域规则

**Files:**
- Create: `backend/tests/test_sql_generation_template.py`
- Modify: `backend/templates/template.yaml:48`

**Interfaces:**
- Consumes: `apps.template.template.get_base_template() -> dict`
- Produces: `template.sql.multi_table_condition` 包含查询块别名可见范围约束

- [x] **Step 1: 写入失败测试**

```python
from apps.template.template import get_base_template


def test_multi_table_rule_restricts_aliases_to_current_query_block() -> None:
    rule = get_base_template()["template"]["sql"]["multi_table_condition"]

    assert "每个SELECT查询块只能引用当前查询块FROM/JOIN中可见的表或别名" in rule
    assert "外层查询只能使用子查询别名及该子查询明确输出的列" in rule
    assert "不得引用子查询内部的表别名" in rule
```

- [x] **Step 2: 运行测试并确认按预期失败**

Run: `D:\\AIWork3\\chat-bi\\backend\\.venv\\Scripts\\python.exe -m pytest backend/tests/test_sql_generation_template.py -q`

Expected: 三条作用域断言至少一条失败。

- [x] **Step 3: 写入最小模板规则**

在 `multi_table_condition.requirements` 中增加：

```yaml
<requirement>每个SELECT查询块只能引用当前查询块FROM/JOIN中可见的表或别名</requirement>
<requirement>外层查询引用子查询时，只能使用子查询别名及该子查询明确输出的列，不得引用子查询内部的表别名</requirement>
```

并在 `enforcement` 中增加：

```yaml
<action>逐个SELECT查询块检查限定字段所使用的表别名是否在当前查询块可见</action>
```

- [x] **Step 4: 运行模板测试并确认通过**

Run: `D:\\AIWork3\\chat-bi\\backend\\.venv\\Scripts\\python.exe -m pytest backend/tests/test_sql_generation_template.py -q`

Expected: PASS。

- [x] **Step 5: 运行相关回归测试**

Run: `D:\\AIWork3\\chat-bi\\backend\\.venv\\Scripts\\python.exe -m pytest backend/tests/test_sql_repair.py backend/tests/test_sql_generation_template.py backend/tests/test_smart_qa_graph.py -q`

Expected: 全部通过，无新增警告或错误。

- [x] **Step 6: 提交模板规则与测试**

```powershell
git add -- backend/templates/template.yaml backend/tests/test_sql_generation_template.py docs/superpowers/plans/2026-07-21-sql-alias-scope-repair.md
git commit -m "完善SQL查询块别名作用域规则"
```
