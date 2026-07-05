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


class _FakeExecRows:
    """
    类说明：_FakeExecRows 模拟 SQLModel session.exec 返回值。
    """

    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows

    def all(self) -> list[Any]:
        return self.rows


class _FakeSchemaSession:
    """
    类说明：_FakeSchemaSession 为 AI schema 字典测试提供最小 exec 能力。
    """

    def __init__(self, results: list[list[Any]]) -> None:
        self.results = results

    def exec(self, _stmt: Any) -> _FakeExecRows:
        return _FakeExecRows(self.results.pop(0))


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


def test_ai_table_schema_uses_workspace_dictionary_without_cached_field_fallback(monkeypatch) -> None:
    """
    是什么：AI 识别结构时应以工作空间数据字典为主，不把未声明的缓存字段偷偷塞回 prompt。
    """
    monkeypatch.setattr(datasource_crud, "_schema_metadata_tenant_id", lambda *_args, **_kwargs: 1)
    monkeypatch.setattr(datasource_crud, "has_datasource_access", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(datasource_crud, "aes_decrypt", lambda _value: json.dumps({"dbSchema": "public"}))
    monkeypatch.setattr(datasource_crud, "get_user_permission_rules", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(datasource_crud, "get_user_scoped_table_ids", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(datasource_crud, "get_column_permission_fields", lambda **kwargs: kwargs["fields"])
    monkeypatch.setattr(datasource_crud, "datasource_physical_schema", lambda *_args, **_kwargs: {"user": {"uid", "pay", "hidden_cache_only"}})
    tracking_config_calls: list[tuple[tuple, dict]] = []

    def fake_get_tracking_config(*args, **kwargs):
        tracking_config_calls.append((args, kwargs))
        return SimpleNamespace(
            enabled=True,
            tables=[
                SimpleNamespace(
                    table_name="user",
                    table_comment="用户表",
                    table_role="profile",
                    aliases=["玩家"],
                    ai_notes="以用户粒度保存注册、留存和付费属性。",
                )
            ],
            fields=[
                SimpleNamespace(
                    table_name="user",
                    field_name="pay.pay2",
                    field_comment="注册后第2日累计付费金额，用于次日 LTV。",
                    field_role="json_path_metric",
                    semantic_type="number",
                    source_field="pay",
                    json_path="$.pay2",
                    aliases=["次日LTV"],
                    value_mappings=None,
                    expression="JSON_UNQUOTE(JSON_EXTRACT(pay, '$.pay2'))",
                    required=True,
                    example_values=[1.25],
                    ai_notes="次日 LTV 必须使用 pay2，不使用 pay1。",
                )
            ],
        )

    monkeypatch.setattr(
        datasource_crud,
        "get_tracking_config",
        fake_get_tracking_config,
    )
    monkeypatch.setattr(
        datasource_crud,
        "get_table_obj_by_ds",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                schema="public",
                table=SimpleNamespace(id=10, ds_id=2, table_name="user", custom_comment="", embedding=None),
                fields=[
                    SimpleNamespace(id=100, field_name="uid", field_type="varchar", custom_comment="", field_comment="用户ID"),
                    SimpleNamespace(id=101, field_name="pay", field_type="json", custom_comment="", field_comment="付费JSON"),
                    SimpleNamespace(id=102, field_name="hidden_cache_only", field_type="text", custom_comment="", field_comment="缓存字段"),
                ],
            )
        ],
    )

    session = _FakeSchemaSession(
        [
            [SimpleNamespace(table_name="user", table_comment="用户宽表")],
            [
                SimpleNamespace(table_name="user", field_name="uid", field_comment="用户ID"),
                SimpleNamespace(table_name="user", field_name="pay", field_comment="付费JSON"),
            ],
        ]
    )
    schema, tables = datasource_crud.get_ai_table_schema(
        session,
        SimpleNamespace(id=1),
        SimpleNamespace(id=2, type="pg", configuration="{}", table_relation=None),
        "次日 LTV",
        embedding=False,
    )

    assert tables == ["user"]
    assert tracking_config_calls
    assert tracking_config_calls[0][0][2] == 2
    assert tracking_config_calls[0][1]["include_legacy"] is False
    assert "workspace data dictionary" in schema
    assert "(pay.pay2:number" in schema
    assert "expression=NULLIF((\"user\".\"pay\"::jsonb #>> '{pay2}'), '')::numeric" in schema
    assert "expression=JSON_UNQUOTE(JSON_EXTRACT(pay, '$.pay2'))" not in schema
    assert "SQL must use expression instead of this dictionary field name" in schema
    assert "(uid:varchar" in schema
    assert "(pay:json" in schema
    assert "hidden_cache_only" not in schema


def test_ai_table_schema_hides_tracking_field_when_source_field_permission_denied(monkeypatch) -> None:
    """
    是什么：字典派生字段依赖的源字段不可见时，AI schema 也不能暴露该派生字段。
    """
    monkeypatch.setattr(datasource_crud, "_schema_metadata_tenant_id", lambda *_args, **_kwargs: 1)
    monkeypatch.setattr(datasource_crud, "has_datasource_access", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(datasource_crud, "aes_decrypt", lambda _value: json.dumps({"dbSchema": "public"}))
    monkeypatch.setattr(datasource_crud, "get_user_permission_rules", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(datasource_crud, "get_user_scoped_table_ids", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(datasource_crud, "get_column_permission_fields", lambda **_kwargs: [])
    monkeypatch.setattr(datasource_crud, "datasource_physical_schema", lambda *_args, **_kwargs: {"user": {"pay"}})
    monkeypatch.setattr(
        datasource_crud,
        "get_tracking_config",
        lambda *_args, **_kwargs: SimpleNamespace(
            enabled=True,
            tables=[SimpleNamespace(table_name="user", table_comment="用户表", table_role="", aliases=[], ai_notes="")],
            fields=[
                SimpleNamespace(
                    table_name="user",
                    field_name="pay.pay2",
                    field_comment="次日 LTV",
                    field_role="json_path_metric",
                    semantic_type="number",
                    source_field="pay",
                    json_path="$.pay2",
                    aliases=[],
                    value_mappings=None,
                    expression="JSON_UNQUOTE(JSON_EXTRACT(pay, '$.pay2'))",
                    required=False,
                    example_values=[],
                    ai_notes="",
                )
            ],
        ),
    )
    monkeypatch.setattr(
        datasource_crud,
        "get_table_obj_by_ds",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                schema="public",
                table=SimpleNamespace(id=10, ds_id=2, table_name="user", custom_comment="", embedding=None),
                fields=[SimpleNamespace(id=101, field_name="pay", field_type="json", custom_comment="", field_comment="付费JSON")],
            )
        ],
    )

    schema, tables = datasource_crud.get_ai_table_schema(
        _FakeSchemaSession([[SimpleNamespace(table_name="user", table_comment="用户宽表")], []]),
        SimpleNamespace(id=1),
        SimpleNamespace(id=2, type="pg", configuration="{}", table_relation=None),
        "次日 LTV",
        embedding=False,
    )

    assert schema == ""
    assert tables == []


def test_ai_table_schema_filters_drifted_dictionary_fields_without_physical_fallback(monkeypatch) -> None:
    """
    是什么：数据字典字段漂移后，AI schema 不回退到物理缓存悄悄继续生成。
    """
    monkeypatch.setattr(datasource_crud, "_schema_metadata_tenant_id", lambda *_args, **_kwargs: 1)
    monkeypatch.setattr(datasource_crud, "has_datasource_access", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(datasource_crud, "aes_decrypt", lambda _value: json.dumps({"dbSchema": "public"}))
    monkeypatch.setattr(datasource_crud, "get_user_permission_rules", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(datasource_crud, "get_user_scoped_table_ids", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(datasource_crud, "get_column_permission_fields", lambda **kwargs: kwargs["fields"])
    monkeypatch.setattr(datasource_crud, "datasource_physical_schema", lambda *_args, **_kwargs: {"user": {"pay"}})
    monkeypatch.setattr(
        datasource_crud,
        "get_tracking_config",
        lambda *_args, **_kwargs: SimpleNamespace(
            enabled=True,
            tables=[SimpleNamespace(table_name="user", table_comment="用户表", table_role="", aliases=[], ai_notes="")],
            fields=[
                SimpleNamespace(
                    table_name="user",
                    field_name="missing_payload.pay2",
                    field_comment="漂移字段",
                    field_role="json_path_metric",
                    semantic_type="number",
                    source_field="missing_payload",
                    json_path="$.pay2",
                    aliases=[],
                    value_mappings=None,
                    expression="missing expression",
                    required=False,
                    example_values=[],
                    ai_notes="",
                )
            ],
            event_name_mappings=[],
            field_role_mappings=[],
            sql_rules=None,
        ),
    )
    monkeypatch.setattr(
        datasource_crud,
        "get_table_obj_by_ds",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                schema="public",
                table=SimpleNamespace(id=10, ds_id=2, table_name="user", custom_comment="", embedding=None),
                fields=[SimpleNamespace(id=101, field_name="pay", field_type="json", custom_comment="", field_comment="付费JSON")],
            )
        ],
    )

    schema, tables = datasource_crud.get_ai_table_schema(
        _FakeSchemaSession([[SimpleNamespace(table_name="user", table_comment="")], []]),
        SimpleNamespace(id=1),
        SimpleNamespace(id=2, type="pg", configuration="{}", table_relation=None),
        "次日 LTV",
        embedding=False,
    )

    assert tables == []
    assert "schema validation found no usable dictionary fields" in schema
    assert "missing_payload" in schema
    assert "(pay:json" not in schema


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
