"""
脚本说明：验证 datasource/table embedding 缺失时会自动投递补齐任务。
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from apps.datasource.crud import datasource as datasource_crud
from apps.datasource.crud import table as table_crud
from apps.datasource.embedding import ds_embedding
from apps.datasource.embedding.utils import dump_embedding_payload


class _ChangedDimEmbeddingModel:
    """
    类说明：_ChangedDimEmbeddingModel 模拟同名模型返回了不同维度的新向量。
    """

    def embed_query(self, _text: str) -> list[float]:
        return [1.0, 0.0, 0.0]


class _FakeSession:
    """
    类说明：_FakeSession 提供 get_ds_embedding 测试所需的最小 session.get 能力。
    """

    def __init__(self, objects: dict[int, Any]) -> None:
        self.objects = objects

    def get(self, _model: Any, object_id: int) -> Any:
        return self.objects.get(int(object_id))


class _FakeExecuteSession:
    """
    类说明：_FakeExecuteSession 提供 run_fill_empty_table_and_ds_embedding 测试所需的 execute 能力。
    """

    def __init__(self, results: list[list[tuple[int, str | None]]]) -> None:
        self.results = results

    def execute(self, _stmt: Any) -> Any:
        rows = self.results.pop(0)
        return SimpleNamespace(all=lambda: rows)


class _FakeSessionMaker:
    """
    类说明：_FakeSessionMaker 模拟 scoped_session 的调用和 remove。
    """

    def __init__(self, session: _FakeExecuteSession) -> None:
        self.session = session

    def __call__(self) -> _FakeExecuteSession:
        return self.session

    def remove(self) -> None:
        return None


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


def test_legacy_datasource_embedding_queues_backfill_and_returns_candidates(monkeypatch) -> None:
    """
    是什么：数据源旧裸数组向量应触发后台补齐，而不是继续参与相似度计算。
    """
    queued: list[tuple[list[int], int | None]] = []
    monkeypatch.setattr(ds_embedding, "run_save_ds_embeddings", lambda ids, tenant_id=None: queued.append((ids, tenant_id)))

    ds = SimpleNamespace(id=2, tenant_id=1, name="Season War", description="demo", embedding=json.dumps([1.0, 0.0]))
    result = ds_embedding.get_ds_embedding(
        _FakeSession({2: ds}),
        SimpleNamespace(id=1),
        [{"id": 2, "name": ds.name, "description": ds.description}],
        SimpleNamespace(),
        "近一个月留存",
    )

    assert queued == [([2], 1)]
    assert result == [{"id": 2, "name": "Season War", "description": "demo"}]


def test_datasource_embedding_dimension_change_queues_backfill_and_returns_candidates(monkeypatch) -> None:
    """
    是什么：同名 embedding 模型维度变化时，应触发后台补齐并保留全部候选。
    """
    queued: list[tuple[list[int], int | None]] = []
    monkeypatch.setattr(ds_embedding, "run_save_ds_embeddings", lambda ids, tenant_id=None: queued.append((ids, tenant_id)))
    monkeypatch.setattr(ds_embedding.EmbeddingModelCache, "get_model", lambda: _ChangedDimEmbeddingModel())

    ds = SimpleNamespace(id=2, tenant_id=1, name="Season War", description="demo", embedding=dump_embedding_payload([1.0, 0.0]))
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
                table=SimpleNamespace(id=11, table_name="fact_b", custom_comment="", embedding=dump_embedding_payload([1.0, 0.0])),
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


def test_legacy_table_embedding_queues_backfill_before_fallback(monkeypatch) -> None:
    """
    是什么：旧裸数组向量缺少模型/维度签名，应触发后台补齐并继续全表兜底。
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
                table=SimpleNamespace(id=10, table_name="fact_a", custom_comment="", embedding=json.dumps([1.0, 0.0])),
                fields=[SimpleNamespace(id=100, field_name="id", field_type="integer", custom_comment="")],
            ),
            SimpleNamespace(
                schema="public",
                table=SimpleNamespace(id=11, table_name="fact_b", custom_comment="", embedding=json.dumps([0.0, 1.0])),
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

    assert queued == [([10, 11], 1)]
    assert result == ["fact_a", "fact_b"]


def test_fill_empty_table_and_ds_embedding_detects_non_empty_stale_vectors(monkeypatch) -> None:
    """
    是什么：全量补漏扫描应覆盖非空但缺少当前模型/维度签名的旧向量。
    """
    saved_tables: list[tuple[list[int], int | None]] = []
    saved_datasources: list[tuple[list[int], int | None]] = []
    monkeypatch.setattr(table_crud.settings, "TABLE_EMBEDDING_ENABLED", True)
    monkeypatch.setattr(table_crud, "save_table_embedding", lambda _session_maker, ids, tenant_id=None: saved_tables.append((list(ids), tenant_id)))
    monkeypatch.setattr(table_crud, "save_ds_embedding", lambda _session_maker, ids, tenant_id=None: saved_datasources.append((list(ids), tenant_id)))

    current_payload = dump_embedding_payload([1.0, 0.0])
    session_maker = _FakeSessionMaker(
        _FakeExecuteSession(
            [
                [(10, None), (11, json.dumps([1.0, 0.0])), (12, current_payload)],
                [(20, ""), (21, json.dumps([0.0, 1.0])), (22, current_payload)],
            ]
        )
    )

    table_crud.run_fill_empty_table_and_ds_embedding(session_maker, tenant_id=None)

    assert saved_tables == [([10, 11], None)]
    assert saved_datasources == [([20, 21], None)]
