from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from typing import Literal

DEFAULT_WINDOW_DAYS = 14
MAX_ANALYSIS_WINDOW_DAYS = 366
MAX_SKILL_WINDOW_DAYS = MAX_ANALYSIS_WINDOW_DAYS
_SKILL_DIRECTIVE_RE = re.compile(
    r"<!--\s*data-skill-analysis-time:(\{.*?\})\s*-->", re.DOTALL
)
_ISO_RANGE_RE = re.compile(
    r"(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})日?\s*"
    r"(?:到|至|~|～|—|-)\s*(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})日?"
)
_FULL_OPEN_RE = re.compile(
    r"(?:(\d{4})年)?\s*(\d{1,2})月\s*(\d{1,2})[日号]\s*"
    r"(之后|以后|起|开始|及以后)"
)
_DAY_ONLY_RE = re.compile(
    r"(?:从\s*)?(\d{1,2})\s*[日号]\s*(之后|以后|起|开始|及以后)"
)
_YEAR_MONTH_RE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月")
_MONTH_RE = re.compile(r"(\d{1,2})\s*月")
_RELATIVE_DAYS_RE = re.compile(r"(?:最近|近)\s*(-?\d+)\s*(?:个)?[天日]")
_RELATIVE_WEEKS_RE = re.compile(r"(?:最近|近)\s*(两|-?\d+)\s*(?:个)?周")
_RECENT_MONTH_RE = re.compile(r"(?:最近|近)\s*(?:一|1)\s*个?月")
_INVALID_DATE_WARNING = "用户指定的日期无效，无法确定时间策略。"
_INVALID_WINDOW_WARNING = "用户指定的时间窗口无效，无法确定时间策略。"
_DESCENDING_RANGE_WARNING = "用户指定的时间范围倒序，无法确定时间策略。"
_MISSING_ANCHOR_WARNING = "无法确认当前数据源的时间锚点，本次仅执行能够确认时间边界的分析块。"
_MISSING_ANCHOR_DATE_WARNING = "无法确认当前数据源的最大业务日期，本次仅执行能够确认时间边界的分析块。"


class AnalysisTimeSource(StrEnum):
    USER = "USER"
    DATA_SKILL = "DATA_SKILL"
    DEFAULT_14_DAYS = "DEFAULT_14_DAYS"


@dataclass(frozen=True)
class AnalysisTimeAnchor:
    table: str
    field: str
    data_type: str | None = None
    encoding: str | None = None
    quoted: bool = False


@dataclass(frozen=True)
class AnalysisTimeIntent:
    kind: Literal[
        "none", "absolute", "relative_days", "day_open", "month", "yesterday", "invalid"
    ]
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
    warning: str | None = None


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
            "anchor": (
                {"table": self.anchor.table, "field": self.anchor.field}
                if self.anchor
                else None
            ),
            "status": "resolved",
        }

    def prompt_text(self) -> str:
        start_op = ">=" if self.start_inclusive else ">"
        end_op = "<=" if self.end_inclusive else "<"
        return (
            f"后端已确定时间策略：{self.description}\n"
            f"起始边界 {start_op} {self.start_date.isoformat()}；"
            f"结束边界 {end_op} {self.end_date.isoformat()}。"
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


def _last_month(text: str) -> int | None:
    matches = list(_MONTH_RE.finditer(text or ""))
    return int(matches[-1].group(1)) if matches else None


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_analysis_time_intent(question: str, history: list[str]) -> AnalysisTimeIntent:
    text = (question or "").strip()
    absolute = _ISO_RANGE_RE.search(text)
    if absolute:
        values = [int(value) for value in absolute.groups()]
        start_date = _safe_date(values[0], values[1], values[2])
        end_date = _safe_date(values[3], values[4], values[5])
        if start_date is None or end_date is None:
            return AnalysisTimeIntent(
                kind="invalid",
                source=AnalysisTimeSource.USER,
                requires_anchor=False,
            )
        return AnalysisTimeIntent(
            kind="absolute",
            source=AnalysisTimeSource.USER,
            start_date=start_date,
            end_date=end_date,
            requires_anchor=False,
        )
    relative = _RELATIVE_DAYS_RE.search(text)
    if relative:
        window_days = int(relative.group(1))
        if not 1 <= window_days <= MAX_ANALYSIS_WINDOW_DAYS:
            return AnalysisTimeIntent(
                kind="invalid",
                source=AnalysisTimeSource.USER,
                warning=_INVALID_WINDOW_WARNING,
            )
        return AnalysisTimeIntent(
            kind="relative_days",
            source=AnalysisTimeSource.USER,
            window_days=window_days,
        )
    relative_weeks = _RELATIVE_WEEKS_RE.search(text)
    if relative_weeks:
        weeks = 2 if relative_weeks.group(1) == "两" else int(relative_weeks.group(1))
        window_days = weeks * 7
        if not 1 <= window_days <= MAX_ANALYSIS_WINDOW_DAYS:
            return AnalysisTimeIntent(
                kind="invalid",
                source=AnalysisTimeSource.USER,
                warning=_INVALID_WINDOW_WARNING,
            )
        return AnalysisTimeIntent(
            kind="relative_days",
            source=AnalysisTimeSource.USER,
            window_days=window_days,
        )
    if _RECENT_MONTH_RE.search(text):
        return AnalysisTimeIntent(
            kind="relative_days",
            source=AnalysisTimeSource.USER,
            window_days=30,
        )
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
        question_year, _ = _last_year_month([text])
        question_month = _last_month(text)
        history_year, history_month = _last_year_month(history)
        marker = day_only.group(2)
        return AnalysisTimeIntent(
            kind="day_open",
            source=AnalysisTimeSource.USER,
            year=question_year if question_month is not None else history_year,
            month=question_month if question_month is not None else history_month,
            day_of_month=int(day_only.group(1)),
            start_inclusive=marker not in {"之后", "以后"},
        )
    for previous in reversed(history):
        inherited = parse_analysis_time_intent(previous, [])
        if inherited.kind not in {"none", "invalid"}:
            return inherited
    return AnalysisTimeIntent(kind="none")


def _latest_occurrence(
    anchor_date: date,
    year: int | None,
    month: int | None,
    day_of_month: int,
) -> date | None:
    if year is not None and month is not None:
        return _safe_date(year, month, day_of_month)
    if month is not None:
        candidate_year = anchor_date.year
        while candidate_year >= 1:
            candidate = _safe_date(candidate_year, month, day_of_month)
            if candidate is not None and candidate <= anchor_date:
                return candidate
            candidate_year -= 1
        return None
    if not 1 <= day_of_month <= 31:
        return None
    candidate_year = anchor_date.year
    candidate_month = anchor_date.month
    while candidate_year >= 1:
        candidate = _safe_date(candidate_year, candidate_month, day_of_month)
        if candidate is not None and candidate <= anchor_date:
            return candidate
        if candidate_month == 1:
            candidate_year -= 1
            candidate_month = 12
        else:
            candidate_month -= 1
    return None


def _unresolved(
    warnings: tuple[str, ...], warning: str
) -> AnalysisTimeResolution:
    return AnalysisTimeResolution(None, "unresolved", warnings + (warning,), (warning,))


def resolve_analysis_time_policy(
    intent: AnalysisTimeIntent,
    *,
    skill_window_days: int | None,
    anchor: AnalysisTimeAnchor | None,
    anchor_date: date | None,
    warnings: tuple[str, ...] = (),
) -> AnalysisTimeResolution:
    if intent.kind == "invalid":
        return _unresolved(warnings, intent.warning or _INVALID_DATE_WARNING)
    if intent.kind == "absolute" and intent.start_date and intent.end_date:
        if intent.start_date > intent.end_date:
            return _unresolved(warnings, _DESCENDING_RANGE_WARNING)
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
        return AnalysisTimeResolution(
            policy,
            "resolved",
            warnings,
            (f"已采用用户指定时间范围：{policy.start_date} 至 {policy.end_date}。",),
        )
    if intent.requires_anchor and anchor is None:
        return _unresolved(warnings, _MISSING_ANCHOR_WARNING)
    if anchor_date is None:
        return _unresolved(warnings, _MISSING_ANCHOR_DATE_WARNING)
    if intent.kind == "day_open" and intent.day_of_month:
        base = _latest_occurrence(
            anchor_date, intent.year, intent.month, intent.day_of_month
        )
        if base is None:
            return _unresolved(warnings, _INVALID_DATE_WARNING)
        effective_start = base if intent.start_inclusive else base + timedelta(days=1)
        policy = AnalysisTimePolicy(
            AnalysisTimeSource.USER,
            None,
            anchor_date,
            base,
            anchor_date,
            intent.start_inclusive,
            True,
            anchor,
            f"用户开放时间范围 {effective_start.isoformat()} 至 {anchor_date.isoformat()}",
        )
    elif intent.kind == "relative_days" and intent.window_days:
        if not 1 <= intent.window_days <= MAX_ANALYSIS_WINDOW_DAYS:
            return _unresolved(warnings, _INVALID_WINDOW_WARNING)
        policy = AnalysisTimePolicy(
            AnalysisTimeSource.USER,
            intent.window_days,
            anchor_date,
            anchor_date - timedelta(days=intent.window_days - 1),
            anchor_date,
            True,
            True,
            anchor,
            f"用户指定最近 {intent.window_days} 个自然日",
        )
    elif intent.kind == "yesterday":
        yesterday = anchor_date - timedelta(days=1)
        policy = AnalysisTimePolicy(
            AnalysisTimeSource.USER,
            1,
            anchor_date,
            yesterday,
            yesterday,
            True,
            True,
            anchor,
            "用户指定昨天",
        )
    elif intent.kind == "month":
        start = anchor_date.replace(day=1)
        policy = AnalysisTimePolicy(
            AnalysisTimeSource.USER,
            None,
            anchor_date,
            start,
            anchor_date,
            True,
            True,
            anchor,
            "用户指定本月",
        )
    else:
        days = skill_window_days or DEFAULT_WINDOW_DAYS
        source = (
            AnalysisTimeSource.DATA_SKILL
            if skill_window_days
            else AnalysisTimeSource.DEFAULT_14_DAYS
        )
        policy = AnalysisTimePolicy(
            source,
            days,
            anchor_date,
            anchor_date - timedelta(days=days - 1),
            anchor_date,
            True,
            True,
            anchor,
            f"最近 {days} 个自然日",
        )
    trace = f"已采用时间范围：{policy.start_date.isoformat()} 至 {policy.end_date.isoformat()}。"
    if intent.kind == "day_open":
        effective_start = (
            policy.start_date
            if policy.start_inclusive
            else policy.start_date + timedelta(days=1)
        )
        trace = (
            f"已将用户日期表达解释为 {effective_start.isoformat()} 至 "
            f"{policy.end_date.isoformat()}。"
        )
    return AnalysisTimeResolution(policy, "resolved", warnings, (trace,))
