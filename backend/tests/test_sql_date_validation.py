import pytest

from apps.chat.task.sql_repair import (
    SqlRepairContext,
    SqlStructureValidationError,
    build_sql_repair_message,
    classify_prepare_sql_error,
    validate_sql_for_datasource,
)
from common.utils.sql_date_validation import mysql_temporal_result_fields


@pytest.mark.parametrize('source', [
    "SELECT DATE_FORMAT(business_day, '%Y%m%d') AS encoded FROM orders",
    "SELECT CAST(DATE_FORMAT(business_day, '%Y%m%d') AS SIGNED) AS encoded FROM orders",
    "SELECT '20260908' AS encoded",
    "SELECT 20260908 AS encoded",
])
@pytest.mark.parametrize('wrapper', [
    "WITH dates AS ({source}) SELECT STR_TO_DATE(CAST(dates.encoded AS CHAR), '%Y-%m-%d') AS day FROM dates",
    "SELECT STR_TO_DATE(CAST(nested.encoded AS CHAR), '%Y-%m-%d') AS day FROM ({source}) nested",
    "WITH original AS ({source}), renamed AS (SELECT encoded AS value FROM original) SELECT STR_TO_DATE(value, '%Y-%m-%d') AS day FROM renamed",
    "WITH original AS ({source}), forwarded AS (SELECT * FROM original) SELECT STR_TO_DATE(encoded, '%Y-%m-%d') AS day FROM forwarded",
    "WITH original AS ({source}), forwarded AS (SELECT original.* FROM original) SELECT STR_TO_DATE(encoded, '%Y-%m-%d') AS day FROM forwarded",
])
def test_rejects_proven_date_encoding_conflict(source, wrapper):
    with pytest.raises(SqlStructureValidationError, match='日期'):
        validate_sql_for_datasource(wrapper.format(source=source), 'mysql')


@pytest.mark.parametrize('sql', [
    "SELECT STR_TO_DATE('20260908', '%Y%m%d') AS day",
    "SELECT STR_TO_DATE('2026-09-08', '%Y-%m-%d') AS day",
    "SELECT STR_TO_DATE(raw_value, '%Y-%m-%d') AS day FROM orders",
    "WITH dates AS (SELECT DATE_FORMAT(created_at, '%Y-%m-%d') AS encoded FROM orders) SELECT STR_TO_DATE(encoded, '%Y-%m-%d') FROM dates",
    "WITH dates AS (SELECT '20260908' AS encoded UNION ALL SELECT '2026-09-09') SELECT STR_TO_DATE(encoded, '%Y-%m-%d') FROM dates",
    "WITH dates AS (SELECT '20260908' AS encoded) SELECT STR_TO_DATE(orders.encoded, '%Y-%m-%d') FROM dates JOIN orders ON dates.encoded = orders.encoded",
    "SELECT DATE_FORMAT(STR_TO_DATE('20260908', '%Y%m%d'), '%Y-%m-%d') AS day",
    "SELECT STR_TO_DATE('20260908 12:00:00', '%Y%m%d %H:%i:%s') AS day",
])
def test_preserves_valid_or_unknown_date_formats(sql):
    validate_sql_for_datasource(sql, 'mysql')


def test_date_failure_is_sent_to_repair_with_evidence():
    sql = "SELECT STR_TO_DATE('2026-09-08', '%Y%m%d') AS day"
    with pytest.raises(SqlStructureValidationError) as caught:
        validate_sql_for_datasource(sql, 'mysql')
    reason = classify_prepare_sql_error(caught.value)
    assert reason is not None
    message = build_sql_repair_message(SqlRepairContext(reason, 'mysql', sql, str(caught.value), None, 0))
    assert '%Y-%m-%d' in message
    assert '%Y%m%d' in message


@pytest.mark.parametrize('expression', ["DATE(raw_day)", "CAST(raw_day AS DATE)", "STR_TO_DATE(raw_day, '%Y%m%d')"])
def test_temporal_fields_survive_star_projection(expression):
    sql = f'WITH dates AS (SELECT {expression} AS day, total FROM orders) SELECT * FROM dates'
    assert mysql_temporal_result_fields(sql, 'mysql') == {'day'}


def test_time_only_conversion_is_not_a_calendar_date():
    assert mysql_temporal_result_fields("SELECT STR_TO_DATE(raw_time, '%H:%i:%s') AS clock FROM orders", 'mysql') == set()


@pytest.mark.parametrize('join', ['JOIN second USING(id)', 'NATURAL JOIN second'])
def test_merged_join_columns_do_not_shift_cte_date_encodings(join):
    sql = (
        "WITH first AS (SELECT 20260908 AS id, '20260908' AS enc), "
        "second AS (SELECT 20260908 AS id, '2026-09-08' AS iso), "
        f"combined(id, enc, iso) AS (SELECT * FROM first {join}) "
        "SELECT STR_TO_DATE(iso, '%Y-%m-%d') AS day FROM combined"
    )
    validate_sql_for_datasource(sql, 'mysql')
