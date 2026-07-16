from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest
import sqlglot
from sqlglot import exp


ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = ROOT / "tools"
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "xiuxian_dashboard_sql_repairs.json"
SCALAR_CTES = {"bounds", "weeks", "months"}

if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

repair = importlib.import_module("xiuxian_dashboard_sql_repair")

FIXTURES = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
SQL_BY_VIEW = {item["view_id"]: item["sql"] for item in FIXTURES}


def _parse(sql: str) -> exp.Expression:
    return sqlglot.parse_one(sql, read="mysql")


def _projection_signature(select: exp.Select) -> tuple[str, ...]:
    return tuple(
        expression.alias_or_name or expression.sql(dialect="mysql")
        for expression in select.expressions
    )


def _clause_signature(select: exp.Select, name: str) -> str | None:
    clause = select.args.get(name)
    return clause.sql(dialect="mysql") if clause is not None else None


def _business_join_signature(select: exp.Select) -> tuple:
    return tuple(
        (
            join.this.name.lower(),
            join.this.alias_or_name.lower(),
            join.side.lower(),
            join.kind.lower(),
            join.args["on"].sql(dialect="mysql") if join.args.get("on") else None,
        )
        for join in select.args.get("joins") or []
        if isinstance(join.this, exp.Table)
        and join.this.name.lower() not in SCALAR_CTES
    )


def _surface_signature(sql: str) -> tuple:
    tree = _parse(sql)
    with_clause = tree.args.get("with_")
    business_ctes = []
    if with_clause:
        for cte in with_clause.expressions:
            name = cte.alias_or_name.lower()
            if name in SCALAR_CTES:
                continue
            select = cte.this
            business_ctes.append(
                (
                    name,
                    _projection_signature(select),
                    _business_join_signature(select),
                    _clause_signature(select, "group"),
                    _clause_signature(select, "order"),
                    _clause_signature(select, "limit"),
                )
            )

    root = tree
    return (
        tuple(business_ctes),
        _projection_signature(root),
        _business_join_signature(root),
        _clause_signature(root, "group"),
        _clause_signature(root, "order"),
        _clause_signature(root, "limit"),
    )


def _direct_predicates(select: exp.Select) -> list[exp.Expression]:
    predicates = []
    where = select.args.get("where")
    if where is not None:
        predicates.append(where.this)
    for join in select.args.get("joins") or []:
        on = join.args.get("on")
        if on is not None:
            predicates.append(on)
    return predicates


def _direct_tables(select: exp.Select) -> list[exp.Table]:
    tables = []
    from_clause = select.args.get("from_")
    if from_clause is not None and isinstance(from_clause.this, exp.Table):
        tables.append(from_clause.this)
    tables.extend(
        join.this
        for join in select.args.get("joins") or []
        if isinstance(join.this, exp.Table)
    )
    return tables


def _has_direct_dt_predicate(select: exp.Select, alias: str) -> bool:
    for predicate in _direct_predicates(select):
        for column in predicate.find_all(exp.Column):
            if column.table.lower() == alias.lower() and column.name.lower() == "dt":
                return True
    return False


def _event_partition_predicate(sql: str) -> str:
    tree = _parse(sql)
    for select in tree.find_all(exp.Select):
        aliases = {
            table.alias_or_name.lower()
            for table in _direct_tables(select)
            if table.name.lower() == "event"
        }
        for predicate in _direct_predicates(select):
            columns = list(predicate.find_all(exp.Column))
            if any(
                column.table.lower() in aliases and column.name.lower() == "dt"
                for column in columns
            ):
                return predicate.sql(dialect="mysql")
    raise AssertionError("未找到 event.dt 分区谓词")


def test_fixture_is_exactly_the_eleven_whitelisted_sql_statements():
    assert len(FIXTURES) == 11
    assert {item["view_id"] for item in FIXTURES} == set(repair.REPAIR_SPECS)
    assert {
        item["view_id"]: item["sql_sha256"] for item in FIXTURES
    } == repair.REPAIR_SOURCE_HASHES


def test_unknown_view_fails_closed():
    with pytest.raises(repair.SourceSqlChangedError, match="白名单"):
        repair.rewrite_bounds_sql("unknown-view", next(iter(SQL_BY_VIEW.values())))


def test_source_byte_drift_fails_closed():
    view_id = "95d8497afac14f0a90342031fb43bc04"
    with pytest.raises(repair.SourceSqlChangedError, match="SHA-256"):
        repair.rewrite_bounds_sql(view_id, SQL_BY_VIEW[view_id] + "\n")


def test_rewrite_removes_direct_bounds_join():
    view_id = "95d8497afac14f0a90342031fb43bc04"
    rewritten = repair.rewrite_bounds_sql(view_id, SQL_BY_VIEW[view_id])
    tree = _parse(rewritten)

    assert not any(
        table.name.lower() == "bounds" for table in tree.find_all(exp.Table)
    )
    assert "u.dt BETWEEN" in rewritten


def test_rewrite_resolves_nested_calendar_cte():
    view_id = "0369399df2eb4a3299d6d34f9663101b"
    rewritten = repair.rewrite_bounds_sql(view_id, SQL_BY_VIEW[view_id])

    assert not any(
        table.name.lower() == "bounds"
        for table in _parse(rewritten).find_all(exp.Table)
    )
    assert "e.dt BETWEEN" in rewritten
    assert "latest_week_start" not in _event_partition_predicate(rewritten)


def test_rewrite_preserves_bounds_value_used_by_downstream_join():
    view_id = "fc272fe6a3a74cda90a0564a98890fab"
    rewritten = repair.rewrite_bounds_sql(view_id, SQL_BY_VIEW[view_id])

    assert "b.max_dt" not in rewritten
    assert "latest.dt" in rewritten


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda item: item["view_id"])
def test_all_whitelisted_sql_rewrites_preserve_surface_and_partition_guards(fixture):
    original = fixture["sql"]
    rewritten = repair.rewrite_bounds_sql(fixture["view_id"], original)
    tree = _parse(rewritten)

    assert _surface_signature(rewritten) == _surface_signature(original)
    assert not any(
        table.name.lower() in SCALAR_CTES for table in tree.find_all(exp.Table)
    )
    assert not any(
        isinstance(function, exp.Max)
        and any(column.name.lower() == "dt" for column in function.find_all(exp.Column))
        for function in tree.find_all(exp.Max)
    )

    checked_aliases = []
    for select in tree.find_all(exp.Select):
        for table in _direct_tables(select):
            if table.name.lower() not in {"event", "user"}:
                continue
            alias = table.alias_or_name
            checked_aliases.append(alias)
            assert _has_direct_dt_predicate(select, alias), (
                f"{fixture['view_id']} 中 {table.name} {alias} 缺少直接 dt 条件"
            )
    assert checked_aliases


def test_validate_rewritten_sql_rejects_remaining_bounds_reference():
    view_id = "95d8497afac14f0a90342031fb43bc04"
    with pytest.raises(repair.UnsafeRewriteError, match="bounds"):
        repair.validate_rewritten_sql(SQL_BY_VIEW[view_id])


def test_validate_rewritten_sql_rejects_max_dt():
    with pytest.raises(repair.UnsafeRewriteError, match=r"MAX\(dt\)"):
        repair.validate_rewritten_sql(
            "SELECT MAX(e.dt) AS max_dt FROM event e WHERE e.dt = 20260715"
        )


def test_validate_rewritten_sql_rejects_unbounded_large_table_alias():
    with pytest.raises(repair.UnsafeRewriteError, match="dt"):
        repair.validate_rewritten_sql("SELECT e.uid FROM event e")


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT e.uid FROM event e WHERE e.dt = e.dt",
        (
            "SELECT e.uid FROM event e "
            "JOIN user u ON u.dt = e.dt"
        ),
        (
            "SELECT e.uid FROM event e "
            "WHERE e.dt BETWEEN 20260701 AND 20260715 OR e.event = 'UserActive'"
        ),
        "SELECT e.uid FROM event e WHERE e.dt = dt",
        (
            "SELECT e.uid FROM event e "
            "LEFT JOIN user u ON u.dt = e.dt "
            "WHERE u.dt BETWEEN 20260701 AND 20260715"
        ),
        (
            "SELECT e.uid FROM event e "
            "LEFT JOIN user u ON u.dt = e.dt "
            "WHERE e.dt BETWEEN 20260701 AND 20260715"
        ),
    ],
    ids=[
        "self-comparison",
        "two-unbounded-aliases",
        "or-branch",
        "unqualified-column",
        "outer-join-preserved-side",
        "outer-join-non-preserved-side",
    ],
)
def test_validate_rewritten_sql_rejects_non_restrictive_dt_conditions(sql):
    with pytest.raises(repair.UnsafeRewriteError, match="dt"):
        repair.validate_rewritten_sql(sql)
