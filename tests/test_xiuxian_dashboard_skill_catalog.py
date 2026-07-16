from __future__ import annotations

import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

catalog = importlib.import_module("xiuxian_dashboard_skill_catalog")


def test_catalog_maps_all_nonempty_views_once():
    mapped = [view_id for topic in catalog.TOPICS for view_id in topic.view_ids]

    assert len(catalog.TOPICS) == 12
    assert len(mapped) == 44
    assert len(set(mapped)) == 44
    assert set(mapped) == catalog.EXPECTED_VIEW_IDS
    assert catalog.EMPTY_VIEW_ID not in mapped


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


def test_revenue_and_order_prompts_preserve_business_boundaries():
    topics = {topic.slug: topic for topic in catalog.TOPICS}

    revenue_prompt = catalog.build_topic_prompt(topics["serverpaylog-revenue"])
    orders_prompt = catalog.build_topic_prompt(topics["orders-products"])

    assert "ServerPayLog" in revenue_prompt
    assert "personal.money" in revenue_prompt
    assert "ServerPayLog" in orders_prompt
    assert "PayBuyRet" in orders_prompt
    assert "流程" in orders_prompt
    assert "真实交易" in orders_prompt
