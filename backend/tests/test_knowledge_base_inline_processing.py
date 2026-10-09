"""Uploads finish parsing in the API process without submitting worker tasks."""
from io import BytesIO
from pathlib import Path
import zipfile

import pytest

from apps.knowledge_base.api import knowledge_base as api
from apps.knowledge_base import tasks
from common.core import task_queue
from test_knowledge_base_upload import workspace, upload, get_document


@pytest.fixture
def queue_requests(workspace, monkeypatch):
    requests = []

    async def reject_queue(*args, **kwargs):
        requests.append((args, kwargs))
        raise RuntimeError("No queue or worker is available")

    monkeypatch.setattr(api, "enqueue_task", reject_queue, raising=False)
    monkeypatch.setattr(task_queue, "enqueue_task", reject_queue)
    return requests


@pytest.mark.parametrize("active", ["true", "false"])
def test_new_markdown_is_ready_in_upload_response_without_queue(workspace, queue_requests, active):
    response = upload(workspace, content="新建正文", active=active)
    assert response.status_code == 200, response.text
    document = response.json()
    assert queue_requests == []
    assert document["status"] == "READY"
    assert document["content"] == "新建正文"
    assert document["active"] is (active == "true")
    assert document["task_id"] is None
    assert get_document(workspace)["content"] == "新建正文"
    assert Path(api.settings.UPLOAD_DIR, document["file_id"]).is_file()


def test_replacement_finishes_before_response_and_keeps_deactivation(workspace, queue_requests):
    original = upload(workspace, active="false").json()
    response = upload(workspace, id=original["id"], content="替换正文")
    assert response.status_code == 200, response.text
    document = response.json()
    assert queue_requests == []
    assert document["status"] == "READY"
    assert document["content"] == "替换正文"
    assert document["active"] is False
    assert document["task_id"] is None
    assert document["file_id"] != original["file_id"]


def test_word_is_parsed_before_upload_returns(workspace, queue_requests):
    body = BytesIO()
    with zipfile.ZipFile(body, "w") as archive:
        archive.writestr("word/document.xml", '<w:document xmlns:w="urn:word"><w:body>'
                         '<w:p><w:r><w:t>Word 正文</w:t></w:r></w:p></w:body></w:document>')
    response = workspace.client.post("/knowledge-base/save", data={"name": "Word 文档", "active": "false"},
                                     files={"file": ("document.docx", body.getvalue(), "application/octet-stream")})
    assert response.status_code == 200, response.text
    assert queue_requests == []
    assert response.json()["status"] == "READY"
    assert response.json()["content"] == "Word 正文"
    assert response.json()["task_id"] is None


def test_empty_document_returns_final_failure_without_queue(workspace, queue_requests):
    response = upload(workspace, content=" \n\t ", active="true")
    assert response.status_code == 200, response.text
    assert queue_requests == []
    document = response.json()
    assert document["status"] == "FAILED"
    assert document["active"] is False
    assert document["content"] is None
    assert "正文为空" in document["error_message"]
    assert document["task_id"] is None


def test_capacity_validation_is_reported_in_upload_response(workspace, queue_requests, monkeypatch):
    monkeypatch.setattr(api.settings, "KNOWLEDGE_CONTEXT_MAX_CHARS", 10)
    response = upload(workspace, content="有效正文", active="true")
    assert response.status_code == 200, response.text
    assert queue_requests == []
    document = response.json()
    assert document["status"] == "READY"
    assert document["content"] == "有效正文"
    assert document["active"] is False
    assert "超过" in document["error_message"]


@pytest.mark.parametrize("workspace", ["single_connection"], indirect=True)
def test_inline_upload_releases_api_connection_before_processing(workspace):
    response = upload(workspace, active="false")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "READY"


@pytest.mark.parametrize("replace_at", ["during_extraction", "after_processing"])
def test_overlapping_upload_reports_conflict_instead_of_another_uploads_state(workspace, monkeypatch, replace_at):
    replaced = False
    original_extract = tasks._extract_content
    original_process = api.process_knowledge_base_document

    def replace(record_id):
        nonlocal replaced
        if replaced:
            return
        replaced = True
        response = upload(workspace, id=record_id, active="false", content="新的上传正文")
        assert response.status_code == 200, response.text

    def extract(record):
        content = original_extract(record)
        replace(record.id)
        return content

    def process(payload):
        result = original_process(payload)
        replace(payload["id"])
        return result

    if replace_at == "during_extraction":
        monkeypatch.setattr(tasks, "_extract_content", extract)
    else:
        monkeypatch.setattr(api, "process_knowledge_base_document", process)
    response = upload(workspace, active="false", content="旧的上传正文")
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "knowledge_upload_superseded"
    latest = get_document(workspace)
    assert latest["content"] == "新的上传正文"
    assert latest["status"] == "READY"


@pytest.mark.parametrize("delete_at", ["during_extraction", "after_processing"])
def test_deletion_during_or_after_parsing_returns_not_found(workspace, monkeypatch, delete_at):
    original_process = api.process_knowledge_base_document
    original_extract = tasks._extract_content

    def delete(record_id):
        response = workspace.client.delete(f"/knowledge-base/{record_id}")
        assert response.status_code == 200, response.text

    def extract(record):
        content = original_extract(record)
        delete(record.id)
        return content

    def process(payload):
        result = original_process(payload)
        delete(payload["id"])
        return result

    if delete_at == "during_extraction":
        monkeypatch.setattr(tasks, "_extract_content", extract)
    else:
        monkeypatch.setattr(api, "process_knowledge_base_document", process)
    response = upload(workspace, active="false")
    assert response.status_code == 404, response.text
    assert response.json()["detail"]["code"] == "knowledge_not_found"
