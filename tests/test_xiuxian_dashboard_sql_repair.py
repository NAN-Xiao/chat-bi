from __future__ import annotations

import importlib
import json
import sys
from datetime import date, datetime
from decimal import Decimal
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


def _apply_business_mutation(tree: exp.Select, mutation: str) -> None:
    if mutation == "aggregate":
        aggregate = next(tree.find_all(exp.Sum))
        aggregate.replace(exp.Count(this=aggregate.this.copy()))
        return
    if mutation == "field":
        column = next(
            column
            for column in tree.find_all(exp.Column)
            if column.name.lower() == "uid"
        )
        column.set("this", exp.to_identifier("uid_changed"))
        return
    if mutation == "event-literal":
        event_column = next(
            column
            for column in tree.find_all(exp.Column)
            if column.name.lower() == "event"
        )
        predicate = event_column.parent
        while predicate is not None and not isinstance(predicate, (exp.EQ, exp.In)):
            predicate = predicate.parent
        assert predicate is not None
        literal = next(
            item for item in predicate.find_all(exp.Literal) if item.is_string
        )
        literal.set("this", literal.this + "_changed")
        return
    if mutation == "json-path":
        path = next(tree.find_all(exp.JSONPath))
        replacement = sqlglot.parse_one(
            "SELECT JSON_EXTRACT(payload, '$.changed')",
            read="mysql",
        ).find(exp.JSONPath)
        assert replacement is not None
        path.replace(replacement.copy())
        return
    if mutation == "where":
        select = next(
            item for item in tree.find_all(exp.Select) if item.args.get("where")
        )
        where = select.args["where"]
        where.set(
            "this",
            exp.and_(
                where.this,
                exp.EQ(
                    this=exp.Literal.number(1),
                    expression=exp.Literal.number(1),
                ),
            ),
        )
        return
    if mutation == "having":
        select = next(
            item
            for item in tree.find_all(exp.Select)
            if item.args.get("group") and item.args.get("having") is None
        )
        select.set(
            "having",
            exp.Having(
                this=exp.GTE(
                    this=exp.Count(this=exp.Star()),
                    expression=exp.Literal.number(0),
                )
            ),
        )
        return
    if mutation == "distinct":
        tree.set("distinct", exp.Distinct())
        return
    if mutation == "nested-select":
        cte = next(
            cte
            for cte in tree.args["with_"].expressions
            if cte.alias_or_name.lower() not in SCALAR_CTES
        )
        cte.this.append("expressions", exp.alias_(exp.Literal.number(1), "changed"))
        return
    raise AssertionError(f"未知测试变异：{mutation}")


def test_fixture_is_exactly_the_ten_whitelisted_sql_statements():
    assert len(FIXTURES) == 10
    assert {item["view_id"] for item in FIXTURES} == set(repair.REPAIR_SPECS)
    assert {
        item["view_id"]: item["sql_sha256"] for item in FIXTURES
    } == repair.REPAIR_SOURCE_HASHES


def test_active_payer_rate_is_not_in_legacy_bounds_repair_catalog():
    assert "95d8497afac14f0a90342031fb43bc04" not in repair.REPAIR_SPECS
    assert len(repair.REPAIR_SPECS) == 10


def test_rewritten_hash_catalog_matches_deterministic_rewrite_output():
    assert set(repair.REPAIR_REWRITTEN_HASHES) == set(repair.REPAIR_SOURCE_HASHES)
    assert {
        view_id: repair._sha256_text(repair.rewrite_bounds_sql(view_id, source_sql))
        for view_id, source_sql in SQL_BY_VIEW.items()
    } == repair.REPAIR_REWRITTEN_HASHES


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda item: item["view_id"])
def test_rewrite_is_idempotent_for_all_whitelisted_sql(fixture):
    once = repair.rewrite_bounds_sql(fixture["view_id"], fixture["sql"])

    assert repair.rewrite_bounds_sql(fixture["view_id"], once) == once


def test_already_rewritten_sql_is_revalidated(monkeypatch):
    view_id = "f499305aa9b44a209cbe72cb68985a46"
    once = repair.rewrite_bounds_sql(view_id, SQL_BY_VIEW[view_id])

    def reject_rewritten_sql(*_args, **_kwargs):
        raise repair.UnsafeRewriteError("rewritten safety validation marker")

    monkeypatch.setattr(repair, "validate_rewritten_sql", reject_rewritten_sql)

    with pytest.raises(repair.UnsafeRewriteError, match="safety validation marker"):
        repair.rewrite_bounds_sql(view_id, once)


def test_unknown_view_fails_closed():
    with pytest.raises(repair.SourceSqlChangedError, match="白名单"):
        repair.rewrite_bounds_sql("unknown-view", next(iter(SQL_BY_VIEW.values())))


def test_source_byte_drift_fails_closed():
    view_id = "f499305aa9b44a209cbe72cb68985a46"
    with pytest.raises(repair.SourceSqlChangedError, match="SHA-256"):
        repair.rewrite_bounds_sql(view_id, SQL_BY_VIEW[view_id] + "\n")


def test_third_sql_variant_still_fails_closed_after_idempotency_support():
    view_id = "f499305aa9b44a209cbe72cb68985a46"
    once = repair.rewrite_bounds_sql(view_id, SQL_BY_VIEW[view_id])
    unknown_variant = once.replace("110000047", "110000048", 1)

    with pytest.raises(repair.SourceSqlChangedError, match="SHA-256"):
        repair.rewrite_bounds_sql(view_id, unknown_variant)


def test_rewrite_removes_direct_bounds_join():
    view_id = "f499305aa9b44a209cbe72cb68985a46"
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
    view_id = "f499305aa9b44a209cbe72cb68985a46"
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
    "mutation",
    [
        "aggregate",
        "field",
        "event-literal",
        "json-path",
        "where",
        "having",
        "distinct",
        "nested-select",
    ],
)
def test_business_equivalence_rejects_non_date_ast_mutations(mutation):
    view_id = "a6eb26710f7b4dc6ab69ded704c32fee"
    original = SQL_BY_VIEW[view_id]
    tree = _parse(repair.rewrite_bounds_sql(view_id, original))
    _apply_business_mutation(tree, mutation)

    with pytest.raises(repair.UnsafeRewriteError, match="业务 AST"):
        repair.validate_business_equivalence(
            original,
            tree.sql(dialect="mysql", pretty=True),
        )


def test_business_equivalence_mask_is_independent_from_production_inline(monkeypatch):
    view_id = "a6eb26710f7b4dc6ab69ded704c32fee"
    original = SQL_BY_VIEW[view_id]
    rewritten = repair.rewrite_bounds_sql(view_id, original)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("业务等价 mask 不得调用生产 scalar 内联")

    monkeypatch.setattr(repair, "_resolve_scalar_cte_values", fail_if_called)
    monkeypatch.setattr(repair, "_inline_scalar_joins", fail_if_called)
    monkeypatch.setattr(repair, "_drop_unreferenced_scalar_ctes", fail_if_called)

    repair.validate_business_equivalence(original, rewritten)


def test_business_equivalence_rejects_scalar_reference_in_business_predicate():
    original = (
        "WITH bounds AS (SELECT 20260701 AS start_dt) "
        "SELECT e.uid FROM event e "
        "JOIN bounds b ON e.dt >= b.start_dt "
        "WHERE e.prod = b.start_dt"
    )
    rewritten = (
        "SELECT e.uid FROM event e "
        "WHERE e.dt >= 20260701"
    )

    with pytest.raises(repair.UnsafeRewriteError, match="业务 AST|非日期"):
        repair.validate_business_equivalence(original, rewritten)


def test_business_equivalence_rejects_unmasked_nested_scalar_join():
    original = (
        "WITH bounds AS (SELECT 20260701 AS start_dt) "
        "SELECT nested.uid FROM ("
        "SELECT e.uid FROM event e "
        "JOIN bounds b ON e.dt >= b.start_dt"
        ") nested"
    )
    rewritten = (
        "SELECT nested.uid FROM ("
        "SELECT e.uid FROM event e"
        ") nested"
    )

    with pytest.raises(repair.UnsafeRewriteError, match="业务 AST|scalar"):
        repair.validate_business_equivalence(original, rewritten)


def test_business_equivalence_rejects_mutated_mixed_scalar_projection():
    original = (
        "WITH bounds AS (SELECT 20260701 AS start_dt) "
        "SELECT SUM(e.uid) + b.start_dt AS metric "
        "FROM event e "
        "JOIN bounds b ON TRUE "
        "WHERE e.dt >= b.start_dt"
    )
    rewritten = (
        "SELECT COUNT(e.uid) + 20260701 AS metric "
        "FROM event e "
        "WHERE e.dt >= 20260701"
    )

    with pytest.raises(repair.UnsafeRewriteError, match="业务 AST|scalar"):
        repair.validate_business_equivalence(original, rewritten)


def test_business_equivalence_rejects_business_logic_inside_partition_term():
    original = (
        "WITH bounds AS (SELECT 20260701 AS start_dt) "
        "SELECT e.uid FROM event e "
        "JOIN bounds b ON TRUE "
        "WHERE e.dt >= b.start_dt + IF(e.event = 'Login', 0, 0)"
    )
    rewritten = (
        "SELECT e.uid FROM event e "
        "WHERE e.dt >= 20260701 + IF(e.event = 'Pay', 0, 0)"
    )

    with pytest.raises(repair.UnsafeRewriteError, match="业务 AST|日期"):
        repair.validate_business_equivalence(original, rewritten)


def test_business_equivalence_rejects_boolean_partition_boundary():
    original = (
        "WITH bounds AS (SELECT 20260701 AS start_dt) "
        "SELECT e.uid FROM event e "
        "JOIN bounds b ON TRUE "
        "WHERE e.dt >= b.start_dt"
    )
    rewritten = (
        "SELECT e.uid FROM event e "
        "WHERE e.dt >= (20260701 <> 20260702)"
    )

    with pytest.raises(repair.UnsafeRewriteError, match="业务 AST|日期"):
        repair.validate_business_equivalence(original, rewritten)


@pytest.mark.parametrize(
    "sql",
    [
        (
            "SELECT e.uid FROM event e "
            "JOIN dim_date d ON e.dt = d.dt"
        ),
        (
            "SELECT e.uid FROM event e "
            "JOIN dim_date d ON e.dt BETWEEN d.start_dt AND d.end_dt"
        ),
        (
            "WITH date_dim AS (SELECT d.dt FROM dim_date d) "
            "SELECT e.uid FROM event e "
            "JOIN date_dim d ON e.dt = d.dt"
        ),
        (
            "WITH date_bounds AS (SELECT 20260701 AS start_dt) "
            "SELECT e.uid FROM event e "
            "JOIN date_bounds d ON e.dt = d.start_dt"
        ),
        (
            "WITH date_dim AS ("
            "SELECT d.dt AS boundary_dt "
            "FROM event e "
            "JOIN dim_date d ON d.dt = e.dt "
            "WHERE e.dt BETWEEN 20260701 AND 20260715"
            ") "
            "SELECT u.uid FROM user u "
            "JOIN date_dim d ON u.dt = d.boundary_dt"
        ),
        (
            "WITH counted_dates AS ("
            "SELECT COUNT(DISTINCT e.dt) AS dt_count "
            "FROM event e "
            "WHERE e.dt BETWEEN 20260701 AND 20260715"
            ") "
            "SELECT u.uid FROM user u "
            "JOIN counted_dates c ON u.dt = c.dt_count"
        ),
        (
            "WITH constant_dates AS ("
            "SELECT 20260701 AS boundary_dt "
            "FROM event e "
            "WHERE e.dt BETWEEN 20260701 AND 20260715"
            ") "
            "SELECT u.uid FROM user u "
            "JOIN constant_dates c ON u.dt = c.boundary_dt"
        ),
        (
            "WITH compared_dates AS ("
            "SELECT e.dt >= 20260701 AS boundary_dt "
            "FROM event e "
            "WHERE e.dt BETWEEN 20260701 AND 20260715"
            ") "
            "SELECT u.uid FROM user u "
            "JOIN compared_dates c ON u.dt = c.boundary_dt"
        ),
        (
            "WITH compared_dates AS ("
            "SELECT e.dt <> 20260701 AS boundary_dt "
            "FROM event e "
            "WHERE e.dt BETWEEN 20260701 AND 20260715"
            ") "
            "SELECT u.uid FROM user u "
            "JOIN compared_dates c ON u.dt = c.boundary_dt"
        ),
        (
            "WITH compared_dates AS ("
            "SELECT e.dt IN (20260701) AS boundary_dt "
            "FROM event e "
            "WHERE e.dt BETWEEN 20260701 AND 20260715"
            ") "
            "SELECT u.uid FROM user u "
            "JOIN compared_dates c ON u.dt = c.boundary_dt"
        ),
        (
            "WITH compared_dates AS ("
            "SELECT e.dt IS NULL AS boundary_dt "
            "FROM event e "
            "WHERE e.dt BETWEEN 20260701 AND 20260715"
            ") "
            "SELECT u.uid FROM user u "
            "JOIN compared_dates c ON u.dt = c.boundary_dt"
        ),
    ],
    ids=[
        "dimension-equality",
        "dimension-range",
        "unproven-cte-output",
        "source-free-constant-cte",
        "unrelated-cte-output",
        "aggregated-dt-output",
        "bounded-cte-constant-output",
        "bounded-cte-boolean-output",
        "bounded-cte-neq-output",
        "bounded-cte-in-output",
        "bounded-cte-is-output",
    ],
)
def test_validate_rewritten_sql_rejects_unproven_date_lineage(sql):
    with pytest.raises(repair.UnsafeRewriteError, match="dt"):
        repair.validate_rewritten_sql(sql)


def test_validate_rewritten_sql_accepts_proven_cte_date_lineage():
    repair.validate_rewritten_sql(
        "WITH cohort AS ("
        "SELECT e.dt AS cohort_dt "
        "FROM event e "
        "WHERE e.dt BETWEEN 20260701 AND 20260715"
        ") "
        "SELECT u.uid FROM user u "
        "JOIN cohort c ON u.dt = c.cohort_dt"
    )


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


def test_freeze_curdate_uses_one_database_date_for_both_queries():
    frozen = repair.freeze_curdate(
        "SELECT DATE_SUB(CURDATE(), INTERVAL 1 DAY)",
        date(2026, 7, 16),
    )

    assert "CURDATE" not in frozen.upper()
    assert "2026-07-16" in frozen


def test_compare_results_reports_first_cell_difference():
    original = repair.QueryResult(
        ("日期", "DAU"),
        ((date(2026, 7, 15), Decimal("10")),),
    )
    rewritten = repair.QueryResult(
        ("日期", "DAU"),
        ((date(2026, 7, 15), Decimal("11")),),
    )

    with pytest.raises(repair.ResultMismatchError, match="DAU"):
        repair.compare_query_results(original, rewritten, ordered=True)


def test_unordered_compare_preserves_duplicate_rows():
    original = repair.QueryResult(("x",), ((1,), (1,), (2,)))
    rewritten = repair.QueryResult(("x",), ((1,), (2,), (2,)))

    with pytest.raises(repair.ResultMismatchError, match="重复"):
        repair.compare_query_results(original, rewritten, ordered=False)


def test_compare_results_normalizes_driver_scalar_types_without_tolerance():
    original = repair.QueryResult(
        ("日期", "金额", "比率", "空值"),
        ((date(2026, 7, 15), Decimal("10.00"), 0.5, None),),
    )
    rewritten = repair.QueryResult(
        ("日期", "金额", "比率", "空值"),
        ((datetime(2026, 7, 15), Decimal("10.0"), 0.5, None),),
    )

    repair.compare_query_results(original, rewritten, ordered=True)


def test_execute_query_preserves_column_order_and_duplicate_rows():
    class Cursor:
        description = (("日期",), ("DAU",))

        def __init__(self):
            self.executed = []

        def execute(self, sql):
            self.executed.append(sql)

        def fetchall(self):
            return [("2026-07-15", 10), ("2026-07-15", 10)]

    cursor = Cursor()

    result = repair.execute_query(cursor, "SELECT stat_date, dau FROM metrics")

    assert cursor.executed == ["SELECT stat_date, dau FROM metrics"]
    assert result.columns == ("日期", "DAU")
    assert result.rows == (("2026-07-15", 10), ("2026-07-15", 10))


def test_validate_explain_plan_rejects_broadcast_hash_join_from_values():
    plan = "-> Values\n-> Exchange[REPLICATE]\n-> InnerJoin[Hash Join]"

    with pytest.raises(repair.UnsafePlanError, match="广播 Hash Join"):
        repair.validate_explain_plan(plan)


class _CasCursor:
    def __init__(self, rowcounts):
        self._rowcounts = iter(rowcounts)
        self.rowcount = 0
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql, params):
        self.calls.append((sql, params))
        self.rowcount = next(self._rowcounts)


class _CasConnection:
    def __init__(self, rowcounts):
        self.cursor_instance = _CasCursor(rowcounts)
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def _dashboard_snapshot(dashboard_id, canvas):
    from xiuxian_dashboard_snapshot import DashboardSnapshot

    return DashboardSnapshot.from_row(
        (
            dashboard_id,
            f"看板 {dashboard_id}",
            7482727237662281728,
            6,
            json.dumps(canvas, ensure_ascii=False, separators=(",", ":")),
        )
    )


def test_apply_dashboard_repairs_uses_exact_canvas_compare_and_preserves_metadata():
    original_view = {
        "sql": "SELECT old",
        "data": [{"x": 1}],
        "chart": {"type": "line"},
        "fields": ["x"],
        "pivot": {"rows": ["x"]},
        "snapshotRefreshedAt": "2026-07-16T10:00:00",
    }
    dashboard = _dashboard_snapshot("dashboard-1", {"view-1": original_view})
    connection = _CasConnection([1])

    updated = repair.apply_dashboard_repairs(
        connection,
        [dashboard],
        {"view-1": "SELECT new"},
        tenant_id=7482727237662281728,
        update_time=1784175253,
    )

    assert updated == 1
    assert connection.committed is True
    assert connection.rolled_back is False
    sql, params = connection.cursor_instance.calls[0]
    assert "canvas_view_info = %s" in sql
    assert "AND canvas_view_info = %s" in sql
    saved_canvas = json.loads(params[0])
    assert saved_canvas["view-1"] == {**original_view, "sql": "SELECT new"}
    assert params[1] == 1784175253
    assert type(params[1]) is int
    assert params[-1] == dashboard.canvas_view_info


@pytest.mark.parametrize(
    "invalid_update_time",
    [datetime(2026, 7, 16, 12, 0, 0), True],
    ids=("datetime", "bool"),
)
def test_apply_dashboard_repairs_rejects_non_integer_update_time(
    invalid_update_time,
):
    dashboard = _dashboard_snapshot(
        "dashboard-1", {"view-1": {"sql": "SELECT old"}}
    )
    connection = _CasConnection([1])

    with pytest.raises(TypeError, match="update_time"):
        repair.apply_dashboard_repairs(
            connection,
            [dashboard],
            {"view-1": "SELECT new"},
            tenant_id=7482727237662281728,
            update_time=invalid_update_time,
        )

    assert connection.cursor_instance.calls == []
    assert connection.committed is False


def test_apply_dashboard_repairs_rolls_back_all_updates_on_cas_conflict():
    dashboards = [
        _dashboard_snapshot("dashboard-1", {"view-1": {"sql": "old-1"}}),
        _dashboard_snapshot("dashboard-2", {"view-2": {"sql": "old-2"}}),
    ]
    connection = _CasConnection([1, 0])

    with pytest.raises(repair.DashboardCasConflictError, match="dashboard-2"):
        repair.apply_dashboard_repairs(
            connection,
            dashboards,
            {"view-1": "new-1", "view-2": "new-2"},
            tenant_id=7482727237662281728,
            update_time=1784175253,
        )

    assert connection.committed is False
    assert connection.rolled_back is True
