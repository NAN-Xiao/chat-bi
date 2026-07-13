"""验证 tracking 采集端字段被统一清理。"""
import importlib.util
from pathlib import Path

from apps.system.crud import tracking_config
from apps.system.models.tenant import TenantTrackingConfigModel
from apps.system.schemas.tenant_schema import TenantTrackingConfigDTO


def test_event_mapping_sanitizer_removes_collect_side_without_mutating_input() -> None:
    mappings = [
        {"event_name": "login", "collect_side": "client"},
        {"event_name": "pay", "collectSide": "server"},
        "plain_event",
    ]

    cleaned = tracking_config._sanitize_event_name_mappings(mappings)

    assert cleaned == [
        {"event_name": "login"},
        {"event_name": "pay"},
        "plain_event",
    ]
    assert mappings[0]["collect_side"] == "client"
    assert mappings[1]["collectSide"] == "server"


def test_tracking_config_dto_hides_legacy_collect_side() -> None:
    row = TenantTrackingConfigModel(
        id=1001,
        tenant_id=2001,
        datasource_id=3,
        event_name_mappings=[
            {"event_name": "login", "collect_side": "client", "collectSide": "server"}
        ],
    )

    dto = tracking_config._config_dto(row, tenant_id=2001, datasource_id=3)

    assert dto.event_name_mappings == [{"event_name": "login"}]


def test_tracking_prompt_hides_collect_side_from_direct_config() -> None:
    config = TenantTrackingConfigDTO(
        tenant_id=2001,
        datasource_id=3,
        enabled=True,
        event_name_mappings=[
            {"event_name": "login", "collect_side": "client", "collectSide": "server"}
        ],
    )

    context, _ = tracking_config.build_tracking_prompt_context(config)

    assert "collect_side" not in context
    assert "collectSide" not in context


def test_collect_side_migration_cleans_json_and_follows_head() -> None:
    migration_path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "143_remove_tracking_collect_side.py"
    )
    spec = importlib.util.spec_from_file_location("remove_tracking_collect_side", migration_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.revision == "143trackingcollectside"
    assert module.down_revision == "142trackinggroups"
    sql = str(module.CLEAN_EVENT_MAPPINGS_SQL)
    assert "WITH ORDINALITY" in sql
    assert "- 'collect_side'" in sql
    assert "- 'collectSide'" in sql
    assert "ORDER BY item_order" in sql
