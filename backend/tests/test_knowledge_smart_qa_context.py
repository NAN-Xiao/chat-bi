"""Smart Q&A prompts consume the fixed knowledge context snapshot."""

from apps.chat.models.chat_model import AiModelQuestion


def test_sql_and_followup_prompts_include_read_only_knowledge_context():
    knowledge = '<retrieved-knowledge priority="reference-only">收入按净额统计</retrieved-knowledge>'
    question = AiModelQuestion(
        question="收入是多少",
        engine="postgresql",
        db_schema="orders(amount numeric)",
        tracking_config="<Tracking>订单事件</Tracking>",
        data_skill="<Data-Skills>收入求和</Data-Skills>",
        knowledge_context=knowledge,
    )

    assert question.sql_sys_question("postgresql")["knowledge_context"] == knowledge
    assert knowledge in question.chart_user_question()
    assert knowledge in question.analysis_sys_question()
    assert knowledge in question.predict_sys_question()
    sql_prompt = question.sql_sys_question("postgresql")["system"]
    assert "与当前" in sql_prompt
    assert "完全忽略无关片段" in sql_prompt
    assert "知识库信息存在冲突" in sql_prompt

    for prompt in (
        question.chart_sys_question()["system"],
        question.analysis_sys_question(),
        question.predict_sys_question(),
    ):
        assert "完全忽略无关片段" not in prompt
        assert "知识库信息存在冲突" not in prompt
