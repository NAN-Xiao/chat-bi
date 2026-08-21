import pytest
from sqlglot import parse_one

from apps.datasource.crud.sql_permission import validate_sql_columns
from apps.system.crud.tracking_expression import compile_tracking_json_expression
from common.sql_json_paths import (
    canonical_json_field_name,
    extract_json_accesses,
    json_paths_intersect,
    normalize_json_path,
)


def _access_tuples(result):
    return {
        (item.table_alias, item.source_field, item.json_path)
        for item in result.accesses
    }


def test_json_path_parent_child_intersection_is_structural():
    assert normalize_json_path("money") == "$.money"
    assert json_paths_intersect("$.payment", "$.payment.money") is True
    assert json_paths_intersect("$.payment.money", "$.payment") is True
    assert json_paths_intersect("$.payment.money", "$.payment.channel") is False


def test_special_json_key_keeps_bracket_notation():
    assert normalize_json_path('$["a-b"]') == '$["a-b"]'
    assert json_paths_intersect('$["a-b"]', '$["a-b"].money') is True
    assert json_paths_intersect('$["a-b"]', '$["other"]') is False


def test_numeric_json_object_key_uses_quoted_bracket_notation():
    assert normalize_json_path("$.1001") == '$["1001"]'
    assert normalize_json_path('$["1001"]') == '$["1001"]'
    assert json_paths_intersect("$.1001", '$["1001"]') is True
    assert json_paths_intersect("$.1001", '$["1002"]') is False


@pytest.mark.parametrize(
    ("json_path", "expected_name"),
    [
        ('$["1001"]', "abtest.1001"),
        ("$[1001]", "abtest[1001]"),
        ("$.items[0].sku", "payload.items[0].sku"),
        ('$["a-b"]', 'payload["a-b"]'),
    ],
)
def test_canonical_json_field_name_preserves_key_and_index_identity(
    json_path,
    expected_name,
):
    source_field = "abtest" if "1001" in json_path else "payload"

    assert canonical_json_field_name(source_field, json_path) == expected_name


def test_mysql_json_extract_returns_static_access():
    statement = parse_one(
        "SELECT JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.money')) FROM event e",
        read="mysql",
    )

    result = extract_json_accesses(statement, dialect="mysql")

    assert _access_tuples(result) == {("e", "personal", "$.money")}
    assert result.issues == ()


def test_dynamic_json_path_is_reported_as_unresolved():
    statement = parse_one(
        "SELECT JSON_EXTRACT(e.personal, e.path) FROM event e",
        read="mysql",
    )

    result = extract_json_accesses(statement, dialect="mysql")

    assert result.accesses == ()
    assert result.issues[0].reason == "dynamic_path"


def test_postgres_hash_operator_returns_complete_path():
    statement = parse_one(
        "SELECT e.personal::jsonb #>> '{payment,money}' FROM event e",
        read="postgres",
    )

    result = extract_json_accesses(statement, dialect="postgres")

    assert _access_tuples(result) == {("e", "personal", "$.payment.money")}
    assert result.issues == ()


def test_postgres_nested_arrow_operators_merge_path():
    statement = parse_one(
        "SELECT e.personal::jsonb -> 'payment' ->> 'money' FROM event e",
        read="postgres",
    )

    result = extract_json_accesses(statement, dialect="postgres")

    assert _access_tuples(result) == {("e", "personal", "$.payment.money")}
    assert result.issues == ()


def test_postgres_numeric_arrow_operand_preserves_key_or_index_type():
    object_statement = parse_one(
        "SELECT e.abtest::jsonb ->> '1001' FROM event e",
        read="postgres",
    )
    array_statement = parse_one(
        "SELECT e.abtest::jsonb ->> 1001 FROM event e",
        read="postgres",
    )

    object_result = extract_json_accesses(object_statement, dialect="postgres")
    array_result = extract_json_accesses(array_statement, dialect="postgres")

    assert _access_tuples(object_result) == {("e", "abtest", '$["1001"]')}
    assert _access_tuples(array_result) == {("e", "abtest", "$[1001]")}
    assert object_result.issues == ()
    assert array_result.issues == ()


def test_postgres_numeric_hash_path_is_reported_as_ambiguous():
    statement = parse_one(
        "SELECT e.abtest::jsonb #>> '{1001}' FROM event e",
        read="postgres",
    )

    result = extract_json_accesses(statement, dialect="postgres")

    assert result.accesses == ()
    assert result.issues[0].reason == "ambiguous_numeric_path"


@pytest.mark.parametrize(
    ("json_path", "expected_path"),
    [
        ('$.outer["1001"]', '$.outer["1001"]'),
        ('$["1001"].leaf', '$["1001"].leaf'),
        ("$.outer[2]", "$.outer[2]"),
        ("$[2].leaf", "$[2].leaf"),
    ],
)
def test_postgres_compiled_nested_numeric_path_round_trips(json_path, expected_path):
    compiled = compile_tracking_json_expression(
        "event_log",
        "payload",
        json_path,
        "text",
        "postgresql",
    )
    statement = parse_one(f"SELECT {compiled} FROM event_log", read="postgres")

    result = extract_json_accesses(statement, dialect="postgres")

    assert _access_tuples(result) == {("event_log", "payload", expected_path)}
    assert result.issues == ()


def test_postgres_compiled_quoted_comma_key_round_trips():
    compiled = compile_tracking_json_expression(
        "event_log",
        "payload",
        '$["a,b"]',
        "text",
        "postgresql",
    )
    statement = parse_one(f"SELECT {compiled} FROM event_log", read="postgres")

    result = extract_json_accesses(statement, dialect="postgres")

    assert compiled == '("event_log"."payload"::jsonb ->> \'a,b\')'
    assert _access_tuples(result) == {("event_log", "payload", '$["a,b"]')}
    assert result.issues == ()


def test_clickhouse_json_value_returns_static_access():
    statement = parse_one(
        "SELECT JSON_VALUE(e.personal, '$.money') FROM event e",
        read="clickhouse",
    )

    result = extract_json_accesses(statement, dialect="clickhouse")

    assert _access_tuples(result) == {("e", "personal", "$.money")}
    assert result.issues == ()


def test_mysql_special_json_key_returns_static_access():
    statement = parse_one(
        "SELECT JSON_EXTRACT(e.personal, '$[\"a-b\"]') FROM event e",
        read="mysql",
    )

    result = extract_json_accesses(statement, dialect="mysql")

    assert _access_tuples(result) == {("e", "personal", '$["a-b"]')}
    assert result.issues == ()


def test_denied_physical_json_container_still_blocks_subfield_access():
    statement = parse_one(
        "SELECT JSON_EXTRACT(e.personal, '$.channel') FROM event e",
        read="mysql",
    )
    scope = {
        "event": {
            "fields": {"uid"},
            "denied_fields": {"personal"},
            "denied_json_paths": {},
        }
    }

    with pytest.raises(ValueError, match="无权限字段"):
        validate_sql_columns(
            [statement],
            scope,
            current_user=None,
            enforce=True,
            dialect="mysql",
        )


def test_current_select_extraction_does_not_claim_nested_query_accesses():
    statement = parse_one(
        "SELECT e.uid, (SELECT JSON_EXTRACT(x.payload, '$.money') FROM audit x) "
        "FROM event e",
        read="mysql",
    )

    result = extract_json_accesses(
        statement,
        dialect="mysql",
        current_select_only=True,
    )

    assert result.accesses == ()
    assert result.issues == ()
