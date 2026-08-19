from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.chat.service import chat_date_filter as chat_date_filter_service
from apps.chat.service.chat_date_filter import (
    ChatDateFilterConfigurationError,
    normalize_chat_date_filter_contract,
    normalize_chat_date_filter_for_question,
    normalize_chat_date_filter,
    render_chat_date_filter_sql,
)
from apps.chat.models.chat_model import ChatFinishStep
from apps.chat.models.chat_model import OperationEnum
from apps.chat.task.llm import LLMService
from apps.chat.task import smart_qa_graph
from apps.chat.curd import chat as chat_crud
from apps.system.crud.tenant import SAMPLE_TENANT_NAME
from common.error import SingleMessageError


DATE_TEMPLATE_SQL = (
    "SELECT * FROM event "
    "WHERE dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}"
)
REALTIME_DATE_TEMPLATE_SQL = (
    "SELECT * FROM event_realtime "
    "WHERE dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}"
)
REALTIME_DATE_START_ONLY_SQL = (
    "SELECT * FROM event_realtime WHERE dt >= {{dashboard_start_yyyymmdd}}"
)
REALTIME_DATE_END_ONLY_SQL = (
    "SELECT * FROM event_realtime WHERE dt <= {{dashboard_end_yyyymmdd}}"
)
DATE_LITERAL_SQL = (
    "SELECT * FROM event "
    "WHERE `e`.`dt` BETWEEN 20260701 AND 20260728"
)
DATE_LITERAL_TEMPLATE_SQL = (
    "SELECT * FROM event "
    "WHERE `e`.`dt` BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}"
)
DATE_CURRENT_FUNCTION_SQL = (
    "SELECT * FROM event "
    "WHERE `e`.`dt` BETWEEN "
    "CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 14 DAY), '%Y%m%d') AS SIGNED) "
    "AND CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED) "
    "AND `e`.`prod` = 110000047"
)
DATE_FILTER = {
    "time_field": "dt",
    "date_parameter_type": "yyyymmdd_number",
    "date_expression": {"version": 1, "mode": "preset", "preset": "past_7_days"},
}
DATE_FILTER_WITH_MODEL_DEFAULT_PAST_28_DAYS = {
    "time_field": "dt",
    "date_parameter_type": "yyyymmdd_number",
    "date_expression": {"version": 1, "mode": "preset", "preset": "past_28_days"},
}
STATIC_DATE_FILTER = {
    "time_field": "dt",
    "date_parameter_type": "yyyymmdd_number",
    "date_expression": {
        "version": 1,
        "mode": "range",
        "start": {"mode": "static", "date": "2026-08-01"},
        "end": {"mode": "static", "date": "2026-08-19"},
    },
}
DEFAULT_STATIC_DATE_FILTER = {
    "time_field": "dt",
    "date_parameter_type": "yyyymmdd_number",
    "date_expression": {
        "version": 1,
        "mode": "range",
        "start": {"mode": "static", "date": "2026-08-12"},
        "end": {"mode": "static", "date": "2026-08-18"},
    },
}


def _attach_time_contract(
    response: dict,
    date_filter: dict,
    *,
    scope: str,
    start: str,
    end: str,
) -> dict:
    return {
        **response,
        "time_scope": scope,
        "time_range": {"start_date": start, "end_date": end},
        "date_filter": date_filter,
    }
TODAY_DATE_FILTER = {
    "time_field": "dt",
    "date_parameter_type": "yyyymmdd_number",
    "date_expression": {
        "version": 1,
        "mode": "range",
        "start": {"mode": "dynamic", "unit": "day", "offset": 0},
        "end": {"mode": "dynamic", "unit": "day", "offset": 0},
    },
}


def test_normalize_accepts_complete_past_seven_days_yyyymmdd_template():
    pivot = normalize_chat_date_filter(DATE_FILTER, DATE_TEMPLATE_SQL, "line")

    assert pivot == {"enabled": False, **DATE_FILTER}


def test_concrete_time_contract_preserves_explicit_month_and_renders_yyyymmdd_number():
    pivot = normalize_chat_date_filter_contract(
        STATIC_DATE_FILTER,
        DATE_TEMPLATE_SQL,
        "line",
        time_scope="explicit",
        time_range={"start_date": "2026-08-01", "end_date": "2026-08-19"},
        business_date=date(2026, 8, 19),
    )

    assert render_chat_date_filter_sql(
        DATE_TEMPLATE_SQL,
        "mysql",
        pivot,
        today=date(2026, 8, 19),
    ).endswith("BETWEEN 20260801 AND 20260819")


@pytest.mark.parametrize(
    ("time_phrase", "start", "end"),
    [
        ("近 3 天", "2026-08-16", "2026-08-18"),
        ("近 7 天", "2026-08-12", "2026-08-18"),
        ("近 14 天", "2026-08-05", "2026-08-18"),
        ("近 21 天", "2026-07-29", "2026-08-18"),
        ("近 30 天", "2026-07-20", "2026-08-18"),
        ("近 45 天", "2026-07-05", "2026-08-18"),
        ("近 60 天", "2026-06-20", "2026-08-18"),
        ("近 90 天", "2026-05-21", "2026-08-18"),
        ("昨天", "2026-08-18", "2026-08-18"),
        ("前天", "2026-08-17", "2026-08-17"),
        ("本周", "2026-08-17", "2026-08-19"),
        ("上周", "2026-08-10", "2026-08-16"),
        ("本月", "2026-08-01", "2026-08-19"),
        ("上月", "2026-07-01", "2026-07-31"),
        ("8月1日到昨天", "2026-08-01", "2026-08-18"),
    ],
)
def test_concrete_time_contract_accepts_llm_resolved_explicit_ranges(
    time_phrase: str,
    start: str,
    end: str,
):
    date_filter = {
        **STATIC_DATE_FILTER,
        "date_expression": {
            "version": 1,
            "mode": "range",
            "start": {"mode": "static", "date": start},
            "end": {"mode": "static", "date": end},
        },
    }

    pivot = normalize_chat_date_filter_contract(
        date_filter,
        DATE_TEMPLATE_SQL,
        "line",
        time_scope="explicit",
        time_range={"start_date": start, "end_date": end},
        business_date=date(2026, 8, 19),
    )

    assert pivot == {"enabled": False, **date_filter}


def test_concrete_time_contract_renders_yyyymmdd_text_with_quotes():
    text_filter = {**STATIC_DATE_FILTER, "date_parameter_type": "yyyymmdd_text"}
    text_sql = (
        "SELECT * FROM event WHERE dt BETWEEN "
        "{{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}"
    )
    pivot = normalize_chat_date_filter_contract(
        text_filter,
        text_sql,
        "line",
        time_scope="explicit",
        time_range={"start_date": "2026-08-01", "end_date": "2026-08-19"},
        business_date=date(2026, 8, 19),
    )

    assert render_chat_date_filter_sql(
        text_sql,
        "mysql",
        pivot,
        today=date(2026, 8, 19),
    ).endswith("BETWEEN '20260801' AND '20260819'")


def test_rewrite_rejects_sql_literal_range_that_conflicts_with_contract():
    from apps.chat.service.chat_date_filter import rewrite_chat_date_filter_literals

    with pytest.raises(ChatDateFilterConfigurationError, match="sql_time_range_mismatch"):
        rewrite_chat_date_filter_literals(
            STATIC_DATE_FILTER,
            "SELECT * FROM event WHERE dt BETWEEN 20260801 AND 20260818",
        )


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        (
            "SELECT * FROM event WHERE `e`.`dt` >= 20260801 AND `e`.`dt` <= 20260819",
            "SELECT * FROM event WHERE `e`.`dt` >= {{dashboard_start_yyyymmdd}} AND `e`.`dt` <= {{dashboard_end_yyyymmdd}}",
        ),
        (
            "SELECT * FROM event WHERE `e`.`dt` = 20260819",
            "SELECT * FROM event WHERE `e`.`dt` BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}",
        ),
    ],
)
def test_rewrite_converts_comparison_date_literals_to_dashboard_tokens(sql: str, expected: str):
    from apps.chat.service.chat_date_filter import rewrite_chat_date_filter_literals

    if " = " in sql:
        single_day_filter = {
            **STATIC_DATE_FILTER,
            "date_expression": {
                "version": 1,
                "mode": "range",
                "start": {"mode": "static", "date": "2026-08-19"},
                "end": {"mode": "static", "date": "2026-08-19"},
            },
        }
        assert rewrite_chat_date_filter_literals(single_day_filter, sql) == expected
    else:
        assert rewrite_chat_date_filter_literals(STATIC_DATE_FILTER, sql) == expected


def test_rewrite_converts_timestamp_exclusive_end_comparison_to_dashboard_tokens():
    from apps.chat.service.chat_date_filter import rewrite_chat_date_filter_literals

    timestamp_filter = {
        "time_field": "time",
        "date_parameter_type": "timestamp",
        "date_expression": {
            "version": 1,
            "mode": "range",
            "start": {"mode": "static", "date": "2026-08-19"},
            "end": {"mode": "static", "date": "2026-08-19"},
        },
    }
    sql = (
        "SELECT * FROM event_realtime WHERE `e`.`time` >= '2026-08-19 00:00:00' "
        "AND `e`.`time` < '2026-08-20 00:00:00'"
    )

    assert rewrite_chat_date_filter_literals(timestamp_filter, sql) == (
        "SELECT * FROM event_realtime WHERE `e`.`time` >= {{dashboard_start_timestamp}} "
        "AND `e`.`time` < {{dashboard_end_exclusive_timestamp}}"
    )


def test_concrete_time_contract_rejects_range_after_business_date():
    future_filter = {
        **STATIC_DATE_FILTER,
        "date_expression": {
            **STATIC_DATE_FILTER["date_expression"],
            "end": {"mode": "static", "date": "2026-08-31"},
        },
    }

    with pytest.raises(ChatDateFilterConfigurationError, match="time_range_exceeds_business_date"):
        normalize_chat_date_filter_contract(
            future_filter,
            DATE_TEMPLATE_SQL,
            "line",
            time_scope="explicit",
            time_range={"start_date": "2026-08-01", "end_date": "2026-08-31"},
            business_date=date(2026, 8, 19),
        )


def test_concrete_time_contract_requires_exact_default_seven_complete_days():
    default_filter = {
        **STATIC_DATE_FILTER,
        "date_expression": {
            "version": 1,
            "mode": "range",
            "start": {"mode": "static", "date": "2026-08-12"},
            "end": {"mode": "static", "date": "2026-08-18"},
        },
    }

    pivot = normalize_chat_date_filter_contract(
        default_filter,
        DATE_TEMPLATE_SQL,
        "line",
        time_scope="unspecified",
        time_range={"start_date": "2026-08-12", "end_date": "2026-08-18"},
        business_date=date(2026, 8, 19),
    )

    assert pivot == {"enabled": False, **default_filter}


def test_concrete_time_contract_requires_current_business_day_for_realtime():
    with pytest.raises(
        ChatDateFilterConfigurationError,
        match="invalid_current_day_time_range",
    ):
        normalize_chat_date_filter_contract(
            DEFAULT_STATIC_DATE_FILTER,
            DATE_TEMPLATE_SQL,
            "line",
            time_scope="unspecified",
            time_range={"start_date": "2026-08-12", "end_date": "2026-08-18"},
            business_date=date(2026, 8, 19),
            requires_current_business_day=True,
        )


def test_concrete_time_contract_accepts_current_business_day_for_realtime():
    current_day_filter = {
        **STATIC_DATE_FILTER,
        "date_expression": {
            "version": 1,
            "mode": "range",
            "start": {"mode": "static", "date": "2026-08-19"},
            "end": {"mode": "static", "date": "2026-08-19"},
        },
    }

    pivot = normalize_chat_date_filter_contract(
        current_day_filter,
        DATE_TEMPLATE_SQL,
        "line",
        time_scope="explicit",
        time_range={"start_date": "2026-08-19", "end_date": "2026-08-19"},
        business_date=date(2026, 8, 19),
        requires_current_business_day=True,
    )

    assert pivot == {"enabled": False, **current_day_filter}


def test_concrete_time_contract_rejects_date_expression_mismatch():
    with pytest.raises(ChatDateFilterConfigurationError, match="time_range_mismatch"):
        normalize_chat_date_filter_contract(
            STATIC_DATE_FILTER,
            DATE_TEMPLATE_SQL,
            "line",
            time_scope="explicit",
            time_range={"start_date": "2026-08-02", "end_date": "2026-08-19"},
            business_date=date(2026, 8, 19),
        )


def test_normalize_uses_explicit_fourteen_day_question_range_instead_of_default():
    pivot = normalize_chat_date_filter_for_question(
        "最近14天每日付费金额趋势",
        DATE_FILTER,
        DATE_TEMPLATE_SQL,
        "line",
    )

    assert pivot == {
        "enabled": False,
        "time_field": "dt",
        "date_parameter_type": "yyyymmdd_number",
        "date_expression": {
            "version": 1,
            "mode": "range",
            "start": {"mode": "dynamic", "unit": "day", "offset": -14},
            "end": {"mode": "dynamic", "unit": "day", "offset": -1},
        },
    }


def test_normalize_keeps_default_past_seven_days_when_question_omits_time_range():
    pivot = normalize_chat_date_filter_for_question(
        "每日付费金额趋势",
        DATE_FILTER,
        DATE_TEMPLATE_SQL,
        "line",
    )

    assert pivot == {"enabled": False, **DATE_FILTER}


def test_normalize_replaces_model_default_when_question_omits_time_range():
    pivot = normalize_chat_date_filter_for_question(
        "每日活跃用户趋势",
        DATE_FILTER_WITH_MODEL_DEFAULT_PAST_28_DAYS,
        DATE_TEMPLATE_SQL,
        "line",
    )

    assert pivot == {"enabled": False, **DATE_FILTER}


def test_normalize_uses_today_for_explicit_current_day_question():
    pivot = normalize_chat_date_filter_for_question(
        "今天每小时的付费事件次数如何变化？",
        DATE_FILTER,
        REALTIME_DATE_TEMPLATE_SQL,
        "column",
    )

    assert pivot == {
        "enabled": False,
        "time_field": "dt",
        "date_parameter_type": "yyyymmdd_number",
        "date_expression": {"version": 1, "mode": "preset", "preset": "today"},
    }


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("实时收入", "current_day"),
        ("今天实时收入", "current_day"),
        ("当前小时收入", "current_day"),
        ("当前分钟收入", "current_day"),
        ("当前整点收入", "current_day"),
        ("昨天实时收入", "explicit_other"),
        ("最近14天实时收入", "explicit_other"),
        ("2026-08-01实时收入", "explicit_other"),
        ("本月实时收入", "explicit_other"),
        ("近两周实时收入", "explicit_other"),
        ("最近一个月实时收入", "explicit_other"),
        ("每日收入趋势", "unspecified"),
    ],
)
def test_question_date_scope_prefers_explicit_date_over_realtime(question, expected):
    assert chat_date_filter_service.question_date_scope(question) == expected


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


def test_normalize_prefers_day_before_yesterday_over_realtime_default():
    pivot = normalize_chat_date_filter_for_question(
        "前天实时收入",
        DATE_FILTER,
        DATE_TEMPLATE_SQL,
        "line",
    )

    assert pivot["date_expression"] == {
        "version": 1,
        "mode": "range",
        "start": {"mode": "dynamic", "unit": "day", "offset": -2},
        "end": {"mode": "dynamic", "unit": "day", "offset": -2},
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


def test_normalize_preserves_explicit_current_month_over_realtime_default():
    month_filter = {
        **DATE_FILTER,
        "date_expression": {
            "version": 1,
            "mode": "preset",
            "preset": "current_month",
        },
    }

    pivot = normalize_chat_date_filter_for_question(
        "本月实时收入",
        month_filter,
        DATE_TEMPLATE_SQL,
        "line",
    )

    assert pivot == {"enabled": False, **month_filter}


def test_normalize_enforces_current_month_from_explicit_question() -> None:
    invalid_model_filter = {
        **DATE_FILTER,
        "date_expression": {
            "version": 1,
            "mode": "preset",
            "preset": "this_month",
        },
    }

    pivot = normalize_chat_date_filter_for_question(
        "本月收入与上月同期相比变化多少？",
        invalid_model_filter,
        DATE_TEMPLATE_SQL,
        "line",
    )

    assert pivot["date_expression"] == {
        "version": 1,
        "mode": "preset",
        "preset": "current_month",
    }


def test_normalize_rejects_metric_for_explicit_realtime_time_series_question():
    with pytest.raises(
        ChatDateFilterConfigurationError,
        match="realtime_requires_hourly_time_series",
    ):
        normalize_chat_date_filter_for_question(
            "实时收入趋势",
            None,
            "SELECT SUM(amount) FROM event_realtime",
            "metric",
        )


def test_normalize_rejects_metric_for_explicit_realtime_scalar_without_date_filter():
    with pytest.raises(ChatDateFilterConfigurationError, match="missing_date_filter"):
        normalize_chat_date_filter_for_question(
            "实时收入",
            None,
            "SELECT SUM(amount) FROM event_realtime",
            "metric",
        )


@pytest.mark.parametrize("question", ["统计今天的实时付费情况", "按渠道统计今天的实时付费"])
def test_normalize_allows_realtime_non_time_series_without_date_filter(question):
    assert (
        normalize_chat_date_filter_for_question(
            question,
            None,
            "SELECT channel, SUM(amount) FROM event_realtime GROUP BY channel",
            "column",
        )
        is None
    )


def test_normalize_rejects_missing_date_filter_for_explicit_today_time_series():
    with pytest.raises(ChatDateFilterConfigurationError, match="missing_date_filter"):
        normalize_chat_date_filter_for_question(
            "按小时统计今天的付费次数",
            None,
            (
                "SELECT COUNT(*) FROM event_realtime "
                "WHERE dt = 20260805 GROUP BY HOUR(FROM_UNIXTIME(time / 1000))"
            ),
            "line",
        )


def test_normalize_rejects_missing_date_filter_for_explicit_recent_days_time_series():
    with pytest.raises(ChatDateFilterConfigurationError, match="missing_date_filter"):
        normalize_chat_date_filter_for_question(
            "最近14天每日付费金额趋势",
            None,
            "SELECT dt, SUM(amount) FROM event GROUP BY dt",
            "line",
        )


def test_normalize_rejects_missing_date_filter_for_explicit_today_metric():
    with pytest.raises(ChatDateFilterConfigurationError, match="missing_date_filter"):
        normalize_chat_date_filter_for_question(
            "今天的付费总额",
            None,
            "SELECT SUM(amount) FROM event_realtime WHERE dt = 20260805",
            "metric",
        )


def test_normalize_rejects_fixed_date_metric_without_date_filter():
    with pytest.raises(ChatDateFilterConfigurationError, match="missing_date_filter"):
        normalize_chat_date_filter_for_question(
            "充值人数",
            None,
            "SELECT COUNT(DISTINCT uid) FROM event WHERE dt = 20260818",
            "metric",
        )


def test_normalize_rejects_missing_date_filter_for_unspecified_time_series():
    with pytest.raises(ChatDateFilterConfigurationError, match="missing_date_filter"):
        normalize_chat_date_filter_for_question(
            "各投放渠道每日新增用户趋势如何？",
            None,
            "SELECT dt, channel, COUNT(*) FROM event GROUP BY dt, channel",
            "area",
        )


def test_normalize_keeps_unspecified_non_time_series_without_date_filter():
    assert (
        normalize_chat_date_filter_for_question(
            "各投放渠道新增用户总量",
            None,
            "SELECT channel, COUNT(*) FROM event GROUP BY channel",
            "column",
        )
        is None
    )


def test_check_sql_rejects_explicit_today_time_series_without_date_filter(monkeypatch):
    monkeypatch.setattr("apps.chat.task.llm.trigger_log_error", lambda *_args: None)
    service = object.__new__(LLMService)
    service.current_logs = {OperationEnum.GENERATE_SQL: None}
    service.dashboard_date_filter_enabled = True
    service.ds = SimpleNamespace(type="mysql")
    service.chat_question = SimpleNamespace(question="按小时统计今天的付费次数", data_skill="")
    service.chat_date_pivot = None
    response = {
        "success": True,
        "sql": "SELECT COUNT(*) FROM event_realtime WHERE dt = 20260805",
        "tables": ["event_realtime"],
        "chart-type": "line",
    }

    with pytest.raises(SingleMessageError, match="missing_time_scope"):
        service.check_sql(
            session=object(),
            res=__import__("json").dumps(response),
            operate=OperationEnum.GENERATE_SQL,
        )


def test_check_sql_keeps_date_contract_disabled_for_sample_workspace(monkeypatch):
    monkeypatch.setattr("apps.chat.task.llm.trigger_log_error", lambda *_args: None)
    service = object.__new__(LLMService)
    service.current_logs = {OperationEnum.GENERATE_SQL: None}
    service.dashboard_date_filter_enabled = False
    service.current_user = SimpleNamespace(tenant_id=1)
    service.ds = SimpleNamespace(type="mysql")
    service.chat_question = SimpleNamespace(question="趋势", data_skill="")
    service.chat_date_pivot = {"enabled": False, **DATE_FILTER}
    service.dashboard_date_filter_enabled = False
    response = {
        "success": True,
        "sql": "SELECT channel, COUNT(*) FROM event GROUP BY channel",
        "tables": ["event"],
        "chart-type": "line",
    }

    class SampleWorkspaceSession:
        def get(self, _model, _tenant_id):
            return SimpleNamespace(name=SAMPLE_TENANT_NAME)

    sql, tables = service.check_sql(
        session=SampleWorkspaceSession(),
        res=__import__("json").dumps(response),
        operate=OperationEnum.GENERATE_SQL,
    )

    assert sql == response["sql"]
    assert tables == ["event"]
    assert service.chat_date_pivot is None


def test_check_sql_keeps_invalid_date_filter_for_regular_workspace(monkeypatch):
    monkeypatch.setattr("apps.chat.task.llm.trigger_log_error", lambda *_args: None)
    monkeypatch.setattr("apps.chat.task.llm.system_business_date", lambda: date(2026, 8, 19))
    service = object.__new__(LLMService)
    service.current_logs = {OperationEnum.GENERATE_SQL: None}
    service.dashboard_date_filter_enabled = True
    service.current_user = SimpleNamespace(tenant_id=2)
    service.ds = SimpleNamespace(type="mysql")
    service.chat_question = SimpleNamespace(question="趋势", data_skill="")
    service.chat_date_pivot = None
    response = _attach_time_contract({
        "success": True,
        "sql": "SELECT channel, COUNT(*) FROM event GROUP BY channel",
        "tables": ["event"],
        "chart-type": "line",
    }, DEFAULT_STATIC_DATE_FILTER, scope="unspecified", start="2026-08-12", end="2026-08-18")

    class RegularWorkspaceSession:
        def get(self, _model, _tenant_id):
            return SimpleNamespace(name="普通工作空间")

    with pytest.raises(SingleMessageError, match="missing_parameters"):
        service.check_sql(
            session=RegularWorkspaceSession(),
            res=__import__("json").dumps(response),
            operate=OperationEnum.GENERATE_SQL,
        )


def test_check_sql_uses_llm_concrete_explicit_range():
    service = object.__new__(LLMService)
    service.current_logs = {OperationEnum.GENERATE_SQL: None}
    service.dashboard_date_filter_enabled = True
    service.ds = SimpleNamespace(type="mysql")
    service.chat_question = SimpleNamespace(question="过去15天各渠道D7留存率对比", data_skill="")
    service.chat_date_pivot = None
    explicit_filter = {
        **DATE_FILTER,
        "date_expression": {
            "version": 1,
            "mode": "range",
            "start": {"mode": "static", "date": "2026-08-04"},
            "end": {"mode": "static", "date": "2026-08-18"},
        },
    }
    response = _attach_time_contract({
        "success": True,
        "sql": DATE_TEMPLATE_SQL,
        "tables": ["event"],
        "chart-type": "line",
    }, explicit_filter, scope="explicit", start="2026-08-04", end="2026-08-18")

    service.check_sql(
        session=object(),
        res=__import__("json").dumps(response),
        operate=OperationEnum.GENERATE_SQL,
    )

    assert service.chat_date_pivot["date_expression"] == {
        "version": 1,
        "mode": "range",
        "start": {"mode": "static", "date": "2026-08-04"},
        "end": {"mode": "static", "date": "2026-08-18"},
    }


def test_normalize_rejects_token_without_configuration():
    with pytest.raises(ChatDateFilterConfigurationError, match="missing_date_filter"):
        normalize_chat_date_filter(None, DATE_TEMPLATE_SQL, "line")


def test_normalize_allows_metric_date_configuration():
    pivot = normalize_chat_date_filter(DATE_FILTER, DATE_TEMPLATE_SQL, "metric")
    assert pivot["time_field"] == "dt"


def test_normalize_rejects_current_date_function_for_date_filter():
    with pytest.raises(ChatDateFilterConfigurationError, match="database_current_date"):
        normalize_chat_date_filter(
            DATE_FILTER,
            "SELECT * FROM event WHERE dt >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)",
            "line",
        )


def test_render_uses_past_seven_days_before_execution():
    sql = render_chat_date_filter_sql(
        DATE_TEMPLATE_SQL,
        "mysql",
        {"enabled": False, **DATE_FILTER},
        today=date(2026, 7, 29),
    )

    assert "20260722" in sql
    assert "20260728" in sql
    assert "{{dashboard_start_yyyymmdd}}" not in sql
    assert "{{dashboard_end_yyyymmdd}}" not in sql


def test_render_allows_current_business_day_for_realtime_table():
    sql = render_chat_date_filter_sql(
        REALTIME_DATE_TEMPLATE_SQL,
        "mysql",
        {"enabled": False, **TODAY_DATE_FILTER},
        today=date(2026, 8, 4),
    )

    assert sql.count("20260804") == 2
    assert "{{dashboard_start_yyyymmdd}}" not in sql
    assert "{{dashboard_end_yyyymmdd}}" not in sql


def test_render_allows_historical_range_for_realtime_table():
    sql = render_chat_date_filter_sql(
        REALTIME_DATE_TEMPLATE_SQL,
        "mysql",
        {"enabled": False, **DATE_FILTER},
        today=date(2026, 8, 4),
    )

    assert "20260728" in sql
    assert "20260803" in sql


@pytest.mark.parametrize(
    ("sql_template", "expected_date"),
    [
        (REALTIME_DATE_START_ONLY_SQL, "20260804"),
        (REALTIME_DATE_END_ONLY_SQL, "20260804"),
    ],
)
def test_render_allows_single_boundary_filter_for_realtime_table(
    sql_template: str,
    expected_date: str,
):
    sql = render_chat_date_filter_sql(
        sql_template,
        "mysql",
        {"enabled": False, **TODAY_DATE_FILTER},
        today=date(2026, 8, 4),
    )

    assert expected_date in sql
    assert "{{dashboard_" not in sql


def test_llm_service_renders_date_template_only_for_execution():
    service = object.__new__(LLMService)
    service.ds = SimpleNamespace(type="mysql")
    service.chat_date_pivot = {"enabled": False, **DATE_FILTER}

    execution_sql = service.render_chat_sql_for_execution(DATE_TEMPLATE_SQL)

    assert "{{dashboard_start_yyyymmdd}}" not in execution_sql
    assert "{{dashboard_end_yyyymmdd}}" not in execution_sql
    assert "BETWEEN" in execution_sql


def test_llm_service_rejects_unrendered_date_template():
    service = object.__new__(LLMService)
    service.ds = SimpleNamespace(type="mysql")
    service.chat_date_pivot = None

    with pytest.raises(ChatDateFilterConfigurationError, match="date_filter_render_incomplete"):
        service.render_chat_sql_for_execution(DATE_TEMPLATE_SQL)


def test_check_sql_keeps_date_template_and_date_filter_pivot(monkeypatch):
    monkeypatch.setattr("apps.chat.task.llm.system_business_date", lambda: date(2026, 8, 19))
    service = object.__new__(LLMService)
    service.current_logs = {OperationEnum.GENERATE_SQL: None}
    service.dashboard_date_filter_enabled = True
    service.ds = SimpleNamespace(type="mysql")
    service.chat_question = SimpleNamespace(question="趋势", data_skill="")
    service.chat_date_pivot = None
    response = _attach_time_contract({
        "success": True,
        "sql": DATE_TEMPLATE_SQL,
        "tables": ["event"],
        "chart-type": "line",
    }, DEFAULT_STATIC_DATE_FILTER, scope="unspecified", start="2026-08-12", end="2026-08-18")

    sql, tables = service.check_sql(
        session=object(),
        res=__import__("json").dumps(response),
        operate=OperationEnum.GENERATE_SQL,
    )

    assert sql == DATE_TEMPLATE_SQL
    assert tables == ["event"]
    assert service.chat_date_pivot == {"enabled": False, **DEFAULT_STATIC_DATE_FILTER}


def test_check_sql_rewrites_date_literals_to_template_for_declared_date_filter():
    service = object.__new__(LLMService)
    service.current_logs = {OperationEnum.GENERATE_SQL: None}
    service.dashboard_date_filter_enabled = True
    service.ds = SimpleNamespace(type="mysql")
    service.chat_question = SimpleNamespace(question="DAU趋势", data_skill="")
    service.chat_date_pivot = None
    literal_filter = {
        **DATE_FILTER,
        "date_expression": {
            "version": 1,
            "mode": "range",
            "start": {"mode": "static", "date": "2026-07-01"},
            "end": {"mode": "static", "date": "2026-07-28"},
        },
    }
    response = _attach_time_contract({
        "success": True,
        "sql": DATE_LITERAL_SQL,
        "tables": ["event"],
        "chart-type": "line",
    }, literal_filter, scope="explicit", start="2026-07-01", end="2026-07-28")

    sql, tables = service.check_sql(
        session=object(),
        res=__import__("json").dumps(response),
        operate=OperationEnum.GENERATE_SQL,
    )

    assert sql == DATE_LITERAL_TEMPLATE_SQL
    assert tables == ["event"]
    assert service.chat_date_pivot == {"enabled": False, **literal_filter}


def test_check_sql_rejects_declared_current_date_function_with_concrete_contract(monkeypatch):
    monkeypatch.setattr("apps.chat.task.llm.trigger_log_error", lambda *_args: None)
    service = object.__new__(LLMService)
    service.current_logs = {OperationEnum.GENERATE_SQL: None}
    service.dashboard_date_filter_enabled = True
    service.ds = SimpleNamespace(type="mysql")
    service.chat_question = SimpleNamespace(question="最近14天每日付费金额趋势", data_skill="")
    service.chat_date_pivot = None
    fourteen_day_filter = {
        **DATE_FILTER,
        "date_expression": {
            "version": 1,
            "mode": "range",
            "start": {"mode": "static", "date": "2026-08-05"},
            "end": {"mode": "static", "date": "2026-08-18"},
        },
    }
    response = _attach_time_contract({
        "success": True,
        "sql": DATE_CURRENT_FUNCTION_SQL,
        "tables": ["event"],
        "chart-type": "line",
    }, fourteen_day_filter, scope="explicit", start="2026-08-05", end="2026-08-18")

    with pytest.raises(SingleMessageError, match="database_current_date"):
        service.check_sql(
            session=object(),
            res=__import__("json").dumps(response),
            operate=OperationEnum.GENERATE_SQL,
        )


def test_prepare_sql_saves_template_but_validates_rendered_sql(monkeypatch):
    class FakeSessionScope:
        def __enter__(self):
            return object()

        def __exit__(self, *_args):
            return False

    saved_sql = []
    validated_sql = []
    service = SimpleNamespace(
        current_assistant=None,
        current_user=object(),
        ds=SimpleNamespace(type="mysql"),
        table_name_list=["event"],
        change_title=False,
        chat_date_pivot={"enabled": False, **DATE_FILTER},
        check_sql=lambda **_kwargs: (DATE_TEMPLATE_SQL, ["event"]),
        get_chart_type_from_sql_answer=lambda _answer: "line",
        save_checked_sql=lambda **kwargs: saved_sql.append(kwargs["sql"]) or kwargs["sql"],
        render_chat_sql_for_execution=lambda sql: render_chat_date_filter_sql(
            sql,
            "mysql",
            {"enabled": False, **DATE_FILTER},
            today=date(2026, 7, 29),
        ),
    )

    monkeypatch.setattr(smart_qa_graph, "_session_scope", lambda: FakeSessionScope())
    monkeypatch.setattr(
        smart_qa_graph,
        "validate_user_query_sql_or_raise",
        lambda **kwargs: (validated_sql.append(kwargs["sql"]) or kwargs["sql"], {"event"}),
    )
    monkeypatch.setattr(
        smart_qa_graph,
        "_rewrite_sql_for_missing_events",
        lambda _service, sql: smart_qa_graph._MissingEventSqlRewrite(sql=sql, executable=True),
    )

    state = smart_qa_graph._prepare_sql(
        {
            "service": service,
            "in_chat": False,
            "stream": False,
            "finish_step": ChatFinishStep.QUERY_DATA,
            "json_result": {},
            "full_sql_text": '{"success":true}',
        }
    )

    assert saved_sql == [DATE_TEMPLATE_SQL]
    assert "{{dashboard_start_yyyymmdd}}" not in validated_sql[0]
    assert "{{dashboard_start_yyyymmdd}}" not in state["real_execute_sql"]


def test_live_chart_refresh_renders_persisted_date_pivot_before_execution(monkeypatch):
    class FakeResult:
        def first(self):
            return SimpleNamespace(
                datasource=1,
                sql=DATE_TEMPLATE_SQL,
                chart={"type": "line", "pivot": {"enabled": False, **DATE_FILTER}},
            )

    class FakeSession:
        def execute(self, _statement):
            return FakeResult()

        def get(self, _model, _identifier):
            return SimpleNamespace(type="mysql")

    executed_sql = []
    monkeypatch.setattr(chat_crud, "_current_tenant_id", lambda _user: 1)
    monkeypatch.setattr(chat_crud, "_saved_record_missing_event_projection", lambda **_kwargs: None)
    monkeypatch.setattr(
        chat_crud,
        "_execute_dashboard_chart_sql",
        lambda _session, _user, _datasource, sql: executed_sql.append(sql) or {"data": []},
    )
    monkeypatch.setattr(
        chat_crud,
        "render_chat_date_filter_sql",
        lambda sql, _datasource_type, pivot: render_chat_date_filter_sql(
            sql,
            "mysql",
            pivot,
            today=date(2026, 7, 29),
        ),
        raising=False,
    )
    result = chat_crud.get_chart_data_with_user_live(FakeSession(), SimpleNamespace(id=2), 3)

    assert result == {"data": []}
    assert "{{dashboard_start_yyyymmdd}}" not in executed_sql[0]
    assert "20260722" in executed_sql[0]


def test_chat_sql_template_requires_date_filter_contract():
    source = (Path(__file__).resolve().parents[1] / "templates" / "template.yaml").read_text(
        encoding="utf-8"
    )

    assert '"date_filter"' in source
    assert '"time_scope"' in source
    assert '"time_range"' in source
    assert "实时粒度规则" in source
    assert "不得把实时问题生成单行 SUM/COUNT 的 metric" in source
