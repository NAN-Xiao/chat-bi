"""Phase-aware management API contracts and Chinese error serialization."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from apps import api as apps_api
from apps.knowledge_base.api import knowledge_base, management, publish
from apps.knowledge_base.api._helpers import v2_write_error
from apps.knowledge_base.cutover import KnowledgeCapabilities
from apps.knowledge_base.lifecycle_models import KnowledgeMigrationPhase


class _Result:
    def __init__(self, row):
        self.row = row

    def one(self):
        return self.row


class _Session:
    def __init__(self, phase: KnowledgeMigrationPhase):
        self.phase = phase

    def exec(self, _statement):
        return _Result(SimpleNamespace(phase=self.phase))


def _capabilities(*, phase: KnowledgeMigrationPhase, mode: str, enabled: bool):
    return KnowledgeCapabilities(
        phase=phase,
        management_mode=mode,
        legacy_write_enabled=phase == KnowledgeMigrationPhase.LEGACY_OPEN,
        v2_write_enabled=enabled,
        runtime_context_enabled=False,
    )


def test_capabilities_route_is_registered_before_dynamic_id_route():
    paths = [route.path for route in management.router.routes]
    assert "/knowledge-base/capabilities" in paths
    assert paths.index("/knowledge-base/capabilities") < paths.index("/knowledge-base/{id}")


def test_v2_create_route_is_registered_before_dynamic_id_route():
    paths = [route.path for route in management.router.routes]
    assert "/knowledge-base/create" in paths
    assert paths.index("/knowledge-base/create") < paths.index("/knowledge-base/{id}")


def test_restore_route_is_registered_before_dynamic_id_route():
    paths = [route.path for route in management.router.routes]
    assert "/knowledge-base/{id}/restore" in paths
    assert paths.index("/knowledge-base/{id}/restore") < paths.index("/knowledge-base/{id}")


def test_active_route_is_registered_before_dynamic_id_route():
    paths = [route.path for route in management.router.routes]
    assert "/knowledge-base/{id}/active" in paths
    assert paths.index("/knowledge-base/{id}/active") < paths.index("/knowledge-base/{id}")


def test_management_read_routes_are_mounted_on_application_api_router():
    methods_by_path: dict[str, set[str]] = {}
    for route in apps_api.api_router.routes:
        methods_by_path.setdefault(route.path, set()).update(route.methods or set())

    assert "GET" in methods_by_path["/knowledge-base/capabilities"]
    assert "GET" in methods_by_path["/knowledge-base/list"]


def test_capabilities_response_is_database_phase_authoritative():
    result = asyncio.run(
        management.knowledge_capabilities(
            session=_Session(KnowledgeMigrationPhase.LEGACY_OPEN),
            current_user=SimpleNamespace(id=1),
        )
    )
    assert result["phase"] == "LEGACY_OPEN"
    assert result["management_mode"] == "LEGACY"
    assert result["v2_write_enabled"] is False


def test_v2_write_block_returns_chinese_upgrade_error():
    error = v2_write_error(
        _capabilities(
            phase=KnowledgeMigrationPhase.LEGACY_OPEN,
            mode="UPGRADING",
            enabled=False,
        )
    )
    assert error is not None
    assert error.code == "KNOWLEDGE_UPGRADE_IN_PROGRESS"
    assert error.message == "知识库升级中，请稍后重试。"
    assert error.status_code == 409


def test_publish_route_returns_database_job_snapshot(monkeypatch):
    monkeypatch.setattr(
        publish,
        "get_capabilities",
        lambda _session: _capabilities(
            phase=KnowledgeMigrationPhase.V2_ACTIVE,
            mode="V2",
            enabled=True,
        ),
    )
    monkeypatch.setattr(
        publish,
        "resolve_record",
        lambda *_args, **_kwargs: SimpleNamespace(
            id=10,
            tenant_id=1,
            visibility_scope="PLATFORM_PUBLIC",
        ),
    )
    monkeypatch.setattr(
        publish,
        "prepare_publish_job",
        lambda *_args, **_kwargs: SimpleNamespace(
            id=20,
            knowledge_base_id=10,
            version_id=12,
            revision=1,
            content_hash="a" * 64,
            status="QUEUING",
            task_id=None,
            stage=None,
            error_code=None,
            error_message=None,
            heartbeat_at=None,
            deadline_at=None,
        ),
    )
    monkeypatch.setattr(publish.KnowledgePermissionService, "require_manage", lambda *_args: None)
    async def reconcile(*_args, **_kwargs):
        assert _kwargs.get("job_id") == 20
        return {"queued": 1}

    monkeypatch.setattr(publish, "reconcile_publish_jobs", reconcile)

    class _CommitSession:
        def commit(self):
            return None

        def refresh(self, _value):
            return None

    response = asyncio.run(
        publish.publish_knowledge(
            id=10,
            body=publish.PublishRequest(version_id=12, revision=1, content_hash="a" * 64),
            session=_CommitSession(),
            current_user=SimpleNamespace(id=1, system_role="system_admin", tenant_id=None),
        )
    )
    assert response["id"] == 20
    assert response["status"] == "QUEUING"


def test_legacy_save_route_remains_registered():
    assert any(route.path == "/knowledge-base/save" for route in knowledge_base.router.routes)
