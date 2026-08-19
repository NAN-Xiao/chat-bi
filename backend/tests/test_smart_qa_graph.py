"""
脚本说明：这个脚本是测试文件，用来验证对应功能在常见情况下能按预期工作。
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import pytest

from apps.chat.models.chat_model import ChatFinishStep, OperationEnum
from apps.chat.task import llm
from apps.chat.task import smart_qa_graph as graph
from apps.chat.task.sql_repair import SqlRepairReason, SqlStructureValidationError
from apps.datasource.crud.permission_errors import (
    PERMISSION_DENIED_ERROR_TYPE,
    SqlSchemaScopeError,
)
from common.error import AppDBConnectionError, DataUnavailableError, SingleMessageError


@contextmanager
def _fake_session_scope():
    """
    是什么：_fake_session_scope 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：测试代码会调用它，用来准备数据或检查结果。
    做了什么：把测试里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    yield object()


def _sql_answer(sql: str = "select 1 as value", tables: list[str] | None = None) -> str:
    """
    是什么：_sql_answer 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：测试代码会调用它，用来准备数据或检查结果。
    做了什么：把测试里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    payload = {
        "success": True,
        "sql": sql,
        "tables": tables or ["orders"],
        "chart_type": "table",
    }
    return json.dumps(payload)


def test_event_predicate_parser_ignores_partition_date_format_literals() -> None:
    tracking_config = '''
## 默认字段
- 默认事件名字段: `event`

## 字段角色映射
[{"role":"subject_id","field":"uid","table":"event","description":"事件主体用户 ID"},{"role":"event_name","field":"event","table":"event","description":"业务事件名"},{"role":"event_time","field":"time","table":"event","description":"毫秒时间戳，实时口径需转 UTC+8"},{"role":"partition_date","field":"dt","table":"event","description":"业务日期分区 yyyyMMdd"},{"role":"subject_id","field":"uid","table":"event_realtime","description":"实时事件主体用户 ID"},{"role":"event_name","field":"event","table":"event_realtime","description":"实时业务事件名"},{"role":"event_time","field":"time","table":"event_realtime","description":"实时事件毫秒时间戳，按 UTC+8 转业务时间"},{"role":"partition_date","field":"dt","table":"event_realtime","description":"实时业务日期分区 yyyyMMdd"}]
'''
    service = SimpleNamespace(
        ds=SimpleNamespace(type="mysql"),
        chat_question=SimpleNamespace(tracking_config=tracking_config),
    )
    sql = """
SELECT COUNT(DISTINCT `e`.`uid`) AS `新增用户数`
FROM `event_realtime` `e`
WHERE `e`.`dt` = CAST(DATE_FORMAT(CURDATE(), '%Y%m%d') AS SIGNED)
  AND `e`.`event` = 'UserRegister'
"""

    predicates = graph._extract_requested_event_predicates(sql, service)

    assert [(item.event_field, item.event_values) for item in predicates] == [
        ("event", {"UserRegister"})
    ]


def _sql_answer_with_message(sql: str, message: str, tables: list[str] | None = None) -> str:
    payload = {
        "success": True,
        "sql": sql,
        "tables": tables or ["orders"],
        "chart_type": "table",
        "message": message,
    }
    return json.dumps(payload)


def _mixed_missing_event_sql() -> str:
    return """
WITH missing_event AS (
  SELECT event_date, count(distinct player_id) AS missing_event_users
  FROM fact_events
  WHERE event_name = 'spaceship_upgrade_complete'
  GROUP BY event_date
)
SELECT d.event_date AS "日期",
       d.dau AS "DAU",
       d.pdau AS "PDAU",
       coalesce(m.missing_event_users, 0) AS "飞船升级完成触发用户数"
FROM daily_metrics d
LEFT JOIN missing_event m ON m.event_date = d.event_date
"""


def _schema_qualified_missing_event_sql() -> str:
    return """
WITH obs AS (
  SELECT max("session_start"::date) AS "max_date"
  FROM "public"."fact_sessions"
),
days AS (
  SELECT generate_series(obs."max_date" - 29, obs."max_date", interval '1 day')::date AS "event_date"
  FROM obs
),
dau AS (
  SELECT "s"."session_start"::date AS "event_date",
         count(DISTINCT "s"."player_id") AS "dau"
  FROM "public"."fact_sessions" "s"
  CROSS JOIN obs
  WHERE "s"."session_start"::date BETWEEN obs."max_date" - 29 AND obs."max_date"
  GROUP BY "s"."session_start"::date
),
pdau AS (
  SELECT "p"."event_date",
         count(DISTINCT "p"."player_id") AS "pdau"
  FROM "public"."fact_payments" "p"
  CROSS JOIN obs
  WHERE "p"."event_date" BETWEEN obs."max_date" - 29 AND obs."max_date"
    AND "p"."payment_status" = 'success'
    AND "p"."net_revenue_usd" > 0
  GROUP BY "p"."event_date"
),
spaceship_upgrade AS (
  SELECT "e"."event_date",
         count(DISTINCT "e"."player_id") AS "spaceship_upgrade_users"
  FROM "public"."fact_events" "e"
  CROSS JOIN obs
  WHERE "e"."event_date" BETWEEN obs."max_date" - 29 AND obs."max_date"
    AND "e"."event_name" = 'spaceship_upgrade_complete'
  GROUP BY "e"."event_date"
)
SELECT "d"."event_date" AS "日期",
       coalesce("da"."dau", 0) AS "DAU",
       coalesce("pa"."pdau", 0) AS "PDAU",
       coalesce("su"."spaceship_upgrade_users", 0) AS "飞船升级完成触发用户数"
FROM days "d"
LEFT JOIN dau "da" ON "da"."event_date" = "d"."event_date"
LEFT JOIN pdau "pa" ON "pa"."event_date" = "d"."event_date"
LEFT JOIN spaceship_upgrade "su" ON "su"."event_date" = "d"."event_date"
ORDER BY "d"."event_date"
LIMIT 1000
"""


def _direct_missing_event_metric_sql() -> str:
    return """
WITH obs AS (
  SELECT max("session_start"::date) AS "max_date"
  FROM "public"."fact_sessions"
),
event_stats AS (
  SELECT count(*) AS "触发次数",
         count(DISTINCT "player_id") AS "触发人数"
  FROM "public"."fact_events" "e"
  CROSS JOIN obs
  WHERE "e"."event_date" BETWEEN obs."max_date" - 6 AND obs."max_date"
    AND "e"."event_name" = 'dragon_summon_success'
)
SELECT "触发次数", "触发人数"
FROM event_stats
LIMIT 1000
"""


def _events(chunks: list[Any]) -> list[dict[str, Any]]:
    """
    是什么：_events 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：测试代码会调用它，用来准备数据或检查结果。
    做了什么：把测试里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    events: list[dict[str, Any]] = []
    for chunk in chunks:
        if isinstance(chunk, str) and chunk.startswith("data:"):
            events.append(json.loads(chunk[5:]))
    return events


@pytest.fixture(autouse=True)
def _patch_graph_runtime(monkeypatch: pytest.MonkeyPatch):
    """
    是什么：_patch_graph_runtime 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：测试代码会调用它，用来准备数据或检查结果。
    做了什么：把测试里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    monkeypatch.setattr(graph, "_session_scope", _fake_session_scope)
    monkeypatch.setattr(graph, "check_connection", lambda ds, trans=None: True)
    monkeypatch.setattr(
        graph,
        "start_log",
        lambda **kwargs: SimpleNamespace(id=1, error=False),
    )
    monkeypatch.setattr(graph, "end_log", lambda **kwargs: kwargs["log"])

    def _trigger_log_error(session, log, full_message=None):
        log.error = True
        if full_message is not None:
            log.messages = full_message
        return log

    monkeypatch.setattr(graph, "trigger_log_error", _trigger_log_error)


class FakeSmartQAService:
    """
    类说明：FakeSmartQAService 把测试的一组操作放在一起，对外提供更容易调用的业务能力。
    """
    def __init__(
        self,
        *,
        current_assistant: Any = None,
        sql_answer: str | None = None,
    ) -> None:
        """
        是什么：FakeSmartQAService.__init__ 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：把这个对象刚创建时需要的信息先放好。
        """
        self.ds = SimpleNamespace(id=1, type="PostgreSQL", type_name="PostgreSQL")
        self.record = SimpleNamespace(
            id=9001,
            chat_id=9000,
            question="test question",
            regenerate_record_id=None,
        )
        self.chat_question = SimpleNamespace(
            question="test question",
            data_skill="",
            ai_modal_id=None,
            ai_modal_name=None,
        )
        self.current_user = SimpleNamespace(id=1)
        self.current_assistant = current_assistant
        self.current_logs: dict[OperationEnum, Any] = {}
        self.table_name_list = ["orders"]
        self.change_title = False
        self.out_ds_instance = None
        self.business_sql_context = SimpleNamespace(
            schema="table orders(value numeric)",
            allowed_tables=["orders"],
        )
        self.sql_answer = sql_answer or _sql_answer()
        self.saved_sql: list[str] = []
        self.saved_data: list[dict[str, Any]] = []
        self.saved_errors: list[str] = []
        self.saved_analysis: list[str] = []
        self.executed: list[dict[str, Any]] = []
        self.repair_answers: list[str] = []
        self.repair_contexts: list[Any] = []
        self.chart_generated = False
        self.finished = False
        self.chart_chunks = [
            {"content": '{"type":"table","title":"Result","columns":[{"value":"value"}]}', "reasoning_content": ""},
        ]

    def get_record(self):
        """
        是什么：FakeSmartQAService.get_record 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：把测试需要的数据找出来，整理成后面好用的样子。
        """
        return self.record

    def trans(self, key: str):
        """
        是什么：FakeSmartQAService.trans 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：把测试里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        return f"{key}: "

    def load_data_skills(self, *args, **kwargs):
        """
        是什么：FakeSmartQAService.load_data_skills 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：把测试需要的数据找出来，整理成后面好用的样子。
        """
        pass

    def filter_custom_prompts(self, *args, **kwargs):
        """
        是什么：FakeSmartQAService.filter_custom_prompts 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：把测试里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        pass

    def save_agent_context_snapshot(self, *args, **kwargs):
        """
        是什么：FakeSmartQAService.save_agent_context_snapshot 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：创建或保存测试需要的东西，让后续流程能继续往下走。
        """
        pass

    def load_tracking_config(self, *args, **kwargs):
        """
        是什么：FakeSmartQAService.load_tracking_config 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：把测试需要的数据找出来，整理成后面好用的样子。
        """
        pass

    def init_messages(self, *args, **kwargs):
        """
        是什么：FakeSmartQAService.init_messages 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：创建或保存测试需要的东西，让后续流程能继续往下走。
        """
        pass

    def validate_history_ds(self, *args, **kwargs):
        """
        是什么：FakeSmartQAService.validate_history_ds 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：检查测试里的数据、权限或配置是否合法，不对就及时拦住。
        """
        pass

    def generate_sql_text_streaming_reasoning(self, *args, **kwargs):
        """
        是什么：FakeSmartQAService.generate_sql_text_streaming_reasoning 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：根据已有信息生成测试的结果，比如答案、SQL、图表或建议。
        """
        if kwargs.get("in_chat"):
            yield graph._sse({
                "content": "",
                "reasoning_content": "thinking",
                "type": "sql-result",
            })
        return self.sql_answer

    def regenerate_sql_after_error_streaming_reasoning(self, session, context, in_chat):
        """
        是什么：FakeSmartQAService.regenerate_sql_after_error_streaming_reasoning 是一段测试代码，用来模拟统一 SQL 修复。
        """
        self.repair_contexts.append(context)
        if in_chat:
            yield graph._sse({
                "content": "",
                "reasoning_content": "repairing",
                "type": "sql-result",
            })
        return self.repair_answers.pop(0)

    def check_sql(self, *, session, res, operate):
        """
        是什么：FakeSmartQAService.check_sql 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：检查测试里的数据、权限或配置是否合法，不对就及时拦住。
        """
        payload = json.loads(res)
        return payload["sql"], payload.get("tables")

    def get_chart_type_from_sql_answer(self, *args, **kwargs):
        """
        是什么：FakeSmartQAService.get_chart_type_from_sql_answer 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：把测试需要的数据找出来，整理成后面好用的样子。
        """
        return "table"

    def save_checked_sql(self, *, session, sql):
        """
        是什么：FakeSmartQAService.save_checked_sql 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：创建或保存测试需要的东西，让后续流程能继续往下走。
        """
        self.saved_sql.append(sql)
        return sql

    def generate_assistant_dynamic_sql(self, *args, **kwargs):
        """
        是什么：FakeSmartQAService.generate_assistant_dynamic_sql 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：根据已有信息生成测试的结果，比如答案、SQL、图表或建议。
        """
        return None

    def check_save_sql(self, *args, **kwargs):
        """
        是什么：FakeSmartQAService.check_save_sql 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：检查测试里的数据、权限或配置是否合法，不对就及时拦住。
        """
        raise AssertionError("dynamic SQL should not be saved in this scenario")

    def save_permission_denied_data(self, *args, **kwargs):
        """
        是什么：FakeSmartQAService.save_permission_denied_data 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：创建或保存测试需要的东西，让后续流程能继续往下走。
        """
        result = {
            "status": "failed",
            "error_type": PERMISSION_DENIED_ERROR_TYPE,
            "fields": [],
            "data": [],
        }
        self.saved_data.append(result)
        return result

    def execute_sql(self, **kwargs):
        """
        是什么：FakeSmartQAService.execute_sql 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：把测试的主要流程跑起来，一步步调用需要的处理。
        """
        self.executed.append(kwargs)
        return {"fields": ["value"], "data": [{"value": 1}]}

    def save_sql_data(self, *, session, data_obj):
        """
        是什么：FakeSmartQAService.save_sql_data 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：创建或保存测试需要的东西，让后续流程能继续往下走。
        """
        self.saved_data.append(data_obj)

    def generate_chart(self, *args, **kwargs):
        """
        是什么：FakeSmartQAService.generate_chart 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：根据已有信息生成测试的结果，比如答案、SQL、图表或建议。
        """
        self.chart_generated = True
        yield from self.chart_chunks

    def check_save_chart(self, *, session, res, result):
        """
        是什么：FakeSmartQAService.check_save_chart 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：检查测试里的数据、权限或配置是否合法，不对就及时拦住。
        """
        assert session is not None
        assert result["fields"] == ["value"]
        return json.loads(res)

    def save_error(self, *, session, message):
        """
        是什么：FakeSmartQAService.save_error 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：创建或保存测试需要的东西，让后续流程能继续往下走。
        """
        self.saved_errors.append(message)

    def save_analysis(self, *, session, answer):
        """
        是什么：FakeSmartQAService.save_analysis 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：创建或保存测试需要的东西，让后续流程能继续往下走。
        """
        self.saved_analysis.append(answer)
        return self.record

    def finish(self, *args, **kwargs):
        """
        是什么：FakeSmartQAService.finish 是 FakeSmartQAService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：把测试这次处理做收尾，记录结果并关掉不再需要的资源。
        """
        self.finished = True


def test_prepare_sql_parse_error_repairs_then_revalidates(monkeypatch: pytest.MonkeyPatch) -> None:
    invalid_sql = "SELECT CAST(value, AS DECIMAL(18, 4)) FROM orders"
    repaired_sql = "SELECT CAST(value AS DECIMAL(18, 4)) FROM orders"
    service = FakeSmartQAService(sql_answer=_sql_answer(invalid_sql))
    service.repair_answers = [_sql_answer(repaired_sql)]
    calls: list[str] = []

    def validate(**kwargs):
        calls.append(kwargs["sql"])
        if kwargs["sql"] == invalid_sql:
            raise ValueError("Parse SQL Error: Expected TYPE after CAST")
        return kwargs["sql"], {"orders"}

    monkeypatch.setattr(graph, "validate_user_query_sql_or_raise", validate)
    chunks = list(
        graph.run_smart_qa_graph(
            service,
            in_chat=True,
            stream=True,
            finish_step=ChatFinishStep.GENERATE_CHART,
        ),
    )
    events = _events(chunks)

    assert calls == [invalid_sql, repaired_sql]
    assert service.saved_sql == [repaired_sql]
    assert service.executed[0]["sql"] == repaired_sql
    assert len(service.repair_contexts) == 1
    assert not any(event["type"] == "error" for event in events)
    assert not any(invalid_sql in str(event.get("content") or "") for event in events)
    sql_events = [event["content"] for event in events if event["type"] == "sql"]
    assert len(sql_events) == 1
    assert "CAST(value AS DECIMAL(18, 4))" in sql_events[0]


def test_schema_field_error_repairs_instead_of_returning_permission_denied(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid_sql = "SELECT p.player_id, MAX(p.channel) FROM fact_payments p GROUP BY p.player_id"
    repaired_sql = (
        "SELECT p.player_id, MAX(p.payment_source_channel) "
        "FROM fact_payments p GROUP BY p.player_id"
    )
    service = FakeSmartQAService(sql_answer=_sql_answer(invalid_sql, ["fact_payments"]))
    service.repair_answers = [_sql_answer(repaired_sql, ["fact_payments"])]
    calls: list[str] = []

    def validate(**kwargs):
        calls.append(kwargs["sql"])
        if kwargs["sql"] == invalid_sql:
            raise SqlSchemaScopeError(
                "SQL 引用了当前 Schema 中不存在或无法解析的字段：p.channel",
                fields={"p.channel"},
            )
        return kwargs["sql"], {"fact_payments"}

    monkeypatch.setattr(graph, "validate_user_query_sql_or_raise", validate)
    events = _events(list(graph.run_smart_qa_graph(
        service,
        in_chat=True,
        stream=True,
        finish_step=ChatFinishStep.GENERATE_CHART,
    )))

    assert calls == [invalid_sql, repaired_sql]
    assert service.saved_sql == [repaired_sql]
    assert service.executed[0]["sql"] == repaired_sql
    assert service.repair_contexts[0].reason is SqlRepairReason.DATABASE_SYNTAX_OR_DIALECT
    assert not any(event.get("error_type") == PERMISSION_DENIED_ERROR_TYPE for event in events)


def test_data_skill_violation_repairs_with_structured_context(monkeypatch: pytest.MonkeyPatch) -> None:
    invalid_sql = "SELECT legacy_amount FROM event WHERE event = 'LegacyEvent'"
    repaired_sql = "SELECT SUM(amount) FROM event WHERE event = 'AuthoritativeEvent'"
    service = FakeSmartQAService(sql_answer=_sql_answer(invalid_sql, ["event"]))
    service.repair_answers = [_sql_answer(repaired_sql, ["event"])]
    violation = llm.DataSkillSqlViolation(
        "口径错误",
        0,
        ("AuthoritativeEvent", "amount"),
        (),
        ("LegacyEvent", "legacy_amount"),
        (),
        (),
    )

    def check_sql(*, session, res, operate):
        assert session is not None
        assert operate == OperationEnum.GENERATE_SQL
        payload = json.loads(res)
        if payload["sql"] == invalid_sql:
            raise llm.DataSkillSqlValidationError(violation)
        return payload["sql"], payload.get("tables")

    service.check_sql = check_sql
    monkeypatch.setattr(
        graph,
        "validate_user_query_sql_or_raise",
        lambda **kwargs: (kwargs["sql"], {"event"}),
    )
    list(
        graph.run_smart_qa_graph(
            service,
            in_chat=True,
            stream=True,
            finish_step=ChatFinishStep.GENERATE_CHART,
        ),
    )

    assert service.repair_contexts[0].violation == violation
    assert service.saved_sql == [repaired_sql]


def test_prepare_sql_date_contract_error_repairs_then_revalidates(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid_sql = "SELECT dt, COUNT(*) FROM event GROUP BY dt"
    repaired_sql = (
        "SELECT dt, COUNT(*) FROM event "
        "WHERE dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}} "
        "GROUP BY dt"
    )
    service = FakeSmartQAService(sql_answer=_sql_answer(invalid_sql, ["event"]))
    service.repair_answers = [_sql_answer(repaired_sql, ["event"])]

    def check_sql(*, session, res, operate):
        assert session is not None
        assert operate == OperationEnum.GENERATE_SQL
        payload = json.loads(res)
        if payload["sql"] == invalid_sql:
            raise llm.ChatDateFilterConfigurationError("missing_parameters")
        return payload["sql"], payload.get("tables")

    service.check_sql = check_sql
    monkeypatch.setattr(
        graph,
        "validate_user_query_sql_or_raise",
        lambda **kwargs: (kwargs["sql"], {"event"}),
    )
    chunks = list(
        graph.run_smart_qa_graph(
            service,
            in_chat=True,
            stream=True,
            finish_step=ChatFinishStep.GENERATE_CHART,
        ),
    )

    assert service.repair_contexts[0].reason.value == "date_filter_configuration"
    assert service.saved_sql == [repaired_sql]
    assert not any(event["type"] == "error" for event in _events(chunks))


def test_prepare_sql_response_format_error_repairs_then_revalidates(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid_answer = "not-json"
    repaired_sql = "SELECT value FROM orders"
    service = FakeSmartQAService(sql_answer=invalid_answer)
    service.repair_answers = [_sql_answer(repaired_sql)]

    def check_sql(*, session, res, operate):
        assert session is not None
        assert operate == OperationEnum.GENERATE_SQL
        if res == invalid_answer:
            raise SingleMessageError("SQL answer is not a valid json object")
        payload = json.loads(res)
        return payload["sql"], payload.get("tables")

    service.check_sql = check_sql
    monkeypatch.setattr(
        graph,
        "validate_user_query_sql_or_raise",
        lambda **kwargs: (kwargs["sql"], {"orders"}),
    )

    chunks = list(
        graph.run_smart_qa_graph(
            service,
            in_chat=True,
            stream=True,
            finish_step=ChatFinishStep.GENERATE_CHART,
        ),
    )

    assert service.repair_contexts[0].reason.value == "sql_response_format"
    assert service.saved_sql == [repaired_sql]
    assert not any(event["type"] == "error" for event in _events(chunks))


@pytest.mark.parametrize(
    ("date_error", "invalid_payload", "repaired_payload"),
    [
        (
            "missing_parameters",
            {
                "sql": "SELECT dt, COUNT(*) FROM event GROUP BY dt",
                "chart_type": "line",
            },
            {
                "sql": (
                    "SELECT dt, COUNT(*) FROM event WHERE dt BETWEEN "
                    "{{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}} GROUP BY dt"
                ),
                "chart_type": "line",
                "date_filter": {
                    "time_field": "dt",
                    "date_parameter_type": "yyyymmdd_number",
                    "date_expression": {"version": 1, "mode": "preset", "preset": "past_7_days"},
                },
            },
        ),
        (
            "database_current_date",
            {
                "sql": "SELECT dt, COUNT(*) FROM event WHERE dt <= CURRENT_DATE GROUP BY dt",
                "chart_type": "line",
                "date_filter": {
                    "time_field": "dt",
                    "date_parameter_type": "yyyymmdd_number",
                    "date_expression": {"version": 1, "mode": "preset", "preset": "past_7_days"},
                },
            },
            {
                "sql": (
                    "SELECT dt, COUNT(*) FROM event WHERE dt BETWEEN "
                    "{{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}} GROUP BY dt"
                ),
                "chart_type": "line",
                "date_filter": {
                    "time_field": "dt",
                    "date_parameter_type": "yyyymmdd_number",
                    "date_expression": {"version": 1, "mode": "preset", "preset": "past_7_days"},
                },
            },
        ),
        (
            "realtime_requires_hourly_time_series",
            {
                "sql": "SELECT SUM(amount) FROM event_realtime",
                "chart_type": "metric",
            },
            {
                "sql": (
                    "SELECT hour_label, SUM(amount) FROM event_realtime "
                    "WHERE dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}} "
                    "GROUP BY hour_label"
                ),
                "chart_type": "line",
                "date_filter": {
                    "time_field": "dt",
                    "date_parameter_type": "yyyymmdd_number",
                    "date_expression": {"version": 1, "mode": "preset", "preset": "today"},
                },
            },
        ),
    ],
)
def test_prepare_sql_date_filter_error_repairs_then_revalidates(
        monkeypatch: pytest.MonkeyPatch,
        date_error: str,
        invalid_payload: dict[str, Any],
        repaired_payload: dict[str, Any],
) -> None:
    invalid_answer = json.dumps({"success": True, "tables": ["event"], **invalid_payload})
    repaired_answer = json.dumps({"success": True, "tables": ["event"], **repaired_payload})
    repaired_sql = repaired_payload["sql"]
    service = FakeSmartQAService(sql_answer=invalid_answer)
    service.repair_answers = [repaired_answer]
    service.render_chat_sql_for_execution = lambda sql: sql

    def check_sql(*, session, res, operate):
        assert session is not None
        assert operate == OperationEnum.GENERATE_SQL
        if res == invalid_answer:
            raise SingleMessageError(f"日期参数配置无效：{date_error}")
        payload = json.loads(res)
        service.chat_date_pivot = llm.normalize_chat_date_filter_for_question(
            service.chat_question.question,
            payload.get("date_filter"),
            payload["sql"],
            payload.get("chart_type") or "",
        )
        return payload["sql"], payload.get("tables")

    service.check_sql = check_sql
    monkeypatch.setattr(
        graph,
        "validate_user_query_sql_or_raise",
        lambda **kwargs: (kwargs["sql"], {"event"}),
    )
    chunks = list(
        graph.run_smart_qa_graph(
            service,
            in_chat=True,
            stream=True,
            finish_step=ChatFinishStep.GENERATE_CHART,
        ),
    )

    assert service.repair_contexts[0].reason.value == "date_filter_configuration"
    assert service.saved_sql == [repaired_sql]
    assert service.chat_date_pivot["time_field"] == "dt"
    assert "CURRENT_DATE" not in repaired_sql
    assert not any(event["type"] == "error" for event in _events(chunks))


def test_check_sql_structure_error_repairs_then_revalidates(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid_sql = "SELECT DATE_FORMAT(created_at, '%Y-%m-%d') FROM orders GROUP BY DATE_FORMAT(created_at, '%Y%m%d')"
    repaired_sql = "SELECT DATE_FORMAT(created_at, '%Y-%m-%d') FROM orders GROUP BY DATE_FORMAT(created_at, '%Y-%m-%d')"
    service = FakeSmartQAService(sql_answer=_sql_answer(invalid_sql))
    service.repair_answers = [_sql_answer(repaired_sql)]

    def check_sql(*, session, res, operate):
        assert session is not None
        assert operate == OperationEnum.GENERATE_SQL
        payload = json.loads(res)
        if payload["sql"] == invalid_sql:
            raise SqlStructureValidationError("DATE_FORMAT 投影与 GROUP BY 表达式不一致")
        return payload["sql"], payload.get("tables")

    service.check_sql = check_sql
    monkeypatch.setattr(
        graph,
        "validate_user_query_sql_or_raise",
        lambda **kwargs: (kwargs["sql"], {"orders"}),
    )
    chunks = list(
        graph.run_smart_qa_graph(
            service,
            in_chat=True,
            stream=True,
            finish_step=ChatFinishStep.GENERATE_CHART,
        ),
    )

    assert service.repair_contexts[0].reason.value == "database_syntax_or_dialect"
    assert service.saved_sql == [repaired_sql]
    assert service.executed[0]["sql"] == repaired_sql
    assert not any(event["type"] == "error" for event in _events(chunks))


def test_validate_sql_structure_error_repairs_then_revalidates(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid_sql = "SELECT DATE_FORMAT(created_at, '%Y-%m-%d') FROM orders GROUP BY DATE_FORMAT(created_at, '%Y%m%d')"
    repaired_sql = "SELECT DATE_FORMAT(created_at, '%Y-%m-%d') FROM orders GROUP BY DATE_FORMAT(created_at, '%Y-%m-%d')"
    service = FakeSmartQAService(sql_answer=_sql_answer(invalid_sql))
    service.repair_answers = [_sql_answer(repaired_sql)]
    validated_sql: list[str] = []

    def validate(**kwargs):
        validated_sql.append(kwargs["sql"])
        if kwargs["sql"] == invalid_sql:
            raise SqlStructureValidationError("DATE_FORMAT 投影与 GROUP BY 表达式不一致")
        return kwargs["sql"], {"orders"}

    monkeypatch.setattr(graph, "validate_user_query_sql_or_raise", validate)
    chunks = list(
        graph.run_smart_qa_graph(
            service,
            in_chat=True,
            stream=True,
            finish_step=ChatFinishStep.GENERATE_CHART,
        ),
    )

    assert validated_sql == [invalid_sql, repaired_sql]
    assert service.repair_contexts[0].reason.value == "database_syntax_or_dialect"
    assert service.saved_sql == [repaired_sql]
    assert service.executed[0]["sql"] == repaired_sql
    assert not any(event["type"] == "error" for event in _events(chunks))


def test_execute_sql_dialect_error_repairs_then_executes_again(monkeypatch: pytest.MonkeyPatch) -> None:
    invalid_sql = "WITH RECURSIVE days AS (SELECT 1 UNION ALL SELECT 2) SELECT * FROM days"
    repaired_sql = "WITH RECURSIVE days(day_value) AS (SELECT 1 UNION ALL SELECT 2) SELECT * FROM days"
    service = FakeSmartQAService(sql_answer=_sql_answer(invalid_sql))
    service.repair_answers = [_sql_answer(repaired_sql)]
    monkeypatch.setattr(
        graph,
        "validate_user_query_sql_or_raise",
        lambda **kwargs: (kwargs["sql"], {"orders"}),
    )
    attempts: list[str] = []

    def execute(**kwargs):
        attempts.append(kwargs["sql"])
        if kwargs["sql"] == invalid_sql:
            error = llm.AppDBError("query failed")
            raise error from RuntimeError("missing column aliases in recursive WITH query")
        return {"fields": ["day_value"], "data": [{"day_value": 1}]}

    service.execute_sql = execute
    service.check_save_chart = lambda **kwargs: json.loads(kwargs["res"])

    chunks = list(
        graph.run_smart_qa_graph(
            service,
            in_chat=True,
            stream=True,
            finish_step=ChatFinishStep.GENERATE_CHART,
        ),
    )

    assert attempts == [invalid_sql, repaired_sql]
    assert service.repair_contexts[0].reason.value == "database_syntax_or_dialect"
    assert not any(event["type"] == "error" for event in _events(chunks))


def test_date_dimension_cross_join_inside_scaffold_cte_is_accepted() -> None:
    data_skill = """
    <!-- data-skill-sql-validation: [{"match":["每日"],"when_sql_has_non_time_group_by":true,
    "required_outer_select_cross_join":true,"message":"需要日期维度骨架"}] -->
    """
    sql = """
    WITH date_spine(dt) AS (SELECT 1), dimensions(value) AS (SELECT 'a'),
    scaffold(dt, value) AS (
        SELECT d.dt, x.value FROM date_spine d CROSS JOIN dimensions x
    ), metrics AS (
        SELECT dt, value, COUNT(*) AS amount
        FROM events
        GROUP BY dt, value
    )
    SELECT s.dt, s.value, COALESCE(m.amount, 0) AS amount
    FROM scaffold s LEFT JOIN metrics m ON m.dt = s.dt AND m.value = s.value
    """

    assert llm._data_skill_sql_validation_violation("每日各分类趋势", sql, data_skill) is None


def test_same_failure_fingerprint_is_not_repaired_twice(monkeypatch: pytest.MonkeyPatch) -> None:
    invalid_sql = "SELECT CAST(value, AS DECIMAL(18, 4)) FROM orders"
    service = FakeSmartQAService(sql_answer=_sql_answer(invalid_sql))
    service.repair_answers = [_sql_answer(invalid_sql)]
    monkeypatch.setattr(
        graph,
        "validate_user_query_sql_or_raise",
        lambda **kwargs: (_ for _ in ()).throw(ValueError("Parse SQL Error: Expected TYPE")),
    )

    chunks = list(
        graph.run_smart_qa_graph(
            service,
            in_chat=True,
            stream=True,
            finish_step=ChatFinishStep.GENERATE_CHART,
        ),
    )

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

    chunks = list(
        graph.run_smart_qa_graph(
            service,
            in_chat=True,
            stream=True,
            finish_step=ChatFinishStep.GENERATE_CHART,
        ),
    )

    assert len(service.repair_contexts) == 2
    assert any(event["type"] == "error" for event in _events(chunks))


def test_execute_sql_repair_uses_user_visible_sql_and_logs_expanded_sql() -> None:
    user_visible_sql = "SELECT * FROM orders"
    real_execute_sql = "SELECT id, amount FROM public.orders"
    service = FakeSmartQAService(sql_answer=_sql_answer(user_visible_sql))

    def execute_sql(**_kwargs):
        raise RuntimeError("syntax error near expanded query")

    service.execute_sql = execute_sql
    state = {
        "service": service,
        "in_chat": True,
        "stream": True,
        "finish_step": ChatFinishStep.GENERATE_CHART,
        "json_result": {},
        "sql": user_visible_sql,
        "real_execute_sql": real_execute_sql,
        "execute_scope_sql": user_visible_sql,
        "execute_allowed_tables": ["orders"],
        "sql_repair_count": 0,
        "sql_repair_fingerprints": [],
    }

    update = graph._execute_sql(state)

    assert update["sql_repair_pending"] is True
    assert update["sql_repair_context"].failed_sql == user_visible_sql
    assert service.current_logs[OperationEnum.EXECUTE_SQL].messages["sql"] == real_execute_sql


@pytest.mark.parametrize(
    "execute_error",
    [
        AppDBConnectionError("database connection refused"),
        TimeoutError("query timeout"),
        RuntimeError("unexpected driver failure"),
    ],
)
def test_execute_sql_nonrepairable_errors_are_raised_without_repair(execute_error: Exception) -> None:
    service = FakeSmartQAService()
    service.execute_sql = lambda **kwargs: (_ for _ in ()).throw(execute_error)
    state = {
        "service": service,
        "in_chat": True,
        "stream": True,
        "finish_step": ChatFinishStep.GENERATE_CHART,
        "json_result": {},
        "sql": "SELECT value FROM orders",
        "real_execute_sql": "SELECT value FROM orders",
        "execute_scope_sql": "SELECT value FROM orders",
        "execute_allowed_tables": ["orders"],
        "sql_repair_count": 0,
        "sql_repair_fingerprints": [],
    }

    with pytest.raises(type(execute_error), match=str(execute_error)):
        graph._execute_sql(state)

    assert service.repair_contexts == []


def test_execute_sql_permission_denied_keeps_audit_and_failed_output(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeSmartQAService(sql_answer=_sql_answer("SELECT secret FROM orders"))
    audit_calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        graph,
        "validate_user_query_sql_or_raise",
        lambda **kwargs: (kwargs["sql"], {"orders"}),
    )
    monkeypatch.setattr(graph, "audit_permission_denied", lambda **kwargs: audit_calls.append(kwargs))
    service.execute_sql = lambda **kwargs: (_ for _ in ()).throw(
        RuntimeError("permission denied: restricted field"),
    )

    chunks = list(
        graph.run_smart_qa_graph(
            service,
            in_chat=True,
            stream=True,
            finish_step=ChatFinishStep.GENERATE_CHART,
        ),
    )
    events = _events(chunks)
    failed_event = next(event for event in events if event["type"] == "sql-data")

    assert audit_calls[0]["operation"] == "smart_qa.execute_sql_permission"
    assert service.saved_data[-1]["error_type"] == PERMISSION_DENIED_ERROR_TYPE
    assert failed_event["status"] == "failed"
    assert failed_event["error_type"] == PERMISSION_DENIED_ERROR_TYPE
    assert service.repair_contexts == []


def test_generate_sql_finish_step_stops_before_execute(monkeypatch: pytest.MonkeyPatch):
    """
    是什么：test_generate_sql_finish_step_stops_before_execute 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
    service = FakeSmartQAService(sql_answer=_sql_answer("select 1 as value"))
    monkeypatch.setattr(
        graph,
        "validate_user_query_sql_or_raise",
        lambda **kwargs: (kwargs["sql"], ["orders"]),
    )

    chunks = list(
        graph.run_smart_qa_graph(
            service,
            in_chat=True,
            stream=True,
            finish_step=ChatFinishStep.GENERATE_SQL,
        ),
    )
    events = _events(chunks)

    assert service.saved_sql == ["select 1 as value"]
    assert service.executed == []
    assert service.finished is True
    assert [event["type"] for event in events if event["type"] in {"sql", "finish"}] == ["sql", "finish"]
    assert not any(event["type"] == "sql-data" for event in events)
    assert not any(event["type"] == "chart" for event in events)


def test_graph_records_run_id_and_node_trace(monkeypatch: pytest.MonkeyPatch):
    """
    是什么：test_graph_records_run_id_and_node_trace 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
    service = FakeSmartQAService(sql_answer=_sql_answer("select 1 as value"))
    monkeypatch.setattr(
        graph,
        "validate_user_query_sql_or_raise",
        lambda **kwargs: (kwargs["sql"], ["orders"]),
    )

    list(
        graph.run_smart_qa_graph(
            service,
            in_chat=True,
            stream=True,
            finish_step=ChatFinishStep.QUERY_DATA,
        ),
    )

    trace = service._smart_qa_graph_trace
    assert service._smart_qa_graph_run_id.startswith("smartqa-9001-")
    assert service._smart_qa_graph_failed_node is None
    assert service._smart_qa_graph_error_type is None
    assert [entry["node"] for entry in trace] == [
        "prepare_context",
        "emit_record_metadata",
        "ensure_datasource",
        "execute_saas_skill",
        "generate_sql",
        "prepare_sql",
        "execute_sql",
    ]
    assert all(entry["status"] == "success" for entry in trace)
    assert all(isinstance(entry["duration_ms"], float) for entry in trace)
    assert trace[-1]["stop"] is True


def test_query_data_finish_step_stops_before_chart(monkeypatch: pytest.MonkeyPatch):
    """
    是什么：test_query_data_finish_step_stops_before_chart 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
    service = FakeSmartQAService(sql_answer=_sql_answer("select 1 as value"))
    monkeypatch.setattr(
        graph,
        "validate_user_query_sql_or_raise",
        lambda **kwargs: (kwargs["sql"], ["orders"]),
    )

    chunks = list(
        graph.run_smart_qa_graph(
            service,
            in_chat=True,
            stream=True,
            finish_step=ChatFinishStep.QUERY_DATA,
        ),
    )
    events = _events(chunks)

    assert service.saved_sql == ["select 1 as value"]
    assert len(service.executed) == 1
    assert service.saved_data == [{"fields": ["value"], "data": [{"value": 1}]}]
    assert service.finished is True
    assert [event["type"] for event in events if event["type"] in {"sql-data", "finish"}] == [
        "sql-data",
        "finish",
    ]
    assert not any(event["type"] == "chart-result" for event in events)
    assert not any(event["type"] == "chart" for event in events)


def test_sql_answer_message_is_streamed_as_plain_business_feedback(monkeypatch: pytest.MonkeyPatch):
    """
    是什么：test_sql_answer_message_is_streamed_as_plain_business_feedback 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：确认部分数据缺失提示不会变成错误卡片。
    """
    message = "当前数据源没有 pdau 埋点，已生成 DAU 部分。"
    service = FakeSmartQAService(
        sql_answer=_sql_answer_with_message("select 1 as value", message),
    )
    monkeypatch.setattr(
        graph,
        "validate_user_query_sql_or_raise",
        lambda **kwargs: (kwargs["sql"], ["orders"]),
    )

    chunks = list(
        graph.run_smart_qa_graph(
            service,
            in_chat=True,
            stream=True,
            finish_step=ChatFinishStep.QUERY_DATA,
        ),
    )
    events = _events(chunks)

    feedback_event = next(event for event in events if event["type"] == "analysis-result")
    saved_feedback = json.loads(service.saved_analysis[-1])
    assert feedback_event["content"] == message
    assert saved_feedback["content"] == message
    assert not any(event["type"] == "error" for event in events)
    assert service.saved_errors == []
    assert service.finished is True


def test_data_unavailable_execution_is_logged_but_not_streamed_as_error(monkeypatch: pytest.MonkeyPatch):
    """
    是什么：test_data_unavailable_execution_is_logged_but_not_streamed_as_error 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：确认缺表/缺字段执行失败会留日志，但用户侧看到普通业务提示。
    """
    message = "当前数据源缺少本次问题所需的表、字段或埋点数据：public.fact_events。"
    service = FakeSmartQAService(sql_answer=_sql_answer('select * from "public"."fact_events"'))
    monkeypatch.setattr(
        graph,
        "validate_user_query_sql_or_raise",
        lambda **kwargs: (kwargs["sql"], ["orders"]),
    )

    def _raise_data_unavailable(**kwargs):
        service.executed.append(kwargs)
        raise DataUnavailableError(message)

    service.execute_sql = _raise_data_unavailable

    chunks = list(
        graph.run_smart_qa_graph(
            service,
            in_chat=True,
            stream=True,
            finish_step=ChatFinishStep.GENERATE_CHART,
        ),
    )
    events = _events(chunks)
    feedback_event = next(event for event in events if event["type"] == "analysis-result")
    execute_log = service.current_logs[OperationEnum.EXECUTE_SQL]

    assert feedback_event["content"] == message
    assert execute_log.error is True
    assert execute_log.messages["error_type"] == "data_unavailable"
    assert execute_log.messages["message"] == message
    assert not any(event["type"] == "error" for event in events)
    assert not any(event["type"] == "chart" for event in events)
    assert service.repair_contexts == []
    assert service.saved_errors == []
    assert service.finished is True
    assert events[-1]["type"] == "finish"


def test_data_skill_schema_unavailable_is_streamed_as_business_feedback(monkeypatch: pytest.MonkeyPatch):
    """
    是什么：Data Skill 校验发现 schema 缺表时，应给用户普通业务提示，失败详情留在生成 SQL 日志。
    """
    service = FakeSmartQAService(sql_answer=_sql_answer("select * from fact_events"))
    schema_error = "Data Skill 要求使用 fact_sessions 表计算 DAU，但当前数据库 Schema 中不存在该表。"
    service.current_logs[OperationEnum.GENERATE_SQL] = SimpleNamespace(id=1, error=False)

    def _raise_schema_unavailable(*, session, res, operate):
        assert session is not None
        assert operate == OperationEnum.GENERATE_SQL
        service.current_logs[operate].error = True
        raise llm.DataSkillSqlValidationError(schema_error)

    service.check_sql = _raise_schema_unavailable
    monkeypatch.setattr(
        graph,
        "validate_user_query_sql_or_raise",
        lambda **kwargs: (kwargs["sql"], ["orders"]),
    )

    chunks = list(
        graph.run_smart_qa_graph(
            service,
            in_chat=True,
            stream=True,
            finish_step=ChatFinishStep.GENERATE_CHART,
        ),
    )
    events = _events(chunks)
    feedback_event = next(event for event in events if event["type"] == "analysis-result")
    sql_log = service.current_logs[OperationEnum.GENERATE_SQL]

    assert "当前数据源缺少本次问题所需的表、字段或埋点数据" in feedback_event["content"]
    assert sql_log.error is True
    assert service.saved_sql == []
    assert service.executed == []
    assert service.saved_errors == []
    assert service.finished is True
    assert events[-1]["type"] == "finish"
    assert not any(event["type"] == "error" for event in events)


def test_missing_event_value_is_pruned_and_streamed_as_business_notice(monkeypatch: pytest.MonkeyPatch):
    """
    是什么：埋点值本身不存在时，应保留可生成指标，裁掉对应 0 值指标，并给业务通知。
    """
    sql = _mixed_missing_event_sql()
    service = FakeSmartQAService(sql_answer=_sql_answer(sql, ["daily_metrics", "fact_events"]))
    captured_chart_result: dict[str, Any] = {}
    service.chart_chunks = [
        {
            "content": json.dumps({
                "type": "line",
                "title": "DAU 与 PDAU 趋势",
                "axis": {
                    "x": {"value": "日期"},
                    "y": [{"value": "DAU"}, {"value": "PDAU"}],
                },
            }),
            "reasoning_content": "",
        },
    ]

    def _execute_sql(**kwargs):
        service.executed.append(kwargs)
        assert "spaceship_upgrade_complete" not in kwargs["sql"]
        assert "missing_event" not in kwargs["sql"]
        assert "飞船升级完成触发用户数" not in kwargs["sql"]
        return {
            "fields": ["日期", "DAU", "PDAU"],
            "data": [
                {"日期": "2026-07-01", "DAU": 10, "PDAU": 2},
                {"日期": "2026-07-02", "DAU": 12, "PDAU": 3},
            ],
        }

    def _check_save_chart(*, session, res, result):
        captured_chart_result.update(result)
        return json.loads(res)

    service.execute_sql = _execute_sql
    service.check_save_chart = _check_save_chart
    monkeypatch.setattr(
        graph,
        "validate_user_query_sql_or_raise",
        lambda **kwargs: (kwargs["sql"], {"daily_metrics", "fact_events"}),
    )
    monkeypatch.setattr(
        graph,
        "_event_values_exist_in_datasource",
        lambda **kwargs: {
            value: value != "spaceship_upgrade_complete"
            for value in kwargs["event_values"]
        },
    )

    chunks = list(
        graph.run_smart_qa_graph(
            service,
            in_chat=True,
            stream=True,
            finish_step=ChatFinishStep.GENERATE_CHART,
        ),
    )
    events = _events(chunks)
    feedback_event = next(event for event in events if event["type"] == "analysis-result")
    saved_feedback = json.loads(service.saved_analysis[-1])

    assert len(service.executed) == 1
    assert service.saved_sql[-1] == service.executed[0]["sql"]
    assert service.saved_data[-1]["fields"] == ["日期", "DAU", "PDAU"]
    assert all("飞船升级完成触发用户数" not in row for row in service.saved_data[-1]["data"])
    assert captured_chart_result["fields"] == ["日期", "DAU", "PDAU"]
    assert feedback_event["notice"]["reason"] == "missing_event"
    assert feedback_event["notice"]["items"] == ["spaceship_upgrade_complete"]
    assert saved_feedback["notice"]["notice_type"] == "data_scope_gap"
    assert "已生成其余可支持的结果" in feedback_event["content"]
    assert not any(event["type"] == "error" for event in events)
    assert any(event["type"] == "chart" for event in events)
    assert service.finished is True


def test_schema_qualified_missing_event_cte_prunes_outer_coalesce_field(monkeypatch: pytest.MonkeyPatch):
    """
    是什么：带 schema、CTE、LEFT JOIN、COALESCE 的 SQL，也要能裁掉不存在埋点的外层展示字段。
    """
    service = FakeSmartQAService()
    service.ds.type = "pg"
    result = {
        "fields": ["日期", "DAU", "PDAU", "飞船升级完成触发用户数"],
        "data": [
            {"日期": "2026-07-01", "DAU": 10, "PDAU": 2, "飞船升级完成触发用户数": 0},
            {"日期": "2026-07-02", "DAU": 12, "PDAU": 3, "飞船升级完成触发用户数": 0},
        ],
    }
    monkeypatch.setattr(
        graph,
        "_event_values_exist_in_datasource",
        lambda **kwargs: {
            value: value != "spaceship_upgrade_complete"
            for value in kwargs["event_values"]
        },
    )

    cleanup = graph._cleanup_missing_event_result(service, _schema_qualified_missing_event_sql(), result)

    assert cleanup.missing_events == ["spaceship_upgrade_complete"]
    assert cleanup.removed_fields == ["飞船升级完成触发用户数"]
    assert cleanup.result["fields"] == ["日期", "DAU", "PDAU"]
    assert all("飞船升级完成触发用户数" not in row for row in cleanup.result["data"])


def test_schema_qualified_missing_event_is_rewritten_before_execute(monkeypatch: pytest.MonkeyPatch):
    """
    是什么：缺失埋点应在 SQL 准备阶段被移出最终执行 SQL，而不是执行后只裁图表字段。
    """
    sql = _schema_qualified_missing_event_sql()
    service = FakeSmartQAService(sql_answer=_sql_answer(sql, ["fact_sessions", "fact_payments", "fact_events"]))
    service.ds.type = "pg"
    service.table_name_list = ["fact_sessions", "fact_payments", "fact_events"]
    captured_chart_result: dict[str, Any] = {}
    service.chart_chunks = [
        {
            "content": json.dumps({
                "type": "line",
                "title": "DAU 与 PDAU 趋势",
                "axis": {
                    "x": {"value": "日期"},
                    "y": [{"value": "DAU"}, {"value": "PDAU"}],
                },
            }),
            "reasoning_content": "",
        },
    ]

    def _execute_sql(**kwargs):
        service.executed.append(kwargs)
        assert "spaceship_upgrade_complete" not in kwargs["sql"]
        assert "spaceship_upgrade" not in kwargs["sql"]
        assert "飞船升级完成触发用户数" not in kwargs["sql"]
        assert "DAU" in kwargs["sql"]
        assert "PDAU" in kwargs["sql"]
        return {
            "fields": ["日期", "DAU", "PDAU"],
            "data": [
                {"日期": "2026-07-01", "DAU": 10, "PDAU": 2},
                {"日期": "2026-07-02", "DAU": 12, "PDAU": 3},
            ],
        }

    def _check_save_chart(*, session, res, result):
        captured_chart_result.update(result)
        return json.loads(res)

    service.execute_sql = _execute_sql
    service.check_save_chart = _check_save_chart
    validated_sql: list[str] = []

    def _validate(**kwargs):
        validated_sql.append(kwargs["sql"])
        return kwargs["sql"], {"fact_sessions", "fact_payments", "fact_events"}

    monkeypatch.setattr(graph, "validate_user_query_sql_or_raise", _validate)
    monkeypatch.setattr(
        graph,
        "_event_values_exist_in_datasource",
        lambda **kwargs: {
            value: value != "spaceship_upgrade_complete"
            for value in kwargs["event_values"]
        },
    )

    chunks = list(
        graph.run_smart_qa_graph(
            service,
            in_chat=True,
            stream=True,
            finish_step=ChatFinishStep.GENERATE_CHART,
        ),
    )
    events = _events(chunks)
    feedback_event = next(event for event in events if event["type"] == "analysis-result")

    assert len(validated_sql) == 2
    assert "spaceship_upgrade_complete" in validated_sql[0]
    assert "spaceship_upgrade_complete" not in validated_sql[1]
    assert service.saved_sql[-1] == service.executed[0]["sql"]
    assert service.saved_data[-1]["fields"] == ["日期", "DAU", "PDAU"]
    assert captured_chart_result["fields"] == ["日期", "DAU", "PDAU"]
    assert feedback_event["notice"]["items"] == ["spaceship_upgrade_complete"]
    assert feedback_event["notice"]["removed_fields"] == ["飞船升级完成触发用户数"]
    assert not any(event["type"] == "error" for event in events)
    assert service.finished is True


def test_only_missing_event_metric_stops_without_zero_chart(monkeypatch: pytest.MonkeyPatch):
    """
    是什么：只统计不存在埋点时，应直接提示缺少埋点，不能把聚合 0 展示成有效图表。
    """
    sql = _direct_missing_event_metric_sql()
    service = FakeSmartQAService(sql_answer=_sql_answer(sql, ["fact_sessions", "fact_events"]))
    service.ds.type = "pg"
    service.table_name_list = ["fact_sessions", "fact_events"]

    monkeypatch.setattr(
        graph,
        "validate_user_query_sql_or_raise",
        lambda **kwargs: (kwargs["sql"], {"fact_sessions", "fact_events"}),
    )
    monkeypatch.setattr(
        graph,
        "_event_values_exist_in_datasource",
        lambda **kwargs: {
            value: value != "dragon_summon_success"
            for value in kwargs["event_values"]
        },
    )

    chunks = list(
        graph.run_smart_qa_graph(
            service,
            in_chat=True,
            stream=True,
            finish_step=ChatFinishStep.GENERATE_CHART,
        ),
    )
    events = _events(chunks)
    feedback_event = next(event for event in events if event["type"] == "analysis-result")
    event_types = [event["type"] for event in events]

    assert service.saved_sql == []
    assert service.executed == []
    assert service.chart_generated is False
    assert "sql-data" not in event_types
    assert "chart" not in event_types
    assert event_types[-1] == "finish"
    assert feedback_event["notice"]["reason"] == "missing_event"
    assert feedback_event["notice"]["items"] == ["dragon_summon_success"]
    assert feedback_event["notice"]["removed_fields"] == []
    assert feedback_event["content"] == "当前数据源缺少 dragon_summon_success 埋点数据。"
    assert service.finished is True


def test_existing_event_zero_values_are_not_pruned(monkeypatch: pytest.MonkeyPatch):
    """
    是什么：埋点存在但当前窗口为 0 时，应保留 0 值指标。
    """
    sql = _mixed_missing_event_sql()
    service = FakeSmartQAService(sql_answer=_sql_answer(sql, ["daily_metrics", "fact_events"]))
    captured_chart_result: dict[str, Any] = {}
    service.chart_chunks = [
        {
            "content": json.dumps({
                "type": "line",
                "title": "DAU、PDAU 与事件趋势",
                "axis": {
                    "x": {"value": "日期"},
                    "y": [
                        {"value": "DAU"},
                        {"value": "PDAU"},
                        {"value": "飞船升级完成触发用户数"},
                    ],
                },
            }),
            "reasoning_content": "",
        },
    ]

    def _execute_sql(**kwargs):
        service.executed.append(kwargs)
        return {
            "fields": ["日期", "DAU", "PDAU", "飞船升级完成触发用户数"],
            "data": [
                {"日期": "2026-07-01", "DAU": 10, "PDAU": 2, "飞船升级完成触发用户数": 0},
            ],
        }

    def _check_save_chart(*, session, res, result):
        captured_chart_result.update(result)
        return json.loads(res)

    service.execute_sql = _execute_sql
    service.check_save_chart = _check_save_chart
    monkeypatch.setattr(
        graph,
        "validate_user_query_sql_or_raise",
        lambda **kwargs: (kwargs["sql"], {"daily_metrics", "fact_events"}),
    )
    monkeypatch.setattr(
        graph,
        "_event_values_exist_in_datasource",
        lambda **kwargs: {value: True for value in kwargs["event_values"]},
    )

    chunks = list(
        graph.run_smart_qa_graph(
            service,
            in_chat=True,
            stream=True,
            finish_step=ChatFinishStep.GENERATE_CHART,
        ),
    )
    events = _events(chunks)

    assert service.saved_data[-1]["fields"] == ["日期", "DAU", "PDAU", "飞船升级完成触发用户数"]
    assert captured_chart_result["fields"] == ["日期", "DAU", "PDAU", "飞船升级完成触发用户数"]
    assert not any(event["type"] == "analysis-result" and event.get("notice") for event in events)
    assert not any(event["type"] == "error" for event in events)
    assert service.finished is True


def test_event_availability_checks_values_in_batches(monkeypatch: pytest.MonkeyPatch):
    """
    是什么：同一表字段上的多个埋点值应批量查询，避免逐值往返数据库。
    """
    sql = """
    SELECT event_name, count(*) AS cnt
    FROM fact_events
    WHERE event_name IN ('event_a', 'event_b')
    GROUP BY event_name
    """
    service = FakeSmartQAService()
    calls: list[set[str]] = []

    def _batch_exists(**kwargs):
        calls.append(set(kwargs["event_values"]))
        return {"event_a": True, "event_b": False}

    monkeypatch.setattr(graph, "_event_values_exist_in_datasource", _batch_exists)

    availability = graph._event_availability_for_sql(service, sql)

    assert len(calls) == 1
    assert calls[0] == {"event_a", "event_b"}
    assert availability[0].existing_values == {"event_a"}
    assert availability[0].missing_values == {"event_b"}


def test_event_availability_trusts_configured_tracking_events(monkeypatch: pytest.MonkeyPatch):
    """
    是什么：工作空间事件字典已声明的事件值不再额外扫物理事件表确认。
    """
    sql = "SELECT count(*) AS cnt FROM event WHERE event = 'UserRegister'"
    service = FakeSmartQAService()
    service.ds = SimpleNamespace(id=3, type="mysql", type_name="MySQL")
    service.chat_question.tracking_config = '''
    - 默认事件名字段: `event`
    ## 事件名映射
    [{"events":["UserRegister"],"metric":"new_user_registration"}]
    '''

    def _should_not_probe(**kwargs):
        raise AssertionError("configured events should not query datasource")

    monkeypatch.setattr(graph, "get_session", _should_not_probe)

    availability = graph._event_availability_for_sql(service, sql)

    assert availability[0].existing_values == {"UserRegister"}
    assert availability[0].missing_values == set()
    assert availability[0].unknown_values == set()


def test_event_availability_trusts_event_name_tracking_mapping(monkeypatch: pytest.MonkeyPatch):
    """
    是什么：当前事件字典使用 event_name 单事件映射时，也应直接视为已确认事件。
    """
    sql = "SELECT count(*) AS cnt FROM event WHERE event = 'UserActive'"
    service = FakeSmartQAService()
    service.ds = SimpleNamespace(id=6, type="mysql", type_name="MySQL")
    service.chat_question.tracking_config = '''
    - 默认事件名字段: `event`
    ## 事件名映射
    [{"event_name":"UserActive","event_display_name":"当日活跃"}]
    '''

    def _should_not_probe(**kwargs):
        raise AssertionError("configured events should not query datasource")

    monkeypatch.setattr(graph, "get_session", _should_not_probe)

    availability = graph._event_availability_for_sql(service, sql)

    assert availability[0].existing_values == {"UserActive"}
    assert availability[0].missing_values == set()
    assert availability[0].unknown_values == set()


def test_unknown_event_policy_can_be_conservative_or_strict(monkeypatch: pytest.MonkeyPatch):
    """
    是什么：埋点存在性查询失败时，默认进入 unknown；strict 策略下按 missing 处理。
    """
    sql = "SELECT count(*) AS cnt FROM fact_events WHERE event_name = 'event_unknown'"
    service = FakeSmartQAService()
    monkeypatch.setattr(
        graph,
        "_event_values_exist_in_datasource",
        lambda **kwargs: {value: None for value in kwargs["event_values"]},
    )

    monkeypatch.setattr(graph.settings, "SMART_QA_EVENT_UNKNOWN_POLICY", "conservative")
    conservative = graph._event_availability_for_sql(service, sql)[0]
    assert conservative.unknown_values == {"event_unknown"}
    assert conservative.missing_values == set()

    monkeypatch.setattr(graph.settings, "SMART_QA_EVENT_UNKNOWN_POLICY", "strict")
    strict = graph._event_availability_for_sql(service, sql)[0]
    assert strict.unknown_values == set()
    assert strict.missing_values == {"event_unknown"}


def test_empty_sql_result_finishes_without_chart(monkeypatch: pytest.MonkeyPatch):
    """
    是什么：SQL 正常执行但没有返回数据时，应提示无数据并跳过图表生成。
    """
    service = FakeSmartQAService(sql_answer=_sql_answer("select value from orders where 1 = 0"))

    def _execute_sql(**kwargs):
        service.executed.append(kwargs)
        return {"fields": ["value"], "data": []}

    service.execute_sql = _execute_sql
    monkeypatch.setattr(
        graph,
        "validate_user_query_sql_or_raise",
        lambda **kwargs: (kwargs["sql"], ["orders"]),
    )
    captured_log_message: dict[str, Any] = {}

    def _end_log(**kwargs):
        captured_log_message.update(kwargs["full_message"])
        log = kwargs["log"]
        log.messages = kwargs["full_message"]
        return log

    monkeypatch.setattr(graph, "end_log", _end_log)

    chunks = list(
        graph.run_smart_qa_graph(
            service,
            in_chat=True,
            stream=True,
            finish_step=ChatFinishStep.GENERATE_CHART,
        ),
    )
    events = _events(chunks)
    feedback_event = next(event for event in events if event["type"] == "analysis-result")
    event_types = [event["type"] for event in events]

    assert len(service.executed) == 1
    assert service.saved_data[-1] == {"fields": ["value"], "data": []}
    assert service.chart_generated is False
    assert "chart" not in event_types
    assert event_types[-1] == "finish"
    assert feedback_event["notice"]["reason"] == "data_unavailable"
    assert "没有可展示的数据" in feedback_event["content"]
    assert captured_log_message["business_notice"]["reason"] == "data_unavailable"
    assert service.finished is True


def test_permission_denied_during_sql_validation_stops_graph(monkeypatch: pytest.MonkeyPatch):
    """
    是什么：test_permission_denied_during_sql_validation_stops_graph 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
    service = FakeSmartQAService(sql_answer=_sql_answer("select secret from orders"))

    def _deny_query(**kwargs):
        """
        是什么：_deny_query 是一段测试代码，用来确认测试的某个场景没有问题。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：把测试里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        assert kwargs["sql"] == "select secret from orders"
        raise Exception("permission denied: allowed tables")

    monkeypatch.setattr(graph, "validate_user_query_sql_or_raise", _deny_query)

    chunks = list(
        graph.run_smart_qa_graph(
            service,
            in_chat=True,
            stream=True,
            finish_step=ChatFinishStep.GENERATE_CHART,
        ),
    )
    events = _events(chunks)
    event_types = [event["type"] for event in events]
    sql_data_event = next(event for event in events if event["type"] == "sql-data")

    assert service.saved_sql == ["select secret from orders"]
    assert service.saved_data and service.saved_data[-1]["error_type"] == PERMISSION_DENIED_ERROR_TYPE
    assert service.executed == []
    assert service.finished is True
    assert sql_data_event["status"] == "failed"
    assert sql_data_event["error_type"] == PERMISSION_DENIED_ERROR_TYPE
    assert event_types[-1] == "finish"
    assert "chart" not in event_types


def test_single_message_error_is_saved_and_streamed(monkeypatch: pytest.MonkeyPatch):
    """
    是什么：test_single_message_error_is_saved_and_streamed 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
    service = FakeSmartQAService(sql_answer='{"success": false, "message": "forced"}')

    def _raise_single_message(*, session, res, operate):
        """
        是什么：_raise_single_message 是一段测试代码，用来确认测试的某个场景没有问题。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：把测试里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        assert session is not None
        assert res == '{"success": false, "message": "forced"}'
        assert operate == OperationEnum.GENERATE_SQL
        raise SingleMessageError("forced invalid sql")

    service.check_sql = _raise_single_message
    monkeypatch.setattr(
        graph,
        "validate_user_query_sql_or_raise",
        lambda **kwargs: (kwargs["sql"], ["orders"]),
    )

    chunks = list(
        graph.run_smart_qa_graph(
            service,
            in_chat=True,
            stream=True,
            finish_step=ChatFinishStep.GENERATE_CHART,
        ),
    )
    events = _events(chunks)
    error_event = next(event for event in events if event["type"] == "error")

    assert service.saved_sql == []
    assert service.executed == []
    assert service.saved_errors == ["forced invalid sql"]
    assert service.finished is True
    assert service._smart_qa_graph_failed_node == "prepare_sql"
    assert service._smart_qa_graph_error_type == "single_message"
    assert service._smart_qa_graph_trace[-1]["node"] == "prepare_sql"
    assert service._smart_qa_graph_trace[-1]["status"] == "error"
    assert error_event["content"] == "forced invalid sql"
    assert not any(event["type"] == "finish" for event in events)


def test_dynamic_assistant_datasource_executes_expanded_sql():
    """
    是什么：test_dynamic_assistant_datasource_executes_expanded_sql 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
    sql_answer = _sql_answer("select * from orders", ["orders"])
    service = FakeSmartQAService(
        current_assistant=SimpleNamespace(type=1),
        sql_answer=sql_answer,
    )

    def _dynamic_sql(session, sql, tables):
        """
        是什么：_dynamic_sql 是一段测试代码，用来确认测试的某个场景没有问题。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：把测试里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        assert session is not None
        assert sql == "select * from orders"
        assert tables == ["orders"]
        return {
            "orders": "select id, amount from public.orders",
            "app_temp_sql_text": _sql_answer("select * from app_dynamic_temp_table_orders", ["orders"]),
        }

    def _check_save_sql(*, session, res, operate):
        """
        是什么：_check_save_sql 是一段测试代码，用来确认测试的某个场景没有问题。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：检查测试里的数据、权限或配置是否合法，不对就及时拦住。
        """
        assert session is not None
        assert operate == OperationEnum.GENERATE_DYNAMIC_SQL
        assert json.loads(res)["sql"] == "select * from app_dynamic_temp_table_orders"
        return "select * from app_dynamic_temp_table_orders"

    service.generate_assistant_dynamic_sql = _dynamic_sql
    service.check_save_sql = _check_save_sql

    chunks = list(
        graph.run_smart_qa_graph(
            service,
            in_chat=True,
            stream=True,
            finish_step=ChatFinishStep.QUERY_DATA,
        ),
    )
    events = _events(chunks)

    assert len(service.executed) == 1
    assert service.executed[0]["sql"] == "select id, amount from public.orders"
    assert service.executed[0]["scope_sql"] == "select * from app_dynamic_temp_table_orders"
    assert service.executed[0]["scope_allowed_tables"] == ["app_dynamic_temp_table_orders"]
    assert service.finished is True
    assert [event["type"] for event in events if event["type"] in {"sql-data", "finish"}] == [
        "sql-data",
        "finish",
    ]
    assert not any(event["type"] == "chart" for event in events)


def test_dynamic_sql_date_filter_error_repairs_then_revalidates():
    sql_answer = _sql_answer("select * from orders", ["orders"])
    service = FakeSmartQAService(
        current_assistant=SimpleNamespace(type=1),
        sql_answer=sql_answer,
    )
    service.repair_answers = [sql_answer]
    checks = 0

    def _dynamic_sql(session, sql, tables):
        return {
            "orders": "select id, amount from public.orders",
            "app_temp_sql_text": _sql_answer(
                "select * from app_dynamic_temp_table_orders", ["orders"]
            ),
        }

    def _check_save_sql(*, session, res, operate):
        nonlocal checks
        checks += 1
        if checks == 1:
            raise SingleMessageError("日期参数配置无效：missing_date_filter")
        return "select * from app_dynamic_temp_table_orders"

    service.generate_assistant_dynamic_sql = _dynamic_sql
    service.check_save_sql = _check_save_sql

    chunks = list(
        graph.run_smart_qa_graph(
            service,
            in_chat=True,
            stream=True,
            finish_step=ChatFinishStep.QUERY_DATA,
        ),
    )

    assert checks == 2
    assert service.repair_contexts[0].reason is SqlRepairReason.DATE_FILTER_CONFIGURATION
    assert len(service.executed) == 1
    assert not any(event["type"] == "error" for event in _events(chunks))


def test_non_chat_stream_query_data_returns_markdown(monkeypatch: pytest.MonkeyPatch):
    """
    是什么：test_non_chat_stream_query_data_returns_markdown 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
    service = FakeSmartQAService(sql_answer=_sql_answer("select 1 as value"))
    monkeypatch.setattr(
        graph,
        "validate_user_query_sql_or_raise",
        lambda **kwargs: (kwargs["sql"], ["orders"]),
    )

    chunks = list(
        graph.run_smart_qa_graph(
            service,
            in_chat=False,
            stream=True,
            finish_step=ChatFinishStep.QUERY_DATA,
        ),
    )

    assert service.finished is True
    assert service.chart_generated is False
    assert any("```sql" in chunk and "select 1 as value" in chunk for chunk in chunks)
    assert any("| value" in chunk and "\u200b1" in chunk for chunk in chunks)


def test_non_stream_full_chart_returns_json_result(monkeypatch: pytest.MonkeyPatch):
    """
    是什么：test_non_stream_full_chart_returns_json_result 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
    service = FakeSmartQAService(sql_answer=_sql_answer("select 1 as value"))
    monkeypatch.setattr(
        graph,
        "validate_user_query_sql_or_raise",
        lambda **kwargs: (kwargs["sql"], ["orders"]),
    )
    monkeypatch.setattr(
        graph,
        "get_chat_chart_data",
        lambda session, record_id: {"fields": ["value"], "data": [{"value": 1}]},
    )
    chunks = list(
        graph.run_smart_qa_graph(
            service,
            in_chat=False,
            stream=False,
            finish_step=ChatFinishStep.GENERATE_CHART,
            return_img=False,
        ),
    )

    assert service.finished is True
    assert service.chart_generated is True
    assert chunks == [
        {
            "success": True,
            "record_id": 9001,
            "sql": "select 1 as value",
            "data": {"fields": ["value"], "data": [{"value": 1}]},
            "chart": {"type": "table", "title": "Result", "columns": [{"value": "value"}]},
        }
    ]


def test_chart_generation_tolerates_reasoning_only_chunk(monkeypatch: pytest.MonkeyPatch):
    """
    是什么：test_chart_generation_tolerates_reasoning_only_chunk 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
    service = FakeSmartQAService(sql_answer=_sql_answer("select 1 as value"))
    service.chart_chunks = [
        {"content": None, "reasoning_content": "thinking chart"},
        {"content": '{"type":"table","title":"Result","columns":[{"value":"value"}]}', "reasoning_content": ""},
    ]
    monkeypatch.setattr(
        graph,
        "validate_user_query_sql_or_raise",
        lambda **kwargs: (kwargs["sql"], ["orders"]),
    )
    chunks = list(
        graph.run_smart_qa_graph(
            service,
            in_chat=True,
            stream=True,
            finish_step=ChatFinishStep.GENERATE_CHART,
        ),
    )
    events = _events(chunks)
    chart_result_events = [event for event in events if event["type"] == "chart-result"]

    assert service.chart_generated is True
    assert chart_result_events[0]["content"] == ""
    assert chart_result_events[0]["reasoning_content"] == "thinking chart"
    assert any(event["type"] == "chart" for event in events)
    assert events[-1]["type"] == "finish"


def test_choose_table_schema_uses_business_context_without_sample_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    是什么：Smart Q&A 生成 SQL 前的结构识别走 AI 字典 schema，不再通过样例数据探测物理库。
    """
    service = llm.LLMService.__new__(llm.LLMService)
    service.record = SimpleNamespace(id=9001)
    service.current_user = SimpleNamespace(id=1, tenant_id=2001)
    service.ds = SimpleNamespace(id=2)
    service.out_ds_instance = None
    service.chat_question = SimpleNamespace(question="次日 LTV", db_schema="", sample_data="old sample")
    service.current_logs = {}

    monkeypatch.setattr(llm, "start_log", lambda **kwargs: SimpleNamespace(id=1))
    monkeypatch.setattr(llm, "end_log", lambda **kwargs: kwargs["log"])
    context = SimpleNamespace(
        schema="【AI schema source】workspace data dictionary\n# Table: user\n[(pay.pay2:number)]",
        allowed_tables=["user"],
    )

    def _load_context(*_args, **_kwargs):
        service.chat_question.db_schema = context.schema
        return context

    service.load_business_sql_context = _load_context

    def _should_not_probe_sample_data(*_args, **_kwargs):
        raise AssertionError("choose_table_schema should not query sample data")

    monkeypatch.setattr(llm, "get_tables_sample_data", _should_not_probe_sample_data, raising=False)

    tables = service.choose_table_schema(object())

    assert tables == ["user"]
    assert service.chat_question.db_schema.startswith("【AI schema source】workspace data dictionary")
    assert service.chat_question.sample_data == ""


def test_choose_table_schema_rejects_missing_business_context(monkeypatch: pytest.MonkeyPatch) -> None:
    service = llm.LLMService.__new__(llm.LLMService)
    service.record = SimpleNamespace(id=9001)
    service.current_user = SimpleNamespace(id=1, tenant_id=2001)
    service.ds = SimpleNamespace(id=2)
    service.out_ds_instance = None
    service.chat_question = SimpleNamespace(question="次日 LTV", db_schema="", sample_data="")
    service.current_logs = {}
    service.load_business_sql_context = lambda *_args, **_kwargs: None

    monkeypatch.setattr(llm, "start_log", lambda **kwargs: SimpleNamespace(id=1))

    with pytest.raises(DataUnavailableError) as exc_info:
        service.choose_table_schema(object())

    assert str(exc_info.value) == llm.BUSINESS_SQL_CONTEXT_UNAVAILABLE_MESSAGE


def test_generate_chart_rejects_service_without_business_context() -> None:
    service = FakeSmartQAService()
    service.business_sql_context = None
    state = {
        "service": service,
        "in_chat": False,
        "stream": False,
        "return_img": False,
        "json_result": {},
        "result": {"fields": ["value"], "data": [{"value": 1}]},
        "tables": ["orders"],
        "chart_type": "table",
    }

    with pytest.raises(DataUnavailableError) as exc_info:
        graph._generate_chart(state)

    assert str(exc_info.value) == graph.BUSINESS_SQL_CONTEXT_UNAVAILABLE_MESSAGE


def test_generate_chart_preserves_external_datasource_schema_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[int, str, bool, list[str] | None]] = []

    class _ExternalDatasource:
        def get_db_schema(self, ds_id, question, embedding=True, table_list=None):
            calls.append((ds_id, question, embedding, table_list))
            return "table orders(value numeric)", ["orders"]

    service = FakeSmartQAService()
    service.out_ds_instance = _ExternalDatasource()
    monkeypatch.setattr(graph, "_emit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(graph, "emit_chart_image", lambda *_args, **_kwargs: None)
    state = {
        "service": service,
        "in_chat": False,
        "stream": False,
        "return_img": False,
        "json_result": {},
        "result": {"fields": ["value"], "data": [{"value": 1}]},
        "tables": ["orders"],
        "chart_type": "table",
    }

    graph._generate_chart(state)

    assert calls == [(1, "test question", False, ["orders"])]


def test_llm_service_routes_smart_qa_to_graph(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    是什么：test_llm_service_routes_smart_qa_to_graph 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
    """
    service = llm.LLMService.__new__(llm.LLMService)
    service.record = SimpleNamespace(id=8001)
    calls: list[dict[str, Any]] = []

    def _fake_graph(service_arg, *, in_chat: bool, stream: bool, finish_step: ChatFinishStep, return_img: bool):
        """
        是什么：_fake_graph 是一段测试代码，用来确认测试的某个场景没有问题。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：把测试里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        calls.append(
            {
                "service": service_arg,
                "in_chat": in_chat,
                "stream": stream,
                "finish_step": finish_step,
                "return_img": return_img,
            }
        )
        yield "graph-result"

    monkeypatch.setattr(graph, "run_smart_qa_graph", _fake_graph)

    assert list(
        service.run_task(
            in_chat=False,
            stream=False,
            finish_step=ChatFinishStep.QUERY_DATA,
            return_img=False,
        )
    ) == ["graph-result"]
    assert calls == [
        {
            "service": service,
            "in_chat": False,
            "stream": False,
            "finish_step": ChatFinishStep.QUERY_DATA,
            "return_img": False,
        },
    ]
