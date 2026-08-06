"""State-machine tests independent from a live PostgreSQL instance."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from apps.knowledge_base.errors import KnowledgeBusinessError
from apps.knowledge_base.lifecycle_models import KnowledgeVersionStatus
from apps.knowledge_base.lifecycle_service import KnowledgeLifecycleService
from apps.knowledge_base.models import KnowledgeBaseVisibilityScopeEnum
from apps.knowledge_base.schemas import DocumentPayload


def _user(tenant_id: int = 7, role: str = "admin"):
    return SimpleNamespace(tenant_id=tenant_id, tenant_role=role, system_role="viewer")


def _payload(text: str = "收入定义") -> DocumentPayload:
    return DocumentPayload(knowledge_type="DOCUMENT", markdown=text)


class _FakeRepo:
    def __init__(self, *, tenant_id: int = 7, scope=KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC):
        self.record = SimpleNamespace(
            id=11,
            tenant_id=tenant_id,
            visibility_scope=scope,
            draft_version_id=None,
            current_version_id=None,
            publishing_version_id=None,
            archived=False,
            active=True,
            update_by=None,
        )
        self.versions = {}
        self.overrides = {}
        self.next_id = 100

    def get_knowledge_base(self, *, tenant_id, knowledge_base_id):
        return self.record if tenant_id == self.record.tenant_id and knowledge_base_id == self.record.id else None

    def lock_knowledge_base(self, *, tenant_id, knowledge_base_id):
        result = self.get_knowledge_base(tenant_id=tenant_id, knowledge_base_id=knowledge_base_id)
        if result is None:
            raise KnowledgeBusinessError(code="KNOWLEDGE_NOT_FOUND", message="知识不存在或已被删除。", status_code=404)
        return result

    def get_version(self, *, tenant_id, knowledge_base_id, version_id, for_update=False):
        value = self.versions.get(version_id)
        return value if value and value.tenant_id == tenant_id and value.knowledge_base_id == knowledge_base_id else None

    def get_active_draft(self, *, tenant_id, knowledge_base_id, for_update=False):
        return next(
            (item for item in self.versions.values() if item.tenant_id == tenant_id and item.knowledge_base_id == knowledge_base_id and item.status in {
                KnowledgeVersionStatus.DRAFT,
                KnowledgeVersionStatus.VALIDATING,
                KnowledgeVersionStatus.VALIDATION_FAILED,
                KnowledgeVersionStatus.READY_TO_PUBLISH,
                KnowledgeVersionStatus.PUBLISHING,
                KnowledgeVersionStatus.PUBLISH_FAILED,
            }),
            None,
        )

    def add_draft(self, *, record, payload, normalized_content, content_hash, actor_id, source_file=None, status=KnowledgeVersionStatus.DRAFT):
        number = max((item.version_number for item in self.versions.values()), default=0) + 1
        version = SimpleNamespace(
            id=self.next_id,
            knowledge_base_id=record.id,
            tenant_id=record.tenant_id,
            version_number=number,
            revision=1,
            status=status,
            payload=payload,
            normalized_content=normalized_content,
            content_hash=content_hash,
            validation_report=None,
            file_id=getattr(source_file, "file_id", None),
            file_name=getattr(source_file, "file_name", None),
            file_ext=getattr(source_file, "file_ext", None),
            parser_version=getattr(source_file, "parser_version", None),
        )
        self.next_id += 1
        self.versions[version.id] = version
        record.draft_version_id = version.id
        return version

    def save_draft_if_revision_matches(self, *, version_id, expected_revision, payload, normalized_content, content_hash, **kwargs):
        version = self.versions.get(version_id)
        if version is None or version.revision != expected_revision or version.status not in {
            KnowledgeVersionStatus.DRAFT,
            KnowledgeVersionStatus.VALIDATION_FAILED,
            KnowledgeVersionStatus.READY_TO_PUBLISH,
            KnowledgeVersionStatus.PUBLISH_FAILED,
        }:
            return None
        version.revision += 1
        version.status = KnowledgeVersionStatus.DRAFT
        version.payload = payload
        version.normalized_content = normalized_content
        version.content_hash = content_hash
        version.validation_report = None
        return version

    def mark_validating_if_revision_matches(self, *, version_id, expected_revision, content_hash, **kwargs):
        version = self.versions.get(version_id)
        if version is None or version.revision != expected_revision or version.content_hash != content_hash or version.status not in {
            KnowledgeVersionStatus.DRAFT,
            KnowledgeVersionStatus.VALIDATION_FAILED,
            KnowledgeVersionStatus.PUBLISH_FAILED,
        }:
            return None
        version.status = KnowledgeVersionStatus.VALIDATING
        return version

    def set_validation_state_if_revision_matches(self, *, version_id, expected_revision, content_hash, status, validation_report, **kwargs):
        version = self.versions.get(version_id)
        if version is None or version.revision != expected_revision or version.content_hash != content_hash or version.status not in {
            KnowledgeVersionStatus.DRAFT,
            KnowledgeVersionStatus.VALIDATING,
        }:
            return None
        version.status = status
        version.validation_report = validation_report
        return version

    def upsert_workspace_override(self, **kwargs):
        self.overrides[(kwargs["tenant_id"], kwargs["knowledge_base_id"])] = kwargs
        return SimpleNamespace(**kwargs)

    def delete_unpublished(self, *, record):
        self.versions.clear()
        self.record = None


def _service(repo):
    return KnowledgeLifecycleService(repo)


def test_concurrent_saves_use_revision_cas_and_keep_first_payload():
    repo = _FakeRepo()
    service = _service(repo)
    draft = service.create_draft(
        tenant_id=7, knowledge_base_id=11, payload=_payload(), actor_id=1, current_user=_user()
    )

    saved = service.save_draft(
        tenant_id=7,
        knowledge_base_id=11,
        draft_version_id=draft.id,
        revision=1,
        payload=_payload("第一次保存"),
        actor_id=1,
        current_user=_user(),
    )
    assert saved.revision == 2

    with pytest.raises(KnowledgeBusinessError) as caught:
        service.save_draft(
            tenant_id=7,
            knowledge_base_id=11,
            draft_version_id=draft.id,
            revision=1,
            payload=_payload("第二次保存"),
            actor_id=2,
            current_user=_user(),
        )
    assert caught.value.code == "KNOWLEDGE_DRAFT_CONFLICT"
    assert caught.value.message == "该知识已被其他用户更新，请刷新后重新编辑。"
    assert repo.versions[draft.id].payload["markdown"] == "第一次保存\n"


def test_validation_transitions_to_ready_to_publish():
    repo = _FakeRepo()
    service = _service(repo)
    draft = service.create_draft(
        tenant_id=7, knowledge_base_id=11, payload=_payload(), actor_id=1, current_user=_user()
    )
    result = service.validate_draft(
        tenant_id=7,
        knowledge_base_id=11,
        draft_version_id=draft.id,
        revision=draft.revision,
        content_hash=draft.content_hash,
        current_user=_user(),
    )
    assert result.status == KnowledgeVersionStatus.READY_TO_PUBLISH
    assert result.validation_report["valid"] is True


@pytest.mark.parametrize("operation", ["save", "validate", "rollback", "archive"])
def test_publishing_blocks_mutations_with_chinese_conflict(operation: str):
    repo = _FakeRepo()
    service = _service(repo)
    draft = service.create_draft(
        tenant_id=7, knowledge_base_id=11, payload=_payload(), actor_id=1, current_user=_user()
    )
    draft.status = KnowledgeVersionStatus.PUBLISHING
    repo.record.publishing_version_id = draft.id
    with pytest.raises(KnowledgeBusinessError) as caught:
        if operation == "save":
            service.save_draft(tenant_id=7, knowledge_base_id=11, draft_version_id=draft.id, revision=1, payload=_payload("x"), actor_id=1, current_user=_user())
        elif operation == "validate":
            service.validate_draft(tenant_id=7, knowledge_base_id=11, draft_version_id=draft.id, revision=1, content_hash=draft.content_hash, current_user=_user())
        elif operation == "rollback":
            service.rollback_to_new_draft(tenant_id=7, knowledge_base_id=11, target_version_id=draft.id, actor_id=1, current_user=_user())
        else:
            service.archive_or_delete(tenant_id=7, knowledge_base_id=11, actor_id=1, current_user=_user())
    assert caught.value.code == "KNOWLEDGE_PUBLISHING"
    assert caught.value.message == "该知识正在发布中，请稍后再试。"


def test_rollback_does_not_replace_an_existing_draft():
    repo = _FakeRepo()
    service = _service(repo)
    draft = service.create_draft(
        tenant_id=7, knowledge_base_id=11, payload=_payload(), actor_id=1, current_user=_user()
    )
    target = SimpleNamespace(
        id=999,
        knowledge_base_id=11,
        tenant_id=7,
        status=KnowledgeVersionStatus.PUBLISHED,
        payload=draft.payload,
        normalized_content=draft.normalized_content,
        content_hash=draft.content_hash,
        file_id=None,
        file_name=None,
        file_ext=None,
        parser_version=None,
    )
    repo.versions[target.id] = target
    with pytest.raises(KnowledgeBusinessError) as caught:
        service.rollback_to_new_draft(tenant_id=7, knowledge_base_id=11, target_version_id=target.id, actor_id=1, current_user=_user())
    assert caught.value.code == "KNOWLEDGE_DRAFT_ALREADY_EXISTS"


def test_unpublished_item_is_deleted_but_published_item_is_archived():
    repo = _FakeRepo()
    service = _service(repo)
    service.create_draft(
        tenant_id=7, knowledge_base_id=11, payload=_payload(), actor_id=1, current_user=_user()
    )
    result = service.archive_or_delete(
        tenant_id=7, knowledge_base_id=11, actor_id=1, current_user=_user()
    )
    assert result is None
    assert repo.record is None

    repo = _FakeRepo()
    service = _service(repo)
    current = service.create_draft(
        tenant_id=7, knowledge_base_id=11, payload=_payload(), actor_id=1, current_user=_user()
    )
    current.status = KnowledgeVersionStatus.PUBLISHED
    repo.record.current_version_id = current.id
    repo.record.draft_version_id = None
    archived = service.archive_or_delete(
        tenant_id=7, knowledge_base_id=11, actor_id=1, current_user=_user()
    )
    assert archived.archived is True
    assert archived.active is False
    assert archived.current_version_id is None
    assert current.status == KnowledgeVersionStatus.ARCHIVED


def test_archiving_published_item_also_closes_a_normal_draft():
    repo = _FakeRepo()
    service = _service(repo)
    draft = service.create_draft(
        tenant_id=7, knowledge_base_id=11, payload=_payload(), actor_id=1, current_user=_user()
    )
    current = SimpleNamespace(
        id=1000,
        knowledge_base_id=11,
        tenant_id=7,
        status=KnowledgeVersionStatus.PUBLISHED,
        payload=draft.payload,
        normalized_content=draft.normalized_content,
        content_hash=draft.content_hash,
        file_id=None,
        file_name=None,
        file_ext=None,
        parser_version=None,
    )
    repo.versions[current.id] = current
    repo.record.current_version_id = current.id
    archived = service.archive_or_delete(
        tenant_id=7, knowledge_base_id=11, actor_id=1, current_user=_user()
    )
    assert archived.archived is True
    assert draft.status == KnowledgeVersionStatus.ARCHIVED
    assert archived.draft_version_id is None


def test_workspace_override_is_tenant_context_bound():
    repo = _FakeRepo(tenant_id=1, scope=KnowledgeBaseVisibilityScopeEnum.PLATFORM_PUBLIC)
    service = _service(repo)
    override = service.set_workspace_enabled(
        knowledge_base_id=11,
        workspace_tenant_id=7,
        enabled=False,
        actor_id=1,
        current_user=_user(tenant_id=7),
    )
    assert override.enabled is False
    assert repo.overrides[(7, 11)]["enabled"] is False
    with pytest.raises(KnowledgeBusinessError) as caught:
        service.set_workspace_enabled(
            knowledge_base_id=11,
            workspace_tenant_id=8,
            enabled=True,
            actor_id=1,
            current_user=_user(tenant_id=7),
        )
    assert caught.value.code == "KNOWLEDGE_TENANT_CONTEXT_MISMATCH"
