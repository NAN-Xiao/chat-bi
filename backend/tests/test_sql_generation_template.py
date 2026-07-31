"""
脚本说明：验证通用 SQL 生成模板中的查询块别名作用域约束。
"""
from apps.template.template import get_base_template
from apps.chat.models.chat_model import AiModelQuestion


def test_multi_table_rule_restricts_aliases_to_current_query_block() -> None:
    rule = get_base_template()["template"]["sql"]["multi_table_condition"]

    assert "每个SELECT查询块只能引用当前查询块FROM/JOIN中可见的表或别名" in rule
    assert "外层查询只能使用子查询别名及该子查询明确输出的列" in rule
    assert "不得引用子查询内部的表别名" in rule


def test_mysql_first_generation_prompt_requires_matching_date_group_expression() -> None:
    rules = AiModelQuestion(
        engine="MySQL 8.0",
        db_schema="【DB_ID】 test\n【Schema】",
    ).sql_sys_question("mysql")["rules"]

    assert "非聚合 DATE_FORMAT 投影" in rules
    assert "直接分组该投影依赖的全部原始字段" in rules
    assert (
        "SELECT DATE_FORMAT(`e`.`dt`, '%Y-%m-%d') AS `日期` "
        "FROM `event` `e` GROUP BY DATE_FORMAT(`e`.`dt`, '%Y%m%d')"
    ) in rules
    assert (
        "SELECT DATE_FORMAT(`e`.`dt`, '%Y-%m-%d') AS `日期` "
        "FROM `event` `e` GROUP BY `e`.`dt`"
    ) in rules
    assert "生成 JSON 前，必须逐个 SELECT 查询块检查" in rules
    assert "DATE_FORMAT(DATE_ADD" in rules


def test_first_generation_prompt_requires_date_filter_for_filtered_category_summary() -> None:
    rules = AiModelQuestion(
        engine="MySQL 8.0",
        db_schema="【DB_ID】 test\n【Schema】",
    ).sql_sys_question("mysql")["rules"]

    assert "即使最终 SELECT 不输出日期列" in rules
    assert "只要 SQL 使用看板日期 token 进行时间范围筛选" in rules
    assert "都必须返回 date_filter" in rules
    assert "只有 SQL 完全不使用日期范围筛选和看板日期 token" in rules


def test_mysql_prompt_requires_backticks_for_chinese_output_aliases() -> None:
    rules = AiModelQuestion(
        engine="MySQL 8.0",
        db_schema="【DB_ID】 test\n【Schema】",
    ).sql_sys_question("mysql")["rules"]

    assert "中文或特殊字符输出别名必须使用反引号" in rules
    assert "单引号表示字符串值" in rules
    assert "AS `注册日期`" in rules
    assert "ORDER BY `注册日期`, `地区`" in rules
    assert "GROUP BY `c`.`register_date`, `c`.`region`" in rules
    assert "上游 CTE 或子查询已经输出中文列" in rules
    assert "GROUP BY `c`.`注册日期`, `c`.`地区`" in rules
    assert "COUNT(*) AS `用户数`" not in rules
