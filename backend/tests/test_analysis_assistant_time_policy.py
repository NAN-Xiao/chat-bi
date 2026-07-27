from datetime import date
from types import SimpleNamespace

import pytest

from apps.analysis_assistant.api import analysis_assistant as analysis_api
from apps.analysis_assistant.service.analysis_time_policy import (
    AnalysisTimeAnchor,
    AnalysisTimeSource,
    parse_analysis_time_intent,
    parse_data_skill_time_directive,
    resolve_analysis_time_policy,
)

ANCHOR = AnalysisTimeAnchor(table="fact_orders", field="business_date")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _resolve(
    question: str,
    *,
    history: list[str] | None = None,
    skill: str = "",
    anchor_date: date = date(2026, 7, 26),
):
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
def test_day_only_open_ranges_have_deterministic_inclusion(
    question: str,
    expected_boundary: date,
    inclusive: bool,
    expected_trace_start: str,
) -> None:
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


def test_day_only_uses_year_month_from_current_question_before_history() -> None:
    resolution = _resolve(
        "分析 2026 年 8 月收入，14 日之后",
        history=["看一下 2026 年 6 月收入"],
    )
    assert resolution.policy is not None
    assert resolution.policy.start_date == date(2026, 8, 14)


def test_day_only_uses_month_from_current_question_without_history_year() -> None:
    intent = parse_analysis_time_intent(
        "分析 8月收入，14日之后",
        ["2026年6月收入"],
    )
    resolution = resolve_analysis_time_policy(
        intent,
        skill_window_days=None,
        anchor=ANCHOR,
        anchor_date=date(2026, 7, 26),
    )
    assert intent.year is None
    assert intent.month == 8
    assert resolution.policy is not None
    assert resolution.policy.start_date == date(2025, 8, 14)


def test_day_only_searches_previous_month_for_latest_valid_month_end() -> None:
    resolution = _resolve("31日之后", anchor_date=date(2026, 4, 10))
    assert resolution.policy is not None
    assert resolution.policy.start_date == date(2026, 3, 31)
    assert resolution.policy.start_inclusive is False
    assert "2026-04-01" in resolution.traces[0]


def test_day_only_searches_previous_leap_day_when_available() -> None:
    resolution = _resolve("29日之后", anchor_date=date(2024, 3, 1))
    assert resolution.policy is not None
    assert resolution.policy.start_date == date(2024, 2, 29)
    assert resolution.policy.start_inclusive is False
    assert "2024-03-01" in resolution.traces[0]


def test_month_without_year_searches_previous_year_for_latest_valid_leap_day() -> None:
    resolution = _resolve("2月29日之后", anchor_date=date(2025, 3, 1))
    assert resolution.policy is not None
    assert resolution.policy.start_date == date(2024, 2, 29)
    assert resolution.policy.start_inclusive is False
    assert "2024-03-01" in resolution.traces[0]


@pytest.mark.parametrize("question", ["4月31日之后", "2025年2月29日之后"])
def test_invalid_explicit_month_day_is_not_rewritten_to_another_year(question: str) -> None:
    resolution = _resolve(question, anchor_date=date(2025, 3, 1))
    assert resolution.status == "unresolved"
    assert resolution.policy is None
    assert resolution.warnings == ("用户指定的日期无效，无法确定时间策略。",)


def test_explicit_absolute_range_does_not_need_anchor() -> None:
    intent = parse_analysis_time_intent("分析 2026-07-01 到 2026-07-10", [])
    resolution = resolve_analysis_time_policy(
        intent,
        skill_window_days=None,
        anchor=None,
        anchor_date=None,
    )
    assert intent.requires_anchor is False
    assert resolution.policy is not None
    assert resolution.policy.start_date == date(2026, 7, 1)
    assert resolution.policy.end_date == date(2026, 7, 10)


def test_anchor_required_intent_is_unresolved_without_anchor() -> None:
    intent = parse_analysis_time_intent("最近7天收入", [])
    resolution = resolve_analysis_time_policy(
        intent,
        skill_window_days=None,
        anchor=None,
        anchor_date=date(2026, 7, 26),
    )
    assert resolution.status == "unresolved"
    assert resolution.policy is None
    assert resolution.warnings == (
        "无法确认当前数据源的时间锚点，本次仅执行能够确认时间边界的分析块。",
    )


@pytest.mark.parametrize(
    "question",
    [
        "分析2026年4月31日之后的数据",
        "分析 2026-02-30 到 2026-03-01",
    ],
)
def test_invalid_calendar_date_is_unresolved_without_substitution(question: str) -> None:
    intent = parse_analysis_time_intent(question, [])
    resolution = resolve_analysis_time_policy(
        intent,
        skill_window_days=None,
        anchor=ANCHOR,
        anchor_date=date(2026, 7, 26),
    )
    assert resolution.status == "unresolved"
    assert resolution.policy is None
    assert resolution.warnings == ("用户指定的日期无效，无法确定时间策略。",)


def test_leap_day_absolute_range_is_resolved() -> None:
    intent = parse_analysis_time_intent("分析 2024-02-29 到 2024-02-29", [])
    resolution = resolve_analysis_time_policy(
        intent,
        skill_window_days=None,
        anchor=None,
        anchor_date=None,
    )
    assert resolution.status == "resolved"
    assert resolution.policy is not None
    assert resolution.policy.start_date == date(2024, 2, 29)
    assert resolution.policy.end_date == date(2024, 2, 29)


def test_month_end_absolute_range_is_resolved() -> None:
    intent = parse_analysis_time_intent("分析 2026-04-30 到 2026-04-30", [])
    resolution = resolve_analysis_time_policy(
        intent,
        skill_window_days=None,
        anchor=None,
        anchor_date=None,
    )
    assert resolution.status == "resolved"
    assert resolution.policy is not None
    assert resolution.policy.start_date == date(2026, 4, 30)
    assert resolution.policy.end_date == date(2026, 4, 30)


def test_descending_absolute_range_is_unresolved() -> None:
    intent = parse_analysis_time_intent("分析 2026-07-10 到 2026-07-01", [])
    resolution = resolve_analysis_time_policy(
        intent,
        skill_window_days=None,
        anchor=None,
        anchor_date=None,
    )
    assert resolution.status == "unresolved"
    assert resolution.policy is None
    assert resolution.warnings == ("用户指定的时间范围倒序，无法确定时间策略。",)


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
        "public.fact_orders": ("business_date", "created_at")
    }


def test_schema_time_candidates_parse_nested_temporal_types() -> None:
    schema = """
# Table: analytics.events
[
(event_time:Nullable(DateTime64(3))),
(settled_on:Nullable(Date)),
(amount:Decimal(18, 2))
]
"""
    assert analysis_api._schema_time_field_candidates(schema, ["events"]) == {
        "analytics.events": ("event_time", "settled_on")
    }


def test_schema_time_candidates_reject_ambiguous_bare_allowed_table() -> None:
    schema = """
# Table: public.orders
[
(business_date:date)
]
# Table: secret.orders
[
(business_date:date)
]
"""
    assert analysis_api._schema_time_field_candidates(schema, ["orders"]) == {}


def test_schema_time_candidates_keep_only_explicitly_allowed_qualified_table() -> None:
    schema = """
# Table: public.orders
[
(business_date:date)
]
# Table: secret.orders
[
(business_date:date)
]
"""
    assert analysis_api._schema_time_field_candidates(
        schema, ["public.orders"]
    ) == {"public.orders": ("business_date",)}


def test_schema_time_candidates_reject_unauthorized_qualified_table() -> None:
    schema = """
# Table: public.orders
[
(business_date:date)
]
"""
    assert analysis_api._schema_time_field_candidates(
        schema, ["secret.orders"]
    ) == {}


def test_anchor_selector_rejects_model_field_outside_exact_candidates() -> None:
    llm = SimpleNamespace(
        invoke=lambda _messages: SimpleNamespace(
            content='{"table":"fact_orders","field":"day"}'
        )
    )
    with pytest.raises(ValueError, match="未选择有效的业务时间字段"):
        analysis_api._select_analysis_time_anchor(
            llm,
            "分析收入",
            "",
            {"fact_orders": ("business_date",)},
        )


def test_latest_date_probe_uses_single_ordered_field_and_permission_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
        anchor=AnalysisTimeAnchor("public.fact_orders", "business_date"),
    )
    assert value == date(2026, 7, 26)
    assert "ORDER BY" in calls[0]["sql"]
    assert "DESC" in calls[0]["sql"]
    assert "LIMIT 1" in calls[0]["sql"]
    assert "MAX(" not in calls[0]["sql"]
    assert 'FROM "public"."fact_orders"' in calls[0]["sql"]
    assert calls[0]["allowed_tables"] == ["fact_orders"]
    assert calls[0]["apply_row_permissions"] is True
    assert calls[0]["query_timeout"] == 5


def test_latest_date_probe_rejects_anchor_outside_allowed_tables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        analysis_api,
        "execute_user_query_or_raise",
        lambda **_kwargs: pytest.fail("未授权锚点不得进入查询执行器"),
    )

    with pytest.raises(ValueError, match="业务时间锚点不在授权表范围内"):
        analysis_api._probe_latest_business_date(
            session=object(),
            current_user=SimpleNamespace(id=7),
            datasource=SimpleNamespace(id=1, type="postgresql"),
            allowed_tables=["public.fact_orders"],
            anchor=AnalysisTimeAnchor("secret.fact_orders", "business_date"),
        )


def test_anchor_cache_key_is_user_business_context_and_permission_scoped() -> None:
    key = analysis_api._analysis_time_anchor_cache_key(
        tenant_id=9,
        datasource_id=10,
        user_id=11,
        context_hash="abc123",
        permission_hash="permission456",
        anchor=AnalysisTimeAnchor("public.fact_orders", "business_date"),
    )
    assert ":tenant:9:datasource:10:" in key
    assert (
        ":analysis-time-anchor:11:abc123:permission456:public.fact_orders:business_date"
        in key
    )


def test_permission_fingerprint_changes_with_row_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    filters = [{"field": "region_id", "operator": "in", "value": [1]}]
    calls: list[dict] = []

    def fake_filters(**kwargs):
        calls.append(kwargs)
        return filters

    monkeypatch.setattr(analysis_api, "get_row_permission_filters", fake_filters)
    anchor = AnalysisTimeAnchor("public.fact_orders", "business_date")
    first = analysis_api._analysis_time_permission_fingerprint(
        session=object(),
        current_user=SimpleNamespace(id=7),
        datasource=SimpleNamespace(id=1),
        anchor=anchor,
    )
    filters[0]["value"] = [2]
    second = analysis_api._analysis_time_permission_fingerprint(
        session=object(),
        current_user=SimpleNamespace(id=7),
        datasource=SimpleNamespace(id=1),
        anchor=anchor,
    )
    assert first != second
    assert [call["tables"] for call in calls] == [["fact_orders"], ["fact_orders"]]


@pytest.mark.anyio
async def test_time_policy_cache_hit_skips_latest_date_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeRedis:
        get_calls = 0
        set_calls = 0

        async def get(self, _key):
            self.get_calls += 1
            return b"2026-07-26"

        async def set(self, *_args, **_kwargs):
            self.set_calls += 1

    client = FakeRedis()
    monkeypatch.setattr(analysis_api, "get_redis_client", lambda: client)
    monkeypatch.setattr(
        analysis_api,
        "_select_analysis_time_anchor",
        lambda *_args, **_kwargs: ANCHOR,
    )
    monkeypatch.setattr(
        analysis_api,
        "_analysis_time_permission_fingerprint",
        lambda **_kwargs: "permission",
    )
    monkeypatch.setattr(
        analysis_api,
        "_probe_latest_business_date",
        lambda **_kwargs: pytest.fail("缓存命中时不应探测最大业务日期"),
    )

    resolution = await analysis_api._resolve_chat_time_policy(
        session=object(),
        current_user=SimpleNamespace(id=7, tenant_id=9),
        datasource=SimpleNamespace(id=10, type="postgresql"),
        business_context=SimpleNamespace(
            data_skill="",
            schema="# Table: fact_orders\n[\n(business_date:date)\n]",
            allowed_tables=["fact_orders"],
            business_context_hash="context",
        ),
        llm=object(),
        request=SimpleNamespace(
            messages=[SimpleNamespace(content="分析收入", role="user")]
        ),
        semantic_context="",
    )

    assert resolution.policy is not None
    assert resolution.policy.anchor_date == date(2026, 7, 26)
    assert client.get_calls == 1
    assert client.set_calls == 0


@pytest.mark.anyio
async def test_time_policy_cache_miss_probes_once_and_writes_short_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe_calls = 0

    class FakeRedis:
        set_calls: list[tuple[tuple, dict]] = []

        async def get(self, _key):
            return None

        async def set(self, *args, **kwargs):
            self.set_calls.append((args, kwargs))

    def fake_probe(**_kwargs):
        nonlocal probe_calls
        probe_calls += 1
        return date(2026, 7, 26)

    client = FakeRedis()
    monkeypatch.setattr(analysis_api, "get_redis_client", lambda: client)
    monkeypatch.setattr(
        analysis_api,
        "_select_analysis_time_anchor",
        lambda *_args, **_kwargs: ANCHOR,
    )
    monkeypatch.setattr(
        analysis_api,
        "_analysis_time_permission_fingerprint",
        lambda **_kwargs: "permission",
    )
    monkeypatch.setattr(analysis_api, "_probe_latest_business_date", fake_probe)

    resolution = await analysis_api._resolve_chat_time_policy(
        session=object(),
        current_user=SimpleNamespace(id=7, tenant_id=9),
        datasource=SimpleNamespace(id=10, type="postgresql"),
        business_context=SimpleNamespace(
            data_skill="",
            schema="# Table: fact_orders\n[\n(business_date:date)\n]",
            allowed_tables=["fact_orders"],
            business_context_hash="context",
        ),
        llm=object(),
        request=SimpleNamespace(
            messages=[SimpleNamespace(content="分析收入", role="user")]
        ),
        semantic_context="",
    )

    assert resolution.policy is not None
    assert resolution.policy.anchor_date == date(2026, 7, 26)
    assert probe_calls == 1
    assert len(client.set_calls) == 1
    assert client.set_calls[0][0][1] == "2026-07-26"
    assert client.set_calls[0][1] == {"ex": 300}


@pytest.mark.anyio
async def test_redis_read_failure_bypasses_cache_and_probes_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe_calls = 0

    class FailingRedis:
        set_calls = 0

        async def get(self, _key):
            raise analysis_api.RedisError("缓存读取失败")

        async def set(self, *_args, **_kwargs):
            self.set_calls += 1

    def fake_probe(**_kwargs):
        nonlocal probe_calls
        probe_calls += 1
        return date(2026, 7, 26)

    client = FailingRedis()
    monkeypatch.setattr(analysis_api, "get_redis_client", lambda: client)
    monkeypatch.setattr(
        analysis_api,
        "_select_analysis_time_anchor",
        lambda *_args, **_kwargs: ANCHOR,
    )
    monkeypatch.setattr(
        analysis_api,
        "_analysis_time_permission_fingerprint",
        lambda **_kwargs: "permission",
    )
    monkeypatch.setattr(analysis_api, "_probe_latest_business_date", fake_probe)

    resolution = await analysis_api._resolve_chat_time_policy(
        session=object(),
        current_user=SimpleNamespace(id=7, tenant_id=9),
        datasource=SimpleNamespace(id=10, type="postgresql"),
        business_context=SimpleNamespace(
            data_skill="",
            schema="# Table: fact_orders\n[\n(business_date:date)\n]",
            allowed_tables=["fact_orders"],
            business_context_hash="context",
        ),
        llm=object(),
        request=SimpleNamespace(
            messages=[SimpleNamespace(content="分析收入", role="user")]
        ),
        semantic_context="",
    )

    assert resolution.policy is not None
    assert resolution.policy.anchor_date == date(2026, 7, 26)
    assert probe_calls == 1
    assert client.set_calls == 0


@pytest.mark.anyio
async def test_permission_fingerprint_failure_bypasses_cache_and_probes_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe_calls = 0

    def fake_probe(**_kwargs):
        nonlocal probe_calls
        probe_calls += 1
        return date(2026, 7, 26)

    monkeypatch.setattr(
        analysis_api,
        "_select_analysis_time_anchor",
        lambda *_args, **_kwargs: ANCHOR,
    )
    monkeypatch.setattr(
        analysis_api,
        "_analysis_time_permission_fingerprint",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("摘要失败")),
    )
    monkeypatch.setattr(
        analysis_api,
        "get_redis_client",
        lambda: pytest.fail("权限摘要失败时应跳过 Redis"),
    )
    monkeypatch.setattr(analysis_api, "_probe_latest_business_date", fake_probe)

    resolution = await analysis_api._resolve_chat_time_policy(
        session=object(),
        current_user=SimpleNamespace(id=7, tenant_id=9),
        datasource=SimpleNamespace(id=10, type="postgresql"),
        business_context=SimpleNamespace(
            data_skill="",
            schema="# Table: fact_orders\n[\n(business_date:date)\n]",
            allowed_tables=["fact_orders"],
            business_context_hash="context",
        ),
        llm=object(),
        request=SimpleNamespace(
            messages=[SimpleNamespace(content="分析收入", role="user")]
        ),
        semantic_context="",
    )

    assert resolution.policy is not None
    assert resolution.policy.anchor_date == date(2026, 7, 26)
    assert probe_calls == 1


@pytest.mark.anyio
async def test_time_policy_runs_permission_and_probe_in_threadpool_sequentially(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    bridged: list[tuple[object, dict]] = []
    session = object()

    class FakeRedis:
        async def get(self, _key):
            events.append("redis_get")
            return None

        async def set(self, *_args, **_kwargs):
            events.append("redis_set")

    def fake_fingerprint(**_kwargs):
        events.append("fingerprint")
        return "permission"

    def fake_probe(**_kwargs):
        events.append("probe")
        return date(2026, 7, 26)

    async def fake_run_in_threadpool(function, *args, **kwargs):
        events.append(f"bridge:{function.__name__}")
        bridged.append((function, kwargs))
        return function(*args, **kwargs)

    monkeypatch.setattr(analysis_api, "get_redis_client", FakeRedis)
    monkeypatch.setattr(
        analysis_api,
        "_select_analysis_time_anchor",
        lambda *_args, **_kwargs: ANCHOR,
    )
    monkeypatch.setattr(
        analysis_api, "_analysis_time_permission_fingerprint", fake_fingerprint
    )
    monkeypatch.setattr(analysis_api, "_probe_latest_business_date", fake_probe)
    monkeypatch.setattr(analysis_api, "run_in_threadpool", fake_run_in_threadpool)

    resolution = await analysis_api._resolve_chat_time_policy(
        session=session,
        current_user=SimpleNamespace(id=7, tenant_id=9),
        datasource=SimpleNamespace(id=10, type="postgresql"),
        business_context=SimpleNamespace(
            data_skill="",
            schema="# Table: fact_orders\n[\n(business_date:date)\n]",
            allowed_tables=["fact_orders"],
            business_context_hash="context",
        ),
        llm=object(),
        request=SimpleNamespace(
            messages=[SimpleNamespace(content="分析收入", role="user")]
        ),
        semantic_context="",
    )

    assert resolution.policy is not None
    assert [item[0] for item in bridged] == [fake_fingerprint, fake_probe]
    assert all(item[1]["session"] is session for item in bridged)
    assert events == [
        "bridge:fake_fingerprint",
        "fingerprint",
        "redis_get",
        "bridge:fake_probe",
        "probe",
        "redis_set",
    ]
