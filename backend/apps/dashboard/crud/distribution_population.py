"""Prove the population used by a distribution denominator from its SQL scope."""
from sqlglot import exp
from sqlglot.optimizer.scope import Scope, build_scope

from apps.dashboard.crud.cohort_input_grain import _bare, _unique_membership
from apps.dashboard.crud.event_sql_contract import _implies, _lineage, _row_predicates
from apps.dashboard.crud.cohort_sql_validation import _expanded
from apps.dashboard.crud.sql_generation_validation import _outputs, _source


POPULATION_RULE = (
    "分布 total_entities 必须统计日期和全部配置分组键下的参与主体总数。"
    "优先先按 population.unique_columns 聚合出 entity_values，再用 "
    "COUNT(*) OVER (PARTITION BY population.partition_columns) 计算总人数；"
    "计算窗口前排除 NULL 主体，每个主体在日期和分组内只有一行，窗口所在 SELECT 不得再次 GROUP BY 或关联明细。"
    "窗口不写 ORDER BY 或 frame；显式 frame 必须覆盖 UNBOUNDED PRECEDING 到 UNBOUNDED FOLLOWING。"
    "total_entities 随主体传递到分桶结果，最终使用 MAX(total_entities) 输出并作为 entity_rate 的 NULLIF 分母；"
    "禁止用 SUM(total_entities)、区间内人数、累计窗口或未引用的 CTE 代替。"
    "也允许独立按相同日期和全部分组键 COUNT(DISTINCT entity_id) 后再关联的等价结构。"
)


def _full_partition(window):
    spec = window.args.get("spec")
    if spec is None:
        return window.args.get("order") is None and not window.args.get("alias")
    return (spec.args.get("start") == "UNBOUNDED" and spec.args.get("start_side") == "PRECEDING"
            and spec.args.get("end") == "UNBOUNDED" and spec.args.get("end_side") == "FOLLOWING"
            and not spec.args.get("exclude"))


def _group_expressions(scope):
    group = scope.expression.args.get("group")
    if group is None:
        return []
    if any(group.args.get(key) for key in ("rollup", "cube", "grouping_sets", "all")):
        raise ValueError("不支持分母使用多层汇总分组")
    outputs = _outputs(scope) or {}
    result = []
    for node in group.expressions:
        if isinstance(node, exp.Literal) and not node.is_string and node.this.isdigit():
            node = scope.expression.selects[int(node.this) - 1]
        elif isinstance(node, exp.Column) and not node.table and node.name in outputs:
            node = outputs[node.name]
        result.append(_expanded(node, scope).sql())
    return result


def _resolve_total(scope, node, dimensions, seen=frozenset()):
    """Follow only value-preserving projections to the count supplying the result."""
    node = _bare(node)
    marker = (id(scope), node.sql())
    if marker in seen or scope.union_scopes:
        raise ValueError("total_entities 来源不唯一")
    seen = seen | {marker}
    if isinstance(node, (exp.Max, exp.Min)):
        return _resolve_total(scope, node.this, dimensions, seen)
    if isinstance(node, exp.Column):
        source = _source(scope, node)
        if not isinstance(source, Scope):
            raise ValueError("total_entities 缺少可验证的聚合来源")
        projection = (_outputs(source) or {}).get(node.name)
        if projection is None:
            raise ValueError("total_entities 来源字段不存在")
        # Carry the output dimensions through the same relation as the total.
        mapped = []
        source_outputs = _outputs(source) or {}
        for dimension in dimensions:
            dimension = _bare(dimension)
            if not isinstance(dimension, exp.Column):
                raise ValueError("分母分组字段必须在各层显式输出")
            if _source(scope, dimension) is source and dimension.name in source_outputs:
                mapped.append(source_outputs[dimension.name])
                continue
            # The separate totals form joins its population keys to the
            # bucket relation. Require an explicit equality for every key.
            candidates = []
            for join in scope.expression.args.get("joins") or []:
                on = join.args.get("on")
                if on is None:
                    continue
                for equality in on.find_all((exp.EQ, exp.NullSafeEQ)):
                    for left, right in ((equality.this, equality.expression), (equality.expression, equality.this)):
                        if (isinstance(left, exp.Column) and isinstance(right, exp.Column)
                                and _expanded(left, scope).sql() == _expanded(dimension, scope).sql()
                                and _source(scope, right) is source and right.name in source_outputs):
                            candidates.append(source_outputs[right.name])
            if not candidates:
                raise ValueError("分母关联必须包含日期和全部配置分组键")
            mapped.append(candidates[0])
        return _resolve_total(source, projection, mapped, seen)
    expected = {_expanded(dimension, scope).sql() for dimension in dimensions}
    if isinstance(node, exp.Window):
        count = node.this
        if not isinstance(count, exp.Count) or not isinstance(count.this, exp.Star):
            raise ValueError("主体聚合后的窗口分母必须使用 COUNT(*)")
        if not _full_partition(node):
            raise ValueError("total_entities 窗口必须覆盖整个分区，不能累计或滑动计数")
        partitions = node.args.get("partition_by") or []
        if {_expanded(item, scope).sql() for item in partitions} != expected:
            raise ValueError("total_entities 窗口分区必须包含日期和全部配置分组键，不能增加主体或区间键")
        if scope.expression.args.get("group") or scope.expression.args.get("having") or scope.expression.args.get("qualify"):
            raise ValueError("total_entities 窗口必须在分桶汇总之前计算")
        sources = list(scope.selected_sources.values())
        if len(sources) != 1 or not isinstance(sources[0][1], Scope):
            raise ValueError("total_entities 窗口必须直接读取主体聚合结果，不能关联明细放大人数")
        source = sources[0][1]
        entity = exp.column("entity_id", table=next(iter(scope.selected_sources)))
        if "entity_id" not in (_outputs(source) or {}):
            raise ValueError("窗口输入缺少 entity_id")
        if not all(isinstance(item, exp.Column) and _source(scope, item) is source for item in partitions):
            raise ValueError("窗口分组必须直接引用主体聚合输入的日期和分组列")
        names = list(dict.fromkeys([item.name for item in partitions] + ["entity_id"]))
        if not _unique_membership(source, names):
            raise ValueError("必须先按日期、全部配置分组键和 entity_id 聚合为每主体一行")
        target = exp.Not(this=exp.Is(this=_expanded(entity, scope), expression=exp.Null()))
        if not any(_implies(predicate, target) for predicate in _row_predicates(scope)):
            raise ValueError("COUNT(*) 窗口计算前必须排除 NULL 主体")
        return (id(scope), node.sql())
    if isinstance(node, exp.Count) and isinstance(node.this, exp.Distinct):
        args = node.this.expressions
        if len(args) != 1 or not isinstance(args[0], exp.Column) or args[0].name != "entity_id":
            raise ValueError("独立分母必须统计 COUNT(DISTINCT entity_id)")
        if set(_group_expressions(scope)) != expected:
            raise ValueError("独立分母必须仅按日期和全部配置分组键聚合，不能按区间聚合")
        return (id(scope), node.sql())
    raise ValueError("total_entities 必须来自主体总数，不能替换成常量或其他计算")


def population_issues(statements, partition_columns):
    try:
        if len(statements) != 1:
            raise ValueError("需要单个分布查询")
        root = build_scope(statements[0])
        if root is None or root.union_scopes:
            raise ValueError("需要明确的最终分布 SELECT")
        outputs = _outputs(root) or {}
        if any(name not in outputs for name in [*partition_columns, "total_entities", "entity_rate"]):
            raise ValueError("最终结果必须输出日期、全部配置分组键、total_entities 和 entity_rate")
        dimensions = [outputs[name] for name in partition_columns]
        total = _resolve_total(root, outputs["total_entities"], dimensions)
        rates = list(_lineage(root, outputs["entity_rate"]))
        divisors = [(scope, node.expression) for scope, expression in rates
                    for node in expression.find_all(exp.Div)]
        if not divisors:
            raise ValueError("entity_rate 必须除以 total_entities")
        matched = False
        for scope, divisor in divisors:
            divisor = _bare(divisor)
            if not isinstance(divisor, exp.Nullif) or not isinstance(divisor.expression, exp.Literal) or divisor.expression.this != "0":
                continue
            # The rate and the displayed total use exactly the same source
            # expression at their output scope. No unrelated NULLIF counts.
            if scope is root and _resolve_total(scope, divisor.this, dimensions) == total:
                matched = True
        if not matched:
            raise ValueError("entity_rate 必须使用同一个 total_entities 并以 NULLIF(..., 0) 保护分母")
        return []
    except (ValueError, KeyError, IndexError, AttributeError) as exc:
        return [f"分布 SQL 总体主体数无法验证：{exc}。"]
