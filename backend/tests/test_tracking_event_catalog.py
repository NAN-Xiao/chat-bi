from apps.system.crud.tracking_config import build_tracking_event_catalog
from apps.system.schemas.tenant_schema import TenantTrackingConfigDTO


def test_build_tracking_event_catalog_groups_events_by_event_category():
    config = TenantTrackingConfigDTO(
        tenant_id=2001,
        datasource_id=3001,
        default_event_table="event",
        default_event_name_field="event_name",
        event_name_mappings=[
            {
                "event_name": "login",
                "event_display_name": "用户登录",
                "event_category": "基础事件",
                "collect_side": "client",
                "collectSide": "server",
                "description": "登录成功后上报",
                "properties": [
                    {
                        "property_name": "ext.allianceId",
                        "property_display_name": "加入联盟",
                        "property_type": "文本",
                        "source_field": "ext",
                        "json_path": "$.allianceId",
                        "description": "加入的联盟 ID",
                    },
                    {
                        "property_name": "ext.abtest",
                        "property_display_name": "AB实验",
                        "property_type": "对象组",
                        "source_field": "ext",
                        "json_path": "$.abtest",
                        "description": "AB 实验对象组",
                    }
                ],
            },
            {
                "event_name": "account_register",
                "event_display_name": "账号注册",
                "event_category": "基础事件",
            },
            {
                "event_name": "battle_end",
                "event_display_name": "战斗结束",
                "event_category": "战斗",
            },
        ],
    )

    catalog = build_tracking_event_catalog(config)

    assert catalog.datasource_id == 3001
    assert catalog.event_table == "event"
    assert catalog.event_name_field == "event_name"
    assert [group.label for group in catalog.groups] == ["基础事件", "战斗"]
    assert [event.event_name for event in catalog.groups[0].events] == ["login", "account_register"]
    assert catalog.groups[0].events[0].display_name == "用户登录"
    assert catalog.groups[0].events[0].description == "登录成功后上报"
    event_payload = catalog.groups[0].events[0].model_dump()
    assert "collect_side" not in event_payload
    assert "collectSide" not in event_payload
    assert catalog.groups[0].events[0].properties[0].display_name == "加入联盟"
    assert catalog.groups[0].events[0].properties[0].property_name == "ext.allianceId"
    assert catalog.groups[0].events[0].properties[0].source_field == "ext"
    assert catalog.groups[0].events[0].properties[0].json_path == "$.allianceId"
    assert catalog.groups[0].events[0].properties[0].value == "tracking-property:event.event_name:login:ext.allianceId"
    assert [item.display_name for item in catalog.groups[0].events[0].properties] == ["加入联盟"]
    assert catalog.groups[1].events[0].value == "tracking-event:event.event_name:battle_end"


def test_build_tracking_event_catalog_uses_default_group_for_uncategorized_events():
    config = TenantTrackingConfigDTO(
        tenant_id=2001,
        default_event_table="event_log",
        default_event_name_field="event",
        event_name_mappings=[
            {"event_name": "online", "event_display_name": "在线数据"},
        ],
    )

    catalog = build_tracking_event_catalog(config)

    assert [group.label for group in catalog.groups] == ["默认分组"]
    assert catalog.groups[0].events[0].event_name == "online"
    assert catalog.groups[0].events[0].value == "tracking-event:event_log.event:online"


def test_build_tracking_event_catalog_does_not_guess_missing_defaults():
    config = TenantTrackingConfigDTO(
        tenant_id=2001,
        event_name_mappings=[{"event_name": "online"}],
    )

    catalog = build_tracking_event_catalog(config)

    assert catalog.event_table == ""
    assert catalog.event_name_field == ""
    assert catalog.groups == []
