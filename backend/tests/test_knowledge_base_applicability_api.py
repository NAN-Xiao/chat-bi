"""Applicability API exposes datasource and schema-scoped status safely."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from apps.knowledge_base.api import management


class _Result:
    def __init__(self, row):
        self.row = row

    def first(self):
        return self.row


class _Session:
    def __init__(self, version, row):
        self.version = version
        self.row = row

    def get(self, _model, _version_id):
        return self.version

    def exec(self, _statement):
        return _Result(self.row)


def test_applicability_returns_existing_status_for_current_schema(monkeypatch):
    monkeypatch.setattr(management, "current_tenant_id", lambda _user: 2)
    monkeypatch.setattr(
        management,
        "resolve_record",
        lambda *_args, **_kwargs: SimpleNamespace(current_version_id=7),
    )
    monkeypatch.setattr(
        management.PermissionScopeService,
        "build_snapshot",
        staticmethod(lambda **_kwargs: SimpleNamespace(schema_hash="a" * 64)),
    )
    row = SimpleNamespace(
        status="INVALID",
        report={"reference_statuses": [{"status": "UNRESOLVED"}]},
        checked_at=None,
    )
    result = asyncio.run(
        management.knowledge_applicability(
            id=9,
            datasource_id=11,
            session=_Session(SimpleNamespace(status="PUBLISHED"), row),
            current_user=SimpleNamespace(id=1),
        )
    )
    assert result["status"] == "INVALID"
    assert result["status_text"] == "不适用"
    assert result["datasource_id"] == 11
    assert result["schema_hash_prefix"] == "a" * 12
    assert result["warnings"]


def test_applicability_without_evaluation_fails_closed_as_stale(monkeypatch):
    monkeypatch.setattr(management, "current_tenant_id", lambda _user: 2)
    monkeypatch.setattr(
        management,
        "resolve_record",
        lambda *_args, **_kwargs: SimpleNamespace(current_version_id=7),
    )
    monkeypatch.setattr(
        management.PermissionScopeService,
        "build_snapshot",
        staticmethod(lambda **_kwargs: SimpleNamespace(schema_hash="b" * 64)),
    )
    result = asyncio.run(
        management.knowledge_applicability(
            id=9,
            datasource_id=11,
            session=_Session(SimpleNamespace(status="PUBLISHED"), None),
            current_user=SimpleNamespace(id=1),
        )
    )
    assert result["status"] == "STALE"
    assert result["status_text"] == "待检查"
    assert result["warnings"] == ["当前数据源尚未完成适用性检查。"]
