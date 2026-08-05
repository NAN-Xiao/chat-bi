from apps.analysis_assistant.api.analysis_assistant import (
    PLAN_PROMPT,
    FORECAST_PLAN_PROMPT,
    CHART_TYPES as ANALYSIS_CHART_TYPES,
)
from apps.chat.models.chat_model import AiModelQuestion
from apps.dashboard.crud.ai_sql_generator import _dashboard_sql_system_prompt
from apps.template.generate_chart.generator import get_chart_template
from apps.template.template import get_sql_template
from common.utils.chart_config import CHART_TYPES as SHARED_CHART_TYPES


def test_grouped_column_is_a_supported_platform_chart_type() -> None:
    assert "grouped_column" in SHARED_CHART_TYPES
    assert "grouped_column" in ANALYSIS_CHART_TYPES


def test_smart_qa_prompts_define_explicit_grouped_column_semantics() -> None:
    question = AiModelQuestion(engine="PostgreSQL", db_schema="【DB_ID】 test\n【Schema】")
    sql_rules = question.sql_sys_question("postgresql")["rules"]
    chart_rules = get_chart_template()["generate_rules"]
    combined = f"{sql_rules}\n{chart_rules}"

    assert "分组柱状图(grouped_column)" in combined
    assert '"type":"grouped_column"' in chart_rules
    assert "明确要求分组、并排或同组比较" in combined
    assert "不能仅因为结果包含多个字段" in combined


def test_analysis_and_dashboard_prompts_accept_grouped_column() -> None:
    assert "grouped_column" in PLAN_PROMPT
    assert "grouped_column" in FORECAST_PLAN_PROMPT
    assert "grouped_column" in _dashboard_sql_system_prompt()
    assert "grouped_column" in get_sql_template("oracle")["template"]["process_check"]
