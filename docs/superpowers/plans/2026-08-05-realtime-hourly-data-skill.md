# “实时”小时粒度 Data Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让“实时收入”等问题稳定解释为今天按小时趋势，同时让用户明确指定的日期优先并选择正确的事件表。

**Architecture:** 在聊天日期归一化服务中建立唯一的问题日期范围分类接口，日期表达式和 Data Skill SQL 校验共同使用该接口。平台公共 Data Skill 负责声明小时粒度和通用选表语义；结构化校验只在已确认是当前业务日时强制 `event_realtime`，避免“昨天实时收入”被误判。

**Tech Stack:** Python 3.11、pytest、FastAPI 后端服务、PostgreSQL `custom_prompt`、OpenAI-compatible embedding

## Global Constraints

- “实时”表示按小时聚合；用户未指定日期时，“实时收入”解释为“今天按小时收入”。
- 用户明确指定日期或时间范围时，用户范围优先；“昨天实时收入”解释为“昨天按小时收入”。
- 今天的事件查询使用 `event_realtime`；已经结束的日期使用 `event`；包含今天的跨日范围保留现有分表与合并规则。
- 平台逻辑保持领域无关，不写入收入字段、事件名、产品 ID 或数据库方言专用小时函数。
- 缺少表、字段、权限或工作空间业务口径时禁止静默回退。
- 平台 Data Skill 保持 `PLATFORM_PUBLIC`、`specific_ds=False`、`target_scope=ALL`，继续使用 marker、备份、CAS、embedding 刷新和发布后验证。

---

### Task 1: 统一问题日期范围与“实时”默认日期

**Files:**
- Modify: `backend/apps/chat/service/chat_date_filter.py:17-88`
- Test: `backend/tests/test_chat_dashboard_date_filter.py:1-180`

**Interfaces:**
- Consumes: 当前问题文本、模型返回的 `date_filter`、SQL 和图表类型。
- Produces: `question_date_scope(question: str | None) -> Literal["current_day", "explicit_other", "unspecified"]`，供日期归一化和 Task 2 的 SQL 校验复用。

- [ ] **Step 1: 写入日期范围分类和归一化失败测试**

在 `backend/tests/test_chat_dashboard_date_filter.py` 导入 `question_date_scope`，并加入：

```python
@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("实时收入", "current_day"),
        ("今天实时收入", "current_day"),
        ("昨天实时收入", "explicit_other"),
        ("最近14天实时收入", "explicit_other"),
        ("2026-08-01实时收入", "explicit_other"),
        ("每日收入趋势", "unspecified"),
    ],
)
def test_question_date_scope_prefers_explicit_date_over_realtime(question, expected):
    assert question_date_scope(question) == expected


def test_normalize_uses_today_when_realtime_omits_date():
    pivot = normalize_chat_date_filter_for_question(
        "实时收入",
        DATE_FILTER,
        REALTIME_DATE_TEMPLATE_SQL,
        "line",
    )

    assert pivot["date_expression"] == {
        "version": 1,
        "mode": "preset",
        "preset": "today",
    }


def test_normalize_prefers_yesterday_over_realtime_default():
    pivot = normalize_chat_date_filter_for_question(
        "昨天实时收入",
        DATE_FILTER,
        DATE_TEMPLATE_SQL,
        "line",
    )

    assert pivot["date_expression"] == {
        "version": 1,
        "mode": "preset",
        "preset": "yesterday",
    }


def test_normalize_preserves_explicit_absolute_date_over_realtime_default():
    absolute_filter = {
        **DATE_FILTER,
        "date_expression": {
            "version": 1,
            "mode": "range",
            "start": {"mode": "static", "date": "2026-08-01"},
            "end": {"mode": "static", "date": "2026-08-01"},
        },
    }

    pivot = normalize_chat_date_filter_for_question(
        "2026-08-01实时收入",
        absolute_filter,
        DATE_TEMPLATE_SQL,
        "line",
    )

    assert pivot == {"enabled": False, **absolute_filter}


def test_normalize_rejects_metric_for_realtime_hourly_question():
    with pytest.raises(
        ChatDateFilterConfigurationError,
        match="realtime_requires_hourly_time_series",
    ):
        normalize_chat_date_filter_for_question(
            "实时收入",
            None,
            "SELECT SUM(amount) FROM event_realtime",
            "metric",
        )
```

- [ ] **Step 2: 运行新测试并确认 RED**

Run:

```powershell
D:\AIWork3\chat-bi\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_chat_dashboard_date_filter.py -q
```

Expected: FAIL，因为 `question_date_scope` 尚不存在，且“实时收入”仍会被归一化为默认 `past_7_days`。

- [ ] **Step 3: 实现统一范围分类和日期优先级**

在 `backend/apps/chat/service/chat_date_filter.py` 增加严格日期模式和分类接口：

```python
from typing import Any, Literal

QuestionDateScope = Literal["current_day", "explicit_other", "unspecified"]

_REALTIME_PATTERN = re.compile(r"实时")
_EXPLICIT_YESTERDAY_PATTERN = re.compile(r"(?:昨天|昨日|前天)")
_EXPLICIT_ABSOLUTE_DATE_PATTERN = re.compile(
    r"(?<!\d)\d{4}(?:[-/.]\d{1,2}[-/.]\d{1,2}|年\d{1,2}月\d{1,2}日?)(?!\d)"
)


def question_date_scope(question: str | None) -> QuestionDateScope:
    text = str(question or "")
    has_explicit_other = bool(
        _EXPLICIT_PAST_DAYS_PATTERN.search(text)
        or _EXPLICIT_YESTERDAY_PATTERN.search(text)
        or _EXPLICIT_ABSOLUTE_DATE_PATTERN.search(text)
    )
    if has_explicit_other:
        return "explicit_other"
    if _EXPLICIT_CURRENT_DAY_PATTERN.search(text) or _REALTIME_PATTERN.search(text):
        return "current_day"
    return "unspecified"
```

按以下契约调整现有私有函数：

```python
def _explicit_question_date_expression(question: str | None) -> dict[str, Any] | None:
    text = str(question or "")
    matches = _EXPLICIT_PAST_DAYS_PATTERN.findall(text)
    distinct_days = {int(value) for value in matches}
    has_current_day = bool(_EXPLICIT_CURRENT_DAY_PATTERN.search(text))
    has_yesterday = bool(_EXPLICIT_YESTERDAY_PATTERN.search(text))
    has_absolute_date = bool(_EXPLICIT_ABSOLUTE_DATE_PATTERN.search(text))

    if has_absolute_date:
        return None
    if has_yesterday and not has_current_day and not distinct_days:
        return {"version": 1, "mode": "preset", "preset": "yesterday"}
    if has_current_day and not has_yesterday and not distinct_days:
        return {"version": 1, "mode": "preset", "preset": "today"}
    if len(distinct_days) != 1 or has_current_day or has_yesterday:
        return (
            {"version": 1, "mode": "preset", "preset": "today"}
            if not distinct_days
            and not has_current_day
            and not has_yesterday
            and question_date_scope(text) == "current_day"
            else None
        )

    days = distinct_days.pop()
    if days == 7:
        return {"version": 1, "mode": "preset", "preset": "past_7_days"}
    if days == 30:
        return {"version": 1, "mode": "preset", "preset": "past_30_days"}
    if days == 90:
        return {"version": 1, "mode": "preset", "preset": "past_90_days"}
    return {
        "version": 1,
        "mode": "range",
        "start": {"mode": "dynamic", "unit": "day", "offset": -days},
        "end": {"mode": "dynamic", "unit": "day", "offset": -1},
    }


def _question_requires_date_filter(question: str | None, chart_type: str) -> bool:
    if _REALTIME_PATTERN.search(str(question or "")):
        return True
    if str(chart_type or "").strip().lower() == "metric":
        return False
    return question_date_scope(question) != "unspecified"
```

在 `normalize_chat_date_filter_for_question(...)` 开头拒绝“实时”生成 `metric`：

```python
question_text = str(question or "")
if (
    _REALTIME_PATTERN.search(question_text)
    and str(chart_type or "").strip().lower() == "metric"
):
    raise ChatDateFilterConfigurationError("realtime_requires_hourly_time_series")
```

当问题范围是 `explicit_other` 且当前函数无法安全构造表达式时，保留并校验模型提供的 `date_expression`；只有 `unspecified` 才替换为平台默认 `past_7_days`。

- [ ] **Step 4: 运行日期归一化测试并确认 GREEN**

Run:

```powershell
D:\AIWork3\chat-bi\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_chat_dashboard_date_filter.py -q
```

Expected: PASS，且已有“今天”“最近 N 天”和默认历史窗口测试不回归。

- [ ] **Step 5: 提交日期语义实现**

```powershell
git add -- backend/apps/chat/service/chat_date_filter.py backend/tests/test_chat_dashboard_date_filter.py
git commit -m "统一实时查询日期范围语义"
```

---

### Task 2: 更新平台 Data Skill 并限定实时选表校验

**Files:**
- Modify: `backend/apps/chat/task/llm.py:250-390`
- Modify: `tools/seed_platform_realtime_event_table_skill.py:31-101`
- Test: `backend/tests/test_data_skill_sql_validation.py:1-165`
- Test: `tests/test_seed_platform_realtime_event_table_skill.py:1-145`
- Test: `backend/tests/test_data_skill_conflict_regressions.py:250-405`

**Interfaces:**
- Consumes: Task 1 的 `question_date_scope(question)` 和 Data Skill 规则字段 `when_question_date_scopes`。
- Produces: `_rule_matches_question_date_scope(rule, question) -> bool`；平台规则仅对 `current_day` 强制 `event_realtime`。

- [ ] **Step 1: 写入结构化校验和 Skill 文案失败测试**

在 `backend/tests/test_data_skill_sql_validation.py` 增加：

```python
def test_realtime_rule_only_forces_realtime_table_for_current_day_scope() -> None:
    rule = json.loads(platform_skill.SQL_VALIDATION_RULE)
    data_skill = _data_skill(rule)

    assert llm._data_skill_sql_validation_violation(
        "实时收入",
        "SELECT SUM(amount) FROM event",
        data_skill,
    ) is not None
    assert llm._data_skill_sql_validation_violation(
        "昨天实时收入",
        "SELECT SUM(amount) FROM event",
        data_skill,
    ) is None
```

在 `tests/test_seed_platform_realtime_event_table_skill.py` 增加：

```python
def test_skill_defines_realtime_as_hourly_with_explicit_date_priority() -> None:
    prompt = module.SKILL["prompt"]
    rule = json.loads(module.SQL_VALIDATION_RULE)

    assert "实时收入" in prompt
    assert "今天按小时收入" in prompt
    assert "昨天实时收入" in prompt
    assert "昨天按小时收入" in prompt
    assert "明确日期或时间范围优先" in prompt
    assert rule["when_question_date_scopes"] == ["current_day"]
```

在 `backend/tests/test_data_skill_conflict_regressions.py` 增加“昨天实时付费趋势”使用 `event` 的冲突回归：

```python
def test_explicit_historical_realtime_query_keeps_history_table(monkeypatch) -> None:
    rows, name_to_id = _fixture_rows()
    monkeypatch.setattr(custom_prompt_crud.settings, "EMBEDDING_ENABLED", False)
    monkeypatch.setattr(
        custom_prompt_crud,
        "_authorized_datasource_tables",
        lambda *_args: {"event", "event_realtime", "user"},
    )

    question = "昨天实时付费趋势"
    skill_text, skill_logs, _model = find_data_skills(
        _QueryAwareFakeSession(rows),
        datasource=6,
        tenant_id=XIUXIAN_TENANT_ID,
        current_user_id=XIUXIAN_OWNER_ID,
        current_user=SimpleNamespace(id=XIUXIAN_OWNER_ID),
        question=question,
    )

    assert 282 in _selected_ids(skill_logs, name_to_id)
    assert _data_skill_sql_validation_violation(
        question,
        "SELECT e.dt, COUNT(*) FROM event e "
        "WHERE e.dt = 20260804 GROUP BY e.dt",
        skill_text,
    ) is None
```

- [ ] **Step 2: 运行新增测试并确认 RED**

Run:

```powershell
D:\AIWork3\chat-bi\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_data_skill_sql_validation.py tests\test_seed_platform_realtime_event_table_skill.py backend\tests\test_data_skill_conflict_regressions.py -q
```

Expected: FAIL，因为平台规则没有 `when_question_date_scopes`，且 Skill 尚未写入小时语义。

- [ ] **Step 3: 为 SQL 校验增加通用日期范围门控**

在 `backend/apps/chat/task/llm.py` 导入 `question_date_scope`，增加：

```python
def _rule_matches_question_date_scope(rule: dict[str, Any], question: str) -> bool:
    scopes = {
        value.strip().lower()
        for value in _normalize_rule_terms(rule.get("when_question_date_scopes"))
        if value.strip()
    }
    if not scopes:
        return True
    return question_date_scope(question) in scopes
```

在 `_data_skill_sql_validation_violation(...)` 的规则循环中，于文本 `match` 之后、SQL scope 之前调用该门控；未声明新字段的现有规则行为保持不变。

- [ ] **Step 4: 更新平台公共 Data Skill 的时间语义和规则字段**

在 `tools/seed_platform_realtime_event_table_skill.py` 的 `SQL_VALIDATION_RULE` 增加：

```python
"when_question_date_scopes": ["current_day"],
```

在 Skill 的“选表规则”之前增加：

```markdown
## “实时”时间语义

- “实时”表示按小时聚合并返回时间序列，不表示单个累计指标或默认多日趋势。
- 用户未指定日期或时间范围时，“实时收入”解释为“今天按小时收入”。
- 用户明确指定日期或时间范围时，该范围优先；例如“昨天实时收入”解释为“昨天按小时收入”。
- 小时字段和聚合表达式必须依据当前数据源 Schema、字段编码和数据库方言生成，不得套用其他数据源示例。
```

同时把“未完成当日”规则改为：只有解析后的范围为今天时使用 `event_realtime`；明确的已结束日期继续使用 `event`。

- [ ] **Step 5: 运行 Task 2 测试并确认 GREEN**

Run:

```powershell
D:\AIWork3\chat-bi\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_data_skill_sql_validation.py tests\test_seed_platform_realtime_event_table_skill.py backend\tests\test_data_skill_conflict_regressions.py -q
```

Expected: PASS；“实时收入”仍拒绝 `event`，“昨天实时收入”允许正确的历史表，其他 Data Skill 规则不受影响。

- [ ] **Step 6: 提交 Data Skill 与校验契约**

```powershell
git add -- backend/apps/chat/task/llm.py tools/seed_platform_realtime_event_table_skill.py backend/tests/test_data_skill_sql_validation.py tests/test_seed_platform_realtime_event_table_skill.py backend/tests/test_data_skill_conflict_regressions.py
git commit -m "明确实时查询小时粒度与选表规则"
```

---

### Task 3: 回归验证并发布平台 Skill 282

**Files:**
- Verify: `backend/apps/chat/service/chat_date_filter.py`
- Verify: `backend/apps/chat/task/llm.py`
- Verify: `tools/seed_platform_realtime_event_table_skill.py`
- Runtime update: PostgreSQL `custom_prompt.id=282`
- Runtime backup: `.codex-runtime/platform-data-skill-backups/<timestamp>/skill.json`

**Interfaces:**
- Consumes: Task 1 和 Task 2 的已提交实现，以及当前系统数据库和远程 embedding 模型配置。
- Produces: 更新后的平台公共 Data Skill 282、非空且签名一致的 embedding、可恢复的发布前备份。

- [ ] **Step 1: 运行完整相关回归**

Run:

```powershell
D:\AIWork3\chat-bi\backend\.venv\Scripts\python.exe -m pytest tests\test_seed_platform_realtime_event_table_skill.py backend\tests\test_data_skill_sql_validation.py backend\tests\test_chat_dashboard_date_filter.py backend\tests\test_data_skill_conflict_regressions.py backend\tests\test_custom_prompt_datasource_scope.py backend\tests\test_analysis_assistant_permissions.py -q
```

Expected: PASS，无失败；现有平台 Skill 召回、权限和分析助手上下文测试保持通过。

- [ ] **Step 2: 检查格式和差异**

Run:

```powershell
git diff --check
git status --short
```

Expected: `git diff --check` 无输出；状态只包含本计划明确列出的文件，或在前两项提交后为空。

- [ ] **Step 3: 对平台 Skill 做只读预检**

Run:

```powershell
D:\AIWork3\chat-bi\backend\.venv\Scripts\python.exe tools\seed_platform_realtime_event_table_skill.py --mode dry-run
```

Expected:

```json
{"mode":"dry-run","skill_id":282,"updated":false,"embedding_verified":false,"backup_path":null}
```

- [ ] **Step 4: 发布 Skill 并验证 embedding 与备份**

Run:

```powershell
D:\AIWork3\chat-bi\backend\.venv\Scripts\python.exe tools\seed_platform_realtime_event_table_skill.py --mode apply
```

Expected: JSON 中 `mode="apply"`、`skill_id=282`、`updated=true`、`embedding_verified=true`，且 `backup_path` 指向 `.codex-runtime/platform-data-skill-backups/.../skill.json`。若发布、embedding 或验证失败，脚本必须恢复目标 Skill，并保留首个错误。

- [ ] **Step 5: 发布后再次只读核验并检查仓库状态**

Run:

```powershell
D:\AIWork3\chat-bi\backend\.venv\Scripts\python.exe tools\seed_platform_realtime_event_table_skill.py --mode dry-run
git log -3 --oneline
git status --short
```

Expected: dry-run 仍返回 `skill_id=282` 且不写数据库；最近提交包含本计划的两个中文实现提交；工作树无未提交源代码或测试修改。运行时备份位于已忽略的 `.codex-runtime` 下，不进入 Git。
