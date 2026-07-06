from apps.datasource.api.datasource import (
    DatasourceFieldListItem,
    _is_selectable_field_list_item,
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
