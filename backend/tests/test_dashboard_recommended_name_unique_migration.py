"""验证推荐看板名称唯一索引迁移。"""
import importlib.util
from pathlib import Path


def test_recommended_dashboard_name_unique_migration_definition() -> None:
    module_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "144_recommended_dashboard_name_unique.py"
    )
    spec = importlib.util.spec_from_file_location("recommended_dashboard_name_unique", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.revision == "144dashboardname"
    assert module.down_revision == "143trackingcollectside"
    duplicate_sql = str(module.DUPLICATE_RECOMMENDED_NAMES_SQL).lower()
    index_sql = str(module.CREATE_UNIQUE_INDEX_SQL).lower()
    assert "uq_core_dashboard_recommended_name" in index_sql
    assert "tenant_id" in index_sql
    assert "lower(btrim(name))" in index_sql
    assert "coalesce(is_default, 0) = 1" in index_sql
    assert "node_type = 'leaf'" in index_sql
    assert "coalesce(delete_flag, 0) = 0" in index_sql
    assert "coalesce(status, 1) not in (2, 3)" in index_sql
    assert "group by tenant_id, lower(btrim(name))" in duplicate_sql
    assert "having count(*) > 1" in duplicate_sql
