# -*- coding: utf-8 -*-
"""对已验签的修仙推荐看板 SQL 做受限日期边界 AST 改写。"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Iterable, Mapping, Sequence

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError


ALLOWED_SCALAR_CTES = frozenset({"bounds", "weeks", "months"})
LARGE_PARTITIONED_TABLES = frozenset({"event", "user"})
ALLOWED_DATE_FUNCTIONS = frozenset(
    {
        "CURRENT_DATE",
        "CURDATE",
        "DATE_ADD",
        "DATE_SUB",
        "LAST_DAY",
        "STR_TO_DATE",
        "DATE_FORMAT",
        "WEEKDAY",
    }
)
DATE_LINEAGE_FUNCTIONS = ALLOWED_DATE_FUNCTIONS | frozenset(
    {
        "CAST",
        "TIME_TO_STR",
        "TS_OR_DS_TO_TIMESTAMP",
    }
)

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


class ResultMismatchError(ValueError):
    """原 SQL 与改写 SQL 的字段、行或值不一致。"""


class UnsafePlanError(ValueError):
    """改写 SQL 的执行计划仍包含被禁止的日期边界广播。"""


class DashboardCasConflictError(RuntimeError):
    """看板在备份后发生变化，compare-and-set 更新被拒绝。"""


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


@dataclass(frozen=True)
class _SelectBusinessMask:
    scalar_projection_indexes: tuple[tuple[int, str], ...]
    partition_shapes: tuple[tuple[str, tuple[str, ...]], ...]


@dataclass(frozen=True)
class QueryResult:
    """一次只读查询的字段和完整结果行。"""

    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]


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


def _business_selects(tree: exp.Select) -> dict[str, exp.Select]:
    selects = {"__root__": tree}
    with_clause = tree.args.get("with_")
    if with_clause is None:
        return selects
    for cte in with_clause.expressions:
        name = cte.alias_or_name.lower()
        if name in ALLOWED_SCALAR_CTES:
            continue
        if not isinstance(cte.this, exp.Select):
            raise UnsafeRewriteError(f"业务 CTE {name} 不是 SELECT")
        selects[f"cte:{name}"] = cte.this
    return selects


def _mask_conjuncts(expression: exp.Expression) -> list[exp.Expression]:
    expression = _unwrap_parentheses(expression)
    if isinstance(expression, exp.And):
        return _mask_conjuncts(expression.this) + _mask_conjuncts(
            expression.expression
        )
    return [expression]


def _partition_shape(
    expression: exp.Expression,
    large_aliases: set[str],
) -> tuple[str, tuple[str, ...]] | None:
    expression = _unwrap_parentheses(expression)
    if not isinstance(
        expression,
        (exp.Between, exp.EQ, exp.GT, exp.GTE, exp.LT, exp.LTE, exp.In),
    ):
        return None
    aliases = tuple(
        sorted(
            {
                column.table.lower()
                for column in expression.find_all(exp.Column)
                if column.table.lower() in large_aliases
                and column.name.lower() == "dt"
            }
        )
    )
    if not aliases:
        return None
    return type(expression).__name__, aliases


def _direct_large_dt_alias(
    expression: exp.Expression,
    large_aliases: set[str],
) -> str | None:
    expression = _unwrap_parentheses(expression)
    if not isinstance(expression, exp.Column):
        return None
    alias = expression.table.lower()
    if alias in large_aliases and expression.name.lower() == "dt":
        return alias
    return None


def _columns_are_scalar_only(
    expression: exp.Expression,
    scalar_aliases: set[str],
) -> bool:
    columns = list(expression.find_all(exp.Column))
    return bool(columns) and all(
        column.table.lower() in scalar_aliases for column in columns
    )


def _is_original_scalar_partition_term(
    expression: exp.Expression,
    large_aliases: set[str],
    scalar_aliases: set[str],
) -> bool:
    expression = _unwrap_parentheses(expression)
    if isinstance(expression, exp.Between):
        return (
            _direct_large_dt_alias(expression.this, large_aliases) is not None
            and _columns_are_scalar_only(expression.args["low"], scalar_aliases)
            and _columns_are_scalar_only(expression.args["high"], scalar_aliases)
        )
    if isinstance(expression, (exp.EQ, exp.GT, exp.GTE, exp.LT, exp.LTE)):
        left_alias = _direct_large_dt_alias(expression.this, large_aliases)
        right_alias = _direct_large_dt_alias(expression.expression, large_aliases)
        if left_alias is not None and right_alias is None:
            return _columns_are_scalar_only(expression.expression, scalar_aliases)
        if right_alias is not None and left_alias is None:
            return _columns_are_scalar_only(expression.this, scalar_aliases)
        return False
    if isinstance(expression, exp.In):
        return (
            _direct_large_dt_alias(expression.this, large_aliases) is not None
            and bool(expression.expressions)
            and all(
                _columns_are_scalar_only(item, scalar_aliases)
                for item in expression.expressions
            )
        )
    return False


def _is_masked_date_value(expression: exp.Expression) -> bool:
    return (
        not any(True for _ in expression.find_all(exp.Column))
        and _has_date_origin(expression)
        and _is_date_value_ast(expression)
    )


def _is_rewritten_partition_term(
    expression: exp.Expression,
    large_aliases: set[str],
) -> bool:
    expression = _unwrap_parentheses(expression)
    if isinstance(expression, exp.Between):
        return (
            _direct_large_dt_alias(expression.this, large_aliases) is not None
            and _is_masked_date_value(expression.args["low"])
            and _is_masked_date_value(expression.args["high"])
        )
    if isinstance(expression, (exp.EQ, exp.GT, exp.GTE, exp.LT, exp.LTE)):
        left_alias = _direct_large_dt_alias(expression.this, large_aliases)
        right_alias = _direct_large_dt_alias(expression.expression, large_aliases)
        if left_alias is not None and right_alias is None:
            return _is_masked_date_value(expression.expression)
        if right_alias is not None and left_alias is None:
            return _is_masked_date_value(expression.this)
        return False
    if isinstance(expression, exp.In):
        return (
            _direct_large_dt_alias(expression.this, large_aliases) is not None
            and bool(expression.expressions)
            and all(_is_masked_date_value(item) for item in expression.expressions)
        )
    return False


def _derive_business_masks(
    tree: exp.Select,
) -> dict[str, _SelectBusinessMask]:
    masks: dict[str, _SelectBusinessMask] = {}
    for owner, select in _business_selects(tree).items():
        scalar_joins = [
            join
            for join in select.args.get("joins") or []
            if isinstance(join.this, exp.Table)
            and join.this.name.lower() in ALLOWED_SCALAR_CTES
        ]
        scalar_aliases = {
            alias
            for join in scalar_joins
            for alias in (
                join.this.name.lower(),
                join.this.alias_or_name.lower(),
            )
        }
        large_aliases = {
            table.alias_or_name.lower()
            for table in _direct_tables(select)
            if table.name.lower() in LARGE_PARTITIONED_TABLES
        }
        projections: list[tuple[int, str]] = []
        for index, projection in enumerate(select.expressions):
            has_scalar_reference = any(
                column.table.lower() in scalar_aliases
                for column in projection.find_all(exp.Column)
            )
            if not has_scalar_reference:
                continue
            value = projection.this if isinstance(projection, exp.Alias) else projection
            value = _unwrap_parentheses(value)
            if not (
                isinstance(value, exp.Column)
                and value.table.lower() in scalar_aliases
            ):
                raise UnsafeRewriteError("scalar-derived 投影必须是纯 scalar 单列")
            projections.append((index, projection.alias_or_name))

        partition_shapes: list[tuple[str, tuple[str, ...]]] = []
        where = select.args.get("where")
        if where is not None:
            for term in _mask_conjuncts(where.this):
                shape = _partition_shape(term, large_aliases)
                has_scalar_reference = any(
                    column.table.lower() in scalar_aliases
                    for column in term.find_all(exp.Column)
                )
                if has_scalar_reference and shape is None:
                    raise UnsafeRewriteError("scalar 引用出现在非日期业务谓词")
                if has_scalar_reference and not _is_original_scalar_partition_term(
                    term,
                    large_aliases,
                    scalar_aliases,
                ):
                    raise UnsafeRewriteError("日期分区合取项混入业务字段或表达式")
                if shape is not None and has_scalar_reference:
                    partition_shapes.append(shape)
        for clause_name in ("group", "having", "qualify", "order"):
            clause = select.args.get(clause_name)
            if clause is not None and any(
                column.table.lower() in scalar_aliases
                for column in clause.find_all(exp.Column)
            ):
                raise UnsafeRewriteError(
                    f"scalar 引用出现在非日期业务子句 {clause_name}"
                )
        for join in scalar_joins:
            on = join.args.get("on")
            if on is None or _is_true(on):
                continue
            terms = _mask_conjuncts(on)
            matched = 0
            for term in terms:
                shape = _partition_shape(term, large_aliases)
                if shape is not None and any(
                    column.table.lower() in scalar_aliases
                    for column in term.find_all(exp.Column)
                ):
                    if not _is_original_scalar_partition_term(
                        term,
                        large_aliases,
                        scalar_aliases,
                    ):
                        raise UnsafeRewriteError(
                            "日期分区合取项混入业务字段或表达式"
                        )
                    partition_shapes.append(shape)
                    matched += 1
            if matched != len(terms):
                raise UnsafeRewriteError("scalar JOIN ON 包含非日期业务条件")

        masks[owner] = _SelectBusinessMask(
            scalar_projection_indexes=tuple(projections),
            partition_shapes=tuple(partition_shapes),
        )
    return masks


def _partition_placeholder(
    index: int,
    shape: tuple[str, tuple[str, ...]],
) -> exp.Expression:
    operator, aliases = shape
    name = f"__allowed_partition_{index}_{operator}_{'_'.join(aliases)}"
    return exp.EQ(
        this=exp.to_identifier(name),
        expression=exp.Literal.number(1),
    )


def _rebuild_masked_where(
    select: exp.Select,
    terms: list[exp.Expression],
    shapes: tuple[tuple[str, tuple[str, ...]], ...],
) -> None:
    all_terms = terms + [
        _partition_placeholder(index, shape)
        for index, shape in enumerate(shapes)
    ]
    if not all_terms:
        select.set("where", None)
        return
    predicate = all_terms[0]
    for term in all_terms[1:]:
        predicate = exp.and_(predicate, term)
    select.set("where", exp.Where(this=predicate))


def _mask_scalar_projections(
    select: exp.Select,
    spec: _SelectBusinessMask,
    *,
    rewritten: bool,
) -> None:
    projections = list(select.expressions)
    for index, output_name in spec.scalar_projection_indexes:
        if index >= len(projections) or projections[index].alias_or_name != output_name:
            raise UnsafeRewriteError("改写改变了 scalar-derived 投影位置或输出名")
        value = (
            projections[index].this
            if isinstance(projections[index], exp.Alias)
            else projections[index]
        )
        if rewritten and not _is_masked_date_value(value):
            raise UnsafeRewriteError("改写后的 scalar-derived 投影不是纯日期表达式")
        projections[index] = exp.alias_(
            exp.to_identifier("__allowed_scalar_value__"),
            output_name,
        )
    select.set("expressions", projections)


def _drop_masked_scalar_infrastructure(tree: exp.Select) -> None:
    with_clause = tree.args.get("with_")
    if with_clause is not None:
        with_clause.set(
            "expressions",
            [
                cte
                for cte in with_clause.expressions
                if cte.alias_or_name.lower() not in ALLOWED_SCALAR_CTES
            ],
        )
        if not with_clause.expressions:
            tree.set("with_", None)
    for select in _business_selects(tree).values():
        select.set(
            "joins",
            [
                join
                for join in select.args.get("joins") or []
                if not (
                    isinstance(join.this, exp.Table)
                    and join.this.name.lower() in ALLOWED_SCALAR_CTES
                )
            ],
        )
    if any(
        table.name.lower() in ALLOWED_SCALAR_CTES
        for table in tree.find_all(exp.Table)
    ):
        raise UnsafeRewriteError("未登记的嵌套 SELECT 仍包含 scalar JOIN")


def _mask_original_business_tree(
    tree: exp.Select,
    masks: Mapping[str, _SelectBusinessMask],
) -> exp.Select:
    selects = _business_selects(tree)
    if set(selects) != set(masks):
        raise UnsafeRewriteError("原 SQL 的业务 SELECT 所有者集合不稳定")
    for owner, select in selects.items():
        spec = masks[owner]
        scalar_aliases = {
            alias
            for join in select.args.get("joins") or []
            if isinstance(join.this, exp.Table)
            and join.this.name.lower() in ALLOWED_SCALAR_CTES
            for alias in (
                join.this.name.lower(),
                join.this.alias_or_name.lower(),
            )
        }
        _mask_scalar_projections(select, spec, rewritten=False)
        where = select.args.get("where")
        terms = _mask_conjuncts(where.this) if where is not None else []
        business_terms: list[exp.Expression] = []
        removed_shapes: list[tuple[str, tuple[str, ...]]] = []
        large_aliases = {
            table.alias_or_name.lower()
            for table in _direct_tables(select)
            if table.name.lower() in LARGE_PARTITIONED_TABLES
        }
        for term in terms:
            has_scalar_reference = any(
                column.table.lower() in scalar_aliases
                for column in term.find_all(exp.Column)
            )
            if not has_scalar_reference:
                business_terms.append(term)
                continue
            shape = _partition_shape(term, large_aliases)
            if shape is None:
                raise UnsafeRewriteError("scalar 引用出现在非日期业务谓词")
            removed_shapes.append(shape)
        unmatched_shapes = list(spec.partition_shapes)
        for shape in removed_shapes:
            if shape not in unmatched_shapes:
                raise UnsafeRewriteError("原 SQL 日期分区 mask 形状无效")
            unmatched_shapes.remove(shape)
        if len(removed_shapes) > len(spec.partition_shapes):
            raise UnsafeRewriteError("原 SQL 日期分区 mask 数量无效")
        _rebuild_masked_where(select, business_terms, spec.partition_shapes)
    _drop_masked_scalar_infrastructure(tree)
    return tree


def _mask_rewritten_business_tree(
    tree: exp.Select,
    masks: Mapping[str, _SelectBusinessMask],
) -> exp.Select:
    selects = _business_selects(tree)
    if set(selects) != set(masks):
        raise UnsafeRewriteError("改写改变了业务 SELECT/CTE 所有者集合")
    for owner, select in selects.items():
        spec = masks[owner]
        _mask_scalar_projections(select, spec, rewritten=True)
        large_aliases = {
            table.alias_or_name.lower()
            for table in _direct_tables(select)
            if table.name.lower() in LARGE_PARTITIONED_TABLES
        }
        where = select.args.get("where")
        terms = _mask_conjuncts(where.this) if where is not None else []
        remaining = list(terms)
        for shape in spec.partition_shapes:
            matches = [
                index
                for index, term in enumerate(remaining)
                if _partition_shape(term, large_aliases) == shape
                and _is_rewritten_partition_term(term, large_aliases)
            ]
            if len(matches) != 1:
                raise UnsafeRewriteError("无法唯一定位改写后的日期分区合取项")
            remaining.pop(matches[0])
        _rebuild_masked_where(select, remaining, spec.partition_shapes)
    _drop_masked_scalar_infrastructure(tree)
    return tree


def _normalized_ast_dump(tree: exp.Select) -> list[dict]:
    normalized = _parse_mysql(tree.sql(dialect="mysql"))
    return normalized.dump()


def validate_business_equivalence(original_sql: str, rewritten_sql: str) -> None:
    """独立验证除明确日期基础设施外的完整业务 AST 结构不变。"""

    original = _parse_mysql(original_sql)
    rewritten = _parse_mysql(rewritten_sql)
    masks = _derive_business_masks(original)
    masked_original = _mask_original_business_tree(original, masks)
    masked_rewritten = _mask_rewritten_business_tree(rewritten, masks)
    if _normalized_ast_dump(masked_original) != _normalized_ast_dump(masked_rewritten):
        raise UnsafeRewriteError("改写改变了完整业务 AST")


def _scalar_lineage_hints_from_original(
    original_sql: str,
) -> dict[str, frozenset[str]]:
    masks = _derive_business_masks(_parse_mysql(original_sql))
    return {
        owner.removeprefix("cte:"): frozenset(
            output_name
            for _, output_name in spec.scalar_projection_indexes
        )
        for owner, spec in masks.items()
        if owner.startswith("cte:") and spec.scalar_projection_indexes
    }


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
    proven_columns_by_alias: Mapping[str, frozenset[str]],
) -> bool:
    return _has_proven_date_lineage(
        expression,
        large_aliases=large_aliases,
        bounded_large_aliases=set(),
        proven_columns_by_alias=proven_columns_by_alias,
    )


def _has_date_origin(expression: exp.Expression) -> bool:
    for literal in expression.find_all(exp.Literal):
        value = str(literal.this)
        if re.fullmatch(r"\d{8}", value) or re.fullmatch(
            r"\d{4}-\d{2}-\d{2}",
            value,
        ):
            return True
    return any(
        _date_function_name(function) in ALLOWED_DATE_FUNCTIONS
        for function in expression.find_all(exp.Func)
    )


def _date_function_name(function: exp.Func) -> str:
    if isinstance(function, exp.Anonymous):
        return function.name.upper()
    return function.sql_name().upper()


def _uses_only_date_lineage_operations(expression: exp.Expression) -> bool:
    if any(
        _date_function_name(function) not in DATE_LINEAGE_FUNCTIONS
        for function in expression.find_all(exp.Func)
    ):
        return False
    return not any(
        True
        for _ in expression.find_all(
            (exp.Add, exp.Sub, exp.Mul, exp.Div, exp.Mod)
        )
    )


def _is_date_value_ast(expression: exp.Expression) -> bool:
    return (
        not any(True for _ in expression.find_all(exp.Predicate))
        and _uses_only_date_lineage_operations(expression)
    )


def _has_proven_date_lineage(
    expression: exp.Expression,
    *,
    large_aliases: set[str],
    bounded_large_aliases: set[str],
    proven_columns_by_alias: Mapping[str, frozenset[str]],
) -> bool:
    if any(True for _ in expression.find_all(exp.Select)):
        return False
    if not _is_date_value_ast(expression):
        return False
    columns = list(expression.find_all(exp.Column))
    if not columns:
        return _has_date_origin(expression)
    for column in columns:
        alias = column.table.lower()
        name = column.name.lower()
        if not alias:
            return False
        if alias in large_aliases:
            if alias not in bounded_large_aliases or name != "dt":
                return False
            continue
        proven_columns = proven_columns_by_alias.get(alias)
        if proven_columns is None or name not in proven_columns:
            return False
    return True


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
    proven_columns_by_alias: Mapping[str, frozenset[str]],
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
                    and _is_external_boundary(
                        low,
                        large_aliases,
                        proven_columns_by_alias,
                    )
                    and _is_external_boundary(
                        high,
                        large_aliases,
                        proven_columns_by_alias,
                    )
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
                    and _is_external_boundary(
                        right,
                        large_aliases,
                        proven_columns_by_alias,
                    )
                ):
                    bounded.add(left_alias)
                if (
                    right_alias in eligible_aliases
                    and _is_external_boundary(
                        left,
                        large_aliases,
                        proven_columns_by_alias,
                    )
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
                    and all(
                        _is_external_boundary(
                            value,
                            large_aliases,
                            proven_columns_by_alias,
                        )
                        for value in values
                    )
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


def _cte_columns_by_alias(
    select: exp.Select,
    cte_lineage: Mapping[str, frozenset[str]],
) -> dict[str, frozenset[str]]:
    columns_by_alias: dict[str, frozenset[str]] = {}
    for table in _direct_tables(select):
        proven_columns = cte_lineage.get(table.name.lower())
        if proven_columns is not None:
            columns_by_alias[table.alias_or_name.lower()] = proven_columns
    return columns_by_alias


def _validate_select_partition_lineage(
    select: exp.Select,
    cte_lineage: Mapping[str, frozenset[str]],
) -> tuple[set[str], dict[str, frozenset[str]]]:
    large_tables = [
        table
        for table in _direct_tables(select)
        if table.name.lower() in LARGE_PARTITIONED_TABLES
    ]
    large_aliases = {table.alias_or_name.lower() for table in large_tables}
    proven_columns_by_alias = _cte_columns_by_alias(select, cte_lineage)
    bounded_aliases = _bounded_large_aliases(
        select,
        large_aliases,
        proven_columns_by_alias,
    )
    for table in large_tables:
        alias = table.alias_or_name.lower()
        if alias not in bounded_aliases:
            raise UnsafeRewriteError(
                f"大表 {table.name} 别名 {alias} 所在 SELECT 缺少直接 dt 条件"
            )
    return bounded_aliases, proven_columns_by_alias


def _validate_partition_lineage(
    tree: exp.Select,
    scalar_lineage_hints: Mapping[str, frozenset[str]] | None = None,
) -> None:
    scalar_lineage_hints = scalar_lineage_hints or {}
    cte_lineage: dict[str, frozenset[str]] = {}
    processed_selects: set[int] = set()
    with_clause = tree.args.get("with_")
    if with_clause is not None:
        for cte in with_clause.expressions:
            name = cte.alias_or_name.lower()
            if not isinstance(cte.this, exp.Select):
                raise UnsafeRewriteError(f"业务 CTE {name} 不是 SELECT")
            select = cte.this
            processed_selects.add(id(select))
            bounded_aliases, proven_columns_by_alias = (
                _validate_select_partition_lineage(select, cte_lineage)
            )
            has_proven_source = bool(bounded_aliases) or any(
                proven_columns_by_alias.values()
            )
            proven_outputs: set[str] = set()
            if has_proven_source:
                large_aliases = {
                    table.alias_or_name.lower()
                    for table in _direct_tables(select)
                    if table.name.lower() in LARGE_PARTITIONED_TABLES
                }
                for projection in select.expressions:
                    output_name = projection.alias_or_name.lower()
                    value = (
                        projection.this
                        if isinstance(projection, exp.Alias)
                        else projection
                    )
                    has_column_lineage = any(
                        True for _ in value.find_all(exp.Column)
                    )
                    hinted_scalar_lineage = (
                        output_name in scalar_lineage_hints.get(name, frozenset())
                        and _is_masked_date_value(value)
                    )
                    if output_name and (
                        (
                            has_column_lineage
                            and _has_proven_date_lineage(
                                value,
                                large_aliases=large_aliases,
                                bounded_large_aliases=bounded_aliases,
                                proven_columns_by_alias=proven_columns_by_alias,
                            )
                        )
                        or hinted_scalar_lineage
                    ):
                        proven_outputs.add(output_name)
            cte_lineage[name] = frozenset(proven_outputs)

    processed_selects.add(id(tree))
    _validate_select_partition_lineage(tree, cte_lineage)
    for select in tree.find_all(exp.Select):
        if id(select) not in processed_selects:
            _validate_select_partition_lineage(select, cte_lineage)


def validate_rewritten_sql(
    sql: str,
    *,
    _scalar_lineage_hints: Mapping[str, frozenset[str]] | None = None,
) -> None:
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

    _validate_partition_lineage(tree, _scalar_lineage_hints)


def rewrite_bounds_sql(view_id: str, sql: str) -> str:
    """在 SHA 白名单约束下把 bounds 标量值内联到日期谓词。"""

    spec = _require_source_hash(view_id, sql)
    scalar_lineage_hints = _scalar_lineage_hints_from_original(sql)
    tree = _parse_mysql(sql)
    original_surface = _surface_signature(tree)
    scalar_values = _resolve_scalar_cte_values(tree, allowed=spec.scalar_ctes)
    _inline_scalar_joins(tree, scalar_values)
    _drop_unreferenced_scalar_ctes(tree, scalar_values)
    if _surface_signature(tree) != original_surface:
        raise UnsafeRewriteError("改写改变了业务 CTE、字段、JOIN、GROUP、ORDER 或 LIMIT")

    rewritten = tree.sql(dialect="mysql", pretty=True)
    validate_business_equivalence(sql, rewritten)
    validate_rewritten_sql(
        rewritten,
        _scalar_lineage_hints=scalar_lineage_hints,
    )
    if _surface_signature(_parse_mysql(rewritten)) != original_surface:
        raise UnsafeRewriteError("SQL 序列化改变了业务表面签名")
    return rewritten


def freeze_curdate(sql: str, business_date: date) -> str:
    """把一条 SQL 中的 CURDATE 固定为同一个数据库业务日期。"""

    tree = _parse_mysql(sql)

    def replace_current_date(node: exp.Expression) -> exp.Expression:
        if not isinstance(node, exp.CurrentDate):
            return node
        return exp.Cast(
            this=exp.Literal.string(business_date.isoformat()),
            to=exp.DataType.build("DATE"),
        )

    return tree.transform(replace_current_date).sql(dialect="mysql", pretty=True)


def execute_query(cursor: Any, sql: str) -> QueryResult:
    """通过既有只读游标执行 SQL，并保留字段顺序和重复行。"""

    cursor.execute(sql)
    description = cursor.description or ()
    columns = tuple(str(getattr(item, "name", item[0])) for item in description)
    return QueryResult(
        columns=columns,
        rows=tuple(tuple(row) for row in cursor.fetchall()),
    )


def normalize_cell(value: Any) -> tuple[str, Any]:
    """规范化数据库驱动标量表示，不引入业务数值容差。"""

    if value is None:
        return "null", None
    if isinstance(value, datetime):
        if value.time() == time.min:
            return "date", value.date().isoformat()
        return "datetime", value.isoformat()
    if isinstance(value, date):
        return "date", value.isoformat()
    if isinstance(value, Decimal):
        return "decimal", value.normalize().to_eng_string()
    if isinstance(value, float):
        return "float", Decimal(str(value)).normalize().to_eng_string()
    return type(value).__name__, value


def _normalize_row(row: Sequence[Any]) -> tuple[tuple[str, Any], ...]:
    return tuple(normalize_cell(value) for value in row)


def compare_query_results(
    original: QueryResult,
    rewritten: QueryResult,
    *,
    ordered: bool,
) -> None:
    """严格比较原 SQL 与改写 SQL，不忽略重复行或数值差异。"""

    if original.columns != rewritten.columns:
        raise ResultMismatchError(
            f"字段不一致：原 SQL={original.columns}，改写 SQL={rewritten.columns}"
        )
    if len(original.rows) != len(rewritten.rows):
        raise ResultMismatchError(
            f"行数不一致：原 SQL={len(original.rows)}，改写 SQL={len(rewritten.rows)}"
        )

    original_rows = tuple(_normalize_row(row) for row in original.rows)
    rewritten_rows = tuple(_normalize_row(row) for row in rewritten.rows)
    if not ordered:
        if Counter(original_rows) != Counter(rewritten_rows):
            raise ResultMismatchError("无序结果的完整行或重复行计数不一致")
        return

    for row_index, (original_row, rewritten_row) in enumerate(
        zip(original_rows, rewritten_rows, strict=True)
    ):
        for column_index, (original_value, rewritten_value) in enumerate(
            zip(original_row, rewritten_row, strict=True)
        ):
            if original_value != rewritten_value:
                column = original.columns[column_index]
                raise ResultMismatchError(
                    f"第 {row_index + 1} 行字段 {column} 不一致："
                    f"原 SQL={original_value}，改写 SQL={rewritten_value}"
                )


def validate_explain_plan(plan: str) -> None:
    """拒绝由日期边界 Values 表触发的广播 Hash Join。"""

    normalized = str(plan or "")
    if all(
        marker in normalized
        for marker in ("Values", "Exchange[REPLICATE]", "InnerJoin[Hash Join]")
    ):
        raise UnsafePlanError("日期边界仍生成广播 Hash Join")


def apply_dashboard_repairs(
    connection: Any,
    dashboards: Sequence[Any],
    rewritten_sql_by_view: Mapping[str, str],
    *,
    tenant_id: int,
    update_time: int,
) -> int:
    """在一个事务中按原始 canvas 做 CAS，仅替换目标抽屉 SQL。"""

    if isinstance(update_time, bool) or not isinstance(update_time, int):
        raise TypeError("update_time 必须是整数 Unix 秒")

    requested = {str(view_id): sql for view_id, sql in rewritten_sql_by_view.items()}
    applied: set[str] = set()
    updated_dashboards = 0
    try:
        with connection.cursor() as cursor:
            for dashboard in dashboards:
                if int(dashboard.tenant_id) != int(tenant_id):
                    raise ValueError(f"看板 {dashboard.id} 不属于目标工作空间")
                canvas = json.loads(dashboard.canvas_view_info)
                if not isinstance(canvas, dict):
                    raise ValueError(f"看板 {dashboard.id} 的 canvas_view_info 不是对象")

                changed = False
                for view_id, view in canvas.items():
                    view_id = str(view_id)
                    if view_id not in requested:
                        continue
                    if view_id in applied:
                        raise ValueError(f"抽屉 {view_id} 在多个看板中重复")
                    if not isinstance(view, dict):
                        raise ValueError(f"看板 {dashboard.id} 的抽屉 {view_id} 不是对象")
                    view["sql"] = requested[view_id]
                    applied.add(view_id)
                    changed = True

                if not changed:
                    continue
                new_canvas = json.dumps(
                    canvas,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                cursor.execute(
                    """
                    UPDATE core_dashboard
                    SET canvas_view_info = %s,
                        update_time = %s
                    WHERE id = %s
                      AND tenant_id = %s
                      AND canvas_view_info = %s
                    """,
                    (
                        new_canvas,
                        update_time,
                        dashboard.id,
                        tenant_id,
                        dashboard.canvas_view_info,
                    ),
                )
                if cursor.rowcount != 1:
                    raise DashboardCasConflictError(
                        f"看板 {dashboard.id} 已变化或不存在，CAS 更新行数={cursor.rowcount}"
                    )
                updated_dashboards += 1

        missing = sorted(set(requested).difference(applied))
        if missing:
            raise ValueError(f"改写目录中的抽屉未在快照中找到：{missing}")
        connection.commit()
        return updated_dashboards
    except BaseException:
        connection.rollback()
        raise
