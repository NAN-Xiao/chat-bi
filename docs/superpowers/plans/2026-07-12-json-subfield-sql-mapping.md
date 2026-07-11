# JSON 子字段 SQL 映射修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让手动看板 AI SQL 生成完整传递 JSON 子字段物理映射，并在生成前后阻断列或路径不一致的 SQL。

**Architecture:** 前端仅在发送 AI 上下文时把公式 token 的字符串字段转换为结构化字段对象，编辑状态继续保存字符串。后端把 `sourceField`、`jsonPath`、`expression` 作为唯一映射来源，先校验元数据，再用 `sqlglot` 按当前方言校验 LLM 生成 SQL 的 JSON 使用。

**Tech Stack:** Vue 3/TypeScript、Python 3.11、FastAPI、LangGraph、pytest、Node.js assert。

## Global Constraints

- JSON 映射只来自工作空间字段元数据，不得按逻辑字段名的点号猜测物理列或路径。
- 映射缺失、无效或未授权时必须显式阻断，不能回退到其他字段。
- 不添加任何数据源或业务领域特例，也不恢复业务库样例数据到 LLM 上下文。
- 保留 `logs/dashboard_ai_sql_llm_outputs.jsonl` 的用户改动，不纳入提交。

---

### Task 1: 公式 token 保留字段对象

**Files:** `frontend/src/views/dashboard/common/formulaMetricUtils.ts`、`frontend/src/views/dashboard/common/DashboardSqlEditor.vue`、`frontend/src/views/dashboard/common/DashboardSqlEditor.preview-fields.test.mjs`

**Interfaces:** `serializeFormulaTokensForContext(tokens, metricAliasById, resolveField)` 接受字段解析器，并让 `resolveField` 返回完整字段对象或原始值。

- [ ] **Step 1: 写失败的前端回归断言**

在预览测试新增：

```js
assert.match(source, /serializeFormulaTokensForContext\(item\.tokens, metricAliasById, fieldOptionPayload\)/)
```

- [ ] **Step 2: 运行失败测试**

运行 `node frontend/src/views/dashboard/common/DashboardSqlEditor.preview-fields.test.mjs`。

预期：断言失败，因为当前公式序列化调用只有两个参数。

- [ ] **Step 3: 最小实现**

扩展 `serializeFormulaTokensForContext`：第三个参数默认为 `(value) => value`；当 token 为 `atomicMetric` 时，复制 token，并对 `metric.field`、`metric.metric` 和递归筛选规则的字段调用解析器。`metric` token 保持只输出 `metricId`、`metricAlias`。在 `collectBuilderAiContext()` 的 `calculatedMetrics` 与 `formulaMetrics` 两处传入 `fieldOptionPayload`。

- [ ] **Step 4: 运行通过测试**

运行 `node frontend/src/views/dashboard/common/DashboardSqlEditor.preview-fields.test.mjs`，预期退出码 `0`。

- [ ] **Step 5: 提交任务**

运行 `git add frontend/src/views/dashboard/common/formulaMetricUtils.ts frontend/src/views/dashboard/common/DashboardSqlEditor.vue frontend/src/views/dashboard/common/DashboardSqlEditor.preview-fields.test.mjs && git commit -m "保留公式指标JSON字段映射"`。

### Task 2: 生成前阻断不完整 JSON 映射

**Files:** `backend/apps/dashboard/crud/ai_sql_generator.py`、`backend/tests/test_dashboard_ai_sql_generator.py`

**Interfaces:** `_json_subfield_mapping_issues(field, label) -> list[str]` 使用字段对象的 `isJsonSubfield`、`sourceField`、`jsonPath`、`expression`。

- [ ] **Step 1: 写失败的后端测试**

为 `_cross_event_arpu_formula_request()` 的 `personal.money` 收入字段补齐：

```python
{
    "table": "event", "field": "personal.money", "category": "number",
    "isJsonSubfield": True, "sourceField": "personal", "jsonPath": "$.money",
    "expression": "CAST(JSON_UNQUOTE(JSON_EXTRACT(`event`.`personal`, '$.money')) AS DECIMAL(38, 10))",
}
```

新增测试断言公式 IR 的 `metric_field` 保留 `sourceField == "personal"`、`jsonPath == "$.money"`。再清空这三个映射属性，断言确定性校验失败且包含“JSON 字段映射不完整”。

- [ ] **Step 2: 运行失败测试**

运行 `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_dashboard_ai_sql_generator.py -k "json_subfield" -v`。

预期：不完整映射仍被放行。

- [ ] **Step 3: 最小实现**

新增：

```python
def _json_subfield_mapping_issues(field: Any, label: str) -> list[str]:
    if not isinstance(field, dict) or field.get("isJsonSubfield") is not True:
        return []
    missing = [key for key in ("sourceField", "jsonPath", "expression") if not str(field.get(key) or "").strip()]
    return [] if not missing else [f"{label} 的 JSON 字段映射不完整，缺少：{'、'.join(missing)}。请重新选择字段。"]
```

在 `_validate_metric_item()` 校验事件字段、计算字段和每个有效筛选规则字段；在 `_dashboard_config_prompt()` 明确字段对象有 `expression` 时必须使用它，不能重写 JSON 宿主列或路径。

- [ ] **Step 4: 运行通过测试**

运行 `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_dashboard_ai_sql_generator.py -k "json_subfield or cross_event_arpu" -v`。

预期：完整映射可进入生成，缺失映射在 LLM 调用前失败。

- [ ] **Step 5: 提交任务**

运行 `git add backend/apps/dashboard/crud/ai_sql_generator.py backend/tests/test_dashboard_ai_sql_generator.py && git commit -m "校验看板JSON字段映射"`。

### Task 3: 生成后校验 JSON 宿主列与路径

**Files:** `backend/apps/dashboard/crud/ai_sql_generator.py`、`backend/tests/test_dashboard_ai_sql_generator.py`

**Interfaces:** `_json_subfield_sql_issues(sql, requirements) -> list[str]`；图状态新增 `json_subfield_requirements`。

- [ ] **Step 1: 写失败的 SQL 语义回归测试**

```python
def test_json_subfield_sql_validation_rejects_wrong_host_column() -> None:
    requirements = [{"label": "后端充值金额", "source_field": "personal", "json_path": "$.money"}]
    sql = "SELECT JSON_UNQUOTE(JSON_EXTRACT(e.ext, '$.personal.money')) FROM event e"
    assert any("JSON 列或路径" in issue for issue in ai_sql_generator._json_subfield_sql_issues(sql, requirements))

def test_json_subfield_sql_validation_accepts_matching_host_column() -> None:
    requirements = [{"label": "后端充值金额", "source_field": "personal", "json_path": "$.money"}]
    sql = "SELECT JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.money')) FROM event e"
    assert ai_sql_generator._json_subfield_sql_issues(sql, requirements, dialect="mysql") == []

def test_json_subfield_sql_validation_accepts_postgres_json_path() -> None:
    requirements = [{"label": "收入", "source_field": "personal", "json_path": "$.money"}]
    sql = "SELECT (e.personal::jsonb #>> '{money}') FROM event e"
    assert ai_sql_generator._json_subfield_sql_issues(sql, requirements, dialect="postgres") == []
```

- [ ] **Step 2: 运行失败测试**

运行 `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_dashboard_ai_sql_generator.py -k "wrong_host_column or matching_host_column" -v`。

预期：失败，因为校验函数不存在。

- [ ] **Step 3: 最小实现**

收集所有 `isJsonSubfield is True` 的字段，按 `sourceField + jsonPath` 去重。新增方言无关的 `_json_subfield_sql_issues(sql, requirements, dialect)`：使用 `sqlglot.parse_one(sql, read=dialect)` 遍历 `exp.JSONExtract`、`exp.JSONBExtractScalar` 与 `JSON_VALUE` 的 `exp.Anonymous` 节点，抽取列名和路径；每个选中字段必须有匹配对，识别出的未选中列/路径组合也必须报错。MySQL、PostgreSQL 和 ClickHouse 分别规范为 `$.a.b` 形式；不支持的方言在存在 JSON 字段需求时返回“当前数据源方言无法校验 JSON 字段映射”，不能静默放行。在 `_node_build_formula_ir()` 写入 `json_subfield_requirements`，在 `_node_validate_sql()` 的只读校验前调用校验。失败时设置 `success=False`、消息“生成 SQL 的 JSON 字段映射与当前配置不一致。”、建议“请重新选择事件参数后生成 SQL。”。

- [ ] **Step 4: 运行通过测试**

运行 `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_dashboard_ai_sql_generator.py -k "json_subfield or cross_event_arpu" -v`。

预期：`ext + $.personal.money` 被阻断，`personal + $.money` 通过 JSON 校验。

- [ ] **Step 5: 运行完整受影响测试集**

运行 `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_dashboard_ai_sql_generator.py backend/tests/test_tracking_excel.py -v`，再运行 `node frontend/src/views/dashboard/common/DashboardSqlEditor.preview-fields.test.mjs`。

预期：pytest 和 Node 测试均退出码 `0`。

- [ ] **Step 6: 提交任务**

运行 `git add backend/apps/dashboard/crud/ai_sql_generator.py backend/tests/test_dashboard_ai_sql_generator.py frontend/src/views/dashboard/common/formulaMetricUtils.ts frontend/src/views/dashboard/common/DashboardSqlEditor.vue frontend/src/views/dashboard/common/DashboardSqlEditor.preview-fields.test.mjs && git commit -m "阻断JSON字段路径错误SQL"`。
