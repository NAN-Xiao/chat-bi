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


def test_first_generation_rule_requires_complete_and_unique_aliases() -> None:
    rule = get_base_template()["template"]["sql"]["multi_table_condition"]

    assert "每个FROM/JOIN来源都必须使用唯一且不重复的来源别名" in rule
    assert "必须使用AS声明明确、稳定且在该输出列表中唯一的列别名" in rule
    assert "同一SELECT输出列表不得产生重复列名或重复列别名" in rule
    assert "如果同名列都要输出，必须分别声明不同的输出别名" in rule
    assert "不得在同一查询块的WHERE或JOIN ON中引用该SELECT刚定义的输出别名" in rule


def test_first_generation_rule_requires_recursive_cte_column_contract() -> None:
    rule = get_base_template()["template"]["sql"]["multi_table_condition"]

    assert "MySQL/AnalyticDB 兼容数据源默认禁止生成 WITH RECURSIVE" in rule
    assert "当前数据源能力元数据明确声明且已有执行样例验证支持递归 CTE" in rule
    assert "只有自引用 CTE" in rule
    assert "锚点分支与递归分支的投影数量、顺序和逐列别名一致" in rule


def test_alias_integrity_rule_is_in_first_generation_prompt() -> None:
    rules = AiModelQuestion(
        engine="MySQL 8.0",
        db_schema="【DB_ID】 test\n【Schema】",
    ).sql_sys_question("mysql")["rules"]

    assert "查询块与输出别名完整性规则" in rules
    assert "每个FROM/JOIN来源都必须使用唯一且不重复的来源别名" in rules
    assert "同一SELECT输出列表不得产生重复列名或重复列别名" in rules
    assert "MySQL/AnalyticDB 兼容数据源默认禁止 WITH RECURSIVE" in rules


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
    assert "只有完全不涉及日期字段或日期条件的全量累计指标" in rules
    assert "metric 图表只要涉及日期字段或日期条件，也必须返回" in rules
    assert "禁止用固定日期字面量规避日期选择器" in rules
    assert "所有非 metric 图表都必须返回 time_scope、time_range 和 date_filter" in rules
    assert "直接换算为具体 YYYY-MM-DD 起止日期" in rules
    assert "time_range 必须与 date_filter.date_expression 的静态 range 完全一致" in rules
    assert "SQL 日期边界必须使用与 date_parameter_type 一致的看板日期 token" in rules
    assert "date_filter 存在时不得使用 CURDATE、CURRENT_DATE、NOW" in rules
    assert "用户完全未指定时间时，time_scope=unspecified" in rules
    assert "最近 7 个完整自然日" in rules
    assert "近/最近/过去 N 天" in rules
    assert "不含系统业务日期" in rules
    assert "本周从周一开始并截止系统业务日期" in rules
    assert "不得补到未来周日、未来月末" in rules
    assert "SQL 中不得保留具体日期字面量" in rules
    assert "单日范围也必须使用成对 token" in rules
    assert "实时日期范围规则" in rules
    assert "不得套用默认七天" in rules
    assert "实时代表当前系统业务日并按小时统计" in rules


def test_first_generation_prompt_requires_complete_time_scaffold_and_zero_fill() -> None:
    rules = AiModelQuestion(
        engine="MySQL 8.0",
        db_schema="【DB_ID】 test\n【Schema】",
    ).sql_sys_question("mysql")["rules"]

    assert "必须先生成覆盖起止边界的独立时间骨架" in rules
    assert "时间骨架 CROSS JOIN 分类集合" in rules
    assert "LEFT JOIN 回填" in rules
    assert "COALESCE(聚合指标, 0)" in rules
    assert "MySQL/AnalyticDB 兼容数据源默认禁止 WITH RECURSIVE" in rules
    assert "只有自引用 CTE 需要" in rules
    assert "不得把物理事实表直接按日期、小时或周范围 JOIN 到时间骨架" in rules
    assert "不要把 date_series、calendar、numbers 等查询块名称当成物理表" in rules


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
