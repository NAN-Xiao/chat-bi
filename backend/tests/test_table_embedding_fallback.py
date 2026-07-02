"""
脚本说明：验证表结构检索在表向量缺失时不会丢表。
"""
from __future__ import annotations

from apps.datasource.embedding.table_embedding import calc_table_embedding


def test_calc_table_embedding_returns_all_tables_when_any_embedding_missing(monkeypatch) -> None:
    """
    是什么：任意表缺少 embedding 时，应返回全部可见表，避免误丢真实存在的表。
    """
    monkeypatch.setattr(
        "apps.datasource.embedding.table_embedding.settings.TABLE_EMBEDDING_COUNT",
        1,
    )
    tables = [
        {
            "id": 1,
            "table_name": "fact_sessions",
            "schema_table": "# Table: public.fact_sessions\n[]\n",
            "embedding": None,
        },
        {
            "id": 2,
            "table_name": "fact_payments",
            "schema_table": "# Table: public.fact_payments\n[]\n",
            "embedding": "[1.0, 0.0]",
        },
    ]

    result = calc_table_embedding(tables, "显示最近30天dau和pdau趋势")

    assert [item["table_name"] for item in result] == ["fact_sessions", "fact_payments"]
