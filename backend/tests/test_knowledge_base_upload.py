from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path
import runpy
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, Boolean, Column, Integer, MetaData, String, Table, inspect, select
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from apps.knowledge_base.api import knowledge_base as api
from apps.knowledge_base import tasks
from apps.knowledge_base.context import build_knowledge_context
from apps.knowledge_base.models import KnowledgeBase, KnowledgeBaseStatusEnum
from common.core.deps import get_current_user, get_session


@pytest.fixture
def workspace(monkeypatch, tmp_path):
    postgres_url = os.getenv("KNOWLEDGE_TEST_POSTGRES_URL")
    engine = (create_engine(postgres_url, connect_args={"options": "-c lock_timeout=1500ms"}) if postgres_url
              else create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool))
    # SQLite requires INTEGER rather than PostgreSQL BIGINT for generated IDs.
    table = KnowledgeBase.__table__.to_metadata(MetaData())
    if not postgres_url:
        table.c.id.type = Integer()
    table.create(engine)
    user = SimpleNamespace(id=100, name="上传者姓名", account="login_account", tenant_id=23, tenant_role="admin")
    app = FastAPI()
    app.include_router(api.router)

    def session_dependency():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = session_dependency
    app.dependency_overrides[get_current_user] = lambda: user
    monkeypatch.setattr(api, "is_platform_admin", lambda _user: False)
    monkeypatch.setattr(api.settings, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(tasks, "engine", engine)
    monkeypatch.setattr(tasks.AppFileUtils, "get_file_path", lambda file_id: str(tmp_path / file_id))
    monkeypatch.setattr(api, "register_builtin_tasks", lambda: None)

    async def enqueue(*args, **kwargs):
        return {"id": "queued-task"}

    monkeypatch.setattr(api, "enqueue_task", enqueue)
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, engine=engine, user=user)
    table.drop(engine)
    engine.dispose()


def upload(workspace, *, content="有效正文", **data):
    return workspace.client.post(
        "/knowledge-base/save", data={"name": "文档", **data},
        files={"file": ("document.md", content.encode(), "text/markdown")},
    )


def process(workspace, document):
    return tasks.process_knowledge_base_document({
        "id": document["id"], "tenant_id": 23, "file_id": document["file_id"],
    })


def get_document(workspace):
    response = workspace.client.get("/knowledge-base/list", params={"visibility_scope": "ADMIN_PUBLIC"})
    assert response.status_code == 200
    return response.json()[0]


def test_new_upload_defaults_enabled_but_only_ready_content_enters_context(workspace):
    response = upload(workspace)
    assert response.status_code == 200, response.text
    document = response.json()
    assert document["active"] is True
    with Session(workspace.engine) as session:
        assert build_knowledge_context(session, tenant_id=23, surface="test").prompt == ""
    process(workspace, document)
    assert get_document(workspace)["active"] is True
    with Session(workspace.engine) as session:
        assert "有效正文" in build_knowledge_context(session, tenant_id=23, surface="test").prompt


def test_upload_records_name_snapshot_not_login_account_and_metadata_edits_preserve_it(workspace):
    response = upload(workspace, active="false")
    assert response.status_code == 200, response.text
    document = response.json()
    assert document["uploaded_by"] == 100
    assert document["uploaded_by_name"] == "上传者姓名"
    workspace.user.id = 101
    workspace.user.name = "另一位编辑者"
    response = workspace.client.post("/knowledge-base/save", data={"id": document["id"], "name": "改名"})
    assert response.status_code == 200, response.text
    assert response.json()["uploaded_by_name"] == "上传者姓名"
    response = upload(workspace, id=document["id"])
    assert response.status_code == 200, response.text
    assert response.json()["uploaded_by"] == 101
    assert get_document(workspace)["uploaded_by_name"] == "另一位编辑者"


def test_replacing_disabled_document_does_not_reenable_it(workspace):
    document = upload(workspace, active="false").json()
    process(workspace, document)
    response = upload(workspace, id=document["id"])
    assert response.status_code == 200, response.text
    process(workspace, response.json())
    assert get_document(workspace)["active"] is False


def test_enabled_document_can_be_replaced_without_manual_deactivation(workspace):
    response = upload(workspace, active="true")
    assert response.status_code == 200, response.text
    process(workspace, response.json())
    replacement = upload(workspace, id=response.json()["id"], active="true", content="新正文")
    assert replacement.status_code == 200, replacement.text
    process(workspace, replacement.json())
    assert get_document(workspace)["active"] is True
    assert get_document(workspace)["content"] == "新正文"


def test_failed_document_is_disabled_and_excluded_from_context(workspace):
    response = upload(workspace, content="  ", active="true")
    assert response.status_code == 200, response.text
    process(workspace, response.json())
    document = get_document(workspace)
    assert document["status"] == "FAILED"
    assert document["active"] is False
    assert document["error_message"]
    with Session(workspace.engine) as session:
        assert build_knowledge_context(session, tenant_id=23, surface="test").prompt == ""


def test_auto_activation_checks_knowledge_capacity(workspace, monkeypatch):
    monkeypatch.setattr(api.settings, "KNOWLEDGE_CONTEXT_MAX_CHARS", 10)
    response = upload(workspace, active="true")
    assert response.status_code == 200, response.text
    process(workspace, response.json())
    document = get_document(workspace)
    assert document["active"] is False
    assert "超过" in document["error_message"]


def test_processing_does_not_overwrite_manual_deactivation(workspace, monkeypatch):
    response = upload(workspace, active="true")
    assert response.status_code == 200, response.text
    document = response.json()
    original_extract = tasks._extract_content

    def extract(record):
        content = original_extract(record)
        changed = workspace.client.post("/knowledge-base/save", data={
            "id": document["id"], "name": "文档", "active": "false",
        })
        assert changed.status_code == 200, changed.text
        return content

    monkeypatch.setattr(tasks, "_extract_content", extract)
    process(workspace, document)
    assert get_document(workspace)["status"] == "READY"
    assert get_document(workspace)["active"] is False


def test_stale_processing_job_does_not_process_replacement_file(workspace):
    old = upload(workspace, active="false").json()
    new = upload(workspace, id=old["id"], active="false", content="新文件").json()
    process(workspace, old)
    assert get_document(workspace)["status"] == "PENDING"
    process(workspace, new)
    assert get_document(workspace)["content"] == "新文件"


def test_legacy_record_has_no_invented_upload_identity(workspace):
    with Session(workspace.engine) as session:
        session.add(KnowledgeBase(name="历史文档", tenant_id=23, create_by=100, active=False,
                                  status=KnowledgeBaseStatusEnum.READY, content="正文"))
        session.commit()
    document = get_document(workspace)
    assert document["uploaded_by"] is None
    assert document["uploaded_by_name"] is None


def test_queue_acknowledgement_does_not_overwrite_replacement_task(workspace, monkeypatch):
    calls = 0

    async def enqueue(handler, payload, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            with Session(workspace.engine) as session:
                replacement = session.get(KnowledgeBase, payload["id"])
                replacement.file_id = "replacement.md"
                replacement.task_id = "new-task"
                session.add(replacement)
                session.commit()
            return {"id": "old-task"}
        return {"id": "new-task"}

    monkeypatch.setattr(api, "enqueue_task", enqueue)
    response = upload(workspace, active="false")
    assert response.status_code == 200, response.text
    assert get_document(workspace)["task_id"] == "new-task"


def test_replacement_during_extraction_is_not_overwritten(workspace, monkeypatch):
    document = upload(workspace, active="false").json()
    original_extract = tasks._extract_content

    def extract(record):
        content = original_extract(record)
        replacement = upload(workspace, id=document["id"], content="替换文档")
        assert replacement.status_code == 200, replacement.text
        return content

    monkeypatch.setattr(tasks, "_extract_content", extract)
    process(workspace, document)
    latest = get_document(workspace)
    assert latest["status"] == "PENDING"
    assert latest["content"] is None
    assert latest["file_id"] != document["file_id"]


def test_upload_identity_migration_preserves_legacy_rows_and_can_be_reversed():
    engine = create_engine("sqlite://")
    table = Table("knowledge_base", MetaData(), Column("id", Integer, primary_key=True),
                  Column("name", String), Column("active", Boolean), Column("create_by", BigInteger))
    table.create(engine)
    migration = runpy.run_path(str(Path(__file__).parents[1] / "alembic/versions/166_knowledge_base_upload_identity.py"))
    with engine.begin() as connection:
        connection.execute(table.insert().values(id=1, name="历史记录", active=False, create_by=100))
        with Operations.context(MigrationContext.configure(connection)):
            migration["upgrade"]()
        migrated = Table("knowledge_base", MetaData(), autoload_with=connection)
        row = connection.execute(select(migrated)).mappings().one()
        assert row["name"] == "历史记录"
        assert row["active"] is False
        assert row["uploaded_by"] is None
        assert row["uploaded_by_name"] is None
        with Operations.context(MigrationContext.configure(connection)):
            migration["downgrade"]()
        assert {column["name"] for column in inspect(connection).get_columns("knowledge_base")} == {
            "id", "name", "active", "create_by",
        }
    engine.dispose()


def test_legacy_queued_job_only_processes_its_matching_upload(workspace, monkeypatch):
    document = upload(workspace, active="false").json()
    monkeypatch.setattr(tasks, "current_task_context", lambda: {"id": "queued-task", "tenant_id": 23}, raising=False)
    tasks.process_knowledge_base_document({"id": document["id"], "tenant_id": 23})
    assert get_document(workspace)["status"] == "READY"


def test_legacy_job_cannot_override_new_upload_or_explicit_file_identity(workspace, monkeypatch):
    document = upload(workspace, active="false").json()
    monkeypatch.setattr(tasks, "current_task_context", lambda: {"id": "obsolete-task", "tenant_id": 23}, raising=False)
    tasks.process_knowledge_base_document({"id": document["id"], "tenant_id": 23})
    assert get_document(workspace)["status"] == "PENDING"
    monkeypatch.setattr(tasks, "current_task_context", lambda: {"id": "queued-task", "tenant_id": 23})
    tasks.process_knowledge_base_document({"id": document["id"], "tenant_id": 23, "file_id": "obsolete.md"})
    assert get_document(workspace)["status"] == "PENDING"
