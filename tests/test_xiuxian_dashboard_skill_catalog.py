from __future__ import annotations

import importlib
import sys
from dataclasses import replace
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

catalog = importlib.import_module("xiuxian_dashboard_skill_catalog")


def test_catalog_maps_all_nonempty_views_once():
    mapped = [view_id for topic in catalog.TOPICS for view_id in topic.view_ids]

    assert len(catalog.TOPICS) == 12
    assert len(mapped) == 42
    assert len(set(mapped)) == 42
    assert set(mapped) == catalog.EXPECTED_VIEW_IDS
    assert "1e4e34743f2d47dfa1c2948742b93a50" not in mapped


def test_current_recommended_dashboard_skill_capacity_is_seventeen_thousand():
    assert catalog.MAX_PROMPT_CHARS == 17_000


def test_catalog_enforces_topic_size():
    catalog.validate_catalog()

    assert all(
        len(topic.view_ids) <= catalog.MAX_SQL_BLOCKS_PER_SKILL
        for topic in catalog.TOPICS
    )


def test_topic_prompt_includes_shared_structure_and_guidance():
    topic = catalog.TOPICS[0]

    prompt = catalog.build_topic_prompt(topic)

    assert topic.guidance in prompt
    assert "## 适用范围" in prompt
    assert "## 日期规则引用" in prompt
    assert "## 业务口径" in prompt
    assert "## 禁止事项" in prompt
    assert "## 推荐输出" in prompt
    assert "## 看板 SQL" in prompt
    assert len(prompt) <= catalog.MAX_PROMPT_CHARS


@pytest.mark.parametrize("topic", catalog.TOPICS, ids=lambda topic: topic.slug)
def test_build_topic_prompt_rejects_every_oversized_topic(topic):
    oversized_topic = replace(topic, guidance="字" * catalog.MAX_PROMPT_CHARS)

    with pytest.raises(ValueError, match="超过字符上限"):
        catalog.build_topic_prompt(oversized_topic)


def test_prompt_length_can_be_checked_again_after_sql_injection():
    prompt_at_limit = "字" * catalog.MAX_PROMPT_CHARS

    catalog.validate_prompt_length(prompt_at_limit)
    with pytest.raises(ValueError, match="超过字符上限"):
        catalog.validate_prompt_length(prompt_at_limit + "字")


def test_revenue_and_order_prompts_preserve_business_boundaries():
    topics = {topic.slug: topic for topic in catalog.TOPICS}

    revenue_prompt = catalog.build_topic_prompt(topics["serverpaylog-revenue"])
    orders_topic = topics["orders-products"]
    orders_prompt = catalog.build_topic_prompt(orders_topic)

    assert "ServerPayLog" in revenue_prompt
    assert "personal.money" in revenue_prompt
    assert orders_topic.name == "修仙订单、礼包、月卡与支付流程"
    assert "月卡" in orders_topic.description
    assert "personal.orderId" in orders_prompt
    assert "personal.productid" in orders_prompt
    assert "月卡购买 cohort 使用 ServerPayLog" in orders_prompt
    assert "留存活跃使用 UserActive" in orders_prompt
    assert "PayBuyRet" in orders_prompt
    assert "流程" in orders_prompt
    assert "真实交易" in orders_prompt


def test_default_date_window_is_generation_only_and_does_not_probe_data():
    prompt = catalog.build_topic_prompt(catalog.TOPICS[0])

    assert "用户未指定日期时" in prompt
    assert "截至昨天的最近 28 个自然日" in prompt
    assert "生成默认规则" in prompt
    assert "不是现场诊断选窗逻辑" in prompt
    assert "不得查询数据中的最大日期或最大分区" in prompt
    assert "MAX(dt)" not in prompt
