"""Workspace selection and role matrix for knowledge management."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from fastapi.responses import JSONResponse

from apps.knowledge_base.api import management
from apps.knowledge_base.models import KnowledgeBaseVisibilityScopeEnum


def _capabilities():
    return SimpleNamespace(
        phase=SimpleNamespace(value="V2_ACTIVE"),
        management_mode="V2",
        v2_write_enabled=True,
    )


def _user(*, tenant_id=None, role="member", system_role="viewer"):
    return SimpleNamespace(
        id=11,
        tenant_id=tenant_id,
        tenant_role=role,
        system_role=system_role,
        workspace_status=None,
    )


class _Session:
    def __init__(self, *, active_tenant_id: int | None = None) -> None:
        self.active_tenant_id = active_tenant_id
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    def get(self, _model, record_id):
        if self.active_tenant_id == int(record_id):
            return SimpleNamespace(id=int(record_id), status=1)
        return None

    def add(self, record):
        if record.id is None:
            record.id = 101
        self.added.append(record)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def refresh(self, _record):
        return None


def _response_json(response: JSONResponse) -> dict:
    return json.loads(response.body.decode("utf-8"))


class _Rows:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def all(self):
        return self.rows


class _ListSession(_Session):
    def __init__(self):
        super().__init__()
        self.statements = []

    def exec(self, statement):
        self.statements.append(statement)
        return _Rows()


def test_list_defaults_to_current_and_supports_explicit_archived_filter(monkeypatch):
    monkeypatch.setattr(management, "get_capabilities", lambda _session: _capabilities())
    current_session = _ListSession()
    archived_session = _ListSession()
    user = _user(system_role="system_admin")

    assert asyncio.run(management.list_knowledge_base(
        session=current_session,
        current_user=user,
        visibility_scope="PLATFORM_PUBLIC",
    )) == []
    assert asyncio.run(management.list_knowledge_base(
        session=archived_session,
        current_user=user,
        visibility_scope="PLATFORM_PUBLIC",
        archived=True,
    )) == []

    assert "knowledge_base.archived IS false" in str(current_session.statements[0])
    assert "knowledge_base.archived IS true" in str(archived_session.statements[0])


def test_restore_route_returns_inactive_restored_record(monkeypatch):
    monkeypatch.setattr(management, "get_capabilities", lambda _session: _capabilities())
    record = SimpleNamespace(
        id=44,
        tenant_id=7,
        name="Archived knowledge",
        description=None,
        visibility_scope="ADMIN_PUBLIC",
        active=False,
        status="READY",
        file_id=None,
        file_name=None,
        file_ext=None,
        error_message=None,
        create_time=None,
        update_time=None,
        archived=False,
        knowledge_type="DOCUMENT",
        stable_key="kb-44",
        draft_version_id=None,
        current_version_id=88,
        publishing_version_id=None,
    )
    monkeypatch.setattr(management, "resolve_record", lambda *_args, **_kwargs: record)

    class _Service:
        def __init__(self, _repository):
            pass

        def restore(self, **kwargs):
            assert kwargs["tenant_id"] == 7
            assert kwargs["knowledge_base_id"] == 44
            return record

    monkeypatch.setattr(management, "KnowledgeLifecycleService", _Service)
    session = _Session()
    response = asyncio.run(management.restore_knowledge_base(
        id=44,
        session=session,
        current_user=_user(tenant_id=7, role="admin"),
    ))

    assert response["archived"] is False
    assert response["active"] is False
    assert response["current_version_id"] == 88
    assert session.commits == 1


def test_active_route_explicitly_enables_current_knowledge(monkeypatch):
    monkeypatch.setattr(management, "get_capabilities", lambda _session: _capabilities())
    record = SimpleNamespace(
        id=44, tenant_id=7, name="Restored knowledge", description=None,
        visibility_scope="ADMIN_PUBLIC", active=False, status="READY",
        file_id=None, file_name=None, file_ext=None, error_message=None,
        create_time=None, update_time=None, archived=False,
        knowledge_type="DOCUMENT", stable_key="kb-44", draft_version_id=None,
        current_version_id=88, publishing_version_id=None,
    )
    monkeypatch.setattr(management, "resolve_record", lambda *_args, **_kwargs: record)

    class _Service:
        def __init__(self, _repository):
            pass

        def set_active(self, **kwargs):
            assert kwargs["active"] is True
            record.active = True
            return record

    monkeypatch.setattr(management, "KnowledgeLifecycleService", _Service)
    session = _Session()
    response = asyncio.run(management.set_knowledge_base_active(
        id=44,
        body=management.SetKnowledgeBaseActiveRequest(active=True),
        session=session,
        current_user=_user(tenant_id=7, role="admin"),
    ))

    assert response["active"] is True
    assert session.commits == 1


def test_workspace_admin_can_create_only_current_workspace_knowledge(monkeypatch):
    monkeypatch.setattr(management, "get_capabilities", lambda _session: _capabilities())
    session = _Session(active_tenant_id=7)

    response = asyncio.run(
        management.create_knowledge_base(
            body=management.CreateKnowledgeBaseRequest(
                name="Workspace knowledge",
                visibility_scope=KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC,
                tenant_id=7,
            ),
            session=session,
            current_user=_user(tenant_id=7, role="admin"),
        )
    )

    assert response["tenant_id"] == 7
    assert response["can_manage"] is True
    assert session.commits == 1


def test_knowledge_type_is_fixed_when_the_record_is_created(monkeypatch):
    monkeypatch.setattr(management, "get_capabilities", lambda _session: _capabilities())
    session = _Session(active_tenant_id=7)

    response = asyncio.run(
        management.create_knowledge_base(
            body=management.CreateKnowledgeBaseRequest(
                name="Event knowledge",
                visibility_scope=KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC,
                tenant_id=7,
                knowledge_type="EVENT",
            ),
            session=session,
            current_user=_user(tenant_id=7, role="admin"),
        )
    )

    assert response["knowledge_type"] == "EVENT"
    assert session.added[0].knowledge_type == "EVENT"


def test_create_rejects_unknown_knowledge_type(monkeypatch):
    monkeypatch.setattr(management, "get_capabilities", lambda _session: _capabilities())
    session = _Session(active_tenant_id=7)

    response = asyncio.run(
        management.create_knowledge_base(
            body=management.CreateKnowledgeBaseRequest(
                name="Unknown knowledge",
                visibility_scope=KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC,
                tenant_id=7,
                knowledge_type="UNKNOWN",
            ),
            session=session,
            current_user=_user(tenant_id=7, role="admin"),
        )
    )

    assert isinstance(response, JSONResponse)
    assert response.status_code == 422
    assert _response_json(response)["code"] == "KNOWLEDGE_TYPE_INVALID"
    assert session.added == []


def test_workspace_member_cannot_create_workspace_knowledge(monkeypatch):
    monkeypatch.setattr(management, "get_capabilities", lambda _session: _capabilities())
    response = asyncio.run(
        management.create_knowledge_base(
            body=management.CreateKnowledgeBaseRequest(
                name="Read only member",
                visibility_scope=KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC,
                tenant_id=7,
            ),
            session=_Session(active_tenant_id=7),
            current_user=_user(tenant_id=7, role="member"),
        )
    )

    assert isinstance(response, JSONResponse)
    assert response.status_code == 403
    assert _response_json(response)["code"] == "KNOWLEDGE_FORBIDDEN"


def test_workspace_user_cannot_query_another_workspace(monkeypatch):
    monkeypatch.setattr(management, "get_capabilities", lambda _session: _capabilities())
    response = asyncio.run(
        management.list_knowledge_base(
            session=_Session(active_tenant_id=8),
            current_user=_user(tenant_id=7, role="admin"),
            visibility_scope=KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC.value,
            tenant_id=8,
        )
    )

    assert isinstance(response, JSONResponse)
    assert response.status_code == 403
    assert _response_json(response)["code"] == "KNOWLEDGE_WORKSPACE_FORBIDDEN"


def test_platform_admin_must_select_workspace_for_workspace_list(monkeypatch):
    monkeypatch.setattr(management, "get_capabilities", lambda _session: _capabilities())

    response = asyncio.run(
        management.list_knowledge_base(
            session=_Session(active_tenant_id=8),
            current_user=_user(system_role="system_admin"),
            visibility_scope=KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC.value,
        )
    )

    assert isinstance(response, JSONResponse)
    assert response.status_code == 400
    assert _response_json(response)["code"] == "KNOWLEDGE_WORKSPACE_REQUIRED"


def test_platform_admin_can_create_selected_workspace_knowledge(monkeypatch):
    monkeypatch.setattr(management, "get_capabilities", lambda _session: _capabilities())
    response = asyncio.run(
        management.create_knowledge_base(
            body=management.CreateKnowledgeBaseRequest(
                name="Managed workspace knowledge",
                visibility_scope=KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC,
                tenant_id=8,
            ),
            session=_Session(active_tenant_id=8),
            current_user=_user(system_role="system_admin"),
        )
    )

    assert response["tenant_id"] == 8
    assert response["can_manage"] is True


def test_platform_admin_must_select_workspace_for_workspace_knowledge(monkeypatch):
    monkeypatch.setattr(management, "get_capabilities", lambda _session: _capabilities())

    response = asyncio.run(
        management.create_knowledge_base(
            body=management.CreateKnowledgeBaseRequest(
                name="Missing workspace selection",
                visibility_scope=KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC,
            ),
            session=_Session(active_tenant_id=8),
            current_user=_user(system_role="system_admin"),
        )
    )

    assert isinstance(response, JSONResponse)
    assert response.status_code == 400
    assert _response_json(response)["code"] == "KNOWLEDGE_WORKSPACE_REQUIRED"


def test_platform_scope_rejects_workspace_tenant_id(monkeypatch):
    monkeypatch.setattr(management, "get_capabilities", lambda _session: _capabilities())
    response = asyncio.run(
        management.create_knowledge_base(
            body=management.CreateKnowledgeBaseRequest(
                name="Platform knowledge",
                visibility_scope=KnowledgeBaseVisibilityScopeEnum.PLATFORM_PUBLIC,
                tenant_id=8,
            ),
            session=_Session(active_tenant_id=8),
            current_user=_user(system_role="system_admin"),
        )
    )

    assert isinstance(response, JSONResponse)
    assert response.status_code == 400
    assert _response_json(response)["code"] == "KNOWLEDGE_WORKSPACE_NOT_APPLICABLE"
