"""Opt-in real engine checks. Only constant SELECT/UNION ALL data is queried."""
import os

import pytest
from sqlalchemy import create_engine, text

from apps.dashboard.crud.distribution_sql_compiler import compile_distribution_sql
from distribution_sql_fixture import config, plan, property_config, simultaneous
from test_distribution_sql_compiler import parameters


@pytest.mark.parametrize("dialect,env",[("mysql","DISTRIBUTION_TEST_MYSQL_DSN"),
    ("starrocks","DISTRIBUTION_TEST_STARROCKS_DSN"),("doris","DISTRIBUTION_TEST_DORIS_DSN")])
@pytest.mark.parametrize("aggregation",["count","median","variance","percentile_95"])
def test_native_engine_aggregates_and_buckets(dialect,env,aggregation):
    dsn=os.environ.get(env)
    if not dsn: pytest.skip(f"{env} not configured; compile/parse coverage does not imply execution coverage")
    c=config() if aggregation=="count" else property_config(aggregation)
    c["distribution"]["interval"]["mode"]="auto"
    sql=parameters(compile_distribution_sql(plan(c,dialect=dialect)))
    source="events AS ("+" UNION ALL ".join(
        f"SELECT 'A' AS subject, 'A' AS action, 20260901 AS dt, NULL AS category, {v} AS amount, NULL AS tag, NULL AS occurred_at, NULL AS payload"
        for v in (1,2,4,9))+"), "
    engine=create_engine(dsn)
    try:
        with engine.connect() as conn:
            rows=conn.execute(text("WITH "+source+sql[5:])).mappings().all()
            assert len(rows)==1 and rows[0]["entity_count"]==rows[0]["total_entities"]==1
            expected={"count":4,"median":3,"variance":9.5,"percentile_95":8.25}[aggregation]
            assert float(rows[0]["interval_label"])==pytest.approx(expected)
    finally:
        engine.dispose()
