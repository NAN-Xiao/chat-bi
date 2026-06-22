import json
import os
from types import SimpleNamespace

import orjson

os.environ["LOG_FORMAT"] = "%(asctime)s - %(name)s - %(levelname)s:%(lineno)d - %(message)s"

from apps.chat.task import llm as llm_task
from apps.chat.task.llm import LLMService, _extract_outer_select_aliases


BUSINESS_METRICS_SQL = """
WITH latest_period AS (
  SELECT max(period_date) AS max_date
  FROM fact_orders
),
period_window AS (
  SELECT (max_date - interval '6 days') AS start_date, max_date
  FROM latest_period
),
orders AS (
  SELECT d.department_name AS department, count(*) AS order_count
  FROM fact_orders o
  JOIN dim_department d ON d.department_id = o.department_id
  CROSS JOIN period_window w
  WHERE o.period_date BETWEEN w.start_date AND w.max_date
  GROUP BY d.department_name
),
sales AS (
  SELECT
    d.department_name AS department,
    coalesce(sum(o.sales_amount), 0) AS sales_amount,
    count(*) FILTER (WHERE o.status = 'completed') AS completed_orders
  FROM fact_orders o
  JOIN dim_department d ON d.department_id = o.department_id
  CROSS JOIN period_window w
  WHERE o.period_date BETWEEN w.start_date AND w.max_date
  GROUP BY d.department_name
)
SELECT
  o.department,
  o.order_count AS order_count,
  coalesce(s.sales_amount, 0) AS sales_amount,
  round(coalesce(s.completed_orders, 0)::numeric / nullif(o.order_count, 0) * 100, 2) AS completion_rate,
  round(coalesce(s.sales_amount, 0) / nullif(o.order_count, 0), 4) AS avg_order_value
FROM orders o
LEFT JOIN sales s ON s.department = o.department
ORDER BY o.order_count DESC
LIMIT 1000
"""


class _SessionStub:
    def __init__(self, data: dict):
        self.data = data

    def execute(self, _stmt):
        return self

    def scalar(self):
        return orjson.dumps(self.data).decode()


def test_extract_outer_select_aliases_from_cte_query():
    assert _extract_outer_select_aliases(BUSINESS_METRICS_SQL) == [
        "department",
        "order_count",
        "sales_amount",
        "completion_rate",
        "avg_order_value",
    ]


def test_check_save_chart_completes_missing_multi_metric_y_axis(monkeypatch):
    saved = {}

    def fake_save_chart(*, session, chart, record_id):
        saved["chart"] = json.loads(chart)
        saved["record_id"] = record_id
        return SimpleNamespace(chart=chart)

    monkeypatch.setattr(llm_task, "save_chart", fake_save_chart)

    service = object.__new__(LLMService)
    service.record = SimpleNamespace(id=42)
    service.chat_question = SimpleNamespace(sql=BUSINESS_METRICS_SQL)

    chart_result = json.dumps(
        {
            "type": "column",
            "title": "部门订单统计",
            "axis": {
                "x": {"name": "部门", "value": "department"},
                "y": [{"name": "订单数", "value": "order_count"}],
            },
        },
        ensure_ascii=False,
    )
    data = {
        "fields": ["department", "order_count", "sales_amount", "completion_rate", "avg_order_value"],
        "data": [
            {
                "department": "North",
                "order_count": 393,
                "sales_amount": 1200.5,
                "completion_rate": 89.1,
                "avg_order_value": 3.0547,
            }
        ],
    }
    monkeypatch.setattr(llm_task, "get_chat_chart_data", lambda session, record_id: data)

    chart = service.check_save_chart(_SessionStub(data), chart_result)

    y_values = [item["value"] for item in chart["axis"]["y"]]
    assert y_values == ["order_count", "sales_amount", "completion_rate", "avg_order_value"]
    assert saved["record_id"] == 42
    assert [item["value"] for item in saved["chart"]["axis"]["y"]] == y_values
