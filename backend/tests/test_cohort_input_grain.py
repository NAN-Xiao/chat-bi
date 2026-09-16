"""Cohort membership must be unique before it meets observation detail rows."""
import pytest

from apps.dashboard.crud import ai_sql_generator


def _config(model="revenue", groups=None):
    event = lambda name: {"kind": "tracking-event", "eventTable": "events", "eventNameField": "kind", "eventName": name, "field": "kind"}
    return {"analysis_model": model, "time": {"date_parameter_type": "date"}, "groups": groups or [],
            "revenue": {"entityField": {"table": "events", "field": "uid"}, "initialEvent": event("Entered"), "paymentEvent": event("Paid"), "observationDays": 7, "metric": {"method": "property_sum"}},
            "retention": {"entityField": {"table": "events", "field": "uid"}, "initialEvent": event("Entered"), "returnEvent": event("Paid")}}


def _query(cohort="SELECT dt AS cohort_date, uid AS entity_id FROM events WHERE kind='Entered'", *, payment="SELECT dt AS payment_date, uid AS entity_id, amount FROM events WHERE kind='Paid'", extra_cte="", source="cohort", groups=False):
    group = ", c.group_1" if groups else ""
    return f"""WITH cohort AS ({cohort}), payments AS ({payment}) {extra_cte},
    matched AS (SELECT c.cohort_date, c.entity_id, p.payment_date, p.amount{group}
      FROM {source} c LEFT JOIN payments p ON c.entity_id=p.entity_id AND p.payment_date>=c.cohort_date)
    SELECT cohort_date, COUNT(DISTINCT entity_id) AS cohort_size,
      """ + ", ".join(f"SUM(amount) AS day_{day}" for day in range(8)) + " FROM matched GROUP BY cohort_date"


def _issues(sql, model="revenue", groups=None):
    result = getattr(ai_sql_generator, f"_{model}_sql_result_issues")(sql, _config(model, groups), sql_dialect="mysql")
    return [issue for issue in result if "唯一粒度" in issue]


@pytest.mark.parametrize("model", ["revenue", "retention"])
def test_rejects_duplicate_initial_events_before_observation_join(model):
    assert _issues(_query(), model)


@pytest.mark.parametrize("cohort", [
    "SELECT DISTINCT dt AS cohort_date, uid AS entity_id FROM events WHERE kind='Entered'",
    "SELECT dt AS cohort_date, uid AS entity_id FROM events WHERE kind='Entered' GROUP BY dt, uid",
    "SELECT dt AS cohort_date, uid AS entity_id FROM events WHERE kind='Entered' GROUP BY cohort_date, entity_id",
    "SELECT dt AS cohort_date, uid AS entity_id FROM events WHERE kind='Entered' GROUP BY 1, 2",
])
def test_accepts_distinct_or_grouped_membership(cohort):
    assert _issues(_query(cohort)) == []


def test_distinct_with_unconfigured_event_id_does_not_prove_membership_unique():
    assert _issues(_query("SELECT DISTINCT dt AS cohort_date, uid AS entity_id, event_id FROM events WHERE kind='Entered'"))


def test_grouped_with_unconfigured_event_id_does_not_prove_membership_unique():
    assert _issues(_query("SELECT dt AS cohort_date, uid AS entity_id, event_id FROM events WHERE kind='Entered' GROUP BY dt,uid,event_id"))


def test_traces_membership_through_renamed_pass_through_cte():
    sql = _query("SELECT DISTINCT dt AS cohort_date, uid AS entity_id FROM events WHERE kind='Entered'", extra_cte=", membership AS (SELECT cohort_date, entity_id FROM cohort)", source="membership")
    assert _issues(sql) == []
    assert _issues(sql.replace("SELECT DISTINCT dt", "SELECT dt"))


def test_preserves_every_payment_detail_row_instead_of_deduplicating_amounts():
    import sqlite3
    sql = _query("SELECT DISTINCT dt AS cohort_date, uid AS entity_id FROM events WHERE kind='Entered'")
    assert _issues(sql) == []
    with sqlite3.connect(":memory:") as connection:
        connection.execute("CREATE TABLE events(dt TEXT, uid TEXT, kind TEXT, amount NUMERIC)")
        connection.executemany("INSERT INTO events VALUES (?,?,?,?)", [
            ("2026-09-01", "a", "Entered", None), ("2026-09-01", "a", "Entered", None),
            ("2026-09-01", "a", "Paid", 6), ("2026-09-01", "a", "Paid", 6),
        ])
        row = connection.execute(sql).fetchone()
    assert row[1:3] == (1, 12)  # One member, two genuine payments of the same amount.


def test_configured_group_is_part_of_membership_key():
    groups = [{"table": "events", "field": "segment"}]
    sql = _query("SELECT DISTINCT dt AS cohort_date, uid AS entity_id, segment AS group_1 FROM events WHERE kind='Entered'", groups=True)
    assert _issues(sql, groups=groups) == []
    assert _issues(sql)  # Extra dimensions can replicate an entity within the requested cohort.


def test_dead_distinct_cte_does_not_hide_the_actual_duplicate_join():
    sql = _query(extra_cte=", unused_unique AS (SELECT DISTINCT cohort_date,entity_id FROM cohort)")
    assert _issues(sql)


def test_later_distinct_does_not_undo_payment_amount_already_aggregated():
    sql = _query().replace("SELECT cohort_date, COUNT", "SELECT DISTINCT cohort_date, COUNT")
    assert _issues(sql)


def test_joining_more_rows_after_distinct_membership_invalidates_uniqueness():
    sql = _query("SELECT DISTINCT dt AS cohort_date, uid AS entity_id FROM events WHERE kind='Entered'", extra_cte=", membership AS (SELECT c.cohort_date,c.entity_id FROM cohort c JOIN events extra ON c.entity_id=extra.uid)", source="membership")
    assert _issues(sql)


def test_single_event_in_filter_does_not_bypass_grain_validation():
    sql = _query().replace("kind='Entered'", "kind IN ('Entered')").replace("kind='Paid'", "kind IN ('Paid')")
    assert _issues(sql)


def test_initial_and_observation_can_be_the_same_configured_event():
    sql = _query().replace("kind='Paid'", "kind='Entered'")
    config = _config("retention")
    config["retention"]["returnEvent"] = config["retention"]["initialEvent"]
    issues = ai_sql_generator._retention_sql_result_issues(sql, config, sql_dialect="mysql")
    assert any("唯一粒度" in issue for issue in issues)


@pytest.mark.parametrize("operation", ["payment_distinct", "sum_distinct"])
def test_rejects_deduplicating_real_payments_as_a_fanout_workaround(operation):
    sql = _query("SELECT DISTINCT dt AS cohort_date, uid AS entity_id FROM events WHERE kind='Entered'")
    if operation == "payment_distinct":
        sql = sql.replace("payments AS (SELECT dt", "payments AS (SELECT DISTINCT dt")
    else:
        sql = sql.replace("SUM(amount)", "SUM(DISTINCT amount)")
    assert _issues(sql)


def test_cohort_summary_join_to_observation_summary_is_not_another_detail_join():
    sql = _query("SELECT DISTINCT dt AS cohort_date, uid AS entity_id FROM events WHERE kind='Entered'")
    sql = sql[:sql.index("    SELECT cohort_date, COUNT(DISTINCT entity_id) AS cohort_size,")] + """,
    sizes AS (SELECT cohort_date,COUNT(DISTINCT entity_id) cohort_size FROM cohort GROUP BY cohort_date),
    amounts AS (SELECT cohort_date,SUM(amount) total FROM matched GROUP BY cohort_date)
    SELECT s.cohort_date,s.cohort_size,""" + ",".join(f"a.total AS day_{day}" for day in range(8)) + " FROM sizes s LEFT JOIN amounts a ON s.cohort_date=a.cohort_date"
    assert _issues(sql) == []
