"""Knowledge scope permissions must distinguish platform and workspace owners."""

from types import SimpleNamespace

import pytest

from apps.knowledge_base.api._helpers import (
    validate_workspace_tenant,
    visible_tenant_ids,
)
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


def test_global_platform_admin_manages_platform_and_selected_workspace_scope():
    service = KnowledgePermissionService()
    platform = _user(tenant_id=None, system_role="system_admin")
    service.require_manage(
        platform,
        _record(tenant_id=1, scope=KnowledgeBaseVisibilityScopeEnum.PLATFORM_PUBLIC),
    )
    service.require_manage(
        platform,
        _record(tenant_id=7, scope=KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC),
    )


def test_workspace_member_can_read_but_not_manage_current_workspace_knowledge():
    service = KnowledgePermissionService()
    workspace_record = _record(
        tenant_id=7,
        scope=KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC,
    )
    member = _user(tenant_id=7, role="member")
    service.require_read(member, workspace_record)
    with pytest.raises(KnowledgeBusinessError) as caught:
        service.require_manage(member, workspace_record)
    assert caught.value.code == "KNOWLEDGE_FORBIDDEN"


def test_workspace_query_rejects_other_tenant_id_explicitly():
    member = _user(tenant_id=7, role="member")
    assert visible_tenant_ids(member, 7) == (7,)
    with pytest.raises(KnowledgeBusinessError) as caught:
        visible_tenant_ids(member, 8)
    assert caught.value.code == "KNOWLEDGE_WORKSPACE_FORBIDDEN"
    assert caught.value.status_code == 403


def test_platform_admin_can_select_one_workspace_tenant():
    platform = _user(tenant_id=None, system_role="system_admin")
    assert visible_tenant_ids(platform, 8) == (8,)


def test_workspace_selection_requires_active_tenant():
    class _Session:
        def __init__(self, row):
            self.row = row

        def get(self, _model, _tenant_id):
            return self.row

    assert validate_workspace_tenant(_Session(SimpleNamespace(id=7, status=1)), 7) == 7
    with pytest.raises(KnowledgeBusinessError) as caught:
        validate_workspace_tenant(_Session(SimpleNamespace(id=7, status=0)), 7)
    assert caught.value.code == "KNOWLEDGE_WORKSPACE_INVALID"
    with pytest.raises(KnowledgeBusinessError) as caught:
        validate_workspace_tenant(_Session(SimpleNamespace(id=1, status=1)), 1)
    assert caught.value.code == "KNOWLEDGE_WORKSPACE_INVALID"


def test_workspace_member_can_read_but_not_manage_platform_knowledge():
    service = KnowledgePermissionService()
    platform_record = _record(
        tenant_id=1,
        scope=KnowledgeBaseVisibilityScopeEnum.PLATFORM_PUBLIC,
    )
    member = _user(tenant_id=7, role="member")
    service.require_read(member, platform_record)
    with pytest.raises(KnowledgeBusinessError) as caught:
        service.require_manage(member, platform_record)
    assert caught.value.code == "KNOWLEDGE_FORBIDDEN"


def test_workspace_admin_can_override_platform_knowledge_for_current_workspace():
    service = KnowledgePermissionService()
    tenant_admin = _user(tenant_id=7, role="admin")
    tenant_id = service.require_workspace_override(
        tenant_admin,
        _record(tenant_id=1, scope=KnowledgeBaseVisibilityScopeEnum.PLATFORM_PUBLIC),
    )
    assert tenant_id == 7
