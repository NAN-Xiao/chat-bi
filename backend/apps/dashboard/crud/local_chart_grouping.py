"""Describe local aggregation from existing SQL; never execute SQL or read a DB."""
import re

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import Scope, build_scope
from sqlglot.dialects.dialect import Dialect
from sqlglot.tokens import Tokenizer


class LocalSqlDialect(Dialect):
    """Structural reader for declared SQL with common identifier delimiters.

    This dialect only reads expressions; it never renders or executes SQL.
    """
    class Tokenizer(Tokenizer):
        IDENTIFIERS = ['"', '`', ('[', ']')]


class LocalPlanError(ValueError):
    pass


class LocalGroupingPlanner:
    def __init__(self, sql, dialect):
        source = re.sub(r'\{\{(dashboard_[a-z0-9_]+)\}\}', r':\1', sql)
        statements = [q for q in sqlglot.parse(source, read=dialect or LocalSqlDialect) if q is not None]
        if len(statements) != 1 or not isinstance(statements[0], exp.Query):
            raise LocalPlanError('需要单条只读查询的计算配置。')
        self.root = build_scope(statements[0])
        if self.root is None or not isinstance(self.root.expression, exp.Select):
            raise LocalPlanError('需要外层 SELECT 明确声明结果字段。')
        self.names = self.root.expression.named_selects
        self.summary_scopes = set()
        if '*' in self.names or len(self.names) != len(set(self.names)):
            raise LocalPlanError('结果字段必须显式声明且名称唯一。')

    def source(self, scope, column):
        sources = scope.selected_sources
        if column.table:
            if column.table not in sources:
                raise LocalPlanError('字段跨查询作用域，缺少本地计算配置。')
            return sources[column.table][1]
        candidates = [s for _, s in sources.values()
                      if not isinstance(s, Scope) or column.name in s.expression.named_selects]
        if len(candidates) != 1:
            raise LocalPlanError('字段来源不唯一，缺少本地计算配置。')
        return candidates[0]

    def output(self, scope, name, evaluate, visited=frozenset()):
        marker = (id(scope), name)
        if marker in visited:
            raise LocalPlanError('递归查询缺少本地计算配置。')
        visited = visited | {marker}
        names = scope.expression.named_selects
        if name not in names:
            raise LocalPlanError('缺少本地计算所需的原始字段。')
        index = names.index(name)
        return self.output_at(scope, index, evaluate, visited)

    def output_at(self, scope, index, evaluate, visited):
        if scope.union_scopes:
            values = [self.output_at(branch, index, evaluate, visited) for branch in scope.union_scopes]
            if evaluate == self.dimension:
                return any(values)
            nonnull = [v for v in values if v != {'value': None}]
            if nonnull and all(v == nonnull[0] for v in nonnull):
                return nonnull[0]
            raise LocalPlanError('联合查询的指标口径不一致，无法本地汇总。')
        return evaluate(scope, scope.expression.expressions[index].unalias(), visited)

    def group_expression(self, scope, item):
        projections = scope.expression.expressions
        if isinstance(item, exp.Literal) and item.is_int:
            index = int(item.this) - 1
            if 0 <= index < len(projections):
                return projections[index].unalias()
        if isinstance(item, exp.Column) and not item.table:
            alias = next((p for p in projections if p.alias == item.name), None)
            if alias is not None:
                return alias.unalias()
        return item

    def dimension(self, scope, expression, visited=frozenset()):
        if expression.find(exp.AggFunc, exp.Window, exp.Subquery):
            return False
        group = scope.expression.args.get('group')
        if group and any(self.group_expression(scope, item) == expression for item in group.expressions):
            return True
        if isinstance(expression, exp.Case):
            values = [item.args.get('true') for item in expression.args.get('ifs', [])]
            values.append(expression.args.get('default'))
            return any(self.dimension(scope, value, visited) for value in values if value is not None)
        columns = list(expression.find_all(exp.Column))
        return bool(columns) and all(
            isinstance(self.source(scope, column), Scope)
            and self.output(self.source(scope, column), column.name, self.dimension, visited)
            for column in columns
        )

    @staticmethod
    def atomic(scope, expression, aggregation):
        return {'atom': f'{id(scope)}:{expression.sql()}', 'aggregation': aggregation}

    def formula(self, scope, expression, visited=frozenset()):
        if isinstance(expression, exp.Paren):
            return self.formula(scope, expression.this, visited)
        if isinstance(expression, exp.Null):
            return {'value': None}
        if isinstance(expression, exp.Literal) and not expression.is_string:
            return {'value': float(expression.this), '_floating': bool(re.search(r'[.eE]', expression.this))}
        if isinstance(expression, exp.Column):
            source = self.source(scope, expression)
            if not isinstance(source, Scope):
                raise LocalPlanError('缺少字段的聚合方式，不能把现有数值直接相加。')
            return self.output(source, expression.name, self.formula, visited)
        if isinstance(expression, exp.AggFunc) and expression.find(exp.Distinct):
            raise LocalPlanError('缺少去重明细，已有去重聚合值不能直接相加。')
        aggregations = {exp.Sum: 'sum', exp.Min: 'min', exp.Max: 'max', exp.Count: 'sum'}
        for cls, aggregation in aggregations.items():
            if isinstance(expression, cls):
                columns = list(expression.this.find_all(exp.Column))
                if any(isinstance(self.source(scope, column), Scope) for column in columns):
                    child = self.formula(scope, expression.this, visited)
                    if child.get('atom') and child['aggregation'] == aggregation and cls is not exp.Count:
                        return child
                    raise LocalPlanError('缺少该指标的原始明细，不能对已有聚合结果再次汇总。')
                return self.atomic(scope, expression, aggregation)
        if isinstance(expression, exp.Avg):
            return {'op': 'divide', 'args': [
                self.atomic(scope, exp.Sum(this=expression.this.copy()), 'sum'),
                self.atomic(scope, exp.Count(this=expression.this.copy()), 'sum'),
            ]}
        operators = {exp.Add: 'add', exp.Sub: 'subtract', exp.Mul: 'multiply', exp.Div: 'divide', exp.Mod: 'modulo'}
        for cls, op in operators.items():
            if isinstance(expression, cls):
                args = [self.formula(scope, expression.this, visited), self.formula(scope, expression.expression, visited)]
                floating = any(arg.get('_floating') for arg in args)
                if op == 'divide' and not floating:
                    raise LocalPlanError('缺少指标数值类型，无法确定整数或小数除法口径。')
                return {'op': op, 'args': args, '_floating': floating}
        if isinstance(expression, exp.Neg):
            return {'op': 'negate', 'args': [self.formula(scope, expression.this, visited)]}
        if isinstance(expression, exp.Nullif):
            args = [self.formula(scope, expression.this, visited), self.formula(scope, expression.expression, visited)]
            return {'op': 'nullif', 'args': args, '_floating': args[0].get('_floating', False)}
        if isinstance(expression, exp.Coalesce):
            args = [self.formula(scope, value, visited) for value in [expression.this, *expression.expressions]]
            if len(args) == 2 and args[0].get('aggregation') == 'sum' and args[1].get('value') == 0.0:
                return args[0]
            return {'op': 'coalesce', 'args': args}
        if isinstance(expression, exp.Round):
            decimals = expression.args.get('decimals') or exp.Literal.number(0)
            return {'op': 'round', 'args': [self.formula(scope, expression.this, visited), self.formula(scope, decimals, visited)]}
        raise LocalPlanError('缺少该指标的本地计算公式或原始计算字段。')

    def summary_marker(self, field, expression):
        if not isinstance(expression, exp.Case):
            return None
        for branch in expression.args.get('ifs', []):
            condition, value = branch.this, branch.args.get('true')
            if not isinstance(condition, exp.EQ) or not isinstance(condition.this, exp.Column) or not isinstance(value, exp.Literal):
                continue
            source = self.source(self.root, condition.this)
            if not isinstance(source, Scope) or not source.union_scopes:
                continue
            index = source.expression.named_selects.index(condition.this.name)
            for union_branch in source.union_scopes:
                query = union_branch.expression
                discriminator = query.expressions[index].unalias()
                if discriminator == condition.expression and query.find(exp.AggFunc) and not query.args.get('group'):
                    self.summary_scopes.add(id(union_branch))
                    return {'field': field, 'value': value.this if value.is_string else float(value.this)}
        return None

    def build(self):
        dimensions, expressions, unavailable = [], {}, {}
        summary = None
        for name, projection in zip(self.names, self.root.expression.expressions):
            try:
                if self.output(self.root, name, self.dimension):
                    dimensions.append(name)
                    summary = summary or self.summary_marker(name, projection.unalias())
                    continue
                expressions[name] = self.output(self.root, name, self.formula)
            except LocalPlanError as exc:
                unavailable[name] = {'kind': 'unavailable', 'reason': str(exc)}
        unsafe_union_aggregates = any(
            isinstance(scope.expression, exp.Select)
            and scope.parent is not None and scope in scope.parent.union_scopes
            and id(scope) not in self.summary_scopes
            and any(isinstance(node, exp.AggFunc) for node in scope.expression.walk(
                prune=lambda node: node is not scope.expression and isinstance(node, exp.Query)))
            for scope in self.root.traverse()
        )
        if unsafe_union_aggregates:
            raise LocalPlanError('已有结果包含联合聚合行，缺少可靠的明细/汇总标记，无法安全取消分组。')
        atom_fields = {value['atom']: name for name, value in expressions.items() if 'atom' in value}

        def bind(expression):
            if 'atom' in expression:
                name = atom_fields.get(expression['atom'])
                if name is None:
                    raise LocalPlanError('缺少可汇总的原始分子、分母或权重字段。')
                return {'field': name}
            if 'op' in expression:
                return {'op': expression['op'], 'args': [bind(arg) for arg in expression['args']]}
            return {'value': expression['value']}

        metrics = dict(unavailable)
        for name, expression in expressions.items():
            try:
                if 'atom' in expression:
                    metrics[name] = {'kind': 'aggregate', 'aggregation': expression['aggregation']}
                elif expression.get('op') == 'round' and 'atom' in expression['args'][0] and expression['args'][0]['atom'] not in atom_fields:
                    # The operation sums the values already loaded in the chart.
                    # Rounded outputs are never bound as exact formula operands.
                    atom = expression['args'][0]
                    if 'atom' not in atom:
                        raise LocalPlanError('缺少可汇总的原始分子、分母或权重字段。')
                    metrics[name] = {'kind': 'aggregate', 'aggregation': atom['aggregation']}
                else:
                    metrics[name] = {'kind': 'formula', 'expression': bind(expression)}
            except LocalPlanError as exc:
                metrics[name] = {'kind': 'unavailable', 'reason': str(exc)}
        return {'dimensions': dimensions, 'metrics': metrics, 'summary': summary, 'reason': ''}


def build_local_grouping_plan(sql: str, dialect: str = '') -> dict:
    try:
        return LocalGroupingPlanner(sql, dialect).build()
    except LocalPlanError as exc:
        return {'dimensions': [], 'metrics': {}, 'summary': None, 'reason': str(exc)}
    except (sqlglot.errors.SqlglotError, ValueError, KeyError, IndexError, RecursionError):
        return {'dimensions': [], 'metrics': {}, 'summary': None, 'reason': '无法读取本地汇总配置：查询结构暂不支持，请补充明确的汇总配置。'}
