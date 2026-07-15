from types import SimpleNamespace

from apps.datasource.api.datasource import (
    DatasourceFieldListItem,
    _field_list_item_from_tracking,
    _is_selectable_field_list_item,
    _tracking_display_name,
)


def _tracking_json_field(*, aliases: list[str] | None = None):
    return SimpleNamespace(
        field_name="adinfo.adId",
        aliases=aliases or [],
        field_comment="来源字段 adinfo 中的 JSON 属性 adId",
        field_role="json_path_dimension",
        semantic_type="text",
        source_field="adinfo",
        json_path="$.adId",
        expression=None,
        category=None,
        value_mappings=None,
        example_values=None,
    )


def test_field_list_item_filters_top_level_json_container_fields() -> None:
    """
    是什么：验证字段下拉接口不会把顶层 JSON/对象组容器当成可筛选字段。
    谁调用：pytest 回归测试字段候选项过滤逻辑。
    做了什么：物理类型是 varchar、语义类型是 json 时，应被识别为容器并过滤。
    """
    item = DatasourceFieldListItem(
        id=1,
        field_name="abtest",
        field_type="varchar",
        display_name="AB实验",
        semantic_type="json",
        source_field="abtest",
        is_json_subfield=False,
    )

    assert _is_selectable_field_list_item(item) is False


def test_field_list_item_keeps_json_leaf_subfields() -> None:
    """
    是什么：验证 JSON 子字段仍可作为筛选字段。
    谁调用：pytest 回归测试字段候选项过滤逻辑。
    做了什么：同样来自 JSON 容器，但有 source_field 和 json_path 的叶子字段应保留。
    """
    item = DatasourceFieldListItem(
        id="tracking:event:abtest.1001",
        field_name="abtest.1001",
        field_type="JSON字段",
        display_name="1001",
        semantic_type="json",
        source_field="abtest",
        json_path="$.1001",
        is_json_subfield=True,
    )

    assert _is_selectable_field_list_item(item) is True


def test_tracking_json_field_does_not_use_comment_as_display_name() -> None:
    item = _field_list_item_from_tracking(
        _tracking_json_field(),
        datasource=SimpleNamespace(type="mysql", type_name="MySQL"),
        table=SimpleNamespace(table_name="event", ds_id=6, id=10),
        field_index=1,
    )

    assert item.display_name is None
    assert item.field_name == "adinfo.adId"
    assert item.custom_comment == "来源字段 adinfo 中的 JSON 属性 adId"


def test_tracking_json_field_prefers_explicit_alias() -> None:
    item = _field_list_item_from_tracking(
        _tracking_json_field(aliases=["广告 ID"]),
        datasource=SimpleNamespace(type="mysql", type_name="MySQL"),
        table=SimpleNamespace(table_name="event", ds_id=6, id=10),
        field_index=1,
    )

    assert item.display_name == "广告 ID"


def test_tracking_display_name_keeps_physical_comment_fallback() -> None:
    row = SimpleNamespace(aliases=[], field_comment="业务日期（分区字段），按天统计")
    assert _tracking_display_name(row) == "业务日期（分区字段）"
