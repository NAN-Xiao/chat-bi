from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from apps.knowledge_base.api import knowledge_base as knowledge_base_api
from apps.knowledge_base.models import KnowledgeBaseVisibilityScopeEnum


WORKSPACE_SCOPE = KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC
PLATFORM_SCOPE = KnowledgeBaseVisibilityScopeEnum.PLATFORM_PUBLIC


def _user(*, tenant_id=None, tenant_role="member"):
    return SimpleNamespace(id=100, tenant_id=tenant_id, tenant_role=tenant_role)


def _set_platform_identity(monkeypatch, *, is_admin: bool, is_delegate: bool = False) -> None:
    monkeypatch.setattr(knowledge_base_api, "is_platform_admin", lambda _user: is_admin)
    monkeypatch.setattr(
        knowledge_base_api,
        "is_platform_workspace_delegate",
        lambda _user: is_delegate,
    )


def test_global_admin_must_select_workspace(monkeypatch) -> None:
    _set_platform_identity(monkeypatch, is_admin=True)

    with pytest.raises(HTTPException) as exc_info:
        knowledge_base_api._scope_tenant_id(object(), _user(), WORKSPACE_SCOPE)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "请选择工作空间"


def test_global_admin_can_manage_selected_active_workspace(monkeypatch) -> None:
    _set_platform_identity(monkeypatch, is_admin=True)
    monkeypatch.setattr(
        knowledge_base_api,
        "get_active_tenant",
        lambda _session, tenant_id: SimpleNamespace(id=tenant_id),
    )
    current_user = _user()

    tenant_id = knowledge_base_api._scope_tenant_id(
        object(),
        current_user,
        WORKSPACE_SCOPE,
        requested_tenant_id=23,
    )

    assert tenant_id == 23
    knowledge_base_api._require_scope_manage(current_user, WORKSPACE_SCOPE)


def test_global_admin_cannot_target_inactive_workspace(monkeypatch) -> None:
    _set_platform_identity(monkeypatch, is_admin=True)
    monkeypatch.setattr(knowledge_base_api, "get_active_tenant", lambda *_args: None)

    with pytest.raises(HTTPException) as exc_info:
        knowledge_base_api._scope_tenant_id(
            object(),
            _user(),
            WORKSPACE_SCOPE,
            requested_tenant_id=23,
        )

    assert exc_info.value.status_code == 404


def test_selected_workspace_must_match_record(monkeypatch) -> None:
    _set_platform_identity(monkeypatch, is_admin=True)
    record = SimpleNamespace(tenant_id=24, visibility_scope=WORKSPACE_SCOPE.value)

    with pytest.raises(HTTPException) as exc_info:
        knowledge_base_api._require_record_manage(_user(), record, scope_tenant_id=23)

    assert exc_info.value.status_code == 404


def test_workspace_admin_cannot_override_current_workspace(monkeypatch) -> None:
    _set_platform_identity(monkeypatch, is_admin=False)
    current_user = _user(tenant_id=23, tenant_role="admin")

    assert (
        knowledge_base_api._scope_tenant_id(
            object(),
            current_user,
            WORKSPACE_SCOPE,
            requested_tenant_id=23,
        )
        == 23
    )
    with pytest.raises(HTTPException) as exc_info:
        knowledge_base_api._scope_tenant_id(
            object(),
            current_user,
            WORKSPACE_SCOPE,
            requested_tenant_id=24,
        )

    assert exc_info.value.status_code == 403


def test_platform_scope_permissions_remain_unchanged(monkeypatch) -> None:
    _set_platform_identity(monkeypatch, is_admin=True)
    platform_admin = _user()

    assert (
        knowledge_base_api._scope_tenant_id(object(), platform_admin, PLATFORM_SCOPE)
        == knowledge_base_api.DEFAULT_TENANT_ID
    )
    knowledge_base_api._require_scope_manage(platform_admin, PLATFORM_SCOPE)

    _set_platform_identity(monkeypatch, is_admin=False)
    with pytest.raises(HTTPException) as exc_info:
        knowledge_base_api._require_scope_manage(
            _user(tenant_id=23, tenant_role="admin"),
            PLATFORM_SCOPE,
        )

    assert exc_info.value.status_code == 403
