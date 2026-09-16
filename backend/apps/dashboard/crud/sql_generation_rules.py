"""Pure SQL constraints shared by dashboard generation and repair.

Only engine and explicit time configuration influence these rules. This module
does not retrieve semantic records, schema, application settings, or business data.
"""
from __future__ import annotations

import re
from typing import Any

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError
from sqlglot.optimizer.normalize_identifiers import normalize_identifiers
from sqlglot.optimizer.scope import Scope, build_scope


MYSQL_FAMILY = frozenset({"mysql", "mariadb", "doris", "starrocks", "analyticdb"})
_POSTGRES_FAMILY = frozenset({"postgres", "postgresql"})
# The dashboard renderer substitutes complete typed SQL literals, so tokens
# must never be quoted here. Keep the same public token contract as
# dashboard_date_filter.dashboard_date_parameter_tokens without importing its
# settings/database dependencies into this pure module.
_DATE_PARAMETER_TOKENS = {
    "date": ("{{dashboard_start_date}}", "{{dashboard_end_date}}"),
    "yyyymmdd_number": ("{{dashboard_start_yyyymmdd}}", "{{dashboard_end_yyyymmdd}}"),
    "yyyymmdd_text": ("{{dashboard_start_yyyymmdd}}", "{{dashboard_end_yyyymmdd}}"),
    "timestamp": ("{{dashboard_start_timestamp}}", "{{dashboard_end_exclusive_timestamp}}"),
}


def _dialect_family(dialect: str) -> str:
    words = set(re.findall(r"[a-z]+", str(dialect or "").lower()))
    mysql = bool(words & MYSQL_FAMILY)
    postgres = bool(words & _POSTGRES_FAMILY)
    if mysql == postgres:
        return "unsupported"
    return "mysql" if mysql else "postgres"


def _parameter_type(time_config: dict[str, Any]) -> str:
    return str(time_config.get("date_parameter_type") or time_config.get("dateParameterType") or "").strip()


def _date_expression(expression: str, parameter_type: str, family: str) -> str:
    if parameter_type == "date":
        return f"CAST({expression} AS DATE)"
    if family == "mysql":
        return f"STR_TO_DATE(CAST({expression} AS CHAR), '%Y%m%d')"
    return f"TO_DATE(CAST({expression} AS TEXT), 'YYYYMMDD')"


def generation_sql_rules(dialect: str, time_config: dict[str, Any]) -> dict[str, Any]:
    """Return shared prompt constraints, including unsupported-capability notes.

    ``supported`` describes the dialect-specific additions, not permission to
    generate SQL. Generic rules remain applicable to every existing dialect.
    """
    family = _dialect_family(dialect)
    parameter_type = _parameter_type(time_config)
    tokens = list(_DATE_PARAMETER_TOKENS.get(parameter_type, ()))
    issues: list[str] = []
    rules = [
        "只读规则：只生成一个 SELECT 或 WITH ... SELECT 查询，禁止 DDL、DML、多语句及有写入副作用的操作。",
        "字段和数据源必须来自当前授权配置；不得根据相似名称替换字段、引用未配置的数据源或虚构业务口径。",
        "每个物理事实来源/指标子查询都必须独立落实适用的时间范围、全局筛选与权限条件；指标内筛选只作用于该指标，不能合并到其他指标。",
        "保留配置的 AND/OR、空值处理与筛选作用域；LEFT JOIN 右侧事实筛选放在事实聚合层或 ON 中，不能用最终 WHERE 删除应保留的空日期行。",
        "禁止在同一 SELECT 输出表达式、WHERE 或 JOIN ON 中依赖该 SELECT 刚定义的别名；先在子查询或 CTE 中计算，再由外层引用。窗口别名的筛选也必须在外层执行。",
        "先按配置粒度聚合事实再连接，避免一对多 JOIN 放大指标；保持分组维度、指标顺序、空值含义和零分母语义。",
        "条件计数仅在当前指标作用域使用 COUNT(CASE WHEN <configured_predicate> THEN 1 END)；去重计数使用 COUNT(DISTINCT CASE WHEN <configured_predicate> THEN <configured_entity> END)。不能用 COUNT(CASE ... ELSE 0 END) 表示条件计数。",
        "条件求和仅在当前指标作用域使用 SUM(CASE WHEN <configured_predicate> THEN <configured_numeric_expression> ELSE 0 END)；谓词、实体和数值表达式必须来自该指标配置，不能跨指标传播筛选或补充业务条件。",
        "需要连续日期时，使用日期骨架 LEFT JOIN 已聚合事实；补零不能代替补日期，不得用 LIMIT 或固定天数序列截断所选范围。额外维度集合只能来自授权配置或数据。",
    ]
    quote = None
    if family == "mysql":
        quote = "`"
        rules.extend([
            "MySQL 兼容方言：标识符使用反引号 `，字符串使用单引号；数值整数转换使用 CAST(... AS SIGNED)，不使用 UNSIGNED。",
            "MySQL/AnalyticDB 兼容方言日期骨架使用非递归 CTE/派生表数字序列，禁止 WITH RECURSIVE；不因驱动名称推断递归 CTE 能力。",
            "MySQL 兼容方言不使用 FULL OUTER JOIN；JOIN ON 中不放 EXISTS、IN 或标量子查询，应先形成 CTE/派生表并显式连接后引用其列。",
        ])
    elif family == "postgres":
        quote = '"'
        rules.append("PostgreSQL 方言：标识符使用双引号，字符串使用单引号；真实 DATE 使用日期加整数天数或对应类型的 INTERVAL 运算。")
    else:
        issues.append(f"未提供方言 {dialect or '(缺失)'} 的日期骨架能力；保留该方言原有生成路径，标识符引用和日期函数必须按实际引擎确认，不能套用 MySQL/PostgreSQL 语法。")

    if tokens:
        rules.append(f"看板时间参数只使用 {tokens[0]} 和 {tokens[1]}；占位符不加引号、不改名，禁止使用当前时间函数或固定日期替代。")
    elif parameter_type:
        issues.append(f"不支持的日期参数类型 {parameter_type}，必须保留配置并明确说明缺失能力，不能替换为其他时间类型。")
    if parameter_type in {"yyyymmdd_number", "yyyymmdd_text"}:
        rules.append("YYYYMMDD 是编码键；原始时间字段直接与同类型参数比较以过滤，日期维度及运算使用另行解析的真实 DATE。禁止 FROM_UNIXTIME、FROM_DAYS 或对编码键直接加减天数、INTERVAL。")
        if family != "unsupported":
            parsed = _date_expression("<yyyymmdd_expression>", parameter_type, family)
            rules.append(f"YYYYMMDD 转真实日期的统一表达式为 {parsed}；仅在已解析 DATE 上计算窗口与日差。")
    elif parameter_type == "timestamp":
        rules.append("timestamp 参数采用开始包含、结束不包含的范围；保留配置的实际时间字段类型、时间单位、时区和粒度，不得擅自按秒、毫秒或日粒度解释。")
    rules.extend(issues)
    return {
        "dialect": dialect,
        "dialect_family": family,
        "supported": family != "unsupported",
        "identifier_quote": quote,
        "required_tokens": tokens,
        "rules": rules,
        "capability_issues": issues,
    }


def build_date_scaffold(time_config: dict[str, Any], dialect: str) -> dict[str, Any]:
    """Build composable, inclusive daily date CTEs for supported configurations.

    ``cte_sql`` contains CTE definitions without WITH or a trailing comma;
    callers can add their aggregate CTEs after it. ``select_sql`` is a complete
    query. ``date_expression`` is a DATE; ``key_expression`` retains the
    configured date/encoded-number/encoded-text type for joins to raw keys.

    Seven decimal positions cover every span representable by the application's
    0001..9999 date parameters. Each expansion is filtered by the dynamic span;
    no configured window, calendar date, or business table is hardcoded.
    """
    family = _dialect_family(dialect)
    parameter_type = _parameter_type(time_config)
    grain = str(time_config.get("grain") or "").strip().lower()
    result: dict[str, Any] = {
        "supported": False,
        "reason": "",
        "dialect": dialect,
        "grain": grain,
        "parameter_type": parameter_type,
        "cte_name": "dashboard_dates",
        "cte_sql": "",
        "select_sql": "",
        "date_column": "calendar_date",
        "date_expression": "dashboard_dates.calendar_date",
        "key_expression": "",
        "required_tokens": list(_DATE_PARAMETER_TOKENS.get(parameter_type, ())),
        "instructions": [],
    }
    if family == "unsupported":
        result["reason"] = f"方言 {dialect or '(缺失)'} 尚无已确认兼容的日期骨架。"
    elif grain != "day":
        result["reason"] = f"日期骨架只支持明确的 day 粒度；当前粒度为 {grain or '(缺失)'}，不做转换。"
    elif parameter_type not in {"date", "yyyymmdd_number", "yyyymmdd_text"}:
        result["reason"] = f"日期骨架未支持参数类型 {parameter_type or '(缺失)'} 的实际时间类型及边界语义。"
    if result["reason"]:
        result["instructions"] = [
            result["reason"],
            "不注入伪造日期骨架；生成器必须按配置的实际时间类型、时区、单位、粒度及当前方言规则处理，不能静默改为日粒度或其他参数类型。",
        ]
        return result

    start, end = (
        _date_expression(token, parameter_type, family)
        for token in result["required_tokens"]
    )
    difference = "DATEDIFF(b.end_date, b.start_date)" if family == "mysql" else "b.end_date - b.start_date"
    ctes = [
        f"dashboard_date_bounds AS (\n    SELECT {start} AS start_date, {end} AS end_date\n)",
        "dashboard_date_span AS (\n"
        f"    SELECT b.start_date, {difference} AS day_count\n"
        "    FROM dashboard_date_bounds AS b\n)",
        "dashboard_digits AS (\n    " + " UNION ALL ".join(f"SELECT {digit} AS n" for digit in range(10)) + "\n)",
        "dashboard_offsets_0 AS (\n"
        "    SELECT b.start_date, b.day_count, d.n\n"
        "    FROM dashboard_date_span AS b CROSS JOIN dashboard_digits AS d\n"
        "    WHERE d.n <= b.day_count\n)",
    ]
    for position in range(1, 7):
        number = f"p.n + d.n * {10 ** position}"
        ctes.append(
            f"dashboard_offsets_{position} AS (\n"
            f"    SELECT p.start_date, p.day_count, {number} AS n\n"
            f"    FROM dashboard_offsets_{position - 1} AS p CROSS JOIN dashboard_digits AS d\n"
            f"    WHERE {number} <= p.day_count\n)"
        )
    calendar_date = "DATE_ADD(p.start_date, INTERVAL p.n DAY)" if family == "mysql" else "p.start_date + p.n"
    ctes.append(f"dashboard_dates AS (\n    SELECT {calendar_date} AS calendar_date\n    FROM dashboard_offsets_6 AS p\n)")
    result["cte_sql"] = ",\n".join(ctes)
    result["select_sql"] = f"WITH {result['cte_sql']}\nSELECT dashboard_dates.calendar_date FROM dashboard_dates ORDER BY dashboard_dates.calendar_date"
    key = result["date_expression"]
    if parameter_type.startswith("yyyymmdd"):
        key = f"DATE_FORMAT({key}, '%Y%m%d')" if family == "mysql" else f"TO_CHAR({key}, 'YYYYMMDD')"
        if parameter_type == "yyyymmdd_number":
            key = f"CAST({key} AS {'SIGNED' if family == 'mysql' else 'INTEGER'})"
    result["key_expression"] = key
    result["supported"] = True
    result["instructions"] = [
        "本骨架需非递归 CTE、CROSS JOIN 与当前方言的日期运算能力；SQL 中保留提供的 CTE 定义，并在其后追加事实聚合 CTE。",
        "日期边界由看板参数决定且两端包含；完整保留动态范围，不改成固定天数、不使用递归 CTE 或 LIMIT 截断。",
        "calendar_date 是真实 DATE；原始事实筛选继续使用原类型的 required_tokens，连接编码键时使用 key_expression。",
        "需要连续日期的结果从 dashboard_dates 出发 LEFT JOIN 已按配置粒度聚合的事实；仅对配置允许补零的数值度量补零，保留未定义比率等 NULL 语义。",
        "日期结果路径使用日期来源作为 FROM 首来源、LEFT JOIN 事实聚合、CROSS JOIN 配置的维度集合；不使用 INNER/SEMI/ANTI/RIGHT JOIN。事实侧条件留在事实 CTE 或 ON，不能在外层 WHERE/HAVING 筛除补零行。",
        "额外维度按配置的授权维度集合与日期组合；保留原有结果列别名、维度粒度与筛选作用域，最终按 calendar_date 排序。",
        "最终日期列必须来自日期骨架，分组列必须来自完整维度集合；不能输出 LEFT JOIN 事实侧的日期/分组列，否则空日期和空分组会变成 NULL。",
    ]
    return result


def _scaffold_ast(sql: str, dialect: str) -> exp.Query:
    # Named placeholders remain distinct AST leaves. Replacing both endpoints
    # with a single sample date would incorrectly accept reversed/same bounds.
    for tokens in _DATE_PARAMETER_TOKENS.values():
        for token in tokens:
            sql = sql.replace(token, f":__scaffold_{token[2:-2]}")
    statements = sqlglot.parse(sql, read=dialect)
    if len(statements) != 1 or not isinstance(statements[0], exp.Query):
        raise ValueError("日期骨架必须属于单个 SELECT 查询")
    statement = normalize_identifiers(statements[0], dialect=dialect)

    for node in reversed(list(statement.walk())):
        # Quoted lowercase identifiers and redundant parentheses do not change
        # the supplied definition. Case-sensitive quoted names remain distinct
        # because normalize_identifiers respects the engine's casing rules.
        if isinstance(node, exp.Identifier):
            node.set("quoted", False)
        if isinstance(node, exp.Paren):
            node.replace(node.this)

    return statement


def _date_row_preservation_issues(root: Scope, target: exp.Expression, date_paths: dict[int, bool]) -> list[str]:
    """Conservatively validate the standard date-left/aggregate-right shape.

    A CROSS JOIN source represents a dimension set selected by the caller;
    this structural check cannot establish its authorization or cardinality.
    Only row sources and filters on reachable date paths are inspected.
    """
    issues: list[str] = []

    def sources(scope: Scope) -> dict[str, Any]:
        return {name: source for name, (_, source) in scope.selected_sources.items()}

    def output_names(source: Any, visited: frozenset[int] = frozenset()) -> set[str] | None:
        if not isinstance(source, Scope) or id(source) in visited:
            return None
        if source.outer_columns:
            return set(source.outer_columns)
        names = set()
        available = sources(source)
        for projection in source.expression.selects:
            if not projection.is_star:
                names.add(projection.alias_or_name)
                continue
            qualifier = projection.table if isinstance(projection, exp.Column) else ""
            for alias, child in available.items():
                if qualifier and alias != qualifier:
                    continue
                child_names = output_names(child, visited | {id(source)})
                if child_names is None:
                    return None
                names.update(child_names)
        return names

    def roles(scope: Scope) -> dict[str, str]:
        result = {}
        from_clause = scope.expression.args.get("from_")
        if from_clause is not None:
            alias = from_clause.this.alias_or_name
            child = sources(scope).get(alias)
            if isinstance(child, Scope) and date_paths.get(id(child)):
                result[alias] = "date"
        for join in scope.expression.args.get("joins") or []:
            # A filtered CROSS JOIN has inner-join semantics, so it cannot be
            # treated as an unconditional date/dimension combination.
            if join.kind == "CROSS" and not join.args.get("on") and not join.args.get("using"):
                result[join.this.alias_or_name] = "dimension"
        return result

    def source_column_safe(scope: Scope, alias: str, name: str, visited: frozenset) -> bool:
        role = roles(scope).get(alias)
        if role == "dimension":
            return True
        if role != "date":
            return False
        source = sources(scope).get(alias)
        return isinstance(source, Scope) and projection_safe(source, name, visited)

    def candidates(scope: Scope, name: str, qualifier: str = "") -> list[str]:
        return [alias for alias, source in sources(scope).items()
                if (not qualifier or alias == qualifier)
                and (output_names(source) is None or name in output_names(source))]

    def projection_safe(scope: Scope, name: str, visited: frozenset) -> bool:
        marker = (id(scope), name)
        if marker in visited:
            return False
        visited = visited | {marker}
        if scope.expression is target:
            return name == "calendar_date"
        projections = list(scope.expression.selects)
        names = scope.outer_columns or [item.alias_or_name for item in projections]
        matching = [item for alias, item in zip(names, projections) if alias == name and not item.is_star]
        if len(matching) == 1:
            item = matching[0]
            return expression_safe(item.this if isinstance(item, exp.Alias) else item, scope, visited)
        if matching:
            return False
        star_sources = []
        for item in projections:
            if item.is_star:
                qualifier = item.table if isinstance(item, exp.Column) else ""
                star_sources.extend(candidates(scope, name, qualifier))
        return bool(star_sources) and all(source_column_safe(scope, alias, name, visited) for alias in star_sources)

    def expression_safe(expression: exp.Expression, scope: Scope, visited: frozenset = frozenset()) -> bool:
        # Scalar queries/EXISTS can filter by facts even without a column in
        # this scope. Require such filters inside the relevant source instead.
        if any(isinstance(node, exp.Query) for node in expression.walk()):
            return False
        for column in expression.find_all(exp.Column):
            aliases = candidates(scope, column.name, column.table)
            if aliases:
                if not all(source_column_safe(scope, alias, column.name, visited) for alias in aliases):
                    return False
            elif column.table or not projection_safe(scope, column.name, visited):
                return False
        return True

    def output_paths(scope: Scope):
        yield scope
        if scope.expression is target:
            return
        if scope.union_scopes:
            for child in scope.union_scopes:
                if date_paths.get(id(child)):
                    yield from output_paths(child)
        else:
            from_clause = scope.expression.args.get("from_")
            child = sources(scope).get(from_clause.this.alias_or_name) if from_clause is not None else None
            if isinstance(child, Scope) and date_paths.get(id(child)):
                yield from output_paths(child)

    # Follow the date-bearing FROM chain, not the nullable aggregate side of
    # a LEFT JOIN. Facts may themselves join the calendar to bound their scan
    # without becoming responsible for preserving the final date rows.
    for scope in output_paths(root):
        expression = scope.expression
        if expression.args.get("limit") is not None or expression.args.get("offset") is not None:
            issues.append("SQL 在日期骨架输出路径使用 LIMIT/OFFSET，可能截断看板所选日期；请完整返回日期范围。")
        if expression is target:
            continue
        if isinstance(expression, (exp.Intersect, exp.Except)):
            issues.append("日期输出路径不能使用 INTERSECT/EXCEPT 筛除日期，请保留日期 FROM 与聚合 LEFT JOIN 的标准结构。")
            continue
        if not isinstance(expression, exp.Select):
            continue
        if "date" not in roles(scope).values():
            issues.append("日期输出路径必须以日期骨架或其结果作为 FROM 首来源，再 LEFT JOIN 聚合；RIGHT JOIN 等其他结构请改写为该标准形式。")
        for join in expression.args.get("joins") or []:
            preserves = (join.side == "LEFT" and join.kind in {"", "OUTER"}) or (
                join.kind == "CROSS" and not join.args.get("on") and not join.args.get("using")
            )
            if not preserves:
                issues.append("日期输出路径的 JOIN 可能删除缺少事实的日期；仅支持日期 FROM、聚合 LEFT JOIN 和配置维度集合的 CROSS JOIN。")
        for clause in ("where", "having", "qualify"):
            predicate = expression.args.get(clause)
            if predicate is not None and not expression_safe(predicate.this, scope):
                issues.append(f"日期输出路径的 {clause.upper()} 引用了事实侧或无法确认保留日期的表达式；请将事实筛选移入事实聚合 CTE 或 LEFT JOIN ON，外层仅保留日期和配置维度筛选。")
    return issues


def date_scaffold_issues(sql: str, scaffold: dict[str, Any], dialect: str) -> list[str]:
    """Validate the supplied CTE contract and its use as a result row source.

    Call with the original SQL before date tokens are rendered. This is a
    normalized structural comparison of supplied definitions, not a proof of
    arbitrary SQL equivalence. Additional metric CTEs are unrestricted by this
    check. LIMIT/OFFSET in independent metric sources do not truncate the date
    source, so only scopes on a result path from the scaffold are checked.
    """
    if not scaffold.get("supported"):
        return []
    family = _dialect_family(dialect)
    if family == "unsupported":
        return ["日期骨架校验缺少已确认的 SQL 方言，不能确认骨架定义及日期范围。"]
    if not scaffold.get("cte_sql") or not scaffold.get("cte_name"):
        return ["日期骨架配置缺少 CTE 定义或输出名称，无法验证完整日期范围。"]
    try:
        expected = _scaffold_ast(f"WITH {scaffold['cte_sql']} SELECT 1", family)
        actual = _scaffold_ast(sql, family)
    except (SqlglotError, ValueError):
        return ["日期骨架 SQL 无法解析为单个查询，请保留提供的 CTE 和原始日期参数后重新生成。"]

    expected_ctes = {cte.alias_or_name: cte for cte in expected.find_all(exp.CTE)}
    if scaffold["cte_name"] not in expected_ctes:
        return ["日期骨架输出名称未由提供的 CTE 定义，无法验证完整日期范围。"]
    actual_ctes: dict[str, list[exp.CTE]] = {}
    for cte in actual.find_all(exp.CTE):
        actual_ctes.setdefault(cte.alias_or_name, []).append(cte)
    missing = [name for name in expected_ctes if name not in actual_ctes]
    changed = [name for name, cte in expected_ctes.items()
               if name in actual_ctes and (len(actual_ctes[name]) != 1 or actual_ctes[name][0] != cte)]
    issues = []
    if missing:
        issues.append("SQL 未完整保留日期骨架 CTE：" + "、".join(missing) + "。")
    if changed:
        issues.append("SQL 改写或遮蔽了日期骨架 CTE：" + "、".join(changed) + "；必须保留原始起止参数、动态天数和完整非递归序列。")
    if any(with_clause.args.get("recursive") for with_clause in actual.find_all(exp.With)):
        issues.append("提供的日期骨架使用非递归 CTE，不能改为 WITH RECURSIVE。")
    if issues:
        return issues

    target = actual_ctes[scaffold["cte_name"]][0].this
    seen: dict[int, bool] = {}

    def depends_on_dates(scope: Scope) -> bool:
        if id(scope) in seen:
            return seen[id(scope)]
        seen[id(scope)] = False
        # Follow actual FROM/JOIN sources and set-operation branches. Merely
        # declared CTEs and scalar subqueries cannot supply continuous rows.
        children = list(scope.union_scopes)
        children.extend(source for _, source in scope.selected_sources.values() if isinstance(source, Scope))
        child_results = [depends_on_dates(child) for child in children]
        depends = scope.expression is target or any(child_results)
        seen[id(scope)] = depends
        return depends

    try:
        root = build_scope(actual)
        if root is None or not depends_on_dates(root):
            issues.append("最终查询未实际以日期骨架作为结果行来源；仅声明或在未使用的 CTE/标量子查询中引用 dashboard_dates 不能补齐日期。")
        else:
            issues.extend(_date_row_preservation_issues(root, target, seen))
    except SqlglotError:
        issues.append("日期骨架来源存在无法解析的别名或 CTE 作用域，请消除重复定义后重新生成。")
    return list(dict.fromkeys(issues))
