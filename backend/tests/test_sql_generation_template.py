"""
脚本说明：验证通用 SQL 生成模板中的查询块别名作用域约束。
"""
from apps.template.template import get_base_template


def test_multi_table_rule_restricts_aliases_to_current_query_block() -> None:
    rule = get_base_template()["template"]["sql"]["multi_table_condition"]

    assert "每个SELECT查询块只能引用当前查询块FROM/JOIN中可见的表或别名" in rule
    assert "外层查询只能使用子查询别名及该子查询明确输出的列" in rule
    assert "不得引用子查询内部的表别名" in rule
