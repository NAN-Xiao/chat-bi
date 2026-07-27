# 综合分析助手默认时间窗口 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 仅为 `/analysis-assistant/chat` 增加可审计、可校验、非阻断的时间策略：用户未指定时间且 Data Skill 未声明时间时，以授权事实表最大业务日期为结束日，默认分析最近 14 个自然日。

**Architecture:** 新增纯函数时间策略模块和 SQLGlot 校验模块；`chat()` 异步入口在创建 SSE 响应前完成锚点选择、Redis 缓存读取和最大业务日期探测，再把已确定策略注入同步 SSE 生成器。提示词负责主动生成正确 SQL，后端负责精确字段校验、常量边界验证、一次定向修复和唯一可定位时的 AST 补齐；无法安全处理的数据块失败但整次分析继续返回 `final` 与 `finish`。

**Tech Stack:** Python 3.11、FastAPI、Pydantic、SQLGlot、redis.asyncio、Pytest、LangChain message API、现有 SQL Engine 权限执行器。

## Global Constraints

- 生效范围固定为 `POST /analysis-assistant/chat`；不得改变 Smart Q&A、看板 SQL、`/analysis-assistant/report-interpretation` 或前端筛选器。
- 时间优先级固定为：用户明确时间 > Data Skill 结构化声明 > 默认最近 14 个自然日。
- 默认窗口固定为 `end_date = 最大业务日期`、`start_date = end_date - 13 天`，包含起止日。
- `14日之后` 不包含 14 日；`从14号开始`、`14日起`、`14日及以后` 包含 14 日。
- 缺少年月时按“本轮年月 > 最近对话年月 > 最大业务日期之前最近发生的该月日”补全。
- Data Skill 仅识别 `<!-- data-skill-analysis-time:{"window_days":30,"anchor":"latest_available"} -->`；不得从示例 SQL 推断窗口。
- 最大日期探测必须使用已验证表字段、当前用户权限和 `ORDER BY ... DESC LIMIT 1`；不得使用宽泛 `MAX/MIN` 扫描、系统日期回退或动态 bounds CTE。
- Redis key 必须通过 `datasource_redis_key(...)` 构造，并包含租户、数据源、用户、业务上下文摘要、当前锚点表行权限摘要、表和字段边界；TTL 固定为 300 秒。
- Redis 调用只发生在异步 `chat()` 入口，不得在同步 SSE generator 中使用 `asyncio.run()` 或跨事件循环 Redis client。
- 事实查询必须使用具体日期常量；不得通过 `MAX(date)`、`CROSS JOIN bounds` 或字符串拼接构造时间边界。
- 无法安全补齐单个块时不执行该 SQL并继续其他块；所有块失败时仍返回正常 `final` 和 `finish`。
- 不静默选择第一个日期字段，不做字段相似度替代，不泄露数据库异常堆栈、权限字段或内部权限规则。
- 代码注释、测试说明和 Git 提交信息使用中文。

---

## 文件结构

- Create: `backend/apps/analysis_assistant/service/__init__.py`：分析助手服务包标记。
- Create: `backend/apps/analysis_assistant/service/analysis_time_policy.py`：时间意图、Data Skill 声明、日期补全、策略描述与快照序列化；纯函数，不执行 SQL 或 Redis。
- Create: `backend/apps/analysis_assistant/service/analysis_time_sql.py`：SQLGlot 时间边界验证与唯一目标 AST 补齐。
- Create: `backend/tests/test_analysis_assistant_time_policy.py`：时间语义、Skill 声明、Schema 候选、缓存键和锚点解析单元测试。
- Modify: `backend/apps/analysis_assistant/api/analysis_assistant.py`：锚点选择/探测、缓存、提示词、快照、执行流和降级接入。
- Modify: `backend/tests/test_analysis_assistant_sql_generation.py`：计划/修复提示词和 SQL 时间校验测试。
- Modify: `backend/tests/test_analysis_assistant_permissions.py`：异步入口、权限探测、SSE 非阻断和报表解读隔离测试。
- Modify: `tests/test_datasource_permission_roles.py`：删除旧宽泛 data profile 断言，改为单锚点权限执行器断言。

---

### Task 1: 实现纯时间语义策略

**Files:**
- Create: `backend/apps/analysis_assistant/service/__init__.py`
- Create: `backend/apps/analysis_assistant/service/analysis_time_policy.py`
- Create: `backend/tests/test_analysis_assistant_time_policy.py`

**Interfaces:**
- Produces: `AnalysisTimeAnchor(table: str, field: str)`。
- Produces: `AnalysisTimeIntent(kind, source, start_date, end_date, window_days, day_of_month, start_inclusive, end_inclusive, requires_anchor)`。
- Produces: `AnalysisTimePolicy(source, window_days, anchor_date, start_date, end_date, start_inclusive, end_inclusive, anchor, description)`。
- Produces: `AnalysisTimeResolution(policy, status, warnings, traces)`。
- Produces: `parse_data_skill_time_directive(data_skill: str) -> tuple[int | None, tuple[str, ...]]`。
- Produces: `parse_analysis_time_intent(question: str, history: list[str]) -> AnalysisTimeIntent`。
- Produces: `resolve_analysis_time_policy(intent: AnalysisTimeIntent, *, skill_window_days: int | None, anchor: AnalysisTimeAnchor | None, anchor_date: date | None, warnings: tuple[str, ...] = ()) -> AnalysisTimeResolution`。

- [ ] **Step 1: 写时间优先级、包含关系和补全年月的失败测试**

在 `backend/tests/test_analysis_assistant_time_policy.py` 写入：

```python
from datetime import date

import pytest

from apps.analysis_assistant.service.analysis_time_policy import (
    AnalysisTimeAnchor,
    AnalysisTimeSource,
    parse_analysis_time_intent,
    parse_data_skill_time_directive,
    resolve_analysis_time_policy,
)


ANCHOR = AnalysisTimeAnchor(table="fact_orders", field="business_date")


def _resolve(question: str, *, history: list[str] | None = None, skill: str = "", anchor_date: date = date(2026, 7, 26)):
    intent = parse_analysis_time_intent(question, history or [])
    window_days, warnings = parse_data_skill_time_directive(skill)
    return resolve_analysis_time_policy(
        intent,
        skill_window_days=window_days,
        anchor=ANCHOR,
        anchor_date=anchor_date,
        warnings=warnings,
    )


def test_default_window_contains_latest_fourteen_calendar_days() -> None:
    resolution = _resolve("分析渠道收入变化")
    assert resolution.status == "resolved"
    assert resolution.policy is not None
    assert resolution.policy.source is AnalysisTimeSource.DEFAULT_14_DAYS
    assert resolution.policy.start_date == date(2026, 7, 13)
    assert resolution.policy.end_date == date(2026, 7, 26)
    assert resolution.policy.start_inclusive is True
    assert resolution.policy.end_inclusive is True


def test_structured_data_skill_window_overrides_default_only() -> None:
    resolution = _resolve(
        "分析渠道收入变化",
        skill='<!-- data-skill-analysis-time:{"window_days":30,"anchor":"latest_available"} -->',
    )
    assert resolution.policy is not None
    assert resolution.policy.source is AnalysisTimeSource.DATA_SKILL
    assert resolution.policy.start_date == date(2026, 6, 27)


def test_sql_example_does_not_override_default_window() -> None:
    resolution = _resolve("分析渠道收入变化", skill="示例 SQL：WHERE day >= CURRENT_DATE - 30")
    assert resolution.policy is not None
    assert resolution.policy.source is AnalysisTimeSource.DEFAULT_14_DAYS


@pytest.mark.parametrize(
    ("question", "expected_boundary", "inclusive", "expected_trace_start"),
    [
        ("分析14日之后的数据", date(2026, 7, 14), False, "2026-07-15"),
        ("从14号开始分析", date(2026, 7, 14), True, "2026-07-14"),
        ("分析14日起的数据", date(2026, 7, 14), True, "2026-07-14"),
        ("分析14日及以后的数据", date(2026, 7, 14), True, "2026-07-14"),
    ],
)
def test_day_only_open_ranges_have_deterministic_inclusion(question: str, expected_boundary: date, inclusive: bool, expected_trace_start: str) -> None:
    resolution = _resolve(question)
    assert resolution.policy is not None
    assert resolution.policy.source is AnalysisTimeSource.USER
    assert resolution.policy.start_date == expected_boundary
    assert resolution.policy.start_inclusive is inclusive
    assert expected_trace_start in resolution.traces[0]


def test_day_only_uses_previous_month_when_day_has_not_occurred() -> None:
    resolution = _resolve("从14号开始分析", anchor_date=date(2026, 7, 10))
    assert resolution.policy is not None
    assert resolution.policy.start_date == date(2026, 6, 14)
    assert resolution.policy.end_date == date(2026, 7, 10)


def test_current_question_month_overrides_history_month() -> None:
    resolution = _resolve("分析8月14日之后的数据", history=["看一下 2026 年 6 月收入"])
    assert resolution.policy is not None
    assert resolution.policy.start_date == date(2025, 8, 14)


def test_explicit_year_is_not_rewritten_when_it_is_after_anchor() -> None:
    resolution = _resolve("分析2026年8月14日之后的数据")
    assert resolution.policy is not None
    assert resolution.policy.start_date == date(2026, 8, 14)
    assert resolution.policy.start_inclusive is False


def test_recent_history_supplies_missing_month_and_year() -> None:
    resolution = _resolve("从14号开始", history=["继续", "看一下 2026 年 6 月收入"])
    assert resolution.policy is not None
    assert resolution.policy.start_date == date(2026, 6, 14)


def test_explicit_absolute_range_does_not_need_anchor() -> None:
    intent = parse_analysis_time_intent("分析 2026-07-01 到 2026-07-10", [])
    resolution = resolve_analysis_time_policy(intent, skill_window_days=None, anchor=None, anchor_date=None)
    assert intent.requires_anchor is False
    assert resolution.policy is not None
    assert resolution.policy.start_date == date(2026, 7, 1)
    assert resolution.policy.end_date == date(2026, 7, 10)


@pytest.mark.parametrize("question", ["最近7天收入", "近两周收入", "昨天收入", "本月收入"])
def test_explicit_relative_time_never_uses_platform_default(question: str) -> None:
    resolution = _resolve(question)
    assert resolution.policy is not None
    assert resolution.policy.source is AnalysisTimeSource.USER


def test_invalid_skill_directive_is_visible_and_falls_back_to_default() -> None:
    resolution = _resolve(
        "分析渠道收入变化",
        skill='<!-- data-skill-analysis-time:{"window_days":0,"anchor":"today"} -->',
    )
    assert resolution.policy is not None
    assert resolution.policy.source is AnalysisTimeSource.DEFAULT_14_DAYS
    assert resolution.warnings == ("Data Skill 时间声明无效，已使用平台默认时间策略。",)
```

- [ ] **Step 2: 运行测试并确认模块不存在**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_analysis_assistant_time_policy.py -q`

Expected: FAIL，错误包含 `ModuleNotFoundError: No module named 'apps.analysis_assistant.service'`。

- [ ] **Step 3: 实现数据对象、Skill 声明和日期解析**

创建空的 `backend/apps/analysis_assistant/service/__init__.py`，并在 `backend/apps/analysis_assistant/service/analysis_time_policy.py` 写入以下实现。正则仅覆盖已确认产品语义；其它无法确定的表达保留给计划模型，但不能覆盖后端已确定策略。

```python
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from typing import Literal


DEFAULT_WINDOW_DAYS = 14
MAX_SKILL_WINDOW_DAYS = 366
_SKILL_DIRECTIVE_RE = re.compile(r"<!--\s*data-skill-analysis-time:(\{.*?\})\s*-->", re.DOTALL)
_ISO_RANGE_RE = re.compile(r"(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})日?\s*(?:到|至|~|～|—|-)\s*(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})日?")
_FULL_OPEN_RE = re.compile(r"(?:(\d{4})年)?\s*(\d{1,2})月\s*(\d{1,2})[日号]\s*(之后|以后|起|开始|及以后)")
_DAY_ONLY_RE = re.compile(r"(?:从\s*)?(\d{1,2})[日号]\s*(之后|以后|起|开始|及以后)")
_YEAR_MONTH_RE = re.compile(r"(\d{4})年\s*(\d{1,2})月")
_RELATIVE_DAYS_RE = re.compile(r"(?:最近|近)\s*(\d+)\s*(?:个)?天")
_RELATIVE_WEEKS_RE = re.compile(r"(?:最近|近)\s*(两|\d+)\s*(?:个)?周")


class AnalysisTimeSource(StrEnum):
    USER = "USER"
    DATA_SKILL = "DATA_SKILL"
    DEFAULT_14_DAYS = "DEFAULT_14_DAYS"


@dataclass(frozen=True)
class AnalysisTimeAnchor:
    table: str
    field: str


@dataclass(frozen=True)
class AnalysisTimeIntent:
    kind: Literal["none", "absolute", "relative_days", "day_open", "month", "yesterday"]
    source: AnalysisTimeSource | None = None
    start_date: date | None = None
    end_date: date | None = None
    window_days: int | None = None
    month: int | None = None
    year: int | None = None
    day_of_month: int | None = None
    start_inclusive: bool = True
    end_inclusive: bool = True
    requires_anchor: bool = True


@dataclass(frozen=True)
class AnalysisTimePolicy:
    source: AnalysisTimeSource
    window_days: int | None
    anchor_date: date | None
    start_date: date
    end_date: date
    start_inclusive: bool
    end_inclusive: bool
    anchor: AnalysisTimeAnchor | None
    description: str

    def to_snapshot(self) -> dict[str, object]:
        return {
            "source": self.source.value,
            "window_days": self.window_days,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "start_inclusive": self.start_inclusive,
            "end_inclusive": self.end_inclusive,
            "anchor": ({"table": self.anchor.table, "field": self.anchor.field} if self.anchor else None),
            "status": "resolved",
        }

    def prompt_text(self) -> str:
        start_op = ">=" if self.start_inclusive else ">"
        end_op = "<=" if self.end_inclusive else "<"
        return (
            f"后端已确定时间策略：{self.description}\n"
            f"起始边界 {start_op} {self.start_date.isoformat()}；结束边界 {end_op} {self.end_date.isoformat()}。"
        )


@dataclass(frozen=True)
class AnalysisTimeResolution:
    policy: AnalysisTimePolicy | None
    status: Literal["resolved", "unresolved"]
    warnings: tuple[str, ...] = ()
    traces: tuple[str, ...] = ()

    def to_snapshot(self) -> dict[str, object]:
        if self.policy:
            return {**self.policy.to_snapshot(), "warnings": list(self.warnings)}
        return {"status": self.status, "warnings": list(self.warnings)}


def parse_data_skill_time_directive(data_skill: str) -> tuple[int | None, tuple[str, ...]]:
    match = _SKILL_DIRECTIVE_RE.search(data_skill or "")
    if not match:
        return None, ()
    try:
        payload = json.loads(match.group(1))
        window_days = int(payload["window_days"])
        if payload.get("anchor") != "latest_available" or not 1 <= window_days <= MAX_SKILL_WINDOW_DAYS:
            raise ValueError("invalid directive")
        return window_days, ()
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None, ("Data Skill 时间声明无效，已使用平台默认时间策略。",)


def _last_year_month(history: list[str]) -> tuple[int | None, int | None]:
    for message in reversed(history):
        matches = list(_YEAR_MONTH_RE.finditer(message or ""))
        if matches:
            return int(matches[-1].group(1)), int(matches[-1].group(2))
    return None, None


def parse_analysis_time_intent(question: str, history: list[str]) -> AnalysisTimeIntent:
    text = (question or "").strip()
    absolute = _ISO_RANGE_RE.search(text)
    if absolute:
        values = [int(value) for value in absolute.groups()]
        return AnalysisTimeIntent(
            kind="absolute",
            source=AnalysisTimeSource.USER,
            start_date=date(values[0], values[1], values[2]),
            end_date=date(values[3], values[4], values[5]),
            requires_anchor=False,
        )
    relative = _RELATIVE_DAYS_RE.search(text)
    if relative:
        return AnalysisTimeIntent(kind="relative_days", source=AnalysisTimeSource.USER, window_days=int(relative.group(1)))
    relative_weeks = _RELATIVE_WEEKS_RE.search(text)
    if relative_weeks:
        weeks = 2 if relative_weeks.group(1) == "两" else int(relative_weeks.group(1))
        return AnalysisTimeIntent(kind="relative_days", source=AnalysisTimeSource.USER, window_days=weeks * 7)
    if "昨天" in text:
        return AnalysisTimeIntent(kind="yesterday", source=AnalysisTimeSource.USER)
    if "本月" in text:
        return AnalysisTimeIntent(kind="month", source=AnalysisTimeSource.USER)
    full_open = _FULL_OPEN_RE.search(text)
    if full_open:
        explicit_year = int(full_open.group(1)) if full_open.group(1) else None
        marker = full_open.group(4)
        return AnalysisTimeIntent(
            kind="day_open",
            source=AnalysisTimeSource.USER,
            year=explicit_year,
            month=int(full_open.group(2)),
            day_of_month=int(full_open.group(3)),
            start_inclusive=marker not in {"之后", "以后"},
        )
    day_only = _DAY_ONLY_RE.search(text)
    if day_only:
        history_year, history_month = _last_year_month(history)
        marker = day_only.group(2)
        return AnalysisTimeIntent(
            kind="day_open",
            source=AnalysisTimeSource.USER,
            year=history_year,
            month=history_month,
            day_of_month=int(day_only.group(1)),
            start_inclusive=marker not in {"之后", "以后"},
        )
    return AnalysisTimeIntent(kind="none")


def _latest_occurrence(anchor_date: date, year: int | None, month: int | None, day_of_month: int) -> date:
    if year is not None and month is not None:
        return date(year, month, day_of_month)
    if month is not None:
        candidate = date(anchor_date.year, month, day_of_month)
        return candidate if candidate <= anchor_date else date(anchor_date.year - 1, month, day_of_month)
    candidate = date(anchor_date.year, anchor_date.month, day_of_month)
    if candidate <= anchor_date:
        return candidate
    previous_month_end = anchor_date.replace(day=1) - timedelta(days=1)
    return date(previous_month_end.year, previous_month_end.month, day_of_month)


def resolve_analysis_time_policy(
    intent: AnalysisTimeIntent,
    *,
    skill_window_days: int | None,
    anchor: AnalysisTimeAnchor | None,
    anchor_date: date | None,
    warnings: tuple[str, ...] = (),
) -> AnalysisTimeResolution:
    if intent.kind == "absolute" and intent.start_date and intent.end_date:
        policy = AnalysisTimePolicy(
            source=AnalysisTimeSource.USER,
            window_days=None,
            anchor_date=None,
            start_date=intent.start_date,
            end_date=intent.end_date,
            start_inclusive=True,
            end_inclusive=True,
            anchor=anchor,
            description=f"用户指定 {intent.start_date.isoformat()} 至 {intent.end_date.isoformat()}",
        )
        return AnalysisTimeResolution(policy, "resolved", warnings, (f"已采用用户指定时间范围：{policy.start_date} 至 {policy.end_date}。",))
    if anchor_date is None:
        warning = "无法确认当前数据源的最大业务日期，本次仅执行能够确认时间边界的分析块。"
        return AnalysisTimeResolution(None, "unresolved", warnings + (warning,), (warning,))
    if intent.kind == "day_open" and intent.day_of_month:
        base = _latest_occurrence(anchor_date, intent.year, intent.month, intent.day_of_month)
        effective_start = base if intent.start_inclusive else base + timedelta(days=1)
        policy = AnalysisTimePolicy(AnalysisTimeSource.USER, None, anchor_date, base, anchor_date, intent.start_inclusive, True, anchor, f"用户开放时间范围 {effective_start.isoformat()} 至 {anchor_date.isoformat()}")
    elif intent.kind == "relative_days" and intent.window_days:
        policy = AnalysisTimePolicy(AnalysisTimeSource.USER, intent.window_days, anchor_date, anchor_date - timedelta(days=intent.window_days - 1), anchor_date, True, True, anchor, f"用户指定最近 {intent.window_days} 个自然日")
    elif intent.kind == "yesterday":
        yesterday = anchor_date - timedelta(days=1)
        policy = AnalysisTimePolicy(AnalysisTimeSource.USER, 1, anchor_date, yesterday, yesterday, True, True, anchor, "用户指定昨天")
    elif intent.kind == "month":
        start = anchor_date.replace(day=1)
        policy = AnalysisTimePolicy(AnalysisTimeSource.USER, None, anchor_date, start, anchor_date, True, True, anchor, "用户指定本月")
    else:
        days = skill_window_days or DEFAULT_WINDOW_DAYS
        source = AnalysisTimeSource.DATA_SKILL if skill_window_days else AnalysisTimeSource.DEFAULT_14_DAYS
        policy = AnalysisTimePolicy(source, days, anchor_date, anchor_date - timedelta(days=days - 1), anchor_date, True, True, anchor, f"最近 {days} 个自然日")
    trace = f"已采用时间范围：{policy.start_date.isoformat()} 至 {policy.end_date.isoformat()}。"
    if intent.kind == "day_open":
        effective_start = policy.start_date if policy.start_inclusive else policy.start_date + timedelta(days=1)
        trace = f"已将用户日期表达解释为 {effective_start.isoformat()} 至 {policy.end_date.isoformat()}。"
    return AnalysisTimeResolution(policy, "resolved", warnings, (trace,))
```

显式年月在未来时回退上一年这一行为必须保留，以满足“最大业务日期之前最近发生”的约束。

- [ ] **Step 4: 运行时间语义测试并修正边界**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_analysis_assistant_time_policy.py -q`

Expected: PASS，至少 `10 passed`。

- [ ] **Step 5: 提交纯时间策略**

```powershell
git add backend/apps/analysis_assistant/service/__init__.py backend/apps/analysis_assistant/service/analysis_time_policy.py backend/tests/test_analysis_assistant_time_policy.py
git commit -m "功能：新增综合分析助手时间策略"
```

---

### Task 2: 增加授权锚点选择、轻量探测与短期缓存

**Files:**
- Modify: `backend/apps/analysis_assistant/api/analysis_assistant.py:1-60,1987-2084,3448-3512`
- Modify: `backend/tests/test_analysis_assistant_time_policy.py`
- Modify: `tests/test_datasource_permission_roles.py:2535-2563`

**Interfaces:**
- Consumes: Task 1 的 `AnalysisTimeAnchor`、`AnalysisTimeIntent`、`AnalysisTimeResolution` 和解析/解析完成函数。
- Produces: `_schema_time_field_candidates(schema: str, allowed_tables: list[str]) -> dict[str, tuple[str, ...]]`。
- Produces: `_select_analysis_time_anchor(llm, question: str, semantic_context: str, candidates: dict[str, tuple[str, ...]]) -> AnalysisTimeAnchor`。
- Produces: `_probe_latest_business_date(..., anchor: AnalysisTimeAnchor) -> date`，固定 `query_timeout=5`。
- Produces: `_resolve_chat_time_policy(...) -> AnalysisTimeResolution` 异步函数，所有 Redis I/O 均在该函数内完成。

- [ ] **Step 1: 写候选字段、权限探测、缓存边界和请求去重的失败测试**

向 `backend/tests/test_analysis_assistant_time_policy.py` 追加：

```python
import asyncio
from types import SimpleNamespace

from apps.analysis_assistant.api import analysis_assistant as analysis_api


def test_schema_time_candidates_keep_only_allowed_exact_temporal_fields() -> None:
    schema = """
# Table: public.fact_orders
[
(business_date:date),
(created_at:timestamp),
(amount:numeric)
]
# Table: secret_orders
[
(business_date:date)
]
"""
    assert analysis_api._schema_time_field_candidates(schema, ["fact_orders"]) == {
        "fact_orders": ("business_date", "created_at")
    }


def test_anchor_selector_rejects_model_field_outside_exact_candidates() -> None:
    llm = SimpleNamespace(invoke=lambda _messages: SimpleNamespace(content='{"table":"fact_orders","field":"day"}'))
    with pytest.raises(ValueError, match="未选择有效的业务时间字段"):
        analysis_api._select_analysis_time_anchor(
            llm,
            "分析收入",
            "",
            {"fact_orders": ("business_date",)},
        )


def test_latest_date_probe_uses_single_ordered_field_and_permission_executor(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    def fake_execute(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(result={"data": [{"anchor_value": "2026-07-26"}]})

    monkeypatch.setattr(analysis_api, "execute_user_query_or_raise", fake_execute)
    value = analysis_api._probe_latest_business_date(
        session=object(),
        current_user=SimpleNamespace(id=7),
        datasource=SimpleNamespace(id=1, type="postgresql"),
        allowed_tables=["fact_orders"],
        anchor=AnalysisTimeAnchor("fact_orders", "business_date"),
    )
    assert value == date(2026, 7, 26)
    assert "ORDER BY" in calls[0]["sql"]
    assert "DESC" in calls[0]["sql"]
    assert "LIMIT 1" in calls[0]["sql"]
    assert "MAX(" not in calls[0]["sql"]
    assert calls[0]["allowed_tables"] == ["fact_orders"]
    assert calls[0]["apply_row_permissions"] is True
    assert calls[0]["query_timeout"] == 5


def test_anchor_cache_key_is_user_business_context_and_permission_scoped() -> None:
    key = analysis_api._analysis_time_anchor_cache_key(
        tenant_id=9,
        datasource_id=10,
        user_id=11,
        context_hash="abc123",
        permission_hash="permission456",
        anchor=AnalysisTimeAnchor("fact_orders", "business_date"),
    )
    assert ":tenant:9:datasource:10:" in key
    assert ":analysis-time-anchor:11:abc123:permission456:fact_orders:business_date" in key


def test_permission_fingerprint_changes_with_row_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    filters = [{"field": "region_id", "operator": "in", "value": [1]}]
    monkeypatch.setattr(analysis_api, "get_row_permission_filters", lambda **_kwargs: filters)
    first = analysis_api._analysis_time_permission_fingerprint(
        session=object(), current_user=SimpleNamespace(id=7), datasource=SimpleNamespace(id=1), anchor=ANCHOR,
    )
    filters[0]["value"] = [2]
    second = analysis_api._analysis_time_permission_fingerprint(
        session=object(), current_user=SimpleNamespace(id=7), datasource=SimpleNamespace(id=1), anchor=ANCHOR,
    )
    assert first != second
```

将 `tests/test_datasource_permission_roles.py::test_analysis_assistant_data_profile_uses_query_executor` 替换为：

```python
def test_analysis_assistant_anchor_probe_uses_query_executor(monkeypatch):
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_role="admin", tenant_id=1)
    datasource = SimpleNamespace(id=1, type="pg")
    calls = []

    def fake_execute_user_query_or_raise(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(result={"data": [{"anchor_value": "2026-01-31"}]})

    monkeypatch.setattr(analysis_assistant_api, "execute_user_query_or_raise", fake_execute_user_query_or_raise)
    result = analysis_assistant_api._probe_latest_business_date(
        session=object(),
        current_user=current_user,
        datasource=datasource,
        allowed_tables=["orders"],
        anchor=analysis_assistant_api.AnalysisTimeAnchor("orders", "order_date"),
    )
    assert result.isoformat() == "2026-01-31"
    assert calls[0]["allowed_tables"] == ["orders"]
    assert calls[0]["apply_row_permissions"] is True
    assert 'ORDER BY "order_date" DESC LIMIT 1' in calls[0]["sql"]
    assert "MAX(" not in calls[0]["sql"]
```

- [ ] **Step 2: 运行定向测试并确认新接口缺失**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_analysis_assistant_time_policy.py ../tests/test_datasource_permission_roles.py::test_analysis_assistant_anchor_probe_uses_query_executor -q`

Expected: FAIL，首个错误包含 `_schema_time_field_candidates` 或 `_probe_latest_business_date` 不存在。

- [ ] **Step 3: 删除旧宽泛日期画像并实现锚点运行时**

在 `backend/apps/analysis_assistant/api/analysis_assistant.py`：

1. 删除 `_collect_date_bounds` 和 `_get_data_profile`，因为生产 `chat()` 已不调用它们，旧测试也已迁移；保留 `_profile_table_expression`，供新的单锚点查询生成受方言保护的表表达式。
2. 增加 `asyncio`、`hashlib`、`json`、`date`、`RedisError`、`get_redis_client`、`datasource_redis_key`、`get_row_permission_filters` 和 Task 1 类型/函数导入。
3. 增加以下常量与函数；字段候选仅由授权 Schema 的精确名称生成。

```python
ANALYSIS_TIME_ANCHOR_CACHE_TTL_SECONDS = 300
ANALYSIS_TIME_ANCHOR_QUERY_TIMEOUT_SECONDS = 5


def _schema_time_field_candidates(schema: str, allowed_tables: list[str]) -> dict[str, tuple[str, ...]]:
    allowed = {str(table).split(".")[-1].lower() for table in allowed_tables}
    candidates: dict[str, tuple[str, ...]] = {}
    for raw_table, body in re.findall(r"# Table:\s*([^\n,]+)[^\n]*\n\[\n(.*?)\n\]", schema, flags=re.DOTALL):
        table = raw_table.strip().split(".")[-1]
        if table.lower() not in allowed:
            continue
        fields = tuple(
            field.strip()
            for field, field_type in re.findall(r"\(([^:()]+):([^,()]+)", body)
            if any(token in field_type.strip().lower() for token in ("date", "time", "timestamp"))
        )
        if fields:
            candidates[table] = fields
    return candidates


def _select_analysis_time_anchor(llm, question: str, semantic_context: str, candidates: dict[str, tuple[str, ...]]) -> AnalysisTimeAnchor:
    payload = orjson.dumps(candidates).decode()
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=(
            "只选择本次问题最相关的主业务时间锚点，不生成 SQL。"
            "只能从候选表字段中逐字选择；无法判断时返回空字符串。"
            '严格返回 {"table":"...","field":"..."}。\n'
            f"用户问题：{question}\n业务语义：{semantic_context[:12000]}\n候选：{payload}"
        )),
    ]
    selected = _extract_json_object(_llm_text(llm, messages))
    table = str(selected.get("table") or "").strip()
    field = str(selected.get("field") or "").strip()
    if table not in candidates or field not in candidates[table]:
        raise ValueError("未选择有效的业务时间字段")
    return AnalysisTimeAnchor(table=table, field=field)


def _analysis_time_permission_fingerprint(*, session, current_user, datasource, anchor: AnalysisTimeAnchor) -> str:
    filters = get_row_permission_filters(
        session=session,
        current_user=current_user,
        ds=datasource,
        tables=[anchor.table],
    )
    payload = json.dumps(filters or [], ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _analysis_time_anchor_cache_key(*, tenant_id: int, datasource_id: int, user_id: int, context_hash: str, permission_hash: str, anchor: AnalysisTimeAnchor) -> str:
    return datasource_redis_key(
        tenant_id,
        datasource_id,
        "analysis-time-anchor",
        user_id,
        context_hash,
        permission_hash,
        anchor.table,
        anchor.field,
    )


def _coerce_business_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if re.fullmatch(r"\d{8}", text):
        return datetime.strptime(text, "%Y%m%d").date()
    return date.fromisoformat(text[:10])


def _probe_latest_business_date(*, session, current_user, datasource, allowed_tables: list[str], anchor: AnalysisTimeAnchor) -> date:
    table_name, table_expr = _profile_table_expression(datasource, anchor.table)
    field_expr = _quote_identifier(datasource, anchor.field)
    sql = (
        f"SELECT {field_expr} AS anchor_value FROM {table_expr} "
        f"WHERE {field_expr} IS NOT NULL ORDER BY {field_expr} DESC LIMIT 1"
    )
    result = execute_user_query_or_raise(
        session=session,
        current_user=current_user,
        datasource=datasource,
        sql=sql,
        allowed_tables=[table_name],
        origin_column=False,
        apply_row_permissions=True,
        query_timeout=ANALYSIS_TIME_ANCHOR_QUERY_TIMEOUT_SECONDS,
    ).result
    rows = result.get("data") or []
    if not rows:
        raise ValueError("业务时间字段没有可用数据")
    return _coerce_business_date(rows[0].get("anchor_value"))
```

保留 `_profile_table_expression` 供单锚点查询使用，只删除其宽泛调用者。然后实现 `_resolve_chat_time_policy(...)`：

```python
async def _resolve_chat_time_policy(
    *, session, current_user, datasource, business_context, llm, request, semantic_context: str,
) -> AnalysisTimeResolution:
    question = request.messages[-1].content.strip()
    history = [item.content for item in request.messages[-6:-1] if item.content.strip()]
    intent = parse_analysis_time_intent(question, history)
    skill_days, warnings = parse_data_skill_time_directive(business_context.data_skill)
    if not intent.requires_anchor:
        return resolve_analysis_time_policy(
            intent,
            skill_window_days=skill_days,
            anchor=None,
            anchor_date=None,
            warnings=warnings,
        )
    candidates = _schema_time_field_candidates(business_context.schema, business_context.allowed_tables)
    try:
        anchor = await asyncio.to_thread(_select_analysis_time_anchor, llm, question, semantic_context, candidates)
    except Exception:
        return resolve_analysis_time_policy(intent, skill_window_days=skill_days, anchor=None, anchor_date=None, warnings=warnings)
    key: str | None = None
    client = None
    cached_date: date | None = None
    try:
        key = _analysis_time_anchor_cache_key(
            tenant_id=require_current_tenant_id(current_user),
            datasource_id=int(datasource.id),
            user_id=int(current_user.id),
            context_hash=str(business_context.business_context_hash or "none"),
            permission_hash=_analysis_time_permission_fingerprint(
                session=session,
                current_user=current_user,
                datasource=datasource,
                anchor=anchor,
            ),
            anchor=anchor,
        )
        client = get_redis_client()
        raw_cached = await client.get(key)
        if raw_cached:
            cached_date = _coerce_business_date(raw_cached.decode() if isinstance(raw_cached, bytes) else raw_cached)
    except (RedisError, RuntimeError, TypeError, ValueError):
        cached_date = None
    if cached_date is not None:
        return resolve_analysis_time_policy(intent, skill_window_days=skill_days, anchor=anchor, anchor_date=cached_date, warnings=warnings)
    try:
        anchor_date = _probe_latest_business_date(
            session=session,
            current_user=current_user,
            datasource=datasource,
            allowed_tables=business_context.allowed_tables,
            anchor=anchor,
        )
    except Exception:
        return resolve_analysis_time_policy(intent, skill_window_days=skill_days, anchor=anchor, anchor_date=None, warnings=warnings)
    if client is not None and key is not None:
        try:
            await client.set(key, anchor_date.isoformat(), ex=ANALYSIS_TIME_ANCHOR_CACHE_TTL_SECONDS)
        except RedisError:
            pass
    return resolve_analysis_time_policy(intent, skill_window_days=skill_days, anchor=anchor, anchor_date=anchor_date, warnings=warnings)
```

同一请求只调用 `_resolve_chat_time_policy()` 一次；它的返回值在 generator 闭包中复用，满足请求级去重。Redis 不可用时继续直接探测，不把缓存异常暴露给用户。

- [ ] **Step 4: 运行锚点与权限测试**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_analysis_assistant_time_policy.py ../tests/test_datasource_permission_roles.py::test_analysis_assistant_anchor_probe_uses_query_executor -q`

Expected: PASS，SQL 断言确认只执行一个排序取首行查询。

- [ ] **Step 5: 提交锚点运行时**

```powershell
git add backend/apps/analysis_assistant/api/analysis_assistant.py backend/tests/test_analysis_assistant_time_policy.py tests/test_datasource_permission_roles.py
git commit -m "功能：增加分析时间锚点探测与缓存"
```

---

### Task 3: 把已确定策略注入计划、执行轨迹和上下文快照

**Files:**
- Modify: `backend/apps/analysis_assistant/api/analysis_assistant.py:234-320,3305-3514`
- Modify: `backend/tests/test_analysis_assistant_sql_generation.py`
- Modify: `backend/tests/test_analysis_assistant_permissions.py:137-218`

**Interfaces:**
- Consumes: Task 2 的 `_resolve_chat_time_policy(...)`。
- Produces: `_time_policy_context(resolution: AnalysisTimeResolution) -> str`。
- Changes: `_initial_outline_messages(..., time_resolution: AnalysisTimeResolution)`。
- Changes: `_build_plan(..., time_resolution: AnalysisTimeResolution)`。
- Changes: `_build_forecast_plan(..., time_resolution: AnalysisTimeResolution)`。
- Snapshot contract: `agentContextSnapshot.business_context.analysis_time_policy`。

- [ ] **Step 1: 写提示词、快照和路由隔离失败测试**

向 `backend/tests/test_analysis_assistant_sql_generation.py` 追加：

```python
from datetime import date
from apps.analysis_assistant.service.analysis_time_policy import AnalysisTimeAnchor, AnalysisTimePolicy, AnalysisTimeResolution, AnalysisTimeSource


def _resolved_time() -> AnalysisTimeResolution:
    policy = AnalysisTimePolicy(
        source=AnalysisTimeSource.DEFAULT_14_DAYS,
        window_days=14,
        anchor_date=date(2026, 7, 26),
        start_date=date(2026, 7, 13),
        end_date=date(2026, 7, 26),
        start_inclusive=True,
        end_inclusive=True,
        anchor=AnalysisTimeAnchor("fact_orders", "business_date"),
        description="最近 14 个自然日",
    )
    return AnalysisTimeResolution(policy=policy, status="resolved")


def test_plan_prompt_receives_backend_resolved_constant_time_policy() -> None:
    class CaptureLLM:
        def __init__(self):
            self.messages = []
        def invoke(self, messages):
            self.messages = messages
            return SimpleNamespace(content='{"intro":"分析","queries":[{"id":"q1","title":"趋势","purpose":"趋势","sql":"SELECT 1","time_fields":[]}]}')
    llm = CaptureLLM()
    request = analysis_api.AnalysisAssistantRequest(
        datasource_id=1,
        messages=[analysis_api.AnalysisAssistantMessage(role="user", content="分析收入")],
    )
    analysis_api._build_plan(
        llm, request, "", "", SimpleNamespace(name="测试", type="pg"),
        time_resolution=_resolved_time(),
    )
    prompt = llm.messages[-1].content
    assert "2026-07-13" in prompt
    assert "2026-07-26" in prompt
    assert "不得重新解释或扩大" in prompt
    assert "具体日期常量" in prompt
```

在 `backend/tests/test_analysis_assistant_permissions.py::test_chat_builds_business_sql_context_before_streaming` 中 mock `_resolve_chat_time_policy` 返回 `_resolved_time()`，并新增断言：

```python
assert snapshots[0]["business_context"]["analysis_time_policy"] == {
    "source": "DEFAULT_14_DAYS",
    "window_days": 14,
    "start_date": "2026-07-13",
    "end_date": "2026-07-26",
    "start_inclusive": True,
    "end_inclusive": True,
    "anchor": {"table": "fact_orders", "field": "business_date"},
    "status": "resolved",
    "warnings": [],
}
```

保留现有 `/report-interpretation` 测试不改 mock 签名，从而证明新预处理仅进入 `chat()`。

- [ ] **Step 2: 运行定向测试并确认签名尚未接入**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_analysis_assistant_sql_generation.py::test_plan_prompt_receives_backend_resolved_constant_time_policy tests/test_analysis_assistant_permissions.py::test_chat_builds_business_sql_context_before_streaming -q`

Expected: FAIL，包含 `_build_plan() got an unexpected keyword argument 'time_resolution'`。

- [ ] **Step 3: 更新计划契约和所有分析提示词**

在 `PLAN_PROMPT`、`FORECAST_PLAN_PROMPT` 和 `SQL_REPAIR_PROMPT` 增加完全相同的通用约束：

```text
后端提供的时间策略是最终约束，不得重新解释或扩大。
所有适用的数据块必须使用给出的具体日期常量和包含关系；不得使用动态 MAX(date)、bounds CTE 或 CROSS JOIN bounds 计算边界。
每个 query 必须返回 time_fields 数组，元素格式为 {"table":"物理表名","field":"物理时间字段"}；无适用时间字段时返回空数组，不得虚构字段。
图表标题、分析说明和最终结论必须说明实际使用的时间范围。
```

修改三个构建函数签名，并在 `user_content` 的用户问题之后插入：

```python
def _time_policy_context(resolution: AnalysisTimeResolution) -> str:
    if resolution.policy:
        return "分析时间策略（后端已确定，必须严格使用）：\n" + resolution.policy.prompt_text() + "\n\n"
    return "分析时间策略：当前无法确认最大业务日期；只生成能够明确证明时间边界的数据块。\n\n"
```

`_build_plan` 和 `_build_forecast_plan` 的 `time_resolution` 参数必须是必传关键字参数，避免其它调用方静默漏传：

```python
def _build_plan(..., data_skill: str = "", *, time_resolution: AnalysisTimeResolution) -> dict[str, Any]:
    ...
    user_content = (... f"用户问题：{question}\n\n" f"{_time_policy_context(time_resolution)}" ...)
```

`_initial_outline_messages` 同样加入时间描述，使初始分析框架不会承诺全历史分析。

- [ ] **Step 4: 在异步入口解析一次并写入快照/轨迹**

在 `chat()` 中，放在 `_create_llm(...)` 之后、`build_agent_context_snapshot(...)` 之前：

```python
time_resolution = await _resolve_chat_time_policy(
    session=session,
    current_user=current_user,
    datasource=datasource,
    business_context=business_context,
    llm=llm,
    request=request,
    semantic_context=semantic_context,
)
snapshot_business_context = business_context.snapshot_metadata()
snapshot_business_context["analysis_time_policy"] = time_resolution.to_snapshot()
```

把 snapshot 调用的 `business_context=` 改为 `snapshot_business_context`。在 generator 首个 `context_snapshot` 之后依次输出 `time_resolution.warnings` 和 `time_resolution.traces`：

```python
for warning in time_resolution.warnings:
    yield _trace(warning)
for trace_message in time_resolution.traces:
    yield _trace(trace_message)
```

所有 `_initial_outline_messages`、`_build_plan`、`_build_forecast_plan` 调用显式传入 `time_resolution=time_resolution`。接受首个 SSE 在锚点选择/探测后才返回的延迟；不得把 Redis 逻辑移入 generator。

- [ ] **Step 5: 运行提示词、快照和报表解读回归测试**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_analysis_assistant_sql_generation.py tests/test_analysis_assistant_permissions.py -q`

Expected: PASS；既有 `/report-interpretation` 测试数量和行为不变。

- [ ] **Step 6: 提交策略接入**

```powershell
git add backend/apps/analysis_assistant/api/analysis_assistant.py backend/tests/test_analysis_assistant_sql_generation.py backend/tests/test_analysis_assistant_permissions.py
git commit -m "功能：向分析计划注入确定时间范围"
```

---

### Task 4: 用 SQLGlot 校验常量边界并做唯一目标补齐

**Files:**
- Create: `backend/apps/analysis_assistant/service/analysis_time_sql.py`
- Modify: `backend/tests/test_analysis_assistant_sql_generation.py`

**Interfaces:**
- Consumes: Task 1 的 `AnalysisTimePolicy`。
- Produces: `AnalysisTimeSqlError`，面向用户的 `str(error)` 固定为安全中文，不包含表字段或原始 SQL。
- Produces: `enforce_analysis_time_sql(sql: str, *, policy: AnalysisTimePolicy, declared_time_fields: list[dict[str, str]], schema_time_fields: dict[str, tuple[str, ...]], dialect: str | None, allow_rewrite: bool) -> str`。

- [ ] **Step 1: 写常量边界、动态 bounds、多表和唯一补齐的失败测试**

向 `backend/tests/test_analysis_assistant_sql_generation.py` 追加：

```python
import pytest
from apps.analysis_assistant.service.analysis_time_sql import AnalysisTimeSqlError, enforce_analysis_time_sql


SCHEMA_TIME_FIELDS = {"fact_orders": ("business_date",), "fact_refunds": ("refund_date",)}


def _enforce(sql: str, fields: list[dict[str, str]], *, rewrite: bool = False) -> str:
    return enforce_analysis_time_sql(
        sql,
        policy=_resolved_time().policy,
        declared_time_fields=fields,
        schema_time_fields=SCHEMA_TIME_FIELDS,
        dialect="postgres",
        allow_rewrite=rewrite,
    )


def test_time_sql_accepts_exact_constant_bounds() -> None:
    sql = "SELECT business_date, SUM(amount) FROM fact_orders WHERE business_date >= DATE '2026-07-13' AND business_date <= DATE '2026-07-26' GROUP BY business_date"
    assert "2026-07-13" in _enforce(sql, [{"table": "fact_orders", "field": "business_date"}])


def test_time_sql_rejects_dynamic_max_boundary() -> None:
    sql = "WITH bounds AS (SELECT MAX(business_date) end_date FROM fact_orders) SELECT * FROM fact_orders CROSS JOIN bounds WHERE business_date <= end_date"
    with pytest.raises(AnalysisTimeSqlError, match="时间边界校验未通过"):
        _enforce(sql, [{"table": "fact_orders", "field": "business_date"}])


def test_time_sql_rejects_conflicting_constant_range() -> None:
    sql = "SELECT * FROM fact_orders WHERE business_date >= DATE '2026-01-01' AND business_date <= DATE '2026-01-31'"
    with pytest.raises(AnalysisTimeSqlError, match="时间边界校验未通过"):
        _enforce(sql, [{"table": "fact_orders", "field": "business_date"}])


def test_time_sql_rewrites_only_one_unambiguous_target() -> None:
    rewritten = _enforce("SELECT * FROM fact_orders", [{"table": "fact_orders", "field": "business_date"}], rewrite=True)
    assert "2026-07-13" in rewritten
    assert "2026-07-26" in rewritten


def test_time_sql_requires_each_declared_fact_scan() -> None:
    sql = "SELECT * FROM fact_orders o JOIN fact_refunds r ON r.order_id = o.id WHERE o.business_date >= DATE '2026-07-13' AND o.business_date <= DATE '2026-07-26'"
    with pytest.raises(AnalysisTimeSqlError, match="时间边界校验未通过"):
        _enforce(sql, [
            {"table": "fact_orders", "field": "business_date"},
            {"table": "fact_refunds", "field": "refund_date"},
        ])


def test_time_sql_does_not_choose_first_field_when_declaration_is_ambiguous() -> None:
    with pytest.raises(AnalysisTimeSqlError, match="时间边界校验未通过"):
        enforce_analysis_time_sql(
            "SELECT * FROM fact_orders",
            policy=_resolved_time().policy,
            declared_time_fields=[],
            schema_time_fields={"fact_orders": ("business_date", "created_at")},
            dialect="postgres",
            allow_rewrite=True,
        )


def test_time_sql_allows_dimension_query_without_temporal_fields() -> None:
    sql = enforce_analysis_time_sql(
        "SELECT region_id, region_name FROM dim_region",
        policy=_resolved_time().policy,
        declared_time_fields=[],
        schema_time_fields=SCHEMA_TIME_FIELDS,
        dialect="postgres",
        allow_rewrite=False,
    )
    assert "dim_region" in sql
```

- [ ] **Step 2: 运行 SQL 单元测试并确认模块不存在**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_analysis_assistant_sql_generation.py -q`

Expected: FAIL，包含 `No module named 'apps.analysis_assistant.service.analysis_time_sql'`。

- [ ] **Step 3: 实现 AST 校验和受限补齐**

创建 `backend/apps/analysis_assistant/service/analysis_time_sql.py`。实现必须遵循以下算法，不得退化为字符串拼接：

```python
from __future__ import annotations

from dataclasses import dataclass

from sqlglot import exp, parse_one
from sqlglot.errors import ParseError

from apps.analysis_assistant.service.analysis_time_policy import AnalysisTimePolicy


class AnalysisTimeSqlError(ValueError):
    def __init__(self) -> None:
        super().__init__("时间边界校验未通过，当前分析角度未执行。")


@dataclass(frozen=True)
class _Binding:
    table: str
    field: str
    alias: str


def _literal_date(node: exp.Expression) -> str | None:
    if isinstance(node, exp.Literal) and node.is_string:
        return str(node.this)[:10]
    if isinstance(node, (exp.Cast, exp.Date)):
        return _literal_date(node.this)
    return None


def _comparison_matches(node: exp.Expression, binding: _Binding, expected: str, *, lower: bool, inclusive: bool) -> bool:
    allowed_types = ((exp.GTE,) if lower and inclusive else (exp.GT,) if lower else (exp.LTE,) if inclusive else (exp.LT,))
    if not isinstance(node, allowed_types):
        return False
    left = node.this
    if not isinstance(left, exp.Column) or left.name.lower() != binding.field.lower():
        return False
    if left.table and left.table.lower() != binding.alias.lower():
        return False
    return _literal_date(node.expression) == expected


def _resolve_bindings(tree: exp.Expression, declared_time_fields: list[dict[str, str]], schema_time_fields: dict[str, tuple[str, ...]]) -> list[_Binding]:
    declared = {(str(item.get("table") or "").lower(), str(item.get("field") or "").lower()) for item in declared_time_fields}
    normalized_schema_fields = {table.lower(): fields for table, fields in schema_time_fields.items()}
    bindings: list[_Binding] = []
    for table_node in tree.find_all(exp.Table):
        table = table_node.name
        candidates = normalized_schema_fields.get(table.lower(), ())
        exact = [field for field in candidates if (table.lower(), field.lower()) in declared]
        if len(candidates) == 1 and not exact:
            exact = [candidates[0]]
        if len(exact) != 1:
            if candidates:
                raise AnalysisTimeSqlError()
            continue
        bindings.append(_Binding(table=table, field=exact[0], alias=table_node.alias_or_name))
    return bindings


def _has_dynamic_boundary(tree: exp.Expression, bindings: list[_Binding]) -> bool:
    bound_fields = {binding.field.lower() for binding in bindings}
    if any(isinstance(node, exp.CrossJoin) for node in tree.walk()):
        return True
    return any(
        isinstance(maximum.this, exp.Column) and maximum.this.name.lower() in bound_fields
        for maximum in tree.find_all(exp.Max)
    )


def _append_bounds(select: exp.Select, binding: _Binding, policy: AnalysisTimePolicy) -> None:
    column = exp.column(binding.field, table=binding.alias)
    start = exp.Literal.string(policy.start_date.isoformat())
    end = exp.Literal.string(policy.end_date.isoformat())
    lower = exp.GTE(this=column.copy(), expression=start) if policy.start_inclusive else exp.GT(this=column.copy(), expression=start)
    upper = exp.LTE(this=column.copy(), expression=end) if policy.end_inclusive else exp.LT(this=column.copy(), expression=end)
    select.where(exp.and_(lower, upper), append=True, copy=False)


def enforce_analysis_time_sql(
    sql: str,
    *,
    policy: AnalysisTimePolicy,
    declared_time_fields: list[dict[str, str]],
    schema_time_fields: dict[str, tuple[str, ...]],
    dialect: str | None,
    allow_rewrite: bool,
) -> str:
    try:
        tree = parse_one(sql, read=dialect or None)
    except ParseError as exc:
        raise AnalysisTimeSqlError() from exc
    bindings = _resolve_bindings(tree, declared_time_fields, schema_time_fields)
    referenced_temporal_tables = {
        table.name.lower()
        for table in tree.find_all(exp.Table)
        if table.name.lower() in {name.lower() for name in schema_time_fields}
    }
    if not referenced_temporal_tables:
        return tree.sql(dialect=dialect or None)
    if not bindings or _has_dynamic_boundary(tree, bindings):
        raise AnalysisTimeSqlError()
    missing: list[_Binding] = []
    for binding in bindings:
        nodes = list(tree.walk())
        has_lower = any(_comparison_matches(node, binding, policy.start_date.isoformat(), lower=True, inclusive=policy.start_inclusive) for node in nodes)
        has_upper = any(_comparison_matches(node, binding, policy.end_date.isoformat(), lower=False, inclusive=policy.end_inclusive) for node in nodes)
        if not (has_lower and has_upper):
            missing.append(binding)
    if not missing:
        return tree.sql(dialect=dialect or None)
    outer_select = tree if isinstance(tree, exp.Select) else tree.find(exp.Select)
    if not allow_rewrite or len(missing) != 1 or outer_select is None:
        raise AnalysisTimeSqlError()
    _append_bounds(outer_select, missing[0], policy)
    return tree.sql(dialect=dialect or None)
```

实现时根据当前 SQLGlot 28.6 的节点实际名称校正 `CrossJoin` 检测：若该版本用 `exp.Join(kind="CROSS")`，改为检查 `exp.Join.args["kind"]`，并用对应测试锁定。补齐只允许一个缺失 binding；多表、子查询目标不唯一或字段候选多义时必须抛错。

- [ ] **Step 4: 运行 SQL 策略测试并检查输出方言**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_analysis_assistant_sql_generation.py -q`

Expected: PASS；重写 SQL 包含两个确定日期常量，不包含 `MAX(` 或 `CROSS JOIN bounds`。

- [ ] **Step 5: 提交 SQL 时间校验器**

```powershell
git add backend/apps/analysis_assistant/service/analysis_time_sql.py backend/tests/test_analysis_assistant_sql_generation.py
git commit -m "功能：校验分析 SQL 时间边界"
```

---

### Task 5: 接入定向修复、执行前强制校验和非阻断降级

**Files:**
- Modify: `backend/apps/analysis_assistant/api/analysis_assistant.py:1650-1673,2945-3185,3514-3688`
- Modify: `backend/tests/test_analysis_assistant_sql_generation.py`
- Modify: `backend/tests/test_analysis_assistant_permissions.py`

**Interfaces:**
- Consumes: Task 4 的 `enforce_analysis_time_sql(...)` 和 `AnalysisTimeSqlError`。
- Changes: `_prepare_sql_for_execution(..., *, time_resolution, schema_time_fields, declared_time_fields, dialect, allow_time_rewrite=False) -> str`。
- Changes: `_repair_sql(..., time_resolution: AnalysisTimeResolution | None = None) -> str`。
- Produces: `_prepare_time_safe_query_sql(...) -> str`，严格执行“模型定向修复一次 > 唯一目标 AST 补齐 > 跳过数据块”。

- [ ] **Step 1: 写修复顺序、禁止执行和最终 SSE 非阻断测试**

向 `backend/tests/test_analysis_assistant_sql_generation.py` 追加：

```python
def test_prepare_time_safe_sql_repairs_before_ast_rewrite(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[bool] = []
    def fake_prepare(*_args, allow_time_rewrite=False, **_kwargs):
        calls.append(allow_time_rewrite)
        if len(calls) == 1:
            raise AnalysisTimeSqlError()
        return "SELECT * FROM fact_orders WHERE business_date >= DATE '2026-07-13' AND business_date <= DATE '2026-07-26'"
    monkeypatch.setattr(analysis_api, "_prepare_sql_for_execution", fake_prepare)
    monkeypatch.setattr(analysis_api, "_repair_sql", lambda *_args, **_kwargs: "SELECT * FROM fact_orders")
    result = analysis_api._prepare_time_safe_query_sql(
        llm=object(), session=object(), current_user=object(), datasource=SimpleNamespace(type="postgresql"),
        raw_query={"sql": "SELECT * FROM fact_orders", "time_fields": [{"table": "fact_orders", "field": "business_date"}]},
        question="分析收入", schema="", sample_data="", data_profile="", custom_agent="", tracking_context="", data_skill="",
        allowed_tables=["fact_orders"], time_resolution=_resolved_time(), schema_time_fields=SCHEMA_TIME_FIELDS, dialect="postgres",
    )
    assert "2026-07-13" in result
    assert calls == [False, True]


def test_prepare_time_safe_sql_never_executes_unbounded_query(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(analysis_api, "_repair_sql", lambda *_args, **_kwargs: "SELECT * FROM fact_orders")
    monkeypatch.setattr(analysis_api, "validate_user_query_sql_or_raise", lambda **kwargs: (kwargs["sql"], {"fact_orders"}))
    with pytest.raises(AnalysisTimeSqlError):
        analysis_api._prepare_time_safe_query_sql(
            llm=object(), session=object(), current_user=object(), datasource=SimpleNamespace(type="postgresql"),
            raw_query={"sql": "SELECT * FROM fact_orders", "time_fields": []}, question="分析收入", schema="", sample_data="", data_profile="",
            custom_agent="", tracking_context="", data_skill="", allowed_tables=["fact_orders"], time_resolution=_resolved_time(),
            schema_time_fields={"fact_orders": ("business_date", "created_at")}, dialect="postgres",
        )
```

在 `backend/tests/test_analysis_assistant_permissions.py` 增加一个流式集成测试，复用该文件的 `_collect_stream_body`，mock 两个 query：第一个 `_prepare_time_safe_query_sql` 抛 `AnalysisTimeSqlError`，第二个返回有界 SQL并成功执行；断言：

```python
payload = body.decode()
assert '"type":"block"' in payload
assert '"status":"failed"' in payload
assert '"type":"final"' in payload
assert '"type":"finish"' in payload
assert execute_calls == ["SELECT bounded"]
```

再加全失败测试：所有 `_prepare_time_safe_query_sql` 均抛错，`execute_user_analysis_query_or_raise` 若被调用则直接 `AssertionError`；仍断言 `final` 和 `finish` 存在且没有接口级 `"type":"error"`。

- [ ] **Step 2: 运行定向测试并确认辅助函数缺失**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_analysis_assistant_sql_generation.py::test_prepare_time_safe_sql_repairs_before_ast_rewrite tests/test_analysis_assistant_sql_generation.py::test_prepare_time_safe_sql_never_executes_unbounded_query tests/test_analysis_assistant_permissions.py -q`

Expected: FAIL，包含 `_prepare_time_safe_query_sql` 不存在。

- [ ] **Step 3: 扩展执行前准备和 SQL 修复上下文**

修改 `_prepare_sql_for_execution`：先标准化 SQL，再调用 `enforce_analysis_time_sql`，最后才调用现有 `validate_user_query_sql_or_raise`。只有 `time_resolution.policy` 存在时允许执行时间字段表；策略未解析时只允许 Schema 中完全没有时间候选的配置/维度查询。

```python
def _prepare_sql_for_execution(
    llm, session, current_user, datasource, raw_sql: str, allowed_tables: list[str],
    *, time_resolution: AnalysisTimeResolution, schema_time_fields: dict[str, tuple[str, ...]],
    declared_time_fields: list[dict[str, str]], dialect: str | None, allow_time_rewrite: bool = False,
) -> str:
    sql = _normalise_sql(raw_sql)
    if time_resolution.policy:
        sql = enforce_analysis_time_sql(
            sql,
            policy=time_resolution.policy,
            declared_time_fields=declared_time_fields,
            schema_time_fields=schema_time_fields,
            dialect=dialect,
            allow_rewrite=allow_time_rewrite,
        )
    elif any(table.lower() in sql.lower() for table in schema_time_fields):
        raise AnalysisTimeSqlError()
    prepared_sql, _tables = validate_user_query_sql_or_raise(
        session=session,
        current_user=current_user,
        datasource=datasource,
        sql=sql,
        allowed_tables=allowed_tables,
    )
    return _normalise_sql(prepared_sql)
```

实现时不得保留示例中的 `table.lower() in sql.lower()` 判断；应先用 SQLGlot 提取物理表并与 `schema_time_fields` 精确比较。可在 `analysis_time_sql.py` 导出 `sql_references_time_bearing_table(sql, schema_time_fields, dialect) -> bool` 复用同一 AST。

给 `_repair_sql` 增加可选 `time_resolution`，在修复提示末尾附加 `_time_policy_context(time_resolution)`。调用方必须传入同一个请求级对象，修复模型不得改变日期。

- [ ] **Step 4: 实现一次修复后补齐的执行辅助函数**

```python
def _prepare_time_safe_query_sql(
    *, llm, session, current_user, datasource, raw_query: dict[str, Any], question: str,
    schema: str, sample_data: str, data_profile: str, custom_agent: str, tracking_context: str,
    data_skill: str, allowed_tables: list[str], time_resolution: AnalysisTimeResolution,
    schema_time_fields: dict[str, tuple[str, ...]], dialect: str | None,
) -> str:
    declared = raw_query.get("time_fields") or []
    raw_sql = str(raw_query.get("sql") or "")
    try:
        return _prepare_sql_for_execution(
            llm, session, current_user, datasource, raw_sql, allowed_tables,
            time_resolution=time_resolution, schema_time_fields=schema_time_fields,
            declared_time_fields=declared, dialect=dialect, allow_time_rewrite=False,
        )
    except AnalysisTimeSqlError as error:
        repaired = _repair_sql(
            llm, question, raw_query, raw_sql, error, schema, sample_data, data_profile,
            custom_agent, tracking_context, data_skill, time_resolution=time_resolution,
        )
        return _prepare_sql_for_execution(
            llm, session, current_user, datasource, repaired, allowed_tables,
            time_resolution=time_resolution, schema_time_fields=schema_time_fields,
            declared_time_fields=declared, dialect=dialect, allow_time_rewrite=True,
        )
```

注意：第二次仍失败时直接抛 `AnalysisTimeSqlError`，外层 block 捕获并标记失败；不得第三次模型调用或执行原 SQL。

- [ ] **Step 5: 替换所有首次与修复后 SQL 准备调用**

在 generator 构建一次：

```python
schema_time_fields = _schema_time_field_candidates(schema, allowed_tables)
dialect = business_context.sql_dialect
```

首次 SQL、执行异常后的 `_repair_sql` SQL、语义校验后的 `_repair_sql` SQL全部经过 `_prepare_time_safe_query_sql` 或等价的 `_prepare_sql_for_execution(... allow_time_rewrite=True)`，保证任何重试都不能绕开时间策略。捕获 `AnalysisTimeSqlError` 时写入安全块状态：

```python
block.update({
    "status": "failed",
    "error": "当前分析角度无法确认安全的时间边界，已跳过。",
    "error_type": "time_policy_unresolved",
    "warning": "当前分析角度未执行，不影响其它分析结果。",
    "summary": "",
})
```

其它数据库/权限异常继续走现有 `_mark_query_error_block`。最终回答提示中把 `time_policy_unresolved` 归入 failed titles；现有 `_final_answer_messages` 已要求结论只基于成功块，因此不新增接口级异常路径。

- [ ] **Step 6: 运行非阻断与全量分析助手测试**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_analysis_assistant_time_policy.py tests/test_analysis_assistant_sql_generation.py tests/test_analysis_assistant_permissions.py ../tests/test_datasource_permission_roles.py -q`

Expected: PASS；全失败 SSE 有 `final`、`finish`，无 `error`；无界 SQL 执行调用次数为 0。

- [ ] **Step 7: 提交执行强制策略**

```powershell
git add backend/apps/analysis_assistant/api/analysis_assistant.py backend/apps/analysis_assistant/service/analysis_time_sql.py backend/tests/test_analysis_assistant_sql_generation.py backend/tests/test_analysis_assistant_permissions.py
git commit -m "功能：强制综合分析 SQL 使用确定时间边界"
```

---

### Task 6: 完成范围回归、静态检查和验收记录

**Files:**
- Modify: `backend/tests/test_analysis_assistant_permissions.py`
- Modify: `backend/tests/test_analysis_assistant_sql_generation.py`

**Interfaces:**
- Consumes: 前五个任务的完整 `/analysis-assistant/chat` 行为。
- Produces: 无新生产接口；只锁定回归边界和验收证据。

- [ ] **Step 1: 增加入口范围和禁止模式回归断言**

在 `backend/tests/test_analysis_assistant_sql_generation.py` 增加源码级范围测试，确保默认策略没有进入共享看板/Smart Q&A 模块：

```python
from pathlib import Path


def test_default_analysis_time_policy_stays_inside_analysis_assistant() -> None:
    repo_backend = Path(__file__).resolve().parents[1]
    forbidden = [
        repo_backend / "apps/chat/task/llm.py",
        repo_backend / "apps/dashboard/crud/ai_sql_generator.py",
    ]
    for path in forbidden:
        source = path.read_text(encoding="utf-8")
        assert "AnalysisTimePolicy" not in source
        assert "DEFAULT_14_DAYS" not in source


def test_analysis_prompts_forbid_dynamic_time_bounds() -> None:
    for prompt in (analysis_api.PLAN_PROMPT, analysis_api.FORECAST_PLAN_PROMPT, analysis_api.SQL_REPAIR_PROMPT):
        assert "具体日期常量" in prompt
        assert "CROSS JOIN bounds" in prompt
        assert "不得重新解释或扩大" in prompt
```

在 `backend/tests/test_analysis_assistant_permissions.py` 保留并运行所有 report interpretation 测试，明确没有给该路由调用 `_resolve_chat_time_policy`。

- [ ] **Step 2: 运行格式和定向测试**

Run: `cd backend; .\.venv\Scripts\python.exe -m ruff check apps/analysis_assistant tests/test_analysis_assistant_time_policy.py tests/test_analysis_assistant_sql_generation.py tests/test_analysis_assistant_permissions.py`

Expected: `All checks passed!`

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_analysis_assistant_time_policy.py tests/test_analysis_assistant_sql_generation.py tests/test_analysis_assistant_permissions.py ../tests/test_datasource_permission_roles.py -q`

Expected: PASS，无失败或错误。

- [ ] **Step 3: 运行后端完整测试防止共享权限和快照回归**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest -q`

Expected: PASS；若存在仓库已知、与本功能无关的失败，记录完整测试名和错误，不得用跳过测试掩盖。

- [ ] **Step 4: 本地手工 SSE 验收三个问题**

按仓库本地运行手册启动四个服务后，在综合分析助手依次验证：

```text
分析一下渠道收入变化
分析14日之后的数据
从14号开始分析
```

验收证据必须同时满足：

```text
1. 未指定时间：轨迹显示最大业务日期锚定的最近 14 个自然日。
2. “14日之后”：开始日为补全年月后的 15 日，轨迹显示完整起止日期。
3. “从14号开始”：开始日包含 14 日，轨迹显示完整起止日期。
4. 每个成功事实 SQL 使用同一组具体日期常量，不包含动态 MAX(date) 或 CROSS JOIN bounds。
5. 人为让一个块缺失时间字段时，其它块继续，最终仍出现 final 和 finish。
6. Smart Q&A、看板和报表解读的时间行为没有改变。
```

- [ ] **Step 5: 检查变更范围并提交回归测试**

Run: `git diff --check`

Expected: 无输出。

Run: `git status --short`

Expected: 只显示本计划列出的分析助手生产文件和测试文件；不得出现前端、看板或 Smart Q&A 生产代码。

```powershell
git add backend/tests/test_analysis_assistant_permissions.py backend/tests/test_analysis_assistant_sql_generation.py
git commit -m "测试：覆盖综合分析默认时间窗口回归"
```

---

## 完成定义

- `分析一下渠道收入变化` 在最大业务日期 `2026-07-26` 时统一使用 `2026-07-13` 至 `2026-07-26`。
- `分析14日之后的数据` 解释为最近有效月份的 15 日起，不应用默认 14 天。
- `从14号开始分析` 解释为最近有效月份的 14 日起，不应用默认 14 天。
- 用户明确时间始终覆盖 Skill；合法 Skill 结构化声明只覆盖平台默认值。
- 锚点查询经过当前用户权限执行器，使用 `ORDER BY ... DESC LIMIT 1` 和 5 秒超时。
- 缓存按租户、数据源、用户、上下文摘要、行权限摘要、表、字段隔离，TTL 为 300 秒。
- 所有事实 SQL 在执行前通过 SQLGlot 的具体常量范围校验；无法唯一补齐时不执行。
- 单块失败不中断其它块；所有块失败也以 `final` + `finish` 正常结束。
- 上下文快照和 SSE 轨迹能审计最终时间策略，不包含敏感权限细节。
- `report-interpretation`、Smart Q&A、看板 SQL 和前端筛选器没有生产代码变更。
