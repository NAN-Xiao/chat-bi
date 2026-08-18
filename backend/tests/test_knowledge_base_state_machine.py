"""State-machine tests independent from a live PostgreSQL instance."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from apps.knowledge_base.errors import KnowledgeBusinessError
from apps.knowledge_base.lifecycle_models import KnowledgeVersionStatus
from apps.knowledge_base.lifecycle_service import KnowledgeLifecycleService
from apps.knowledge_base.models import KnowledgeBaseVisibilityScopeEnum
from apps.knowledge_base.schemas import DocumentBlock, DocumentPayload
from apps.knowledge_base.version_repository import KnowledgeVersionRepository


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
        self.audits = []
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

    def get_latest_archived_published_version(self, *, tenant_id, knowledge_base_id, for_update=False):
        candidates = [
            item for item in self.versions.values()
            if item.tenant_id == tenant_id
            and item.knowledge_base_id == knowledge_base_id
            and item.status == KnowledgeVersionStatus.ARCHIVED
            and getattr(item, "publish_time", None) is not None
        ]
        return max(
            candidates,
            key=lambda item: (item.publish_time, item.version_number),
            default=None,
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

    def update_locked_draft(self, *, version, payload, normalized_content, content_hash, **kwargs):
        version.revision += 1
        version.status = KnowledgeVersionStatus.DRAFT
        version.payload = payload
        version.normalized_content = normalized_content
        version.content_hash = content_hash
        version.validation_report = None
        return version

    def add_document_block_audit(self, **kwargs):
        self.audits.append(kwargs)
        return SimpleNamespace(**kwargs)

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

    def delete_all(self, *, record):
        file_ids = tuple(
            sorted(
                {
                    str(item.file_id)
                    for item in self.versions.values()
                    if getattr(item, "file_id", None)
                }
                | ({str(record.file_id)} if getattr(record, "file_id", None) else set())
            )
        )
        self.versions.clear()
        self.record = None
        return file_ids


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
    assert repo.versions[draft.id].payload["blocks"][0]["markdown"] == "第一次保存\n"


def _multi_block_payload() -> DocumentPayload:
    return DocumentPayload(
        knowledge_type="DOCUMENT",
        blocks=[
            DocumentBlock(id="block-a", title="A", markdown="A0"),
            DocumentBlock(id="block-b", title="B", markdown="B0"),
        ],
        structure_revision=1,
    )


def test_different_document_blocks_can_save_from_the_same_initial_snapshot():
    repo = _FakeRepo()
    service = _service(repo)
    draft = service.create_draft(
        tenant_id=7,
        knowledge_base_id=11,
        payload=_multi_block_payload(),
        actor_id=1,
        current_user=_user(),
    )

    service.save_document_block(
        tenant_id=7,
        knowledge_base_id=11,
        draft_version_id=draft.id,
        block_id="block-a",
        block_revision=1,
        title="A",
        markdown="A1",
        enabled=True,
        actor_id=1,
        current_user=_user(),
    )
    saved = service.save_document_block(
        tenant_id=7,
        knowledge_base_id=11,
        draft_version_id=draft.id,
        block_id="block-b",
        block_revision=1,
        title="B",
        markdown="B1",
        enabled=True,
        actor_id=2,
        current_user=_user(),
    )

    assert saved.revision == 3
    blocks = {item["id"]: item for item in saved.payload["blocks"]}
    assert blocks["block-a"]["markdown"] == "A1\n"
    assert blocks["block-b"]["markdown"] == "B1\n"
    assert blocks["block-a"]["block_revision"] == 2
    assert blocks["block-b"]["block_revision"] == 2
    assert len(repo.audits) == 2
    assert repo.audits[0]["operation_types"] == ["UPDATE_BLOCK"]
    assert repo.audits[0]["block_ids"] == ["block-a"]
    assert repo.audits[1]["block_ids"] == ["block-b"]


def test_same_document_block_returns_server_snapshot_on_conflict():
    repo = _FakeRepo()
    service = _service(repo)
    draft = service.create_draft(
        tenant_id=7, knowledge_base_id=11, payload=_multi_block_payload(), actor_id=1, current_user=_user()
    )
    service.save_document_block(
        tenant_id=7, knowledge_base_id=11, draft_version_id=draft.id,
        block_id="block-a", block_revision=1, title="A", markdown="server",
        enabled=True, actor_id=1, current_user=_user(),
    )

    with pytest.raises(KnowledgeBusinessError) as caught:
        service.save_document_block(
            tenant_id=7, knowledge_base_id=11, draft_version_id=draft.id,
            block_id="block-a", block_revision=1, title="A", markdown="local",
            enabled=True, actor_id=2, current_user=_user(),
        )

    assert caught.value.code == "KNOWLEDGE_DOCUMENT_BLOCK_CONFLICT"
    assert caught.value.details["conflict_type"] == "BLOCK"
    assert caught.value.details["server_block"]["markdown"] == "server\n"


def test_document_structure_conflict_returns_latest_payload():
    repo = _FakeRepo()
    service = _service(repo)
    draft = service.create_draft(
        tenant_id=7, knowledge_base_id=11, payload=_multi_block_payload(), actor_id=1, current_user=_user()
    )
    first = _multi_block_payload().model_copy(update={
        "blocks": list(reversed(_multi_block_payload().blocks)),
    })
    service.save_document_structure(
        tenant_id=7, knowledge_base_id=11, draft_version_id=draft.id,
        structure_revision=1, payload=first, actor_id=1, current_user=_user(),
    )

    with pytest.raises(KnowledgeBusinessError) as caught:
        service.save_document_structure(
            tenant_id=7, knowledge_base_id=11, draft_version_id=draft.id,
            structure_revision=1, payload=_multi_block_payload(), actor_id=2, current_user=_user(),
        )

    assert caught.value.code == "KNOWLEDGE_DOCUMENT_STRUCTURE_CONFLICT"
    assert caught.value.details["structure_revision"] == 2
    assert [item["id"] for item in caught.value.details["server_payload"]["blocks"]] == ["block-b", "block-a"]


def test_saving_a_deleted_document_block_preserves_conflict_context():
    repo = _FakeRepo()
    service = _service(repo)
    draft = service.create_draft(
        tenant_id=7, knowledge_base_id=11, payload=_multi_block_payload(), actor_id=1, current_user=_user()
    )
    remaining = _multi_block_payload().model_copy(update={"blocks": [_multi_block_payload().blocks[0]]})
    service.save_document_structure(
        tenant_id=7, knowledge_base_id=11, draft_version_id=draft.id,
        structure_revision=1, payload=remaining, actor_id=1, current_user=_user(),
    )

    with pytest.raises(KnowledgeBusinessError) as caught:
        service.save_document_block(
            tenant_id=7, knowledge_base_id=11, draft_version_id=draft.id,
            block_id="block-b", block_revision=1, title="B", markdown="local",
            enabled=True, actor_id=2, current_user=_user(),
        )

    assert caught.value.code == "KNOWLEDGE_DOCUMENT_BLOCK_DELETED"
    assert caught.value.details["conflict_type"] == "BLOCK_DELETED"


def test_structure_save_preserves_hidden_metadata_and_normalizes_new_block_revision():
    repo = _FakeRepo()
    service = _service(repo)
    draft = service.create_draft(
        tenant_id=7,
        knowledge_base_id=11,
        payload=DocumentPayload(
            knowledge_type="DOCUMENT",
            blocks=[DocumentBlock(id="block-a", title="A", markdown="one")],
            structure_revision=1,
            tags=["hidden"],
            datasource_neutral=False,
            object_references=[{"object_type": "TABLE", "schema": "public", "table": "orders"}],
        ),
        actor_id=1,
        current_user=_user(),
    )
    submitted = DocumentPayload(
        knowledge_type="DOCUMENT",
        blocks=[
            DocumentBlock(id="block-a", title="stale", markdown="stale", block_revision=99),
            DocumentBlock(id="block-new", title="New", markdown="new", block_revision=99),
        ],
        structure_revision=1,
        tags=[],
        datasource_neutral=True,
        object_references=[],
    )
    saved = service.save_document_structure(
        tenant_id=7,
        knowledge_base_id=11,
        draft_version_id=draft.id,
        structure_revision=1,
        payload=submitted,
        actor_id=1,
        current_user=_user(),
    )
    assert saved.payload["tags"] == ["hidden"]
    assert saved.payload["datasource_neutral"] is False
    assert saved.payload["object_references"] == [{"object_type": "TABLE", "schema": "public", "table": "orders"}]
    blocks = {item["id"]: item for item in saved.payload["blocks"]}
    assert blocks["block-a"]["title"] == "A"
    assert blocks["block-a"]["block_revision"] == 1
    assert blocks["block-new"]["block_revision"] == 1
    assert repo.audits[-1]["operation_types"] == ["ADD_BLOCK"]
    assert repo.audits[-1]["added_block_ids"] == ["block-new"]


def test_document_block_audit_records_disable_and_structure_delete():
    repo = _FakeRepo()
    service = _service(repo)
    draft = service.create_draft(
        tenant_id=7, knowledge_base_id=11, payload=_multi_block_payload(), actor_id=1, current_user=_user()
    )
    service.save_document_block(
        tenant_id=7, knowledge_base_id=11, draft_version_id=draft.id,
        block_id="block-a", block_revision=1, title="A", markdown="A0",
        enabled=False, actor_id=9, current_user=_user(),
    )
    structure = _multi_block_payload().model_copy(update={
        "blocks": [_multi_block_payload().blocks[1]],
    })
    service.save_document_structure(
        tenant_id=7, knowledge_base_id=11, draft_version_id=draft.id,
        structure_revision=1, payload=structure, actor_id=9, current_user=_user(),
    )

    assert repo.audits[0]["operation_types"] == ["DISABLE_BLOCK"]
    assert repo.audits[0]["actor_id"] == 9
    assert repo.audits[1]["operation_types"] == ["DELETE_BLOCK"]
    assert repo.audits[1]["deleted_block_ids"] == ["block-a"]


def test_document_structure_audit_records_reordered_block_ids():
    repo = _FakeRepo()
    service = _service(repo)
    draft = service.create_draft(
        tenant_id=7, knowledge_base_id=11, payload=_multi_block_payload(), actor_id=1, current_user=_user()
    )
    reordered = _multi_block_payload().model_copy(update={
        "blocks": list(reversed(_multi_block_payload().blocks)),
    })
    service.save_document_structure(
        tenant_id=7, knowledge_base_id=11, draft_version_id=draft.id,
        structure_revision=1, payload=reordered, actor_id=9, current_user=_user(),
    )

    assert repo.audits[0]["operation_types"] == ["REORDER_BLOCKS"]
    assert repo.audits[0]["reordered_block_ids"] == ["block-b", "block-a"]


def test_document_block_audit_persists_redacted_transaction_scoped_detail():
    class _AuditSession:
        def __init__(self):
            self.added = []
            self.flushes = 0

        def add(self, value):
            self.added.append(value)

        def flush(self):
            self.flushes += 1

    session = _AuditSession()
    audit = KnowledgeVersionRepository(session).add_document_block_audit(
        record=SimpleNamespace(id=11, tenant_id=7, name="Revenue rules"),
        version=SimpleNamespace(id=100, version_number=3, revision=5),
        actor_id=9,
        operation_types=["UPDATE_BLOCK", "DISABLE_BLOCK"],
        block_ids=["block-a"],
    )

    assert session.added == [audit]
    assert session.flushes == 1
    assert audit.tenant_id == 7
    assert audit.user_id == 9
    assert audit.resource_id == "11"
    assert audit.resource_name == "Revenue rules"
    detail = json.loads(audit.operation_detail)
    assert detail == {
        "added_block_ids": [],
        "block_ids": ["block-a"],
        "deleted_block_ids": [],
        "document_id": 11,
        "operation_types": ["UPDATE_BLOCK", "DISABLE_BLOCK"],
        "reordered_block_ids": [],
        "version_id": 100,
        "version_number": 3,
        "version_revision": 5,
    }


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
    assert result.archived is False
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
    assert archived.archived_record.active is False
    assert archived.archived_record.current_version_id is None
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
    assert archived.archived_record.draft_version_id is None


def test_permanent_delete_requires_archive_and_returns_source_file_ids():
    repo = _FakeRepo()
    service = _service(repo)
    draft = service.create_draft(
        tenant_id=7, knowledge_base_id=11, payload=_payload(), actor_id=1, current_user=_user()
    )
    draft.file_id = "draft.md"
    with pytest.raises(KnowledgeBusinessError) as caught:
        service.permanently_delete_archived(
            tenant_id=7, knowledge_base_id=11, current_user=_user()
        )
    assert caught.value.code == "KNOWLEDGE_PERMANENT_DELETE_REQUIRES_ARCHIVE"

    repo.record.archived = True
    result = service.permanently_delete_archived(
        tenant_id=7, knowledge_base_id=11, current_user=_user()
    )
    assert result.archived is False
    assert result.source_file_ids == ("draft.md",)
    assert repo.record is None


def test_permanent_delete_uses_existing_management_permission_boundary():
    repo = _FakeRepo()
    repo.record.archived = True

    with pytest.raises(KnowledgeBusinessError) as caught:
        _service(repo).permanently_delete_archived(
            tenant_id=7,
            knowledge_base_id=11,
            current_user=_user(role="member"),
        )

    assert caught.value.code == "KNOWLEDGE_FORBIDDEN"
    assert repo.record is not None


def test_restore_uses_latest_previously_published_version_and_reenables_retrieval():
    repo = _FakeRepo()
    service = _service(repo)
    older = SimpleNamespace(
        id=1000,
        knowledge_base_id=11,
        tenant_id=7,
        version_number=1,
        status=KnowledgeVersionStatus.ARCHIVED,
        publish_time=datetime.now() - timedelta(days=2),
    )
    latest = SimpleNamespace(
        id=1001,
        knowledge_base_id=11,
        tenant_id=7,
        version_number=2,
        status=KnowledgeVersionStatus.ARCHIVED,
        publish_time=datetime.now() - timedelta(days=1),
    )
    discarded_draft = SimpleNamespace(
        id=1002,
        knowledge_base_id=11,
        tenant_id=7,
        version_number=3,
        status=KnowledgeVersionStatus.ARCHIVED,
        publish_time=None,
    )
    repo.versions = {item.id: item for item in (older, latest, discarded_draft)}
    repo.record.archived = True
    repo.record.active = False
    repo.record.current_version_id = None
    repo.record.draft_version_id = None

    restored = service.restore(
        tenant_id=7,
        knowledge_base_id=11,
        actor_id=9,
        current_user=_user(),
    )

    assert restored.archived is False
    assert restored.active is True
    assert restored.current_version_id == latest.id
    assert restored.draft_version_id is None
    assert restored.publishing_version_id is None
    assert restored.update_by == 9
    assert latest.status == KnowledgeVersionStatus.PUBLISHED
    assert older.status == KnowledgeVersionStatus.ARCHIVED
    assert discarded_draft.status == KnowledgeVersionStatus.ARCHIVED


def test_restore_without_previously_published_version_is_explicit_conflict():
    repo = _FakeRepo()
    repo.record.archived = True
    service = _service(repo)

    with pytest.raises(KnowledgeBusinessError) as caught:
        service.restore(
            tenant_id=7,
            knowledge_base_id=11,
            actor_id=9,
            current_user=_user(),
        )

    assert caught.value.code == "KNOWLEDGE_RESTORE_VERSION_NOT_FOUND"
    assert caught.value.status_code == 409


def test_restore_is_idempotent_for_current_record():
    repo = _FakeRepo()
    repo.record.current_version_id = 77
    result = _service(repo).restore(
        tenant_id=7,
        knowledge_base_id=11,
        actor_id=9,
        current_user=_user(),
    )
    assert result is repo.record
    assert result.current_version_id == 77


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
