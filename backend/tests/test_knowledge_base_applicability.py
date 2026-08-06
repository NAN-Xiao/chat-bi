"""Applicability stays datasource-scoped and fails closed."""

from __future__ import annotations

from types import SimpleNamespace

from apps.datasource.crud.semantic_object_key import DeclaredObjectPath
from apps.knowledge_base.applicability import KnowledgeApplicabilityService
from apps.knowledge_base.object_references import ProjectedObjectReference


class _Session:
    pass


def _version():
    return SimpleNamespace(id=7, knowledge_base_id=9, tenant_id=1)


def _knowledge(scope="PLATFORM_PUBLIC"):
    return SimpleNamespace(id=9, tenant_id=1, visibility_scope=scope)


def _reference():
    return ProjectedObjectReference(
        object_type="TABLE",
        declared_path=DeclaredObjectPath(object_type="TABLE", schema="public", table="orders"),
        declared_key="a" * 64,
        source_kind="EXPLICIT",
    )


def _service(resolver, *, override=None):
    service = KnowledgeApplicabilityService(
        resolver=resolver,
        version_loader=lambda _session, _version_id: _version(),
        knowledge_loader=lambda _session, _kb_id, _tenant_id: _knowledge(),
        reference_loader=lambda _session, _version_id: [_reference()],
        override_loader=lambda _session, _tenant_id, _kb_id: override,
    )
    service._persist = lambda _session, _result: None
    return service


def test_unresolved_reference_is_not_applicable():
    service = _service(lambda *_args, **_kwargs: [SimpleNamespace(status="UNRESOLVED", declared_key="a")])
    result = service.evaluate(
        session=_Session(), tenant_id=2, datasource_id=10, version_id=7, physical_schema_hash="a" * 64
    )
    assert result.status == "INVALID"
    assert not result.eligible


def test_platform_override_can_disable_knowledge_before_resolution():
    resolver_called = []
    service = _service(
        lambda *_args, **_kwargs: resolver_called.append(True),
        override=SimpleNamespace(enabled=False),
    )
    result = service.evaluate(
        session=_Session(), tenant_id=2, datasource_id=10, version_id=7, physical_schema_hash="a" * 64
    )
    assert result.status == "INVALID"
    assert resolver_called == []


def test_empty_reference_set_is_valid_for_current_schema():
    service = KnowledgeApplicabilityService(
        resolver=lambda *_args, **_kwargs: [],
        version_loader=lambda _session, _version_id: _version(),
        knowledge_loader=lambda _session, _kb_id, _tenant_id: _knowledge(),
        reference_loader=lambda _session, _version_id: [],
        override_loader=lambda *_args: None,
    )
    service._persist = lambda _session, _result: None
    result = service.evaluate(
        session=_Session(), tenant_id=2, datasource_id=10, version_id=7, physical_schema_hash="a" * 64
    )
    assert result.status == "VALID"
    assert result.resolved_count == 0
