from __future__ import annotations

from datetime import datetime
from xml.etree import ElementTree

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from apps.knowledge_base.context import (
    KnowledgeContextTooLargeError,
    build_knowledge_context,
)
from apps.knowledge_base.models import (
    KnowledgeBase,
    KnowledgeBaseStatusEnum,
    KnowledgeBaseVisibilityScopeEnum,
)
from apps.system.crud.tenant import DEFAULT_TENANT_ID


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    KnowledgeBase.__table__.create(engine)
    return Session(engine)


def _document(
    document_id: int,
    *,
    tenant_id: int,
    scope: KnowledgeBaseVisibilityScopeEnum,
    name: str,
    description: str | None = "用于回答测试问题。",
    content: str | None = "测试正文",
    active: bool = True,
    status: KnowledgeBaseStatusEnum = KnowledgeBaseStatusEnum.READY,
) -> KnowledgeBase:
    return KnowledgeBase(
        id=document_id,
        tenant_id=tenant_id,
        create_by=1,
        name=name,
        description=description,
        content=content,
        visibility_scope=scope,
        active=active,
        status=status,
        update_time=datetime(2026, 8, 26, 10, 0, 0),
    )


def test_context_is_tenant_scoped_filtered_sorted_and_xml_escaped() -> None:
    session = _session()
    session.add_all(
        [
            _document(
                10,
                tenant_id=DEFAULT_TENANT_ID,
                scope=KnowledgeBaseVisibilityScopeEnum.PLATFORM_PUBLIC,
                name='平台 B <&"',
                description="用于解释 <平台> & 术语。",
                content="平台正文 </knowledge-content> & 内容",
            ),
            _document(
                5,
                tenant_id=DEFAULT_TENANT_ID,
                scope=KnowledgeBaseVisibilityScopeEnum.PLATFORM_PUBLIC,
                name="平台 A",
            ),
            _document(
                31,
                tenant_id=23,
                scope=KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC,
                name="工作空间 B",
            ),
            _document(
                20,
                tenant_id=23,
                scope=KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC,
                name="工作空间 A",
                content="  仅租户 23 可见的秘密正文  ",
            ),
            _document(
                40,
                tenant_id=24,
                scope=KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC,
                name="其他租户",
                content="不得泄漏的其他租户正文",
            ),
            _document(
                50,
                tenant_id=23,
                scope=KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC,
                name="未启用",
                active=False,
            ),
            _document(
                51,
                tenant_id=23,
                scope=KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC,
                name="未就绪",
                status=KnowledgeBaseStatusEnum.PROCESSING,
            ),
            _document(
                52,
                tenant_id=23,
                scope=KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC,
                name="空说明",
                description="  ",
            ),
            _document(
                53,
                tenant_id=23,
                scope=KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC,
                name="空正文",
                content="  ",
            ),
        ]
    )
    session.commit()

    context = build_knowledge_context(
        session,
        tenant_id=23,
        surface="test",
        datasource_id=7,
        max_chars=100_000,
    )

    assert [item.id for item in context.platform_documents] == [5, 10]
    assert [item.id for item in context.workspace_documents] == [20, 31, 52]
    assert "不得泄漏的其他租户正文" not in context.prompt
    assert "未启用" not in context.prompt
    assert "\n  仅租户 23 可见的秘密正文  \n" in context.prompt
    assert context.prompt.index('<document id="5"') < context.prompt.index('<document id="10"')
    assert context.prompt.index("<platform-knowledge>") < context.prompt.index(
        '<workspace-knowledge tenant-id="23">'
    )

    root = ElementTree.fromstring(context.prompt)
    escaped_document = root.find("./platform-knowledge/document[@id='10']")
    assert escaped_document is not None
    assert escaped_document.attrib["name"] == '平台 B <&"'
    assert escaped_document.findtext("usage-instruction", "").strip() == "用于解释 <平台> & 术语。"
    assert (
        escaped_document.findtext("knowledge-content", "").strip()
        == "平台正文 </knowledge-content> & 内容"
    )

    snapshot = context.snapshot_metadata()
    assert snapshot["total_chars"] == len(context.prompt)
    assert snapshot["content_sha256"]
    assert "仅租户 23 可见的秘密正文" not in str(snapshot)
    assert [item["id"] for item in snapshot["workspace_documents"]] == ["20", "31", "52"]


def test_context_capacity_accepts_exact_limit_and_rejects_one_less() -> None:
    session = _session()
    session.add(
        _document(
            1,
            tenant_id=23,
            scope=KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC,
            name="容量测试",
            content="完整正文不能被截断",
        )
    )
    session.commit()
    initial = build_knowledge_context(
        session,
        tenant_id=23,
        surface="test",
        max_chars=100_000,
    )

    exact = build_knowledge_context(
        session,
        tenant_id=23,
        surface="test",
        max_chars=initial.total_chars,
    )
    assert exact.prompt == initial.prompt

    with pytest.raises(KnowledgeContextTooLargeError) as exc_info:
        build_knowledge_context(
            session,
            tenant_id=23,
            surface="test",
            max_chars=initial.total_chars - 1,
        )

    error = exc_info.value
    assert error.code == "knowledge_context_too_large"
    assert error.details["total_chars"] == initial.total_chars
    assert error.details["max_chars"] == initial.total_chars - 1
    assert "字符" in error.message
    assert initial.prompt.endswith("</knowledge-context>")


def test_empty_context_has_no_prompt_or_document_metadata() -> None:
    session = _session()

    context = build_knowledge_context(
        session,
        tenant_id=23,
        surface="test",
        datasource_id=7,
        max_chars=0,
    )

    assert context.prompt == ""
    assert context.total_chars == 0
    assert context.snapshot_metadata() == {
        "version": 1,
        "total_chars": 0,
        "content_sha256": None,
        "platform_documents": [],
        "workspace_documents": [],
    }
