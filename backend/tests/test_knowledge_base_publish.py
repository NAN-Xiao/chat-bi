"""Durable publish-job preparation and source-file download contracts."""

from __future__ import annotations

import asyncio
import json
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote

import pytest
from fastapi import UploadFile

from apps.knowledge_base.api import versions
from apps.knowledge_base.errors import KnowledgeBusinessError
from apps.knowledge_base.lifecycle_models import (
    KnowledgeBaseVersion,
    KnowledgeMigrationPhase,
    KnowledgePublishJob,
    KnowledgeVersionStatus,
)
from apps.knowledge_base.markdown_template import KNOWLEDGE_MARKDOWN_PARSER_VERSION
from apps.knowledge_base.models import KnowledgeBase, KnowledgeBaseVisibilityScopeEnum
from apps.knowledge_base.publish_jobs import finalize_publish_job, prepare_publish_job
from apps.knowledge_base.version_repository import (
    KnowledgeVersionRepository,
    SourceFileRef,
)


class _Result:
    def __init__(self, value):
        self.value = value

    def first(self):
        return self.value


class _PublishSession:
    def __init__(self, *, existing_job=None):
        self.record = KnowledgeBase(
            id=11,
            tenant_id=7,
            name="收入知识",
            visibility_scope=KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC,
            draft_version_id=12,
        )
        self.version = KnowledgeBaseVersion(
            id=12,
            knowledge_base_id=11,
            tenant_id=7,
            version_number=1,
            revision=3,
            status=KnowledgeVersionStatus.READY_TO_PUBLISH,
            content_hash="a" * 64,
            payload={"knowledge_type": "DOCUMENT", "markdown": "收入"},
        )
        self.job = existing_job
        self.added = []

    def exec(self, statement):
        sql = str(statement)
        if "knowledge_publish_job" in sql:
            return _Result(self.job)
        if "knowledge_base_version" in sql:
            return _Result(self.version)
        return _Result(self.record)

    def add(self, value):
        self.added.append(value)
        if isinstance(value, KnowledgePublishJob):
            value.id = 99
            self.job = value

    def flush(self):
        return None


def _prepare(session):
    return prepare_publish_job(
        session,
        tenant_id=7,
        knowledge_base_id=11,
        version_id=12,
        revision=3,
        content_hash="a" * 64,
        actor_id=1,
    )


def _valid_markdown(body: str = "有效正文") -> bytes:
    return (
        "# 标题\n\n"
        "## 章节\n\n"
        f"{body}\n"
    ).encode()


def test_duplicate_publish_returns_the_same_database_job():
    session = _PublishSession()
    first = _prepare(session)
    second = _prepare(session)
    assert first.id == 99
    assert second.id == first.id
    assert len(session.added) == 1
    assert session.version.status == "PUBLISHING"
    assert session.record.publishing_version_id == 12


def test_publish_requires_the_latest_ready_snapshot():
    session = _PublishSession()
    session.version.revision = 2
    with pytest.raises(KnowledgeBusinessError) as caught:
        _prepare(session)
    assert caught.value.code == "KNOWLEDGE_VERSION_NOT_READY"
    assert caught.value.message == "知识尚未通过最新校验，请重新校验后发布。"


def test_publish_rejects_a_different_active_job():
    session = _PublishSession(existing_job=None)
    session.record.publishing_version_id = 99
    with pytest.raises(KnowledgeBusinessError) as caught:
        _prepare(session)
    assert caught.value.code == "KNOWLEDGE_PUBLISHING"


def test_finalize_second_version_supersedes_current_version():
    job = KnowledgePublishJob(
        id=99,
        tenant_id=7,
        knowledge_base_id=11,
        version_id=13,
        revision=1,
        content_hash="b" * 64,
        status="RUNNING",
    )
    current = KnowledgeBaseVersion(
        id=12,
        knowledge_base_id=11,
        tenant_id=7,
        version_number=1,
        revision=1,
        status=KnowledgeVersionStatus.PUBLISHED,
        content_hash="a" * 64,
        payload={"knowledge_type": "DOCUMENT", "markdown": "旧版本"},
    )
    target = KnowledgeBaseVersion(
        id=13,
        knowledge_base_id=11,
        tenant_id=7,
        version_number=2,
        revision=1,
        status=KnowledgeVersionStatus.PUBLISHING,
        index_status="READY",
        content_hash="b" * 64,
        payload={"knowledge_type": "DOCUMENT", "markdown": "新版本"},
    )
    record = KnowledgeBase(
        id=11,
        tenant_id=7,
        name="收入知识",
        visibility_scope=KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC,
        current_version_id=12,
        publishing_version_id=13,
        draft_version_id=13,
        active=False,
    )

    class _FinalizeSession:
        def __init__(self):
            self.results = iter((job, target, record, current))

        def exec(self, _statement):
            return _Result(next(self.results))

        def add(self, _value):
            return None

        def add_all(self, _values):
            return None

        def flush(self):
            return None

    assert finalize_publish_job(_FinalizeSession(), job_id=99)
    assert current.status == "SUPERSEDED"
    assert target.status == "PUBLISHED"
    assert record.current_version_id == 13
    assert record.publishing_version_id is None
    assert record.active is True


def test_download_uses_version_binding_and_does_not_expose_storage_id(monkeypatch, tmp_path: Path):
    file_id = "immutable-source.md"
    (tmp_path / file_id).write_text("收入版本", encoding="utf-8")

    class _Result:
        def first(self):
            return SimpleNamespace(
                id=12,
                knowledge_base_id=11,
                tenant_id=7,
                file_id=file_id,
                file_name="收入说明.md",
            )

    class _Session:
        def exec(self, _statement):
            return _Result()

    monkeypatch.setattr(versions, "resolve_record", lambda *_args, **_kwargs: SimpleNamespace(id=11))
    monkeypatch.setattr(versions, "record_tenant_id", lambda *_args, **_kwargs: 7)
    monkeypatch.setattr(versions.settings, "UPLOAD_DIR", str(tmp_path))
    response = asyncio.run(
        versions.download_version_source(
            id=11,
            version_id=12,
            session=_Session(),
            current_user=SimpleNamespace(id=1),
        )
    )
    assert Path(response.path) == tmp_path / file_id
    assert file_id not in response.headers.get("content-disposition", "")
    assert "收入说明.md" in unquote(response.headers["content-disposition"])


def test_conflicting_source_upload_cleans_only_request_staged_file(monkeypatch, tmp_path: Path):
    deleted: list[str] = []

    class _Result:
        def first(self):
            return SimpleNamespace(
                id=12,
                knowledge_base_id=11,
                tenant_id=7,
                payload={"knowledge_type": "DOCUMENT", "markdown": "旧正文"},
            )

    class _Session:
        def exec(self, _statement):
            return _Result()

        def rollback(self):
            return None

    class _Service:
        def save_draft(self, **_kwargs):
            raise KnowledgeBusinessError(
                code="KNOWLEDGE_DRAFT_CONFLICT",
                message="该知识已被其他用户更新，请刷新后重新编辑。",
                status_code=409,
                error_type="CONFLICT",
            )

    monkeypatch.setattr(
        versions,
        "get_capabilities",
        lambda _session: SimpleNamespace(
            phase=KnowledgeMigrationPhase.V2_ACTIVE,
            management_mode="V2",
            v2_write_enabled=True,
        ),
    )
    monkeypatch.setattr(versions, "resolve_record", lambda *_args, **_kwargs: SimpleNamespace(id=11))
    monkeypatch.setattr(versions, "record_tenant_id", lambda *_args, **_kwargs: 7)
    monkeypatch.setattr(versions, "KnowledgeLifecycleService", lambda *_args: _Service())
    monkeypatch.setattr(versions.settings, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(versions.AppFileUtils, "delete_file", lambda file_id: deleted.append(file_id))

    response = asyncio.run(
        versions.replace_draft_source_file(
            id=11,
            session=_Session(),
            current_user=SimpleNamespace(id=1),
            version_id=12,
            revision=1,
            file=UploadFile(filename="new.md", file=BytesIO(_valid_markdown("冲突正文"))),
        )
    )
    assert response.status_code == 409
    assert response.body.decode("utf-8").startswith('{"code":"KNOWLEDGE_DRAFT_CONFLICT"')
    assert len(deleted) == 1
    assert deleted[0].startswith(".knowledge-stage-")


def test_successful_source_upload_reclaims_only_the_previous_file(monkeypatch, tmp_path: Path):
    version = KnowledgeBaseVersion(
        id=12,
        knowledge_base_id=11,
        tenant_id=7,
        version_number=1,
        revision=1,
        status=KnowledgeVersionStatus.DRAFT,
        payload={"knowledge_type": "DOCUMENT", "markdown": "旧正文"},
        file_id="old.md",
        file_name="old.md",
        file_ext=".md",
    )
    saved = KnowledgeBaseVersion(
        id=12,
        knowledge_base_id=11,
        tenant_id=7,
        version_number=1,
        revision=2,
        status=KnowledgeVersionStatus.DRAFT,
        payload={"knowledge_type": "DOCUMENT", "markdown": "新正文"},
        normalized_content="新正文",
        content_hash="a" * 64,
        file_id="new.md",
        file_name="new.md",
        file_ext=".md",
    )

    class _Session:
        def __init__(self):
            self.commits = 0

        def exec(self, _statement):
            return _Result(version)

        def commit(self):
            self.commits += 1

        def rollback(self):
            return None

    source_files: list[SourceFileRef] = []

    class _Service:
        def save_draft(self, **kwargs):
            source_file = kwargs["source_file"]
            source_files.append(source_file)
            saved.parser_version = source_file.parser_version
            return saved

    cleaned = []
    monkeypatch.setattr(versions, "get_capabilities", lambda _session: SimpleNamespace(
        phase=KnowledgeMigrationPhase.V2_ACTIVE,
        management_mode="V2",
        v2_write_enabled=True,
    ))
    monkeypatch.setattr(versions, "resolve_record", lambda *_args, **_kwargs: SimpleNamespace(id=11))
    monkeypatch.setattr(versions, "record_tenant_id", lambda *_args, **_kwargs: 7)
    monkeypatch.setattr(versions, "KnowledgeLifecycleService", lambda *_args: _Service())
    monkeypatch.setattr(versions.settings, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(
        versions,
        "cleanup_unreferenced_source_files",
        lambda _session, file_ids: cleaned.append(tuple(file_ids)),
    )
    session = _Session()

    response = asyncio.run(versions.replace_draft_source_file(
        id=11,
        session=session,
        current_user=SimpleNamespace(id=1),
        version_id=12,
        revision=1,
        file=UploadFile(filename="new.md", file=BytesIO(_valid_markdown("新正文"))),
    ))

    assert response["revision"] == 2
    assert response["parser_version"] == KNOWLEDGE_MARKDOWN_PARSER_VERSION
    assert source_files[0].parser_version == KNOWLEDGE_MARKDOWN_PARSER_VERSION == "markdown-v1"
    assert session.commits == 1
    assert cleaned == [("old.md",)]


def test_repository_persists_source_parser_version_on_replacement():
    version = SimpleNamespace(id=12, parser_version=KNOWLEDGE_MARKDOWN_PARSER_VERSION)

    class _Session:
        def __init__(self):
            self.update_params = {}

        def exec(self, statement):
            if str(statement).lstrip().startswith("UPDATE"):
                self.update_params = statement.compile().params
                return SimpleNamespace(rowcount=1)
            return _Result(version)

        def flush(self):
            return None

    session = _Session()
    saved = KnowledgeVersionRepository(session).save_draft_if_revision_matches(
        tenant_id=7,
        knowledge_base_id=11,
        version_id=12,
        expected_revision=1,
        payload={"knowledge_type": "DOCUMENT", "blocks": []},
        normalized_content="# 标题\n\n## 章节\n\n正文",
        content_hash="a" * 64,
        actor_id=1,
        source_file=SourceFileRef(
            file_id="new.md",
            file_name="new.md",
            file_ext=".md",
            parser_version=KNOWLEDGE_MARKDOWN_PARSER_VERSION,
        ),
    )

    assert saved is version
    assert session.update_params["parser_version"] == "markdown-v1"


def test_invalid_source_upload_is_atomic_and_removes_staged_file(monkeypatch, tmp_path: Path):
    original_payload = {"knowledge_type": "DOCUMENT", "markdown": "旧正文"}
    version = KnowledgeBaseVersion(
        id=12,
        knowledge_base_id=11,
        tenant_id=7,
        version_number=1,
        revision=4,
        status=KnowledgeVersionStatus.DRAFT,
        payload=original_payload.copy(),
        file_id="old.md",
        file_name="old.md",
        file_ext=".md",
    )

    class _Session:
        def __init__(self):
            self.commits = 0
            self.rollbacks = 0

        def exec(self, _statement):
            return _Result(version)

        def commit(self):
            self.commits += 1

        def rollback(self):
            self.rollbacks += 1

    service_calls = 0

    def lifecycle_service(*_args):
        nonlocal service_calls
        service_calls += 1
        raise AssertionError("invalid templates must fail before draft CAS")

    monkeypatch.setattr(versions, "get_capabilities", lambda _session: SimpleNamespace(
        phase=KnowledgeMigrationPhase.V2_ACTIVE,
        management_mode="V2",
        v2_write_enabled=True,
    ))
    monkeypatch.setattr(versions, "resolve_record", lambda *_args, **_kwargs: SimpleNamespace(id=11))
    monkeypatch.setattr(versions, "record_tenant_id", lambda *_args, **_kwargs: 7)
    monkeypatch.setattr(versions, "KnowledgeLifecycleService", lifecycle_service)
    monkeypatch.setattr(versions.settings, "UPLOAD_DIR", str(tmp_path))
    session = _Session()

    response = asyncio.run(versions.replace_draft_source_file(
        id=11,
        session=session,
        current_user=SimpleNamespace(id=1),
        version_id=12,
        revision=4,
        file=UploadFile(filename="invalid.md", file=BytesIO(b"# missing second-level heading")),
    ))

    payload = json.loads(response.body)
    assert response.status_code == 422
    assert payload["code"] == "KNOWLEDGE_MARKDOWN_FORMAT_INVALID"
    assert payload["message"].startswith("格式错误")
    assert version.revision == 4
    assert version.payload == original_payload
    assert version.file_id == "old.md"
    assert session.commits == 0
    assert session.rollbacks == 1
    assert service_calls == 0
    assert list(tmp_path.iterdir()) == []
