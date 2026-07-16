# -*- coding: utf-8 -*-
"""对已验签的修仙推荐看板 SQL 做受限日期边界 AST 改写。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable, Mapping

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError


ALLOWED_SCALAR_CTES = frozenset({"bounds", "weeks", "months"})
LARGE_PARTITIONED_TABLES = frozenset({"event", "user"})

REPAIR_SOURCE_HASHES = {
    "95d8497afac14f0a90342031fb43bc04": "815c35585e7769575fa01ca6eb13069eaf47821da3943080b0968255b999b503",
    "f499305aa9b44a209cbe72cb68985a46": "364956182ef6e2dd84b5a30e66e99801741da627cec1797f7383ea9f8fa0e6b5",
    "f99d0fb5f3624192953bdbfa31549abd": "6385a9ac88f2908207a785d150565c1d8cf473bd1bbef0afd94381cea49cb261",
    "531bc723e3cb42f0a1fe2c412d7f05b0": "67ce7636a2a409cb4dcc9a9e773b74bc45b4fd63109b5ef71355dec73f13959e",
    "b0f27793e48349c1a6a7fbf40ff03ffd": "9d9ce46714e0472bbb43199efa90d8e51b29ac136d72a0f7652dfdb7219d2c58",
    "a6eb26710f7b4dc6ab69ded704c32fee": "4c2b7532ece58222c0e6e6e099394fd181389143cb14c280acebd70f4c875dd8",
    "0369399df2eb4a3299d6d34f9663101b": "75df3dbb120f0da0423e12116a6f3513540edec98ccef3d7a2fab32a392fdf11",
    "ad88b71e2b08435c8c7a0606c5579f30": "148640112c5a584360fd643f5a8a331d7041b6a95ee1d092ff0a308acf146cd2",
    "d4675e033a9c4d4881264a66861b066e": "afdbcc182590860c6fb89aafb14f8ce1994c654829af21f7e8b34f89b0c04e4c",
    "e797a8af6785452e9fdcee7d80786b6e": "6385a9ac88f2908207a785d150565c1d8cf473bd1bbef0afd94381cea49cb261",
    "fc272fe6a3a74cda90a0564a98890fab": "27ebb37991f8177f460650ac359a8aedbd4dc06033ca5a8cb7293c71b2a7a9fe",
}


class SourceSqlChangedError(ValueError):
    """原 SQL 不属于已审核白名单或内容已经漂移。"""


class UnsafeRewriteError(ValueError):
    """改写结果超出允许的日期边界变换范围。"""


@dataclass(frozen=True)
class RepairSpec:
    """单个抽屉 SQL 的不可变改写约束。"""

    view_id: str
    source_sha256: str
    scalar_ctes: frozenset[str] = ALLOWED_SCALAR_CTES


REPAIR_SPECS = {
    view_id: RepairSpec(view_id=view_id, source_sha256=source_sha256)
    for view_id, source_sha256 in REPAIR_SOURCE_HASHES.items()
}


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _require_source_hash(view_id: str, sql: str) -> RepairSpec:
    spec = REPAIR_SPECS.get(view_id)
    if spec is None:
        raise SourceSqlChangedError(f"抽屉 {view_id} 不在 SQL 改写白名单中")
    actual = _sha256_text(sql)
    if actual != spec.source_sha256:
        raise SourceSqlChangedError(
            f"抽屉 {view_id} 的原 SQL SHA-256 已变化，拒绝自动改写"
        )
    return spec


def _parse_mysql(sql: str) -> exp.Expression:
    try:
        statements = sqlglot.parse(sql, read="mysql")
    except ParseError as exc:
        raise UnsafeRewriteError("SQL 无法按 MySQL 方言解析") from exc
    if len(statements) != 1:
        raise UnsafeRewriteError("只允许改写单条 SELECT SQL")
    tree = statements[0]
    if not isinstance(tree, exp.Select):
        raise UnsafeRewriteError("只允许改写 SELECT SQL")
    return tree


def _direct_tables(select: exp.Select) -> list[exp.Table]:
    tables: list[exp.Table] = []
    from_clause = select.args.get("from_")
    if from_clause is not None and isinstance(from_clause.this, exp.Table):
        tables.append(from_clause.this)
    tables.extend(
        join.this
        for join in select.args.get("joins") or []
        if isinstance(join.this, exp.Table)
    )
    return tables


def _direct_predicates(select: exp.Select) -> list[exp.Expression]:
    predicates: list[exp.Expression] = []
    where = select.args.get("where")
    if where is not None:
        predicates.append(where.this)
    predicates.extend(
        on
        for join in select.args.get("joins") or []
        if (on := join.args.get("on")) is not None
    )
    return predicates


def _projection_signature(select: exp.Select) -> tuple[str, ...]:
    return tuple(
        expression.alias_or_name or expression.sql(dialect="mysql")
        for expression in select.expressions
    )


def _clause_signature(select: exp.Select, name: str) -> str | None:
    clause = select.args.get(name)
    return clause.sql(dialect="mysql") if clause is not None else None


def _select_surface(select: exp.Select) -> tuple:
    from_clause = select.args.get("from_")
    from_table = from_clause.this if from_clause is not None else None
    business_from = (
        (from_table.name.lower(), from_table.alias_or_name.lower())
        if isinstance(from_table, exp.Table)
        and from_table.name.lower() not in ALLOWED_SCALAR_CTES
        else None
    )
    business_joins = tuple(
        (
            join.this.name.lower(),
            join.this.alias_or_name.lower(),
            join.side.lower(),
            join.kind.lower(),
            join.args["on"].sql(dialect="mysql") if join.args.get("on") else None,
        )
        for join in select.args.get("joins") or []
        if isinstance(join.this, exp.Table)
        and join.this.name.lower() not in ALLOWED_SCALAR_CTES
    )
    return (
        _projection_signature(select),
        business_from,
        business_joins,
        _clause_signature(select, "group"),
        _clause_signature(select, "order"),
        _clause_signature(select, "limit"),
    )


def _surface_signature(tree: exp.Expression) -> tuple:
    with_clause = tree.args.get("with_")
    business_ctes = []
    if with_clause is not None:
        for cte in with_clause.expressions:
            name = cte.alias_or_name.lower()
            if name in ALLOWED_SCALAR_CTES:
                continue
            if not isinstance(cte.this, exp.Select):
                raise UnsafeRewriteError(f"业务 CTE {name} 不是 SELECT")
            business_ctes.append((name, _select_surface(cte.this)))
    return tuple(business_ctes), _select_surface(tree)


def _dependency_aliases(
    select: exp.Select,
    resolved: Mapping[str, Mapping[str, exp.Expression]],
) -> dict[str, Mapping[str, exp.Expression]]:
    dependencies: dict[str, Mapping[str, exp.Expression]] = {}
    tables = _direct_tables(select)
    for table in tables:
        name = table.name.lower()
        if name not in resolved:
            raise UnsafeRewriteError(
                f"标量 CTE 只能依赖已解析的 {sorted(ALLOWED_SCALAR_CTES)}"
            )
        dependencies[table.alias_or_name.lower()] = resolved[name]
        dependencies[name] = resolved[name]
    return dependencies


def _replace_scalar_columns(
    expression: exp.Expression,
    values_by_alias: Mapping[str, Mapping[str, exp.Expression]],
) -> exp.Expression:
    dependency_values = tuple({id(values): values for values in values_by_alias.values()}.values())

    def replace(node: exp.Expression) -> exp.Expression:
        if not isinstance(node, exp.Column):
            return node
        column_name = node.name.lower()
        table_name = node.table.lower()
        if table_name:
            values = values_by_alias.get(table_name)
            if values is None:
                return node
            value = values.get(column_name)
            if value is None:
                raise UnsafeRewriteError(
                    f"标量 CTE {table_name} 没有输出列 {column_name}"
                )
            return value.copy()

        matches = [values[column_name] for values in dependency_values if column_name in values]
        if not matches:
            return node
        if len(matches) != 1:
            raise UnsafeRewriteError(f"无法唯一解析标量列 {column_name}")
        return matches[0].copy()

    return expression.transform(replace, copy=False)


def _resolve_scalar_cte_values(
    tree: exp.Expression,
    *,
    allowed: Iterable[str],
) -> dict[str, dict[str, exp.Expression]]:
    allowed_names = {name.lower() for name in allowed}
    with_clause = tree.args.get("with_")
    if with_clause is None:
        raise UnsafeRewriteError("原 SQL 缺少 bounds 标量 CTE")

    resolved: dict[str, dict[str, exp.Expression]] = {}
    for cte in with_clause.expressions:
        name = cte.alias_or_name.lower()
        if name not in allowed_names:
            continue
        select = cte.this
        if not isinstance(select, exp.Select):
            raise UnsafeRewriteError(f"标量 CTE {name} 必须是 SELECT")
        if any(
            select.args.get(clause) is not None
            for clause in ("group", "having", "qualify", "order", "limit")
        ):
            raise UnsafeRewriteError(f"标量 CTE {name} 不能包含聚合、排序或限制")
        if select.args.get("joins"):
            raise UnsafeRewriteError(f"标量 CTE {name} 不能包含 JOIN")

        dependencies = _dependency_aliases(select, resolved)
        outputs: dict[str, exp.Expression] = {}
        for projection in select.expressions:
            alias = projection.alias_or_name.lower()
            if not alias or not isinstance(projection, exp.Alias):
                raise UnsafeRewriteError(f"标量 CTE {name} 的每个输出都必须有别名")
            value = projection.this.copy()
            outputs[alias] = _replace_scalar_columns(value, dependencies)
        if not outputs:
            raise UnsafeRewriteError(f"标量 CTE {name} 没有输出")
        resolved[name] = outputs

    if "bounds" not in resolved:
        raise UnsafeRewriteError("原 SQL 缺少可解析的 bounds 标量 CTE")
    return resolved


def _is_true(expression: exp.Expression | None) -> bool:
    return isinstance(expression, exp.Boolean) and expression.this is True


def _inline_select_scalar_joins(
    select: exp.Select,
    scalar_values: Mapping[str, Mapping[str, exp.Expression]],
) -> None:
    joins = list(select.args.get("joins") or [])
    scalar_joins = [
        join
        for join in joins
        if isinstance(join.this, exp.Table)
        and join.this.name.lower() in scalar_values
    ]
    if not scalar_joins:
        return

    values_by_alias: dict[str, Mapping[str, exp.Expression]] = {}
    for join in scalar_joins:
        table = join.this
        name = table.name.lower()
        values_by_alias[table.alias_or_name.lower()] = scalar_values[name]
        values_by_alias[name] = scalar_values[name]

    moved_predicates: list[exp.Expression] = []
    for join in scalar_joins:
        on = join.args.get("on")
        if on is not None:
            on = _replace_scalar_columns(on.copy(), values_by_alias)
            if not _is_true(on):
                moved_predicates.append(on)

    select.set("joins", [join for join in joins if join not in scalar_joins])

    rewritten_projections: list[exp.Expression] = []
    for projection in select.expressions:
        output_name = projection.alias_or_name
        rewritten_projection = _replace_scalar_columns(projection, values_by_alias)
        if (
            output_name
            and not isinstance(rewritten_projection, exp.Alias)
            and rewritten_projection.alias_or_name != output_name
        ):
            rewritten_projection = exp.alias_(rewritten_projection, output_name)
        rewritten_projections.append(rewritten_projection)
    select.set("expressions", rewritten_projections)
    for name in ("where", "group", "having", "qualify", "order", "limit"):
        clause = select.args.get(name)
        if clause is not None:
            select.set(name, _replace_scalar_columns(clause, values_by_alias))
    for join in select.args.get("joins") or []:
        on = join.args.get("on")
        if on is not None:
            join.set("on", _replace_scalar_columns(on, values_by_alias))

    if moved_predicates:
        where = select.args.get("where")
        predicate = where.this if where is not None else None
        for moved in moved_predicates:
            predicate = moved if predicate is None else exp.and_(predicate, moved)
        select.set("where", exp.Where(this=predicate))

    for alias in values_by_alias:
        if any(
            column.table.lower() == alias
            for clause in (
                list(select.expressions)
                + _direct_predicates(select)
                + [
                    item
                    for item in (
                        select.args.get("group"),
                        select.args.get("having"),
                        select.args.get("order"),
                        select.args.get("limit"),
                    )
                    if item is not None
                ]
            )
            for column in clause.find_all(exp.Column)
        ):
            raise UnsafeRewriteError(f"标量 JOIN 别名 {alias} 仍有未内联引用")


def _inline_scalar_joins(
    tree: exp.Expression,
    scalar_values: Mapping[str, Mapping[str, exp.Expression]],
) -> None:
    for select in list(tree.find_all(exp.Select)):
        _inline_select_scalar_joins(select, scalar_values)


def _drop_unreferenced_scalar_ctes(
    tree: exp.Expression,
    scalar_values: Mapping[str, Mapping[str, exp.Expression]],
) -> None:
    with_clause = tree.args.get("with_")
    if with_clause is None:
        return
    scalar_names = set(scalar_values)
    with_clause.set(
        "expressions",
        [
            cte
            for cte in with_clause.expressions
            if cte.alias_or_name.lower() not in scalar_names
        ],
    )
    if not with_clause.expressions:
        tree.set("with_", None)
    if any(
        table.name.lower() in scalar_names for table in tree.find_all(exp.Table)
    ):
        raise UnsafeRewriteError("删除标量 CTE 后仍存在 bounds/weeks/months 引用")


def _unwrap_parentheses(expression: exp.Expression) -> exp.Expression:
    while isinstance(expression, exp.Paren):
        expression = expression.this
    return expression


def _conjunctive_terms(expression: exp.Expression) -> Iterable[exp.Expression]:
    expression = _unwrap_parentheses(expression)
    if isinstance(expression, exp.Or):
        return
    if isinstance(expression, exp.And):
        yield from _conjunctive_terms(expression.this)
        yield from _conjunctive_terms(expression.expression)
        return
    yield expression


def _large_dt_alias(
    expression: exp.Expression,
    large_aliases: set[str],
) -> str | None:
    expression = _unwrap_parentheses(expression)
    if not isinstance(expression, exp.Column):
        return None
    alias = expression.table.lower()
    if expression.name.lower() != "dt" or alias not in large_aliases:
        return None
    return alias


def _is_external_boundary(
    expression: exp.Expression,
    large_aliases: set[str],
) -> bool:
    columns = list(expression.find_all(exp.Column))
    return all(
        bool(column.table) and column.table.lower() not in large_aliases
        for column in columns
    )


def _predicate_scopes(
    select: exp.Select,
    large_aliases: set[str],
) -> Iterable[tuple[exp.Expression, set[str], bool]]:
    where = select.args.get("where")
    if where is not None:
        yield where.this, set(large_aliases), True

    for join in select.args.get("joins") or []:
        on = join.args.get("on")
        if on is None:
            continue
        joined_alias = (
            join.this.alias_or_name.lower()
            if isinstance(join.this, exp.Table)
            else ""
        )
        side = join.side.lower()
        if side == "left":
            eligible = {joined_alias} & large_aliases
        elif side == "right":
            eligible = large_aliases - {joined_alias}
        elif side == "full":
            eligible = set()
        else:
            eligible = set(large_aliases)
        yield on, eligible, not side


def _bounded_large_aliases(
    select: exp.Select,
    large_aliases: set[str],
) -> set[str]:
    bounded: set[str] = set()
    equality_edges: set[tuple[str, str]] = set()

    for predicate, eligible_aliases, allow_equality_edges in _predicate_scopes(
        select, large_aliases
    ):
        for term in _conjunctive_terms(predicate):
            term = _unwrap_parentheses(term)
            if isinstance(term, exp.Between):
                alias = _large_dt_alias(term.this, large_aliases)
                low = term.args.get("low")
                high = term.args.get("high")
                if (
                    alias is not None
                    and low is not None
                    and high is not None
                    and _is_external_boundary(low, large_aliases)
                    and _is_external_boundary(high, large_aliases)
                    and alias in eligible_aliases
                ):
                    bounded.add(alias)
                continue

            if isinstance(term, (exp.EQ, exp.GT, exp.GTE, exp.LT, exp.LTE)):
                left = term.this
                right = term.expression
                left_alias = _large_dt_alias(left, large_aliases)
                right_alias = _large_dt_alias(right, large_aliases)
                if left_alias is not None and right_alias is not None:
                    if (
                        allow_equality_edges
                        and isinstance(term, exp.EQ)
                        and left_alias != right_alias
                    ):
                        if left_alias in eligible_aliases:
                            equality_edges.add((right_alias, left_alias))
                        if right_alias in eligible_aliases:
                            equality_edges.add((left_alias, right_alias))
                    continue
                if (
                    left_alias in eligible_aliases
                    and _is_external_boundary(right, large_aliases)
                ):
                    bounded.add(left_alias)
                if (
                    right_alias in eligible_aliases
                    and _is_external_boundary(left, large_aliases)
                ):
                    bounded.add(right_alias)
                continue

            if isinstance(term, exp.In):
                alias = _large_dt_alias(term.this, large_aliases)
                values = list(term.expressions)
                if (
                    alias is not None
                    and alias in eligible_aliases
                    and values
                    and all(_is_external_boundary(value, large_aliases) for value in values)
                ):
                    bounded.add(alias)

    changed = True
    while changed:
        changed = False
        for source_alias, target_alias in equality_edges:
            if source_alias in bounded and target_alias not in bounded:
                bounded.add(target_alias)
                changed = True
    return bounded


def validate_rewritten_sql(sql: str) -> None:
    """验证改写结果没有日期边界引用、MAX(dt) 或无分区大表扫描。"""

    tree = _parse_mysql(sql)
    with_clause = tree.args.get("with_")
    if with_clause is not None and any(
        cte.alias_or_name.lower() in ALLOWED_SCALAR_CTES
        for cte in with_clause.expressions
    ):
        raise UnsafeRewriteError("改写后仍包含 bounds/weeks/months CTE")
    if any(
        table.name.lower() in ALLOWED_SCALAR_CTES
        for table in tree.find_all(exp.Table)
    ):
        raise UnsafeRewriteError("改写后仍引用 bounds/weeks/months")
    if any(
        any(column.name.lower() == "dt" for column in function.find_all(exp.Column))
        for function in tree.find_all(exp.Max)
    ):
        raise UnsafeRewriteError("改写后禁止出现 MAX(dt)")

    for select in tree.find_all(exp.Select):
        large_tables = [
            table
            for table in _direct_tables(select)
            if table.name.lower() in LARGE_PARTITIONED_TABLES
        ]
        large_aliases = {table.alias_or_name.lower() for table in large_tables}
        bounded_aliases = _bounded_large_aliases(select, large_aliases)
        for table in large_tables:
            alias = table.alias_or_name.lower()
            if alias not in bounded_aliases:
                raise UnsafeRewriteError(
                    f"大表 {table.name} 别名 {alias} 所在 SELECT 缺少直接 dt 条件"
                )


def rewrite_bounds_sql(view_id: str, sql: str) -> str:
    """在 SHA 白名单约束下把 bounds 标量值内联到日期谓词。"""

    spec = _require_source_hash(view_id, sql)
    tree = _parse_mysql(sql)
    original_surface = _surface_signature(tree)
    scalar_values = _resolve_scalar_cte_values(tree, allowed=spec.scalar_ctes)
    _inline_scalar_joins(tree, scalar_values)
    _drop_unreferenced_scalar_ctes(tree, scalar_values)
    if _surface_signature(tree) != original_surface:
        raise UnsafeRewriteError("改写改变了业务 CTE、字段、JOIN、GROUP、ORDER 或 LIMIT")

    rewritten = tree.sql(dialect="mysql", pretty=True)
    validate_rewritten_sql(rewritten)
    if _surface_signature(_parse_mysql(rewritten)) != original_surface:
        raise UnsafeRewriteError("SQL 序列化改变了业务表面签名")
    return rewritten
