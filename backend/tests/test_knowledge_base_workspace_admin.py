import asyncio
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, HTTPException

from apps.knowledge_base.api import knowledge_base as knowledge_base_api
from apps.knowledge_base.context import KnowledgeContextTooLargeError
from apps.knowledge_base.models import (
    KnowledgeBaseStatusEnum,
    KnowledgeBaseVisibilityScopeEnum,
)

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
    assert exc_info.value.detail == {
        "code": "knowledge_workspace_context_missing",
        "message": "请选择工作空间后再管理工作空间知识库。",
    }


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
    assert exc_info.value.detail["message"] == "工作空间不存在或已停用。"


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
    assert exc_info.value.detail["message"] == "仅 SaaS 管理员可以维护 SaaS 知识库。"
    assert exc_info.value.detail["code"] == "knowledge_scope_forbidden"


def test_save_allows_empty_usage_instruction(monkeypatch) -> None:
    class _Session:
        def add(self, _record):
            return None

        def flush(self):
            return None

        def commit(self):
            return None

        def refresh(self, _record):
            return None

    monkeypatch.setattr(knowledge_base_api, "_require_scope_manage", lambda *_args: None)
    monkeypatch.setattr(knowledge_base_api, "_scope_tenant_id", lambda *_args, **_kwargs: 23)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            knowledge_base_api.save_knowledge_base(
                _Session(),
                _user(tenant_id=23, tenant_role="admin"),
                BackgroundTasks(),
                id=None,
                name="测试知识库",
                description="  ",
                active=False,
                visibility_scope=WORKSPACE_SCOPE.value,
                tenant_id=23,
                file=None,
            )
        )

    assert exc_info.value.detail["code"] == "knowledge_file_required"


def test_non_ready_document_cannot_be_activated(monkeypatch) -> None:
    record = SimpleNamespace(
        id=1,
        tenant_id=23,
        visibility_scope=WORKSPACE_SCOPE.value,
        status=KnowledgeBaseStatusEnum.PROCESSING,
        content=None,
        file_id="test.md",
    )
    session = SimpleNamespace(get=lambda _model, _id: record)
    monkeypatch.setattr(knowledge_base_api, "_scope_tenant_id", lambda *_args, **_kwargs: 23)
    monkeypatch.setattr(knowledge_base_api, "_require_record_manage", lambda *_args: None)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            knowledge_base_api.save_knowledge_base(
                session,
                _user(tenant_id=23, tenant_role="admin"),
                BackgroundTasks(),
                id=1,
                name="测试知识库",
                description="用于回答测试问题。",
                active=True,
                visibility_scope=WORKSPACE_SCOPE.value,
                file=None,
            )
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "knowledge_content_not_ready"
    assert exc_info.value.detail["message"] == "文档尚未处理完成，请检查处理状态后重试。"


def test_activation_preflights_capacity_and_returns_chinese_counts(monkeypatch) -> None:
    record = SimpleNamespace(
        id=1,
        tenant_id=23,
        visibility_scope=WORKSPACE_SCOPE.value,
        status=KnowledgeBaseStatusEnum.READY,
        content="完整正文",
        file_id="test.md",
    )

    class _Session:
        committed = False
        rolled_back = False

        def get(self, _model, _id):
            return record

        def add(self, _record):
            return None

        def flush(self):
            return None

        def commit(self):
            self.committed = True

        def rollback(self):
            self.rolled_back = True

    session = _Session()
    monkeypatch.setattr(knowledge_base_api, "_scope_tenant_id", lambda *_args, **_kwargs: 23)
    monkeypatch.setattr(knowledge_base_api, "_require_record_manage", lambda *_args: None)
    monkeypatch.setattr(
        knowledge_base_api,
        "build_knowledge_context",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            KnowledgeContextTooLargeError(
                total_chars=40000,
                max_chars=32768,
                platform_chars=10000,
                workspace_chars=30000,
                document_count=4,
            )
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            knowledge_base_api.save_knowledge_base(
                session,
                _user(tenant_id=23, tenant_role="admin"),
                BackgroundTasks(),
                id=1,
                name="测试知识库",
                description="用于回答测试问题。",
                active=True,
                visibility_scope=WORKSPACE_SCOPE.value,
                file=None,
            )
        )

    assert session.committed is False
    assert session.rolled_back is True
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "knowledge_context_too_large"
    assert exc_info.value.detail["details"] == {
        "total_chars": 40000,
        "max_chars": 32768,
        "platform_chars": 10000,
        "workspace_chars": 30000,
        "document_count": 4,
    }
    assert "当前共 40000 字符" in exc_info.value.detail["message"]
