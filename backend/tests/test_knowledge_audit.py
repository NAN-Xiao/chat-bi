"""Audit writers never persist query or knowledge bodies."""

from __future__ import annotations

from types import SimpleNamespace
from datetime import datetime

from apps.knowledge_base.audit import write_retrieval_audit, write_semantic_context_audit
from apps.knowledge_base.retrieval import KnowledgeCitation, KnowledgeRetrievalResult
from apps.knowledge_base.retrieval import KnowledgeRetrievalService
from apps.datasource.crud.permission_scope import PermissionScopeSnapshot


class _Session:
    def __init__(self):
        self.rows = []

    def add(self, row):
        self.rows.append(row)

    def flush(self):
        return None


def _snapshot():
    return PermissionScopeSnapshot(
        tenant_id=2,
        user_id=8,
        datasource_id=10,
        permission_version="permission-1",
        schema_hash="schema-1",
        allowed_object_keys=frozenset(),
        denied_object_keys=frozenset(),
        row_constraints_hash="rows-1",
    )


def test_retrieval_audit_is_redacted():
    session = _Session()
    result = KnowledgeRetrievalResult(
        query_hash="query-hash",
        model_signature="model",
        citations=(
            KnowledgeCitation(7, 20, 21, "收入", 0.9, "secret body", "ADMIN_PUBLIC"),
        ),
        context="secret body",
        warnings=("检索告警",),
        failure_type="RuntimeError",
    )
    write_retrieval_audit(
        session=session,
        request_id="request-1",
        surface="SMART_QA",
        snapshot=_snapshot(),
        result=result,
    )
    payload = session.rows[0].model_dump_json()
    assert "secret body" not in payload
    assert "query-hash" in payload
    assert '"chunk_id":"7"' in payload


def test_semantic_context_audit_is_redacted():
    session = _Session()
    semantic = SimpleNamespace(
        permission_snapshot=_snapshot(),
        knowledge_citations=[KnowledgeCitation(7, 20, 21, "收入", 0.9, "secret body", "ADMIN_PUBLIC")],
        selected_skills=[SimpleNamespace(skill_id=31, selection_mode="AUTOMATIC", source_hash="skill-hash")],
        warnings=["检索告警"],
    )
    write_semantic_context_audit(
        session=session,
        request_id="request-1",
        surface="AI_DASHBOARD_SQL",
        semantic=semantic,
    )
    payload = session.rows[0].model_dump_json()
    assert "secret body" not in payload
    assert "skill-hash" in payload
    assert "permission-1" in payload


def test_retrieval_audit_failure_does_not_escape():
    service = KnowledgeRetrievalService(audit_writer=_raise_audit)
    service._audit(
        "SMART_QA",
        _snapshot(),
        KnowledgeRetrievalResult(
            query_hash="query-hash", model_signature=None, citations=(), context=""
        ),
        datetime.utcnow(),
        request_id="request-1",
        user_id=8,
    )


def _raise_audit(**_kwargs):
    raise RuntimeError("audit unavailable")
