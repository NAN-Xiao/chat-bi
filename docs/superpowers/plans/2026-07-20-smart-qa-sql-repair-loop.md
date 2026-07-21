# Smart Q&A SQL 受控修复闭环 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Smart Q&A 增加最多两次、不可绕过安全与 Data Skills 校验的 SQL 修复闭环，并修复 `q025`、`q043`、`q045`、`q048`、`q086`。

**Architecture:** 新建领域无关的 SQL 修复模型与错误分类模块，把准备阶段解析/语义错误和执行阶段数据库语法/方言错误统一路由到 LangGraph `repair_sql` 节点。修复结果只替换 LLM SQL JSON，随后重新进入 `prepare_sql` 完成 Data Skills、只读、范围和权限校验；修仙业务口径仅通过 datasource 6 Data Skills 增强。

**Tech Stack:** Python 3.11、LangGraph、sqlglot、pytest、ruff、PostgreSQL 系统库、MySQL 兼容业务数据源、Playwright。

## Global Constraints

- 单次工作流 SQL 修复总预算固定为 `2` 次；相同错误指纹不得重复修复。
- 修复 SQL 必须重新通过 Data Skills、只读、安全、表字段范围、租户和用户权限校验。
- 权限、写 SQL、危险函数、连接失败、超时、取消、数据不可用和未知异常不得自动修复。
- 共享代码不得硬编码 `ServerPayLog`、`personal.money`、ARPU、ARPPU、修仙产品号或测试问题。
- datasource 6 继续要求 `ServerPayLog + personal.money + COUNT(DISTINCT uid)`，不得放宽。
- 错误发给 LLM 前必须脱敏，不得包含密码、API Key、Token 或连接串凭据。
- 不增加字段、表、事件、日期边界或图表字段的静默回退。
- 未经用户明确要求，不执行 Git 提交、推送或建分支。

## File Map

- Create: `backend/apps/chat/task/sql_repair.py` — 修复模型、分类、脱敏、指纹和提示载荷。
- Create: `backend/tests/test_sql_repair.py` — 修复分类、脱敏、指纹和预算测试。
- Create: `backend/tests/test_data_skill_sql_validation.py` — 通用结构化 Data Skills 违规测试。
- Modify: `backend/apps/chat/task/llm.py:129`、`:326`、`:1990`、`:2422`。
- Modify: `backend/apps/chat/task/smart_qa_graph.py:1263`、`:1599`、`:1912`、`:2199`、`:2228`。
- Modify: `backend/tests/test_smart_qa_graph.py:280`。
- Modify: `tools/seed_xiuxian_data_skills.py:34`、`:115`、`:170`、`:189`。
- Modify: `backend/tests/test_xiuxian_data_skill_seed.py:64`。
- Create: `tools/sync_xiuxian_sql_repair_skills.py` — 只更新日期与 ServerPayLog 两条 Skill。
- Create: `backend/tests/test_sync_xiuxian_sql_repair_skills.py` — 定向同步、幂等和 marker 边界测试。
- Runtime validation: `.codex-runtime/ai-dashboard-100-test/ui_runner.cjs`。

---

### Task 1: SQL 修复模型与错误分类

**Files:**
- Create: `backend/apps/chat/task/sql_repair.py`
- Create: `backend/tests/test_sql_repair.py`

**Interfaces:**
- Produces: `SqlRepairReason`、`DataSkillSqlViolation`、`DataSkillSqlValidationError`、`SqlRepairContext`、`classify_prepare_sql_error`、`classify_execute_sql_error`、`sanitize_sql_repair_error`、`sql_repair_fingerprint`、`build_sql_repair_message`。

- [ ] **Step 1: 写失败测试**

```python
from sqlglot.errors import ParseError
from apps.chat.task.sql_repair import (
    DataSkillSqlValidationError,
    DataSkillSqlViolation,
    SqlRepairContext,
    SqlRepairReason,
    build_sql_repair_message,
    classify_execute_sql_error,
    classify_prepare_sql_error,
    sanitize_sql_repair_error,
    sql_repair_fingerprint,
)
from common.error import AppDBConnectionError, AppDBError, DataUnavailableError, SingleMessageError


def test_prepare_error_classification() -> None:
    violation = DataSkillSqlViolation("口径错误", 0, ("required",), (), ("forbidden",), (), ())
    assert classify_prepare_sql_error(SingleMessageError("SQL answer is not a valid json object")) == SqlRepairReason.SQL_RESPONSE_FORMAT
    assert classify_prepare_sql_error(ParseError("Expected TYPE")) == SqlRepairReason.SQL_PARSE
    assert classify_prepare_sql_error(DataSkillSqlValidationError(violation)) == SqlRepairReason.DATA_SKILL_VALIDATION


def test_execute_error_only_repairs_syntax_or_dialect() -> None:
    wrapped = AppDBError("query failed")
    wrapped.__cause__ = RuntimeError("missing column aliases in recursive WITH query")
    assert classify_execute_sql_error(wrapped) == SqlRepairReason.DATABASE_SYNTAX_OR_DIALECT
    assert classify_execute_sql_error(DataUnavailableError("unknown column")) is None
    assert classify_execute_sql_error(AppDBConnectionError("connection refused")) is None
    assert classify_execute_sql_error(TimeoutError("query timeout")) is None
    assert classify_execute_sql_error(PermissionError("permission denied")) is None


def test_error_redaction_and_fingerprint() -> None:
    message = sanitize_sql_repair_error(RuntimeError("mysql://root:secret@host/db api_key=abc123"))
    assert "secret" not in message and "abc123" not in message and "[REDACTED]" in message
    first = SqlRepairContext(SqlRepairReason.SQL_PARSE, "mysql", "SELECT  1", "parse error", None, 0, 2)
    second = SqlRepairContext(SqlRepairReason.SQL_PARSE, "mysql", "SELECT 1", "parse error", None, 0, 2)
    assert sql_repair_fingerprint(first) == sql_repair_fingerprint(second)
    assert "重写完整 SQL JSON" in build_sql_repair_message(first)
```

- [ ] **Step 2: 确认测试先失败**

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_sql_repair.py -q
Pop-Location
```

Expected: `ModuleNotFoundError: No module named 'apps.chat.task.sql_repair'`。

- [ ] **Step 3: 实现公开模型和分类器**

`backend/apps/chat/task/sql_repair.py` 必须包含以下签名：

```python
SQL_REPAIR_MAX_ATTEMPTS = 2

class SqlRepairReason(str, Enum):
    SQL_RESPONSE_FORMAT = "sql_response_format"
    SQL_PARSE = "sql_parse"
    DATA_SKILL_VALIDATION = "data_skill_validation"
    DATABASE_SYNTAX_OR_DIALECT = "database_syntax_or_dialect"

@dataclass(frozen=True)
class DataSkillSqlViolation:
    message: str
    rule_index: int
    missing_required_contains: tuple[str, ...]
    missing_required_patterns: tuple[str, ...]
    matched_forbidden_contains: tuple[str, ...]
    matched_forbidden_patterns: tuple[str, ...]
    matched_forbidden_groups: tuple[tuple[str, ...], ...]

class DataSkillSqlValidationError(SingleMessageError):
    def __init__(self, violation: DataSkillSqlViolation | str):
        self.violation = violation if isinstance(violation, DataSkillSqlViolation) else None
        super().__init__(violation.message if self.violation is not None else str(violation))

@dataclass(frozen=True)
class SqlRepairContext:
    reason: SqlRepairReason
    dialect: str
    failed_sql: str
    error_message: str
    violation: DataSkillSqlViolation | None
    attempt: int
    max_attempts: int = 2
```

实现要求：

- `sanitize_sql_repair_error` 遍历 `__cause__`/`__context__`，脱敏 URI 密码及 `password|api_key|token`，截断到 2000 字符。
- `classify_prepare_sql_error` 只接受结构化语义异常、sqlglot `ParseError`、已知 SQL JSON/空 SQL 文本和 `Parse SQL Error`。
- `classify_execute_sql_error` 先排除平台权限/数据不可用分类，再接受 SQLSTATE `42601/42804/42883/42P18`、errno `1064/1305/1582` 和明确语法/方言文本。
- 指纹对 SQL 与错误摘要只折叠空白并转小写，不改动业务 SQL。
- 修复消息使用 JSON 载荷，包含 reason、dialect、failed_sql、error、attempt、max_attempts、violation。

- [ ] **Step 4: 验证通过并执行 Ruff**

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_sql_repair.py -q
.\.venv\Scripts\python.exe -m ruff check apps/chat/task/sql_repair.py tests/test_sql_repair.py
Pop-Location
```

Expected: tests pass；Ruff 输出 `All checks passed!`。

---

### Task 2: Data Skills 结构化违规对象

**Files:**
- Create: `backend/tests/test_data_skill_sql_validation.py`
- Modify: `backend/apps/chat/task/llm.py:129-377`

**Interfaces:**
- Consumes: Task 1 的 `DataSkillSqlViolation` 和 `DataSkillSqlValidationError`。
- Produces: `_data_skill_sql_validation_violation(question, sql, data_skill)`；保留 `_data_skill_sql_validation_error(...) -> str | None` 文本接口。

- [ ] **Step 1: 写失败测试**

```python
import json
from types import SimpleNamespace
import pytest
from apps.chat.models.chat_model import OperationEnum
from apps.chat.task import llm
from apps.chat.task.sql_repair import DataSkillSqlValidationError

RULES = """<!-- data-skill-sql-validation:[{
  "match":["收入"],
  "required_sql_contains":["AuthoritativeEvent","$.amount"],
  "required_sql_patterns":["COUNT\\\\s*\\\\(\\\\s*DISTINCT\\\\s+uid\\\\s*\\\\)"],
  "forbidden_sql_contains":["LegacyEvent","legacy_amount"],
  "message":"必须使用权威收入口径。"
}] -->"""


def test_structured_violation_reports_evidence() -> None:
    violation = llm._data_skill_sql_validation_violation(
        "统计收入",
        "SELECT SUM(legacy_amount) FROM event WHERE event = 'LegacyEvent'",
        RULES,
    )
    assert violation is not None
    assert violation.rule_index == 0
    assert violation.missing_required_contains == ("AuthoritativeEvent", "$.amount")
    assert violation.missing_required_patterns
    assert violation.matched_forbidden_contains == ("LegacyEvent", "legacy_amount")
    assert llm._data_skill_sql_validation_error("统计收入", "SELECT legacy_amount FROM event", RULES) == "必须使用权威收入口径。"


def test_check_sql_raises_structured_error(monkeypatch: pytest.MonkeyPatch) -> None:
    service = object.__new__(llm.LLMService)
    service.current_logs = {OperationEnum.GENERATE_SQL: SimpleNamespace(error=False)}
    service.chat_question = SimpleNamespace(question="统计收入", data_skill=RULES)
    monkeypatch.setattr(llm, "trigger_log_error", lambda session, log: setattr(log, "error", True))
    response = json.dumps({"success": True, "sql": "SELECT legacy_amount FROM event", "tables": ["event"]})
    with pytest.raises(DataSkillSqlValidationError) as captured:
        service.check_sql(object(), response, OperationEnum.GENERATE_SQL)
    assert str(captured.value) == "必须使用权威收入口径。"
    assert captured.value.violation is not None
```

- [ ] **Step 2: 确认测试失败**

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_data_skill_sql_validation.py -q
Pop-Location
```

Expected: `_data_skill_sql_validation_violation` 不存在，当前异常没有 `violation`。

- [ ] **Step 3: 实现结构化收集并保持文本兼容**

在 `llm.py` 导入 Task 1 类型并删除原空异常类：

```python
from apps.chat.task.sql_repair import DataSkillSqlValidationError, DataSkillSqlViolation
```

新增函数按首条违反规则收集：

```python
def _data_skill_sql_validation_violation(question: str, sql: str, data_skill: str = "") -> DataSkillSqlViolation | None:
    if not sql:
        return None
    sql_text = str(sql)
    sql_lower = sql_text.lower()
    for rule_index, rule in enumerate(_extract_data_skill_sql_validation_rules(data_skill)):
        if not _rule_matches_question(rule, question) or _rule_allowed_by_question(rule, question):
            continue
        missing_contains = tuple(text for text in _normalize_rule_terms(rule.get("required_sql_contains")) if text.lower() not in sql_lower)
        missing_patterns = tuple(pattern for pattern in _normalize_rule_terms(rule.get("required_sql_patterns")) if not _sql_pattern_matches(pattern, sql_text, sql_lower))
        forbidden_contains = tuple(text for text in _normalize_rule_terms(rule.get("forbidden_sql_contains")) if text.lower() in sql_lower)
        forbidden_patterns = tuple(pattern for pattern in _normalize_rule_terms(rule.get("forbidden_sql_patterns")) if _sql_pattern_matches(pattern, sql_text, sql_lower))
        forbidden_groups = tuple(
            tuple(_normalize_rule_terms(group))
            for group in rule.get("forbidden_sql_all_contains") or []
            if all(term.lower() in sql_lower for term in _normalize_rule_terms(group))
        )
        required_group_missing = any(
            terms and not all(term.lower() in sql_lower for term in terms)
            for terms in (_normalize_rule_terms(group) for group in rule.get("required_sql_all_contains") or [])
        )
        select_group_forbidden = _forbidden_select_group_matches(rule, sql_text)
        if not (missing_contains or missing_patterns or forbidden_contains or forbidden_patterns or forbidden_groups or required_group_missing or select_group_forbidden):
            continue
        if select_group_forbidden:
            forbidden_groups += tuple(tuple(_normalize_rule_terms(group)) for group in rule.get("forbidden_sql_select_all_contains") or [])
        return DataSkillSqlViolation(
            message=str(rule.get("message") or "SQL 与本次匹配的 Data Skill 业务口径冲突，请按 Data Skill 重写 SQL。"),
            rule_index=rule_index,
            missing_required_contains=missing_contains,
            missing_required_patterns=missing_patterns,
            matched_forbidden_contains=forbidden_contains,
            matched_forbidden_patterns=forbidden_patterns,
            matched_forbidden_groups=forbidden_groups,
        )
    return None


def _data_skill_sql_validation_error(question: str, sql: str, data_skill: str = "") -> str | None:
    violation = _data_skill_sql_validation_violation(question, sql, data_skill)
    return violation.message if violation is not None else None
```

`LLMService.check_sql` 改为：

```python
violation = _data_skill_sql_validation_violation(self.chat_question.question or "", sql, self.chat_question.data_skill)
if violation is not None:
    trigger_log_error(session, log)
    raise DataSkillSqlValidationError(violation)
```

- [ ] **Step 4: 运行通用与现有修仙语义测试**

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_data_skill_sql_validation.py tests/test_xiuxian_data_skill_seed.py -q
Pop-Location
```

Expected: 全部通过，现有错误文本不变。

---

### Task 3: 统一 LLM 修复接口与异常链保真

**Files:**
- Modify: `backend/apps/chat/task/llm.py:1990-2029`
- Modify: `backend/apps/chat/task/llm.py:2422-2457`
- Modify: `backend/tests/test_sql_repair.py`

**Interfaces:**
- Consumes: `SqlRepairContext`、`build_sql_repair_message`。
- Produces: `LLMService.regenerate_sql_after_error_streaming_reasoning(session, context, in_chat)`。

- [ ] **Step 1: 写统一接口失败测试**

```python
from types import SimpleNamespace
import pytest
from apps.chat.task import llm
from apps.chat.task.sql_repair import SqlRepairContext, SqlRepairReason


def test_llm_repair_interface_appends_structured_message() -> None:
    service = object.__new__(llm.LLMService)
    service.sql_message = []
    captured = {}
    def generate(session, *, in_chat, append_question):
        captured.update(in_chat=in_chat, append_question=append_question)
        if False:
            yield None
        return '{"success":true,"sql":"SELECT 1","tables":["orders"]}'
    service.generate_sql_text_streaming_reasoning = generate
    context = SqlRepairContext(SqlRepairReason.SQL_PARSE, "mysql", "SELECT CAST(value, AS DECIMAL(18,4))", "parse error", None, 0, 2)
    generator = service.regenerate_sql_after_error_streaming_reasoning(SimpleNamespace(), context, in_chat=True)
    with pytest.raises(StopIteration) as stopped:
        next(generator)
    assert stopped.value.value.startswith('{"success":true')
    assert captured == {"in_chat": True, "append_question": False}
    assert "sql-repair-context" in service.sql_message[-1].content
```

- [ ] **Step 2: 确认测试失败**

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_sql_repair.py::test_llm_repair_interface_appends_structured_message -q
Pop-Location
```

Expected: 新方法不存在。

- [ ] **Step 3: 替换专用语义修复方法**

```python
def regenerate_sql_after_error_streaming_reasoning(self, _session: Session, context: SqlRepairContext, in_chat: bool):
    self.sql_message.append(HumanMessage(content=build_sql_repair_message(context)))
    return (yield from self.generate_sql_text_streaming_reasoning(
        _session,
        in_chat=in_chat,
        append_question=False,
    ))
```

删除两个旧 `regenerate_sql_after_validation_error*` 方法；仓库检索必须确认无剩余调用。

- [ ] **Step 4: 保留数据库异常链**

```python
except Exception as error:
    if isinstance(error, ParseSQLResultError):
        raise
    traceback_text = traceback.format_exc(limit=1, chain=True)
    raise AppDBError(traceback_text) from error
```

- [ ] **Step 5: 验证测试和 Ruff**

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_sql_repair.py -q
.\.venv\Scripts\python.exe -m ruff check apps/chat/task/sql_repair.py apps/chat/task/llm.py tests/test_sql_repair.py
Pop-Location
```

Expected: 全部通过。

---

### Task 4: 准备阶段修复路由

**Files:**
- Modify: `backend/apps/chat/task/smart_qa_graph.py:1263-1292`
- Modify: `backend/apps/chat/task/smart_qa_graph.py:1599-1815`
- Modify: `backend/apps/chat/task/smart_qa_graph.py:2199-2283`
- Modify: `backend/tests/test_smart_qa_graph.py:280-377`

**Interfaces:**
- Produces: `_queue_sql_repair`、`_repair_sql`、`sql_repair_pending` 条件路由。
- Consumes: Tasks 1-3 的修复分类与 LLM 接口。

- [ ] **Step 1: 扩展 Fake Service**

将 Fake Service 的 `check_sql` 改为解析传入的 `res`，并增加修复答案队列：

```python
self.repair_answers: list[str] = []
self.repair_contexts: list[Any] = []

def check_sql(self, *, session, res, operate):
    payload = json.loads(res)
    return payload["sql"], payload.get("tables")

def regenerate_sql_after_error_streaming_reasoning(self, session, context, in_chat):
    self.repair_contexts.append(context)
    if in_chat:
        yield graph._sse({"content": "", "reasoning_content": "repairing", "type": "sql-result"})
    return self.repair_answers.pop(0)
```

- [ ] **Step 2: 写 `q043` 解析修复测试**

```python
def test_prepare_sql_parse_error_repairs_then_revalidates(monkeypatch: pytest.MonkeyPatch) -> None:
    invalid_sql = "SELECT CAST(value, AS DECIMAL(18, 4)) FROM orders"
    repaired_sql = "SELECT CAST(value AS DECIMAL(18, 4)) FROM orders"
    service = FakeSmartQAService(sql_answer=_sql_answer(invalid_sql))
    service.repair_answers = [_sql_answer(repaired_sql)]
    calls = []
    def validate(**kwargs):
        calls.append(kwargs["sql"])
        if kwargs["sql"] == invalid_sql:
            raise ValueError("Parse SQL Error: Expected TYPE after CAST")
        return kwargs["sql"], {"orders"}
    monkeypatch.setattr(graph, "validate_user_query_sql_or_raise", validate)
    chunks = list(graph.run_smart_qa_graph(service, in_chat=True, stream=True, finish_step=ChatFinishStep.GENERATE_CHART))
    assert calls == [invalid_sql, repaired_sql]
    assert service.saved_sql == [repaired_sql]
    assert service.executed[0]["sql"] == repaired_sql
    assert len(service.repair_contexts) == 1
    assert not any(event["type"] == "error" for event in _events(chunks))
```

- [ ] **Step 3: 写结构化 Data Skills 修复测试**

```python
def test_data_skill_violation_repairs_with_structured_context(monkeypatch: pytest.MonkeyPatch) -> None:
    invalid_sql = "SELECT legacy_amount FROM event WHERE event = 'LegacyEvent'"
    repaired_sql = "SELECT SUM(amount) FROM event WHERE event = 'AuthoritativeEvent'"
    service = FakeSmartQAService(sql_answer=_sql_answer(invalid_sql, ["event"]))
    service.repair_answers = [_sql_answer(repaired_sql, ["event"])]
    violation = llm.DataSkillSqlViolation("口径错误", 0, ("AuthoritativeEvent", "amount"), (), ("LegacyEvent", "legacy_amount"), (), ())
    def check_sql(*, session, res, operate):
        payload = json.loads(res)
        if payload["sql"] == invalid_sql:
            raise llm.DataSkillSqlValidationError(violation)
        return payload["sql"], payload.get("tables")
    service.check_sql = check_sql
    monkeypatch.setattr(graph, "validate_user_query_sql_or_raise", lambda **kwargs: (kwargs["sql"], {"event"}))
    list(graph.run_smart_qa_graph(service, in_chat=True, stream=True, finish_step=ChatFinishStep.GENERATE_CHART))
    assert service.repair_contexts[0].violation == violation
    assert service.saved_sql == [repaired_sql]
```

- [ ] **Step 4: 确认两项测试失败**

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_smart_qa_graph.py::test_prepare_sql_parse_error_repairs_then_revalidates tests/test_smart_qa_graph.py::test_data_skill_violation_repairs_with_structured_context -q
Pop-Location
```

Expected: 图中没有 `repair_sql`，解析错误仍直接终止。

- [ ] **Step 5: 增加状态与入队函数**

在 `SmartQAGraphState` 增加：

```python
sql_repair_count: int
sql_repair_pending: bool
sql_repair_context: SqlRepairContext | None
sql_repair_fingerprints: list[str]
```

实现：

```python
def _queue_sql_repair(state: SmartQAGraphState, *, error: BaseException, reason: SqlRepairReason, failed_sql: str) -> dict[str, Any]:
    service = state["service"]
    context = SqlRepairContext(
        reason=reason,
        dialect=get_sqlglot_dialect(getattr(getattr(service, "ds", None), "type", None)),
        failed_sql=failed_sql,
        error_message=sanitize_sql_repair_error(error),
        violation=getattr(error, "violation", None),
        attempt=state.get("sql_repair_count", 0),
        max_attempts=SQL_REPAIR_MAX_ATTEMPTS,
    )
    fingerprint = sql_repair_fingerprint(context)
    fingerprints = list(state.get("sql_repair_fingerprints") or [])
    if context.attempt >= context.max_attempts or fingerprint in fingerprints:
        raise error
    return {
        "sql_repair_pending": True,
        "sql_repair_context": context,
        "sql_repair_fingerprints": [*fingerprints, fingerprint],
        "stop": False,
    }
```

- [ ] **Step 6: 实现修复节点**

```python
def _repair_sql(state: SmartQAGraphState) -> dict[str, Any]:
    context = state.get("sql_repair_context")
    if context is None:
        raise RuntimeError("SQL repair context is missing")
    with _session_scope() as session:
        full_sql_text = _consume_generator_return(
            state["service"].regenerate_sql_after_error_streaming_reasoning(session, context, in_chat=state["in_chat"]),
            _emit,
        )
    return {
        "full_sql_text": full_sql_text,
        "sql_repair_count": state.get("sql_repair_count", 0) + 1,
        "sql_repair_pending": False,
        "sql_repair_context": None,
        "stop": False,
    }
```

- [ ] **Step 7: 修改 `_prepare_sql` 异常分支**

- `DataSkillSqlValidationError` 若属于 schema 缺失，保持现有业务提示并结束。
- 其他语义错误调用 `classify_prepare_sql_error` 和 `_queue_sql_repair`。
- `SingleMessageError` 只有分类为 `sql_response_format` 才修复。
- `validate_user_query_sql_or_raise` 的权限分支保持原样；非权限异常只有分类为 `sql_parse` 才修复。
- 删除原有一次专用 Data Skills 内联重写。
- 将最终 `sql-result`/`sql` SSE 移到准备校验成功之后，避免重复展示无效 SQL。

- [ ] **Step 8: 注册节点和条件边**

```python
def _should_continue_after_sql(state: SmartQAGraphState) -> str:
    if state.get("stop"):
        return END
    if state.get("sql_repair_pending"):
        return "repair_sql"
    return "execute_sql"

graph.add_node("repair_sql", _observe_node("repair_sql", _repair_sql))
graph.add_edge("repair_sql", "prepare_sql")
```

初始状态增加 `sql_repair_count=0`、`sql_repair_pending=False`、`sql_repair_context=None`、`sql_repair_fingerprints=[]`。

- [ ] **Step 9: 验证准备阶段路由**

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_smart_qa_graph.py::test_prepare_sql_parse_error_repairs_then_revalidates tests/test_smart_qa_graph.py::test_data_skill_violation_repairs_with_structured_context tests/test_smart_qa_graph.py::test_data_skill_schema_unavailable_is_streamed_as_business_feedback -q
Pop-Location
```

Expected: `3 passed`。

---

### Task 5: 执行阶段修复、重复指纹与预算

**Files:**
- Modify: `backend/apps/chat/task/smart_qa_graph.py:1912-1994`
- Modify: `backend/apps/chat/task/smart_qa_graph.py:2219-2225`
- Modify: `backend/tests/test_smart_qa_graph.py`

**Interfaces:**
- Consumes: `_queue_sql_repair`、`classify_execute_sql_error`。
- Produces: 可恢复数据库错误到 `repair_sql` 的条件路由。

- [ ] **Step 1: 写 `q025` 执行错误修复测试**

```python
def test_execute_sql_dialect_error_repairs_then_executes_again(monkeypatch: pytest.MonkeyPatch) -> None:
    invalid_sql = "WITH RECURSIVE days AS (SELECT 1 UNION ALL SELECT 2) SELECT * FROM days"
    repaired_sql = "WITH RECURSIVE days(day_value) AS (SELECT 1 UNION ALL SELECT 2) SELECT * FROM days"
    service = FakeSmartQAService(sql_answer=_sql_answer(invalid_sql))
    service.repair_answers = [_sql_answer(repaired_sql)]
    monkeypatch.setattr(graph, "validate_user_query_sql_or_raise", lambda **kwargs: (kwargs["sql"], {"orders"}))
    attempts = []
    def execute(**kwargs):
        attempts.append(kwargs["sql"])
        if kwargs["sql"] == invalid_sql:
            error = llm.AppDBError("query failed")
            raise error from RuntimeError("missing column aliases in recursive WITH query")
        return {"fields": ["day_value"], "data": [{"day_value": 1}]}
    service.execute_sql = execute
    chunks = list(graph.run_smart_qa_graph(service, in_chat=True, stream=True, finish_step=ChatFinishStep.GENERATE_CHART))
    assert attempts == [invalid_sql, repaired_sql]
    assert service.repair_contexts[0].reason.value == "database_syntax_or_dialect"
    assert not any(event["type"] == "error" for event in _events(chunks))
```

- [ ] **Step 2: 写重复指纹和共享预算测试**

```python
def test_same_failure_fingerprint_is_not_repaired_twice(monkeypatch: pytest.MonkeyPatch) -> None:
    invalid_sql = "SELECT CAST(value, AS DECIMAL(18, 4)) FROM orders"
    service = FakeSmartQAService(sql_answer=_sql_answer(invalid_sql))
    service.repair_answers = [_sql_answer(invalid_sql)]
    monkeypatch.setattr(graph, "validate_user_query_sql_or_raise", lambda **kwargs: (_ for _ in ()).throw(ValueError("Parse SQL Error: Expected TYPE")))
    chunks = list(graph.run_smart_qa_graph(service, in_chat=True, stream=True, finish_step=ChatFinishStep.GENERATE_CHART))
    assert len(service.repair_contexts) == 1
    assert any(event["type"] == "error" for event in _events(chunks))


def test_prepare_and_execute_share_two_attempt_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    first = "SELECT CAST(value, AS DECIMAL(18, 4)) FROM orders"
    second = "SELECT BAD_FUNCTION(value) FROM orders"
    third = "SELECT STILL_BAD(value) FROM orders"
    service = FakeSmartQAService(sql_answer=_sql_answer(first))
    service.repair_answers = [_sql_answer(second), _sql_answer(third)]
    def validate(**kwargs):
        if kwargs["sql"] == first:
            raise ValueError("Parse SQL Error: Expected TYPE")
        return kwargs["sql"], {"orders"}
    monkeypatch.setattr(graph, "validate_user_query_sql_or_raise", validate)
    service.execute_sql = lambda **kwargs: (_ for _ in ()).throw(RuntimeError("syntax error near function"))
    chunks = list(graph.run_smart_qa_graph(service, in_chat=True, stream=True, finish_step=ChatFinishStep.GENERATE_CHART))
    assert len(service.repair_contexts) == 2
    assert any(event["type"] == "error" for event in _events(chunks))
```

- [ ] **Step 3: 确认测试失败**

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_smart_qa_graph.py::test_execute_sql_dialect_error_repairs_then_executes_again tests/test_smart_qa_graph.py::test_same_failure_fingerprint_is_not_repaired_twice tests/test_smart_qa_graph.py::test_prepare_and_execute_share_two_attempt_budget -q
Pop-Location
```

Expected: 执行异常仍直接抛出。

- [ ] **Step 4: 修改 `_execute_sql` 通用异常分支**

权限分支保持现有审计和失败数据输出。非权限异常执行：

```python
reason = classify_execute_sql_error(execute_error)
if reason is None:
    raise
trigger_log_error(
    session,
    service.current_logs[OperationEnum.EXECUTE_SQL],
    full_message={
        "sql": real_execute_sql,
        "error_type": reason.value,
        "message": sanitize_sql_repair_error(execute_error),
        "repair_attempt": state.get("sql_repair_count", 0),
    },
)
return _queue_sql_repair(state, error=execute_error, reason=reason, failed_sql=sql)
```

动态数据源必须以用户可见的 `sql` 重新生成和校验，日志可记录实际 `real_execute_sql`；不得直接修补展开后的 SQL。

- [ ] **Step 5: 修改执行条件边**

```python
def _should_continue_after_execute(state: SmartQAGraphState) -> str:
    if state.get("stop"):
        return END
    if state.get("sql_repair_pending"):
        return "repair_sql"
    return "generate_chart"
```

- [ ] **Step 6: 运行执行修复和安全回归**

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_smart_qa_graph.py::test_execute_sql_dialect_error_repairs_then_executes_again tests/test_smart_qa_graph.py::test_same_failure_fingerprint_is_not_repaired_twice tests/test_smart_qa_graph.py::test_prepare_and_execute_share_two_attempt_budget tests/test_smart_qa_graph.py::test_permission_denied_during_sql_validation_stops_graph tests/test_smart_qa_graph.py::test_data_skill_schema_unavailable_is_streamed_as_business_feedback -q
.\.venv\Scripts\python.exe -m pytest tests/test_smart_qa_graph.py -q
Pop-Location
```

Expected: 聚焦测试 `5 passed`，完整 Graph 测试无失败。

---

### Task 6: 修仙日期与付费 Data Skills 示例

**Files:**
- Modify: `tools/seed_xiuxian_data_skills.py:34-100`
- Modify: `tools/seed_xiuxian_data_skills.py:170-221`
- Modify: `backend/tests/test_xiuxian_data_skill_seed.py`
- Create: `tools/sync_xiuxian_sql_repair_skills.py`
- Create: `backend/tests/test_sync_xiuxian_sql_repair_skills.py`

**Interfaces:**
- Produces: `DATE_SPINE_GUIDANCE`、`SERVERPAYLOG_REPAIR_EXAMPLES`；`sync_target_skills(backend, apply)` 只更新 datasource 6 的日期与 ServerPayLog 两条 Skill。
- Consumes: `sync_xiuxian_active_payer_rate_skill.py` 的备份、CAS、Embedding 和召回验证模式，不依赖完整看板目录一致性。

- [ ] **Step 1: 写失败测试**

```python
def test_date_skill_contains_non_recursive_spine() -> None:
    prompt = seed.DATE_PARTITION_SKILL["prompt"]
    assert "day_offsets" in prompt
    assert "SELECT 0 AS day_offset" in prompt
    assert "SELECT 14" in prompt
    assert "WITH RECURSIVE" not in prompt


def test_payment_skill_contains_three_repair_examples() -> None:
    prompt = _payment_skill()["prompt"]
    assert "修复示例：按渠道付费用户" in prompt
    assert "$.mediaSource" in prompt
    assert "修复示例：等级段人均付费" in prompt
    assert "JSON_EXTRACT(u.lastinfo, '$.level')" in prompt
    assert "LEFT JOIN user_payment" in prompt
    assert "修复示例：最新完整数据日核心指标" in prompt
    assert "event = 'ServerPayLog'" in prompt
    assert "$.money" in prompt


def test_repair_examples_exclude_forbidden_payment_sources() -> None:
    assert "PayBuyRet" not in seed.SERVERPAYLOG_REPAIR_EXAMPLES
    assert "ed_money" not in seed.SERVERPAYLOG_REPAIR_EXAMPLES
    assert "paytotal" not in seed.SERVERPAYLOG_REPAIR_EXAMPLES
```

- [ ] **Step 2: 确认测试失败**

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_xiuxian_data_skill_seed.py -q
Pop-Location
```

Expected: 新常量和示例标记不存在。

- [ ] **Step 3: 增加非递归日期骨架**

定义 `DATE_SPINE_GUIDANCE`，SQL 必须为固定 0-14 偏移的非递归 CTE：

```sql
WITH day_offsets AS (
    SELECT 0 AS day_offset
    UNION ALL SELECT 1
    UNION ALL SELECT 2
    UNION ALL SELECT 3
    UNION ALL SELECT 4
    UNION ALL SELECT 5
    UNION ALL SELECT 6
    UNION ALL SELECT 7
    UNION ALL SELECT 8
    UNION ALL SELECT 9
    UNION ALL SELECT 10
    UNION ALL SELECT 11
    UNION ALL SELECT 12
    UNION ALL SELECT 13
    UNION ALL SELECT 14
), date_spine AS (
    SELECT CAST(
        DATE_FORMAT(DATE_SUB(DATE_SUB(CURDATE(), INTERVAL 1 DAY), INTERVAL day_offset DAY), '%Y%m%d')
        AS SIGNED
    ) AS dt
    FROM day_offsets
)
SELECT dt FROM date_spine ORDER BY dt
```

提示必须同时声明：读取 `event`、`user` 时仍在各自表别名直接写 `dt` 分区条件，日期骨架只负责补齐输出日期。

构造 Skill 时复制字典并追加提示：

```python
DATE_PARTITION_SKILL = {
    **_LEGACY_DATA_SKILLS[0],
    "prompt": _LEGACY_DATA_SKILLS[0]["prompt"].rstrip() + "\n\n" + DATE_SPINE_GUIDANCE,
}
```

- [ ] **Step 4: 增加三类付费修复 SQL**

`SERVERPAYLOG_REPAIR_EXAMPLES` 必须包含以下三条完整 SQL：

```sql
-- 修复示例：按渠道付费用户
SELECT
    DATE_FORMAT(STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d'), '%Y-%m-%d') AS dt,
    COALESCE(
        NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.adinfo, '$.mediaSource')), ''),
        NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.adinfo, '$.campaignName')), ''),
        '未知'
    ) AS `渠道`,
    COUNT(DISTINCT e.uid) AS `付费用户数`
FROM `event` e
WHERE e.dt BETWEEN CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 15 DAY), '%Y%m%d') AS SIGNED)
                   AND CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED)
  AND e.prod = 110000047
  AND e.event = 'ServerPayLog'
GROUP BY e.dt, `渠道`
ORDER BY e.dt, `渠道`;
```

```sql
-- 修复示例：等级段人均付费
WITH user_level AS (
    SELECT
        u.uid,
        CASE
            WHEN CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(u.lastinfo, '$.level')), '') AS DECIMAL(18, 4)) < 10 THEN '0-9'
            WHEN CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(u.lastinfo, '$.level')), '') AS DECIMAL(18, 4)) < 20 THEN '10-19'
            WHEN CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(u.lastinfo, '$.level')), '') AS DECIMAL(18, 4)) < 30 THEN '20-29'
            ELSE '30+'
        END AS level_band
    FROM `user` u
    WHERE u.dt = CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED)
      AND u.prod = 110000047
), user_payment AS (
    SELECT e.uid,
           SUM(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.money')), '') AS DECIMAL(18, 4))) AS pay_amount
    FROM `event` e
    WHERE e.dt = CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED)
      AND e.prod = 110000047
      AND e.event = 'ServerPayLog'
    GROUP BY e.uid
)
SELECT ul.level_band AS `等级段`,
       ROUND(SUM(COALESCE(up.pay_amount, 0)) / NULLIF(COUNT(DISTINCT ul.uid), 0), 2) AS `人均付费金额`
FROM user_level ul
LEFT JOIN user_payment up ON up.uid = ul.uid
GROUP BY ul.level_band;
```

```sql
-- 修复示例：最新完整数据日核心指标
SELECT
    DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 DAY), '%Y-%m-%d') AS dt,
    COUNT(DISTINCT CASE WHEN e.event = 'UserActive' THEN e.uid END) AS `DAU`,
    COUNT(DISTINCT CASE WHEN e.event = 'UserRegister' THEN e.uid END) AS `新增用户数`,
    COUNT(DISTINCT CASE WHEN e.event = 'ServerPayLog' THEN e.uid END) AS `付费用户数`,
    ROUND(SUM(CASE WHEN e.event = 'ServerPayLog'
                   THEN CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.money')), '') AS DECIMAL(18, 4))
                   ELSE 0 END), 2) AS `付费金额`
FROM `event` e
WHERE e.dt = CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED)
  AND e.prod = 110000047
  AND e.event IN ('UserActive', 'UserRegister', 'ServerPayLog');
```

将该字符串追加到 `_topic_authority("serverpaylog-revenue")`。不得追加到全局提示或其他 datasource Skill。

- [ ] **Step 5: 写定向同步失败测试**

`backend/tests/test_sync_xiuxian_sql_repair_skills.py` 覆盖：

```python
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import sync_xiuxian_sql_repair_skills as sync  # noqa: E402


def test_replace_managed_section_is_idempotent() -> None:
    original = "header\nbody"
    once = sync.replace_managed_section(original, sync.DATE_SECTION_MARKER, "date-content")
    twice = sync.replace_managed_section(once, sync.DATE_SECTION_MARKER, "date-content")
    assert once == twice
    assert once.count(sync.DATE_SECTION_MARKER) == 1


def test_build_target_prompts_only_changes_two_markers() -> None:
    current = {
        sync.DATE_SKILL_MARKER: "date prompt",
        sync.SERVERPAYLOG_SKILL_MARKER: "payment prompt",
    }
    updated = sync.build_target_prompts(current)
    assert set(updated) == {sync.DATE_SKILL_MARKER, sync.SERVERPAYLOG_SKILL_MARKER}
    assert "day_offsets" in updated[sync.DATE_SKILL_MARKER]
    assert "修复示例：按渠道付费用户" in updated[sync.SERVERPAYLOG_SKILL_MARKER]
```

- [ ] **Step 6: 实现两条 Skill 的安全定向同步**

`tools/sync_xiuxian_sql_repair_skills.py` 必须：

- 固定 `TENANT_ID=7482727237662281728`、`DATASOURCE_ID=6`。
- 按 source marker 精确读取日期 Skill 与 ServerPayLog Skill，目标必须恰好两条且 ID 唯一。
- 使用成对 start/end marker 替换托管段，重复执行结果字节一致。
- dry-run 写恢复备份并校验 prompt 长度，但不更新数据库。
- apply 在发布锁内重新读取并比较原 prompt hash，CAS 更新两条 Skill。
- 更新后刷新并验证两条 Embedding，再验证“最近15天补齐新增趋势”和“最近七天收入和 ARPPU”召回。
- 任一步失败时恢复两条 Skill；不得写入看板或其他 11 条 Skill。

CLI：

```python
parser.add_argument("--mode", choices=("dry-run", "apply"), default="dry-run")
```

- [ ] **Step 7: 运行语义测试与定向 dry-run**

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_xiuxian_data_skill_seed.py tests/test_data_skill_sql_validation.py tests/test_sync_xiuxian_sql_repair_skills.py -q
Pop-Location
$env:SHUZHI_DB_HOST='10.1.5.28'
$env:SHUZHI_DB_PORT='5432'
$env:SHUZHI_DB_DB='zhishu_bi'
$env:SHUZHI_DB_USER='root'
$env:SHUZHI_DB_PASSWORD='Password123@pg'
backend\.venv\Scripts\python.exe tools\sync_xiuxian_sql_repair_skills.py --mode dry-run
```

Expected: 测试全部通过；dry-run 输出 `mode=dry-run`、`target_skill_count=2`、`updated=false` 和恢复备份路径。当前完整看板目录存在既有不一致，本任务不得调用全量发布器绕过该门禁。

---

### Task 7: 综合验证、发布与页面串行回归

**Files:**
- Verify: `backend/apps/chat/task/sql_repair.py`
- Verify: `backend/apps/chat/task/llm.py`
- Verify: `backend/apps/chat/task/smart_qa_graph.py`
- Verify: `tools/seed_xiuxian_data_skills.py`
- Verify: `tools/sync_xiuxian_sql_repair_skills.py`
- Runtime modify: `.codex-runtime/ai-dashboard-100-test/ui_runner.cjs`
- Output: `.codex-runtime/ai-dashboard-100-test/ui-summary.json`
- Output: `.codex-runtime/ai-dashboard-100-test/ui-final-report.md`

**Interfaces:**
- Consumes: Tasks 1-6 的实现和本地四服务开发栈。
- Produces: 后端测试证据、Data Skills 发布证据、五题页面结果和完整 100 题报告。

- [ ] **Step 1: 运行聚焦后端测试**

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_sql_repair.py tests/test_data_skill_sql_validation.py tests/test_smart_qa_graph.py tests/test_xiuxian_data_skill_seed.py tests/test_sync_xiuxian_sql_repair_skills.py -q
Pop-Location
```

Expected: 所选测试零失败。

- [ ] **Step 2: 运行 Ruff**

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m ruff check apps/chat/task/sql_repair.py apps/chat/task/llm.py apps/chat/task/smart_qa_graph.py tests/test_sql_repair.py tests/test_data_skill_sql_validation.py tests/test_smart_qa_graph.py tests/test_xiuxian_data_skill_seed.py
Pop-Location
backend\.venv\Scripts\python.exe -m ruff check tools\seed_xiuxian_data_skills.py
```

Expected: 两条命令均输出 `All checks passed!`。

- [ ] **Step 3: 发布 datasource 6 Data Skills**

仅在 dry-run 和全部测试通过后执行：

```powershell
$env:SHUZHI_DB_HOST='10.1.5.28'
$env:SHUZHI_DB_PORT='5432'
$env:SHUZHI_DB_DB='zhishu_bi'
$env:SHUZHI_DB_USER='root'
$env:SHUZHI_DB_PASSWORD='Password123@pg'
backend\.venv\Scripts\python.exe tools\sync_xiuxian_sql_repair_skills.py --mode apply
```

Expected: 输出 `mode=apply`、`target_skill_count=2`、`embedding_verified=true`、`retrieval_verified=true` 且两个 `skill_ids` 非空。保存输出中的 `backup_path`；发布或 Embedding 验证失败时使用工具已有恢复流程，不手工覆盖线上记录。

- [ ] **Step 4: 重启并核对本地四服务**

```powershell
.\tools\stack-local.ps1 -Action restart -BackendPorts 8000 -StartMcp -SkipDatabase -SkipRedis -SkipNginx
$workspaceRoot=(Resolve-Path '.').Path
$runtimeRoot=Join-Path $workspaceRoot '.codex-runtime'
$frontendListener=Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue
if (-not $frontendListener) {
    Start-Process -FilePath 'C:\Windows\System32\cmd.exe' -WorkingDirectory (Join-Path $workspaceRoot 'frontend') -ArgumentList '/c','npm run dev' -RedirectStandardOutput (Join-Path $runtimeRoot 'frontend-5173.current.out.log') -RedirectStandardError (Join-Path $runtimeRoot 'frontend-5173.current.err.log') -WindowStyle Hidden
}
.\tools\stack-local.ps1 -Action status -BackendPorts 8000 -StartMcp -SkipDatabase -SkipRedis -SkipNginx
Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,OwningProcess
rg -n "LLM_REQUEST_TIMEOUT|LLM_TASK_MAX_WAIT_SECONDS|LLM_MAX_RETRIES" .codex-runtime\backend-8000.current.out.log .codex-runtime\backend-8000.current.err.log
```

Expected:

- API `8000`、MCP `8001`、前端 `5173` 均监听。
- 一个 Worker 使用与 API 相同的独立 `local-*` 队列。
- 日志值固定为 `LLM_REQUEST_TIMEOUT=120`、`LLM_TASK_MAX_WAIT_SECONDS=900`、`LLM_MAX_RETRIES=1`。

- [ ] **Step 5: 为页面 runner 增加目标题过滤**

在 `.codex-runtime/ai-dashboard-100-test/ui_runner.cjs` 增加：

```javascript
const selectedCases = new Set(
  String(process.env.AI_TEST_CASES || '')
    .split(',')
    .map(value => value.trim())
    .filter(Boolean),
);
const entries = questions
  .map((item, index) => ({
    item,
    index,
    caseName: 'q' + String(index + 1).padStart(3, '0'),
  }))
  .filter(entry => selectedCases.size === 0 || selectedCases.has(entry.caseName));
```

将固定索引循环替换为：

```javascript
for (const entry of entries) {
  const index = entry.index + 1;
  const caseName = entry.caseName;
  const item = entry.item;
```

当 `AI_TEST_CASES` 非空时，只替换这些 case 的旧结果；当变量为空时，清空旧结果并从 `q001` 到 `q100` 全量执行。账号密码继续只从环境变量读取。

- [ ] **Step 6: 串行重跑五个失败问题**

```powershell
$env:AI_TEST_USERNAME='dongjinchao_t1'
$env:AI_TEST_PASSWORD=Read-Host '请输入测试密码'
$env:AI_TEST_CASES='q025,q043,q045,q048,q086'
node .codex-runtime\ai-dashboard-100-test\ui_runner.cjs
Remove-Item Env:AI_TEST_PASSWORD
```

Expected:

- 顺序固定为 `q025 -> q043 -> q045 -> q048 -> q086`。
- 五题 `status` 均为 `passed`。
- `q025` 不再出现 `missing column aliases in recursive WITH query`。
- `q043` 最终 SQL 不包含非法 `CAST(..., AS DECIMAL)`。
- `q045/q048/q086` 使用 `ServerPayLog` 和 `$.money`，付费用户按 `uid` 去重。

- [ ] **Step 7: 检查修复日志和安全不变量**

```powershell
rg -n "sql_response_format|sql_parse|data_skill_validation|database_syntax_or_dialect|repair_attempt" .codex-runtime\backend-8000.current.err.log .codex-runtime\backend-8000.current.out.log backend\logs\debug.log
rg -n "PayBuyRet|ed_money|paytotal|missing column aliases|CAST\([^)]*,\s*AS" .codex-runtime\ai-dashboard-100-test\ui-summary.json backend\logs\debug.log
rg -n "password=|api_key=|token=|://[^:/ ]+:[^@ ]+@" .codex-runtime\backend-8000.current.err.log .codex-runtime\backend-8000.current.out.log backend\logs\debug.log
```

Expected:

- 每题最多两次 SQL 修复，没有重复指纹循环。
- 五题最终 SQL 不包含被禁止的付费来源或已知非法语法。
- 修复上下文日志不包含凭据；如第三条命令命中既有非本次日志，按时间戳和 record ID 排除并记录。

- [ ] **Step 8: 串行重跑完整 100 题**

```powershell
$env:AI_TEST_USERNAME='dongjinchao_t1'
$env:AI_TEST_PASSWORD=Read-Host '请输入测试密码'
Remove-Item Env:AI_TEST_CASES -ErrorAction SilentlyContinue
node .codex-runtime\ai-dashboard-100-test\ui_runner.cjs
Remove-Item Env:AI_TEST_PASSWORD
```

Expected:

- 从 `q001` 到 `q100` 顺序执行，不并发提交。
- 不再出现本规格定义的五类 P0 失败。
- 新失败、无数据、会话切换、停止按钮残留和埋点警告写入 `ui-issues.jsonl`，不得静默忽略。

- [ ] **Step 9: 更新最终报告**

在 `.codex-runtime/ai-dashboard-100-test/ui-final-report.md` 增加：

```markdown
## SQL 修复闭环回归

- 执行日期：2026-07-20
- 执行方式：真实 AI 看板页面，100 题串行
- 修复目标：q025、q043、q045、q048、q086
- 五题结果：逐题记录状态、最终 SQL 口径、是否触发修复、修复次数
- 100 题汇总：成功、真实失败、无数据、页面问题数量
- 安全检查：无权限绕过、无 Data Skills 绕过、无修复死循环、无敏感信息泄漏
- 新发现问题：按 P0/P1/P2 单独列出
```

验收条件：五个目标问题全部成功，完整 100 题没有同类 P0 回归，且每次修复均有重新校验和有限重试日志证据。
