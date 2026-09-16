"""Concurrency regression tests; use an isolated, disposable PostgreSQL database."""
import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from threading import Barrier, BrokenBarrierError

import pytest
from fastapi import BackgroundTasks, UploadFile
from sqlmodel import Session

from apps.knowledge_base.api import knowledge_base as api
from apps.knowledge_base import tasks
from apps.knowledge_base.context import build_knowledge_context
from test_knowledge_base_upload import workspace, upload, process, get_document

pytestmark = pytest.mark.skipif(not os.getenv("KNOWLEDGE_TEST_POSTGRES_URL"), reason="requires disposable PostgreSQL")


def test_concurrent_replacements_do_not_block_the_api_event_loop(workspace, monkeypatch):
    document = upload(workspace, active="false").json()

    async def save_file(file):
        # Match the yield made by reading a disk-spooled UploadFile.
        await asyncio.sleep(0.05)
        return file.filename, file.filename, ".md"

    monkeypatch.setattr(api, "_save_upload", save_file)

    async def save(filename):
        with Session(workspace.engine) as session:
            return await api.save_knowledge_base(
                session, workspace.user, BackgroundTasks(), id=document["id"], name="文档",
                description="", active=False, visibility_scope="ADMIN_PUBLIC", tenant_id=23,
                file=UploadFile(filename=filename, file=BytesIO(b"body")),
            )

    async def concurrent():
        first = asyncio.create_task(save("first.md"))
        await asyncio.sleep(0.01)
        second = asyncio.create_task(save("second.md"))
        return await asyncio.gather(first, second)

    results = asyncio.run(concurrent())
    assert len(results) == 2
    assert get_document(workspace)["file_id"] == "second.md"


def test_parallel_processing_cannot_exceed_combined_context_capacity(workspace, monkeypatch):
    monkeypatch.setattr(api.settings, "KNOWLEDGE_CONTEXT_MAX_CHARS", 2000)
    first = upload(workspace, content="a" * 1000, active="true").json()
    second = upload(workspace, content="b" * 1000, active="true").json()
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
        futures = [pool.submit(process, workspace, item) for item in (first, second)]
        for future in futures:
            future.result(timeout=5)
    documents = workspace.client.get("/knowledge-base/list", params={"visibility_scope": "ADMIN_PUBLIC"}).json()
    assert sum(document["active"] for document in documents) == 1
    assert any("超过" in (document["error_message"] or "") for document in documents)
    with Session(workspace.engine) as session:
        context = build_knowledge_context(session, tenant_id=23, surface="test")
        assert context.total_chars <= 2000
