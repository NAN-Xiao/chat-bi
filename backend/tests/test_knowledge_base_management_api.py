"""Phase-aware management API contracts and Chinese error serialization."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

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


def test_publish_route_returns_safe_unavailable_contract_when_worker_not_ready(monkeypatch):
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
    response = asyncio.run(
        publish.publish_knowledge(
            id=10,
            body=publish.PublishRequest(version_id=12, revision=1, content_hash="a" * 64),
            session=object(),
            current_user=SimpleNamespace(id=1, system_role="system_admin", tenant_id=None),
        )
    )
    assert response.status_code == 503
    assert response.body.decode("utf-8") == (
        '{"code":"KNOWLEDGE_PUBLISH_NOT_READY","message":"知识发布能力尚未启用，请稍后重试。",'
        '"field_path":null,"error_type":"UNAVAILABLE","suggestion":"请确认发布任务和索引 Worker 已就绪。"}'
    )


def test_legacy_save_route_remains_registered():
    assert any(route.path == "/knowledge-base/save" for route in knowledge_base.router.routes)
