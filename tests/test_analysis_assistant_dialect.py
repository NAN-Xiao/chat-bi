import os

import pytest

os.environ["LOG_FORMAT"] = "%(asctime)s - %(name)s - %(levelname)s:%(lineno)d - %(message)s"

from apps.analysis_assistant.api import analysis_assistant
from apps.datasource.models.datasource import CoreDatasource


def _datasource(ds_type: str) -> CoreDatasource:
    return CoreDatasource(
        id=1,
        name="Project",
        type=ds_type,
        configuration="{}",
        create_by=1,
        recommended_config=1,
    )


def test_analysis_sql_normalisation_uses_sql_server_limit_syntax():
    sql = analysis_assistant._normalise_sql(
        "select order_id from orders order by order_id",
        _datasource("sqlServer"),
    )

    assert "TOP 200" in sql
    assert "LIMIT" not in sql.upper()


def test_analysis_sql_normalisation_uses_oracle_limit_syntax():
    sql = analysis_assistant._normalise_sql(
        "select order_id from orders order by order_id",
        _datasource("oracle"),
    )

    assert "FETCH FIRST 200 ROWS ONLY" in sql
    assert "LIMIT" not in sql.upper()


def test_analysis_sql_normalisation_rejects_multi_statement_sql():
    with pytest.raises(ValueError, match="只允许执行一条"):
        analysis_assistant._normalise_sql(
            "select order_id from orders; select amount from payments",
            _datasource("pg"),
        )


@pytest.mark.parametrize(
    ("ds_type", "raw_sql", "expected"),
    [
        ("pg", "select order_id from orders limit 10000", "LIMIT 200"),
        ("mysql", "select order_id from orders limit 10000", "LIMIT 200"),
        ("sqlServer", "select top 10000 order_id from orders", "TOP 200"),
        ("oracle", "select order_id from orders fetch first 10000 rows only", "FETCH FIRST 200 ROWS ONLY"),
        ("oracle", "select order_id from orders where rownum <= 10000", "rownum <= 200"),
    ],
)
def test_analysis_sql_normalisation_clamps_oversized_limits(ds_type, raw_sql, expected):
    sql = analysis_assistant._normalise_sql(raw_sql, _datasource(ds_type))

    assert expected in sql
    assert "10000" not in sql


def test_analysis_dialect_prompt_is_bound_to_current_datasource():
    block = analysis_assistant._dialect_block(_datasource("sqlServer"))

    assert "Microsoft SQL Server" in block
    assert "TOP 200" in block
    assert "禁止使用 LIMIT" in block


def test_collect_date_bounds_uses_datasource_specific_quotes_without_pg_cast(monkeypatch):
    captured: list[str] = []

    def fake_exec_sql(_datasource, sql, origin_column=False):
        captured.append(sql)
        return {"fields": ["f0_max", "f0_min"], "data": [{"f0_max": "2026-01-31", "f0_min": "2026-01-01"}]}

    monkeypatch.setattr(analysis_assistant, "exec_sql", fake_exec_sql)
    schema = """# Table: dbo.orders
[
(created_at:timestamp),
(amount:numeric)
]
"""

    profile = analysis_assistant._collect_date_bounds(_datasource("sqlServer"), schema)

    assert captured == ["SELECT MAX([created_at]) AS [f0_max], MIN([created_at]) AS [f0_min] FROM [dbo].[orders]"]
    assert "::text" not in captured[0]
    assert "orders.created_at" in profile
