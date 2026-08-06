"""Knowledge scope permissions must distinguish platform and workspace owners."""

from types import SimpleNamespace

import pytest

from apps.knowledge_base.errors import KnowledgeBusinessError
from apps.knowledge_base.models import KnowledgeBaseVisibilityScopeEnum
from apps.knowledge_base.permissions import KnowledgePermissionService


def _user(*, tenant_id=None, role="member", system_role="viewer", workspace_status=None):
    return SimpleNamespace(
        tenant_id=tenant_id,
        tenant_role=role,
        system_role=system_role,
        workspace_status=workspace_status,
    )


def _record(*, tenant_id, scope):
    return SimpleNamespace(tenant_id=tenant_id, visibility_scope=scope)


def test_workspace_admin_can_manage_only_current_workspace_knowledge():
    service = KnowledgePermissionService()
    record = _record(tenant_id=7, scope=KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC)
    service.require_manage(_user(tenant_id=7, role="admin"), record)
    with pytest.raises(KnowledgeBusinessError) as caught:
        service.require_manage(_user(tenant_id=8, role="admin"), record)
    assert caught.value.code == "KNOWLEDGE_NOT_FOUND"


def test_global_platform_admin_manages_platform_scope_but_not_workspace_scope():
    service = KnowledgePermissionService()
    platform = _user(tenant_id=None, system_role="system_admin")
    service.require_manage(
        platform,
        _record(tenant_id=1, scope=KnowledgeBaseVisibilityScopeEnum.PLATFORM_PUBLIC),
    )
    with pytest.raises(KnowledgeBusinessError) as caught:
        service.require_manage(
            platform,
            _record(tenant_id=7, scope=KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC),
        )
    assert caught.value.code == "KNOWLEDGE_NOT_FOUND"


def test_workspace_admin_can_override_platform_knowledge_for_current_workspace():
    service = KnowledgePermissionService()
    tenant_admin = _user(tenant_id=7, role="admin")
    tenant_id = service.require_workspace_override(
        tenant_admin,
        _record(tenant_id=1, scope=KnowledgeBaseVisibilityScopeEnum.PLATFORM_PUBLIC),
    )
    assert tenant_id == 7
