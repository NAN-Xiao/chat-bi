"""
脚本说明：验证 SQL Engine 统一业务库上下文。
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from apps.chat.curd.custom_prompt import CustomPromptTargetScopeEnum
from apps.datasource.crud import sql_engine, sql_engine_executor
from apps.system.crud.tracking_expression import compile_tracking_json_expression


class _Session:
    def get(self, model, obj_id):
        if getattr(model, "__name__", "") == "CoreDatasource":
            return SimpleNamespace(
                id=obj_id,
                name="业务库",
                type="postgresql",
                type_name="PostgreSQL",
            )
        return None


def test_business_sql_context_collects_schema_dictionary_skills_and_dialect(monkeypatch):
    """
    是什么：统一上下文一次性提供 Agent 生成 SQL 所需的业务库信息。
    """
    calls = []

    monkeypatch.setattr(sql_engine, "has_datasource_access", lambda *_args, **_kwargs: True)

    def _schema(**kwargs):
        calls.append(("schema", kwargs["ds"].id, kwargs["question"], kwargs.get("data_skill_text")))
        return "【Schema】\n# Table: event\n[(event_name:text)]\n", ["event"]

    def _skills(*args, **kwargs):
        calls.append(("skills", args[1], args[2], kwargs.get("question")))
        return "<Data-Skills>口径</Data-Skills>", ["口径"], 99

    def _tracking(_session, tenant_id, datasource_id, **kwargs):
        calls.append((
            "tracking",
            tenant_id,
            datasource_id,
            kwargs.get("datasource_type"),
            kwargs.get("question"),
            kwargs.get("data_skill_text"),
        ))
        return "<Tracking>事件字典</Tracking>", ["schema校验: ok"]

    monkeypatch.setattr(sql_engine, "get_ai_table_schema", _schema)
    monkeypatch.setattr(sql_engine, "find_data_skills", _skills)
    monkeypatch.setattr(sql_engine, "find_tracking_prompt_context", _tracking)

    context = sql_engine.BusinessSqlContextService.build(
        session=_Session(),
        current_user=SimpleNamespace(id=1001),
        tenant_id=2001,
        datasource_id=1,
        question="看登录人数",
        target_scope=CustomPromptTargetScopeEnum.SMART_QA,
        data_skill_id=None,
        embedding=False,
    )

    assert context.datasource_id == 1
    assert context.sql_dialect == "postgres"
    assert context.schema.startswith("【Schema】")
    assert context.allowed_tables == ["event"]
    assert context.data_skill == "<Data-Skills>口径</Data-Skills>"
    assert context.tracking_config == "<Tracking>事件字典</Tracking>"
    assert context.warnings == ["ok"]
    assert context.business_context_hash
    assert "事件字典" in context.semantic_context
    snapshot = context.snapshot_metadata()
    assert snapshot["datasource_id"] == "1"
    assert snapshot["sql_dialect"] == "postgres"
    assert snapshot["allowed_tables"] == ["event"]
    assert snapshot["tracking_warnings"] == ["ok"]
    assert snapshot["data_skill_count"] == 1
    assert calls == [
        ("skills", 1, CustomPromptTargetScopeEnum.SMART_QA, "看登录人数"),
        ("schema", 1, "看登录人数", "<Data-Skills>口径</Data-Skills>"),
        ("tracking", 2001, 1, "postgresql", "看登录人数", "<Data-Skills>口径</Data-Skills>"),
    ]


def test_sql_engine_exports_query_execution_entrypoints() -> None:
    """
    是什么：SQL Engine 是业务代码面向的执行入口，底层 executor 是内部实现。
    """
    assert sql_engine.execute_user_query is sql_engine_executor.execute_user_query
    assert sql_engine.execute_user_query_or_raise is sql_engine_executor.execute_user_query_or_raise
    assert sql_engine.validate_user_query_sql_or_raise is sql_engine_executor.validate_user_query_sql_or_raise
    assert sql_engine.SqlEngineResult is sql_engine_executor.SqlEngineResult


def test_query_executor_module_has_been_removed() -> None:
    """
    是什么：旧 query_executor 模块已经删除，避免继续形成第二个执行入口。
    """
    query_executor_path = Path(sql_engine.__file__).resolve().with_name("query_executor.py")

    assert not query_executor_path.exists()


def test_app_code_imports_sql_engine_instead_of_query_executor() -> None:
    """
    是什么：业务代码只能依赖 SQL Engine 入口，不能恢复 query_executor 或绕过内部 executor。
    """
    apps_root = Path(__file__).resolve().parents[1] / "apps"
    allowed = {
        Path("datasource/crud/sql_engine.py"),
        Path("datasource/crud/sql_engine_executor.py"),
    }
    approved_roi_adapter = Path("roi_dashboard/query_executor.py")
    query_executor_offenders: list[str] = []
    query_executor_files: list[str] = []
    executor_offenders: list[str] = []
    for path in apps_root.rglob("*.py"):
        relative = path.relative_to(apps_root)
        if path.name == "query_executor.py" and relative != approved_roi_adapter:
            query_executor_files.append(relative.as_posix())
        text = path.read_text(encoding="utf-8")
        if relative not in allowed and (
            "from apps.datasource.crud.query_executor" in text
            or "import query_executor" in text
        ):
            query_executor_offenders.append(relative.as_posix())
        if relative not in {
            Path("datasource/crud/sql_engine.py"),
            Path("datasource/crud/sql_engine_executor.py"),
            approved_roi_adapter,
        } and (
            "from apps.datasource.crud.sql_engine_executor" in text
            or "import sql_engine_executor" in text
        ):
            executor_offenders.append(relative.as_posix())

    assert query_executor_offenders == []
    assert query_executor_files == []
    assert executor_offenders == []


def test_sql_engine_result_keeps_legacy_and_standard_fields() -> None:
    """
    是什么：SQL Engine 标准结果对象同时保留旧 data 字段和新 rows/requested_sql/executed_sql 字段。
    """
    engine_result = sql_engine.SqlEngineResult(
        status="success",
        fields=["day"],
        rows=[{"day": "2026-07-01"}],
        requested_sql="select day from event",
        executed_sql="select day from event where tenant_id = 1",
        tables=["event"],
        execution_time_ms=12,
    )

    payload = engine_result.to_legacy_dict(include_execution_meta=True)

    assert payload["data"] == [{"day": "2026-07-01"}]
    assert payload["rows"] == [{"day": "2026-07-01"}]
    assert payload["requested_sql"] == "select day from event"
    assert payload["executed_sql"] == "select day from event where tenant_id = 1"
    assert payload["tables"] == ["event"]
    assert payload["_execution_meta"]["execution_time_ms"] == 12


def test_tracking_json_expression_compiles_by_runtime_datasource_type() -> None:
    """
    是什么：JSON 字段 expression 由当前数据源方言运行时编译，不依赖 Excel 导入时固化结果。
    """
    postgres_expression = compile_tracking_json_expression(
        "event_log",
        "event_props",
        "$.amount",
        "number",
        "postgresql",
    )
    mysql_expression = compile_tracking_json_expression(
        "event_log",
        "event_props",
        "$.amount",
        "number",
        "mysql",
    )
    clickhouse_expression = compile_tracking_json_expression(
        "event_log",
        "event_props",
        "$.amount",
        "number",
        "clickhouse",
    )

    assert postgres_expression == 'NULLIF(("event_log"."event_props"::jsonb ->> \'amount\'), \'\')::numeric'
    assert mysql_expression == "CAST(JSON_UNQUOTE(JSON_EXTRACT(`event_log`.`event_props`, '$.amount')) AS DECIMAL(38, 10))"
    assert clickhouse_expression == "toFloat64OrNull(JSON_VALUE(`event_log`.`event_props`, '$.amount'))"


def test_tracking_json_expression_normalizes_numeric_object_key() -> None:
    postgres_expression = compile_tracking_json_expression(
        "event_log", "abtest", "$.1001", "text", "postgresql"
    )
    mysql_expression = compile_tracking_json_expression(
        "event_log", "abtest", "$.1001", "text", "mysql"
    )
    clickhouse_expression = compile_tracking_json_expression(
        "event_log", "abtest", "$.1001", "text", "clickhouse"
    )

    postgres_array_expression = compile_tracking_json_expression(
        "event_log", "abtest", "$[1001]", "text", "postgresql"
    )

    assert postgres_expression == '("event_log"."abtest"::jsonb ->> \'1001\')'
    assert postgres_array_expression == '("event_log"."abtest"::jsonb ->> 1001)'
    assert mysql_expression == 'JSON_UNQUOTE(JSON_EXTRACT(`event_log`.`abtest`, \'$["1001"]\'))'
    assert clickhouse_expression == 'JSON_VALUE(`event_log`.`abtest`, \'$["1001"]\')'
