from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session
from fastapi.testclient import TestClient
from starlette.middleware.cors import CORSMiddleware

from apps.knowledge_base.api import knowledge_base as api
from apps.knowledge_base.models import KnowledgeBase, KnowledgeBaseStatusEnum
from test_knowledge_base_upload import workspace, upload, process, get_document


def download(workspace, document):
    return workspace.client.get(f"/knowledge-base/{document['id']}/download")


def test_missing_source_is_recreated_from_body_and_reused(workspace):
    document = upload(workspace, content="# 指标\n\n中文正文", active="false").json()
    process(workspace, document)
    before = get_document(workspace)
    Path(api.settings.UPLOAD_DIR, before["file_id"]).unlink()

    response = download(workspace, document)

    assert response.status_code == 200, response.text
    assert response.content.decode("utf-8") == "# 指标\n\n中文正文"
    assert response.headers["x-knowledge-document-recovered"] == "true"
    after = get_document(workspace)
    saved = Path(api.settings.UPLOAD_DIR, after["file_id"])
    assert saved.read_text(encoding="utf-8") == "# 指标\n\n中文正文"
    assert after["file_ext"] == ".md"
    for key in ("active", "status", "content", "uploaded_by", "uploaded_by_name", "update_time", "task_id"):
        assert after[key] == before[key]
    second = download(workspace, document)
    assert second.status_code == 200
    assert second.content == response.content
    assert get_document(workspace)["file_id"] == after["file_id"]
    assert list(Path(api.settings.UPLOAD_DIR).iterdir()) == [saved]


def test_legacy_body_without_file_identity_can_be_downloaded(workspace):
    with Session(workspace.engine) as session:
        record = KnowledgeBase(name="历史术语", tenant_id=23, active=False,
                               status=KnowledgeBaseStatusEnum.READY, content="历史正文")
        session.add(record)
        session.commit()
        session.refresh(record)
        document = {"id": record.id}

    response = download(workspace, document)

    assert response.status_code == 200, response.text
    assert response.content.decode("utf-8") == "历史正文"
    assert get_document(workspace)["file_id"]
    assert get_document(workspace)["uploaded_by"] is None


def test_lost_word_source_exports_a_markdown_body_with_matching_name(workspace):
    with Session(workspace.engine) as session:
        record = KnowledgeBase(name="术语", tenant_id=23, active=True,
                               status=KnowledgeBaseStatusEnum.READY, content="Word 中的正文",
                               file_id="lost.docx", file_name="业务术语.docx", file_ext=".docx")
        session.add(record)
        session.commit()
        session.refresh(record)
        document = {"id": record.id}

    response = download(workspace, document)

    assert response.status_code == 200, response.text
    assert response.content.decode("utf-8") == "Word 中的正文"
    assert "业务术语_正文.md" in unquote(response.headers["content-disposition"])
    assert response.headers["content-type"].startswith("text/markdown")
    assert "content-disposition" in response.headers["access-control-expose-headers"].lower()
    restored = get_document(workspace)
    assert restored["file_name"] == "业务术语_正文.md"
    assert restored["file_ext"] == ".md"
    assert restored["file_id"].endswith(".md")


def test_existing_source_bytes_and_metadata_are_preserved(workspace):
    document = upload(workspace, content="原始文件", active="false").json()
    process(workspace, document)
    before = get_document(workspace)
    with Session(workspace.engine) as session:
        record = session.get(KnowledgeBase, document["id"])
        record.content = "数据库正文不同"
        session.add(record)
        session.commit()

    response = download(workspace, document)

    assert response.status_code == 200, response.text
    assert response.content.decode("utf-8") == "原始文件"
    assert get_document(workspace)["file_id"] == before["file_id"]
    assert get_document(workspace)["file_name"] == "document.md"


def test_multichunk_download_is_complete_and_closes_the_file(workspace, monkeypatch):
    body = "中文分块内容" * 20000
    document = upload(workspace, content=body, active="false").json()
    sources = []
    prepare = api._knowledge_download_file

    def capture_source(session, record):
        response = prepare(session, record)
        sources.append(response.source)
        return response

    monkeypatch.setattr(api, "_knowledge_download_file", capture_source)

    response = download(workspace, document)

    assert response.status_code == 200, response.text
    assert response.content == body.encode("utf-8")
    assert int(response.headers["content-length"]) == len(body.encode("utf-8"))
    assert sources[0].closed


def test_replacement_after_recovery_does_not_break_the_selected_download(workspace, monkeypatch):
    document = upload(workspace, content="下载选中的正文", active="false").json()
    process(workspace, document)
    Path(api.settings.UPLOAD_DIR, document["file_id"]).unlink()
    recover = api._knowledge_download_file

    def replace_before_response(session, record):
        selected_file = recover(session, record)
        replacement = upload(workspace, id=document["id"], content="之后上传的新正文", active="false")
        assert replacement.status_code == 200, replacement.text
        return selected_file

    monkeypatch.setattr(api, "_knowledge_download_file", replace_before_response)

    response = download(workspace, document)

    assert response.status_code == 200, response.text
    assert response.content.decode("utf-8") == "下载选中的正文"
    assert "document_正文.md" in unquote(response.headers["content-disposition"])
    latest = get_document(workspace)
    assert latest["status"] == "READY"
    assert latest["content"] == "之后上传的新正文"
    assert latest["file_name"] == "document.md"


def test_cross_origin_download_exposes_the_actual_filename(workspace):
    document = upload(workspace, content="跨域正文", active="false").json()
    process(workspace, document)
    Path(api.settings.UPLOAD_DIR, document["file_id"]).unlink()
    app = CORSMiddleware(workspace.client.app, allow_origins=["http://localhost:5173"],
                         allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

    with TestClient(app) as client:
        response = client.get(f"/knowledge-base/{document['id']}/download",
                              headers={"Origin": "http://localhost:5173"})

    assert response.status_code == 200, response.text
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "content-disposition" in response.headers["access-control-expose-headers"].lower()
    assert response.content.decode("utf-8") == "跨域正文"


@pytest.mark.parametrize("body", [None, "", " \n\t "])
def test_missing_source_without_body_reports_an_explicit_error(workspace, body):
    with Session(workspace.engine) as session:
        record = KnowledgeBase(name="无正文", tenant_id=23, active=False,
                               status=KnowledgeBaseStatusEnum.READY, content=body)
        session.add(record)
        session.commit()
        session.refresh(record)
        document = {"id": record.id}

    response = download(workspace, document)

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "knowledge_file_not_found"
    assert "正文" in response.json()["detail"]["message"]
    assert list(Path(api.settings.UPLOAD_DIR).iterdir()) == []


def test_unfinished_body_is_not_exported_as_a_recovered_document(workspace):
    with Session(workspace.engine) as session:
        record = KnowledgeBase(name="处理中", tenant_id=23, active=False,
                               status=KnowledgeBaseStatusEnum.PROCESSING, content="未完成正文")
        session.add(record)
        session.commit()
        session.refresh(record)
        document = {"id": record.id}

    response = download(workspace, document)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "knowledge_content_not_ready"
    assert list(Path(api.settings.UPLOAD_DIR).iterdir()) == []


def test_other_workspace_cannot_trigger_file_recovery(workspace):
    document = upload(workspace, active="false").json()
    process(workspace, document)
    Path(api.settings.UPLOAD_DIR, document["file_id"]).unlink()
    workspace.user.tenant_id = 24

    response = download(workspace, document)

    assert response.status_code == 404
    assert list(Path(api.settings.UPLOAD_DIR).iterdir()) == []


@pytest.mark.parametrize("failure", ["write", "commit"])
def test_failed_recovery_does_not_leave_a_file_or_change_identity(workspace, monkeypatch, failure):
    document = upload(workspace, active="false").json()
    process(workspace, document)
    before = get_document(workspace)
    Path(api.settings.UPLOAD_DIR, before["file_id"]).unlink()

    def fail(*args, **kwargs):
        if failure == "write":
            raise PermissionError("test upload directory is read-only")
        raise SQLAlchemyError("test commit failed")

    with monkeypatch.context() as patch:
        if failure == "write":
            patch.setattr(api.os, "replace", fail)
        else:
            patch.setattr(Session, "commit", fail)
        response = download(workspace, document)

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "knowledge_file_recovery_failed"
    assert get_document(workspace)["file_id"] == before["file_id"]
    assert list(Path(api.settings.UPLOAD_DIR).iterdir()) == []
