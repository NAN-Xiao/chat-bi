"""验证 ROI 看板单例迁移及模型约束。"""

import importlib.util
from pathlib import Path
from types import ModuleType


def load_migration(filename: str) -> ModuleType:
    module_path = (
        Path(__file__).resolve().parents[1] / "alembic" / "versions" / filename
    )
    spec = importlib.util.spec_from_file_location(module_path.stem, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_roi_singleton_migration_contract() -> None:
    module = load_migration("148_roi_dashboard_singleton.py")

    assert module.revision == "148roisingleton"
    assert module.down_revision == "147refreshsqlgroupingskill"
    assert module.ROI_DASHBOARD_NAME == "ROI 看板"
    assert module.ACTIVE_UNIQUE_INDEX == "uq_core_roi_dashboard_active_tenant"


def test_roi_singleton_upgrade_merges_before_creating_unique_index(monkeypatch) -> None:
    module = load_migration("148_roi_dashboard_singleton.py")
    calls: list[tuple[str, object]] = []

    monkeypatch.setattr(module.op, "execute", lambda statement: calls.append(("execute", str(statement))))
    monkeypatch.setattr(
        module.op,
        "create_index",
        lambda name, table, columns, **kwargs: calls.append(
            ("create_index", (name, table, columns, kwargs))
        ),
    )

    module.upgrade()

    assert [kind for kind, _ in calls] == [
        "execute",
        "execute",
        "execute",
        "execute",
        "create_index",
    ]
    statements = [str(payload) for kind, payload in calls if kind == "execute"]
    assert 'name = \'ROI 看板\'' in statements[0]
    assert "ROW_NUMBER() OVER" in statements[0]
    assert "c.deleted = false" in statements[1]
    assert "c.status = 1" in statements[1]
    assert "c.sort, c.create_time, c.id" in statements[1]
    assert "SET roi_dashboard_id = ordered.canonical_id" in statements[1]
    assert "SET roi_dashboard_id = canonical.canonical_id" in statements[2]
    assert "SET deleted = true" in statements[3]
    assert "status = 0" in statements[3]

    _, index_payload = calls[-1]
    name, table, columns, kwargs = index_payload
    assert name == "uq_core_roi_dashboard_active_tenant"
    assert table == "core_roi_dashboard"
    assert columns == ["tenant_id"]
    assert kwargs["unique"] is True
    assert str(kwargs["postgresql_where"]) == "deleted = false AND status = 1"


def test_roi_dashboard_model_declares_singleton_index() -> None:
    from apps.roi_dashboard.models import CoreRoiDashboard

    index = next(
        item
        for item in CoreRoiDashboard.__table__.indexes
        if item.name == "uq_core_roi_dashboard_active_tenant"
    )
    assert index.unique is True
    assert str(index.dialect_options["postgresql"]["where"]) == (
        "deleted = false AND status = 1"
    )
