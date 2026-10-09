"""Concurrency regression tests; use an isolated, disposable PostgreSQL database."""
import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from threading import Barrier, BrokenBarrierError

import pytest
from fastapi import HTTPException, UploadFile
from sqlmodel import Session

from apps.knowledge_base.api import knowledge_base as api
from apps.knowledge_base import tasks
from apps.knowledge_base.context import build_knowledge_context
from test_knowledge_base_upload import workspace, upload, process, get_document

pytestmark = pytest.mark.skipif(not os.getenv("KNOWLEDGE_TEST_POSTGRES_URL"), reason="requires disposable PostgreSQL")


def test_concurrent_replacements_do_not_block_the_api_event_loop(workspace, monkeypatch):
    document = upload(workspace, active="false").json()
    original_save = api._save_upload

    async def save_file(file):
        # Match the yield made by reading a disk-spooled UploadFile.
        await asyncio.sleep(0.05)
        return await original_save(file)

    monkeypatch.setattr(api, "_save_upload", save_file)

    async def save(filename):
        with Session(workspace.engine) as session:
            return await api.save_knowledge_base(
                session, workspace.user, id=document["id"], name="文档",
                description="", active=False, visibility_scope="ADMIN_PUBLIC", tenant_id=23,
                file=UploadFile(filename=filename, file=BytesIO(b"body")),
            )

    async def concurrent():
        first = asyncio.create_task(save("first.md"))
        await asyncio.sleep(0.01)
        second = asyncio.create_task(save("second.md"))
        return await asyncio.gather(first, second, return_exceptions=True)

    results = asyncio.run(concurrent())
    assert len(results) == 2
    for result in results:
        if isinstance(result, HTTPException):
            assert result.status_code == 409
            assert result.detail["code"] == "knowledge_upload_superseded"
        else:
            assert not isinstance(result, Exception), result
            assert result.status == "READY"
    assert not isinstance(results[1], Exception)
    latest = get_document(workspace)
    assert latest["file_name"] == "second.md"
    assert latest["status"] == "READY"
    assert latest["content"] == "body"


def test_parallel_processing_cannot_exceed_combined_context_capacity(workspace, monkeypatch):
    monkeypatch.setattr(api.settings, "KNOWLEDGE_CONTEXT_MAX_CHARS", 2000)
    extraction_barrier = Barrier(2)
    validation_barrier = Barrier(2)
    original_extract = tasks._extract_content

    def extract(record):
        content = original_extract(record)
        extraction_barrier.wait(timeout=3)
        return content

    def validate(*args, **kwargs):
        context = build_knowledge_context(*args, **kwargs)
        # Both unprotected validations would finish before either transaction
        # commits. Serialized validations legitimately time out at this barrier.
        try:
            validation_barrier.wait(timeout=0.5)
        except BrokenBarrierError:
            pass
        return context

    monkeypatch.setattr(tasks, "_extract_content", extract)
    monkeypatch.setattr(tasks, "build_knowledge_context", validate)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(upload, workspace, content=body, active="true")
                   for body in ("a" * 1000, "b" * 1000)]
        for future in futures:
            response = future.result(timeout=10)
            assert response.status_code == 200, response.text
            assert response.json()["status"] == "READY"
            assert response.json()["task_id"] is None
    documents = workspace.client.get("/knowledge-base/list", params={"visibility_scope": "ADMIN_PUBLIC"}).json()
    assert sum(document["active"] for document in documents) == 1
    assert any("超过" in (document["error_message"] or "") for document in documents)
    with Session(workspace.engine) as session:
        context = build_knowledge_context(session, tenant_id=23, surface="test")
        assert context.total_chars <= 2000


def test_concurrent_downloads_recover_only_one_source_file(workspace, monkeypatch):
    document = upload(workspace, content="并发恢复正文", active="false").json()
    process(workspace, document)
    Path(api.settings.UPLOAD_DIR, document["file_id"]).unlink()
    boundary = Barrier(2)
    recover = api._knowledge_download_file

    def simultaneous_recovery(session, record):
        boundary.wait(timeout=3)
        return recover(session, record)

    monkeypatch.setattr(api, "_knowledge_download_file", simultaneous_recovery)

    async def download():
        with Session(workspace.engine) as session:
            return await api.download_knowledge_base_file(
                session, workspace.user, id=document["id"], tenant_id=None,
            )

    async def concurrent():
        return await asyncio.gather(download(), download())

    async def read_responses():
        responses = await concurrent()
        bodies = [b"".join([chunk async for chunk in response.body_iterator]) for response in responses]
        return responses, bodies

    responses, bodies = asyncio.run(read_responses())
    assert sum(response.headers["x-knowledge-document-recovered"] == "true" for response in responses) == 1
    assert responses[0].headers["content-disposition"] == responses[1].headers["content-disposition"]
    assert bodies == ["并发恢复正文".encode("utf-8")] * 2
    restored = get_document(workspace)
    assert list(Path(api.settings.UPLOAD_DIR).iterdir()) == [Path(api.settings.UPLOAD_DIR, restored["file_id"])]
