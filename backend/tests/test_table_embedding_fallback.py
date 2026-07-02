"""
脚本说明：验证表结构检索在表向量缺失时不会丢表。
"""
from __future__ import annotations

import json

from apps.datasource.embedding import table_embedding
from apps.datasource.embedding.table_embedding import calc_table_embedding
from apps.datasource.embedding.utils import dump_embedding_payload


class _FakeEmbeddingModel:
    """
    类说明：_FakeEmbeddingModel 提供表召回测试所需的最小 embedding 能力。
    """

    def embed_query(self, text: str) -> list[float]:
        if "payment" in text or "收入" in text:
            return [1.0, 0.0]
        return [0.0, 1.0]


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


def test_calc_table_embedding_returns_all_tables_when_embedding_payload_is_legacy(monkeypatch) -> None:
    """
    是什么：旧裸数组向量没有模型/维度签名，应走全表兜底，等待后台重算。
    """
    monkeypatch.setattr(table_embedding.EmbeddingModelCache, "get_model", lambda: _FakeEmbeddingModel())
    monkeypatch.setattr(
        "apps.datasource.embedding.table_embedding.settings.TABLE_EMBEDDING_COUNT",
        1,
    )
    tables = [
        {
            "id": 1,
            "table_name": "fact_sessions",
            "schema_table": "# Table: public.fact_sessions\n[]\n",
            "embedding": json.dumps([0.0, 1.0]),
        },
        {
            "id": 2,
            "table_name": "fact_payments",
            "schema_table": "# Table: public.fact_payments\n[]\n",
            "embedding": json.dumps([1.0, 0.0]),
        },
    ]

    result = calc_table_embedding(tables, "payment revenue")

    assert [item["table_name"] for item in result] == ["fact_sessions", "fact_payments"]


def test_calc_table_embedding_uses_current_payloads(monkeypatch) -> None:
    """
    是什么：新格式向量匹配当前模型/维度时，按相似度召回 Top N。
    """
    fake_model = _FakeEmbeddingModel()
    monkeypatch.setattr(table_embedding.EmbeddingModelCache, "get_model", lambda: fake_model)
    monkeypatch.setattr(
        "apps.datasource.embedding.table_embedding.settings.TABLE_EMBEDDING_COUNT",
        1,
    )
    tables = [
        {
            "id": 1,
            "table_name": "fact_sessions",
            "schema_table": "# Table: public.fact_sessions\n[]\n",
            "embedding": dump_embedding_payload([0.0, 1.0], fake_model),
        },
        {
            "id": 2,
            "table_name": "fact_payments",
            "schema_table": "# Table: public.fact_payments\n[]\n",
            "embedding": dump_embedding_payload([1.0, 0.0], fake_model),
        },
    ]

    result = calc_table_embedding(tables, "payment revenue")

    assert [item["table_name"] for item in result] == ["fact_payments"]


def test_calc_table_embedding_queues_refresh_when_query_dimension_changes(monkeypatch) -> None:
    """
    是什么：同名 embedding 模型返回维度变化时，应排队重算并返回全表兜底。
    """
    fake_model = _FakeEmbeddingModel()
    monkeypatch.setattr(
        table_embedding.EmbeddingModelCache,
        "get_model",
        lambda: type("ChangedDimModel", (), {"embed_query": lambda _self, _text: [1.0, 0.0, 0.0]})(),
    )
    queued: list[list[int]] = []
    tables = [
        {
            "id": 1,
            "table_name": "fact_sessions",
            "schema_table": "# Table: public.fact_sessions\n[]\n",
            "embedding": dump_embedding_payload([0.0, 1.0], fake_model),
        },
        {
            "id": 2,
            "table_name": "fact_payments",
            "schema_table": "# Table: public.fact_payments\n[]\n",
            "embedding": dump_embedding_payload([1.0, 0.0], fake_model),
        },
    ]

    result = calc_table_embedding(tables, "payment revenue", stale_embedding_callback=lambda ids: queued.append(ids))

    assert queued == [[1, 2]]
    assert [item["table_name"] for item in result] == ["fact_sessions", "fact_payments"]
