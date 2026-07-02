"""
脚本说明：验证 datasource/table embedding 缺失时会自动投递补齐任务。
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from apps.datasource.crud import datasource as datasource_crud
from apps.datasource.embedding import ds_embedding


class _FakeSession:
    """
    类说明：_FakeSession 提供 get_ds_embedding 测试所需的最小 session.get 能力。
    """

    def __init__(self, objects: dict[int, Any]) -> None:
        self.objects = objects

    def get(self, _model: Any, object_id: int) -> Any:
        return self.objects.get(int(object_id))


def test_missing_datasource_embedding_queues_backfill_and_returns_candidates(monkeypatch) -> None:
    """
    是什么：数据源 embedding 缺失时应触发后台补齐，并保留全部候选让后续 LLM 选择。
    """
    queued: list[tuple[list[int], int | None]] = []
    monkeypatch.setattr(ds_embedding, "run_save_ds_embeddings", lambda ids, tenant_id=None: queued.append((ids, tenant_id)))

    ds = SimpleNamespace(id=2, tenant_id=1, name="Season War", description="demo", embedding=None)
    result = ds_embedding.get_ds_embedding(
        _FakeSession({2: ds}),
        SimpleNamespace(id=1),
        [{"id": 2, "name": ds.name, "description": ds.description}],
        SimpleNamespace(),
        "近一个月留存",
    )

    assert queued == [([2], 1)]
    assert result == [{"id": 2, "name": "Season War", "description": "demo"}]


def test_missing_table_embedding_queues_backfill_before_fallback(monkeypatch) -> None:
    """
    是什么：表 embedding 缺失时应触发后台补齐，并继续走全表兜底避免漏表。
    """
    queued: list[tuple[list[int], int | None]] = []
    monkeypatch.setattr(datasource_crud, "run_save_table_embeddings", lambda ids, tenant_id=None: queued.append((ids, tenant_id)))
    monkeypatch.setattr(datasource_crud, "_schema_metadata_tenant_id", lambda *_args, **_kwargs: 1)
    monkeypatch.setattr(datasource_crud.settings, "TABLE_EMBEDDING_ENABLED", True)
    monkeypatch.setattr(
        datasource_crud,
        "get_table_obj_by_ds",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                schema="public",
                table=SimpleNamespace(id=10, table_name="fact_a", custom_comment="", embedding=None),
                fields=[SimpleNamespace(id=100, field_name="id", field_type="integer", custom_comment="")],
            ),
            SimpleNamespace(
                schema="public",
                table=SimpleNamespace(id=11, table_name="fact_b", custom_comment="", embedding="[1.0, 0.0]"),
                fields=[SimpleNamespace(id=101, field_name="id", field_type="integer", custom_comment="")],
            ),
        ],
    )

    _schema, result = datasource_crud.get_table_schema(
        SimpleNamespace(),
        SimpleNamespace(id=1),
        SimpleNamespace(id=2, type="pg", table_relation=None),
        "问题",
        embedding=True,
    )

    assert queued == [([10], 1)]
    assert result == ["fact_a", "fact_b"]
