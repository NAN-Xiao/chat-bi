"""Data Skill 对象引用权限过滤回归测试。"""

from __future__ import annotations

from types import SimpleNamespace

from apps.chat.curd.skill_object_references import _references_allowed


class _Result:
    def first(self):
        return SimpleNamespace(canonical_key="table:orders")


class _Session:
    def exec(self, statement):
        assert statement.__class__.__name__ == "SelectOfScalar"
        return _Result()


def test_reference_permission_query_returns_model_instead_of_row() -> None:
    snapshot = SimpleNamespace(
        tenant_id=2,
        datasource_id=10,
        schema_hash="schema-1",
        allowed_object_keys=frozenset({"table:orders"}),
        denied_object_keys=frozenset(),
    )
    references = [SimpleNamespace(id=7, datasource_id=10)]

    assert _references_allowed(_Session(), references, snapshot) is True
