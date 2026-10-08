"""Payer eligibility and metric detail have independent event identities."""
import copy
from datetime import date

import pytest

from apps.dashboard.crud.revenue_sql_plan import RevenueConfigurationError, validate_revenue_input
from revenue_sql_fixture import config, event, field, plan
from test_revenue_sql_postgres import connection, execute


def independent_config(method="property_sum", cost=False):
    result = config(method, cost=cost)
    result["revenue"]["paymentEvent"] = event("paid")
    result["revenue"]["metricEvent"] = event("income")
    if cost: result["revenue"]["cost"]["event"] = event("paid")
    return result


SOURCE = """events(subject, day, event_name, category, amount, cost, payload) AS (VALUES
 ('A',20260901,'start','one',NULL::numeric,NULL::numeric,'{}'::jsonb),
 ('A',20260901,'start','one',NULL,NULL,'{}'),
 ('B',20260901,'start','one',NULL,NULL,'{}'),
 ('C',20260901,'start',NULL,NULL,NULL,'{}'),
 ('A',20260901,'paid','one',999,1,'{}'),
 ('A',20260901,'paid','one',999,2,'{}'),
 ('A',20260902,'paid','one',999,3,'{}'),
 ('C',20260904,'paid',NULL,999,4,'{}'),
 ('A',20260901,'income','one',10,100,'{}'),
 ('A',20260901,'income','one',10,100,'{}'),
 ('A',20260902,'income','one',20,100,'{}'),
 ('B',20260901,'income','one',1000,100,'{}'),
 ('C',20260901,'income',NULL,1000,100,'{}'),
 ('X',20260901,'paid','one',999,1,'{}'),
 ('X',20260901,'income','one',1000,100,'{}'))"""


@pytest.mark.parametrize("method,expected", [
    ("count", [2, 1, 0]), ("entity_count", [1, 1, 0]),
    ("per_entity_count", [2, 1, None]),
    ("period_cumulative_count", [2, 3, 3]), ("period_average_count", [2, 1.5, 1]),
    ("period_cumulative_entity_count", [1, 2, 2]), ("period_average_entity_count", [1, 1, 2/3]),
    ("property_sum", [20, 20, 0]), ("property_avg", [10, 20, None]),
])
def test_metric_event_only_counts_eligible_payers_without_multiplying_detail(connection, method, expected):
    rows = execute(connection, independent_config(method), source=SOURCE)
    assert rows[0][:2] == (date(2026, 9, 1), 3)
    for actual, wanted in zip(rows[0][2:], expected):
        assert actual is None if wanted is None else float(actual) == pytest.approx(wanted)


def test_cost_uses_payment_details_once_and_null_groups_survive(connection):
    conf = independent_config(cost=True)
    conf["groups"] = [field("category")]
    rows = execute(connection, conf, source=SOURCE)
    by_group = {row[-1]: row for row in rows}
    assert by_group["one"] == (date(2026, 9, 1), 2, 20, 20, 0, 6, "one")
    assert by_group[None] == (date(2026, 9, 1), 1, 0, 0, 0, 0, None)


def test_missing_metric_event_is_explicitly_rejected_instead_of_copying_payment_event():
    conf = independent_config()
    del conf["revenue"]["metricEvent"]
    assert any(issue.path == "revenue.metricEvent" for issue in validate_revenue_input(conf))


def test_metric_and_cost_properties_resolve_against_their_own_event():
    conf = independent_config(cost=True)
    conf["revenue"]["metric"]["field"] = {**field("amount"), "eventName": "income"}
    conf["revenue"]["cost"]["field"] = {**field("cost"), "eventName": "paid"}
    actual = plan(conf)
    assert "'income'" in actual.metric_event.predicate
    assert "'paid'" in actual.payment.predicate
    assert actual.metric_event.metric and not actual.payment.metric
    assert actual.cost_event.cost and not actual.payment.cost and not actual.metric_event.cost
    bad = copy.deepcopy(conf)
    bad["revenue"]["metric"]["field"]["eventName"] = "paid"
    with pytest.raises(RevenueConfigurationError):
        plan(bad)


def test_metric_event_cannot_cross_authorized_event_table():
    conf = independent_config()
    conf["revenue"]["metricEvent"]["eventTable"] = "private_events"
    with pytest.raises(RevenueConfigurationError):
        plan(conf)
