import { applyTableFilters } from './tableFilter.ts'

export type LocalFormula = { field: string } | { value: number | null } | { op: string; args: LocalFormula[] }
export type LocalMetric =
  | { kind: 'aggregate'; aggregation: 'sum' | 'min' | 'max' }
  | { kind: 'formula'; expression: LocalFormula }
  | { kind: 'unavailable'; reason: string }
export type LocalGroupingPlan = {
  dimensions: string[]
  metrics: Record<string, LocalMetric>
  summary?: { field: string; value: unknown } | null
  reason?: string
}
export type LocalGroupingResult = { data: Record<string, any>[]; issues: Record<string, string> }
export type LocalTableGroupingState = {
  plan?: LocalGroupingPlan
  excludedFields: Set<string>
  filters: Map<string, Set<string>>
  loading?: boolean
  requiresPlan?: boolean
  error?: string
  onChange?: (result: LocalGroupingResult) => void
}

function numeric(value: unknown): number | null {
  if (value === null || value === undefined || (typeof value === 'string' && !value.trim())) return null
  if (typeof value !== 'number' && typeof value !== 'string') throw new Error('字段包含非数值，无法准确汇总')
  const result = Number(value)
  if (!Number.isFinite(result)) throw new Error('字段包含非数值，无法准确汇总')
  if (Number.isInteger(result) && !Number.isSafeInteger(result)) throw new Error('数值超出安全精度，无法准确汇总')
  return result
}

function decimalParts(value: number) {
    const [significand, exponent = '0'] = String(value).split('e')
    const [whole, fraction = ''] = significand.split('.')
    return { coefficient: BigInt(whole + fraction), exponent: Number(exponent) - fraction.length }
}

function decimalSum(values: number[]) {
  const parts = values.map(decimalParts)
  const exponent = parts.reduce((minimum, part) => Math.min(minimum, part.exponent), Infinity)
  const coefficient = parts.reduce((sum, part) => sum + part.coefficient * 10n ** BigInt(part.exponent - exponent), 0n)
  return Number(`${coefficient}e${exponent}`)
}

function decimalRound(value: number, precision: number) {
  const part = decimalParts(value)
  const targetExponent = -precision
  if (part.exponent >= targetExponent) return value
  const divisor = 10n ** BigInt(targetExponent - part.exponent)
  const absolute = part.coefficient < 0 ? -part.coefficient : part.coefficient
  const quotient = absolute / divisor + (absolute % divisor * 2n >= divisor ? 1n : 0n)
  return Number(`${part.coefficient < 0 ? -quotient : quotient}e${targetExponent}`)
}

function evaluate(expression: LocalFormula, metrics: Record<string, number | null>): number | null {
  if ('field' in expression) return metrics[expression.field] ?? null
  if ('value' in expression) return expression.value
  const args = expression.args.map((arg) => evaluate(arg, metrics))
  if (expression.op === 'coalesce') return args.find((arg) => arg !== null) ?? null
  if (expression.op === 'nullif') return args[0] === args[1] ? null : args[0]
  if (args.some((arg) => arg === null)) return null
  const [a, b] = args as number[]
  let result: number
  switch (expression.op) {
    case 'add': result = a + b; break
    case 'subtract': result = a - b; break
    case 'multiply': result = a * b; break
    case 'divide': result = b === 0 ? NaN : a / b; break
    case 'modulo': result = b === 0 ? NaN : a % b; break
    case 'negate': result = -a; break
    case 'round': {
      if (!Number.isInteger(b) || Math.abs(b) > 15) throw new Error('公式的舍入精度无效')
      result = decimalRound(a, b)
      break
    }
    default: throw new Error('缺少支持的本地计算公式')
  }
  if (Number.isInteger(result) && !Number.isSafeInteger(result)) throw new Error('公式结果超出安全精度，无法准确计算')
  return Number.isFinite(result) ? result : null
}

function keyValue(value: unknown): unknown {
  if (value === undefined) return ['undefined']
  if (value instanceof Date) return ['date', value.toISOString()]
  return [typeof value, value]
}

export function regroupLocalChartData(
  rows: Record<string, any>[], plan: LocalGroupingPlan, excluded: Set<string>
): LocalGroupingResult {
  if (!excluded.size) return { data: [...rows], issues: {} }
  for (const field of excluded) {
    if (!plan.dimensions.includes(field)) throw new Error(`「${field}」缺少分组配置，无法取消分组`)
  }
  const remaining = plan.dimensions.filter((field) => !excluded.has(field))
  for (const field of remaining) {
    if (rows.some((row) => !Object.prototype.hasOwnProperty.call(row, field))) throw new Error(`已有数据缺少分组字段「${field}」，无法保留此分组`)
  }
  const summary = plan.summary
  const isSummary = (row: Record<string, any>) => Boolean(summary && row[summary.field] === summary.value)
  const details = rows.filter((row) => !isSummary(row))
  const groups = new Map<string, Record<string, any>[]>()
  for (const row of details) {
    const key = JSON.stringify(remaining.map((field) => keyValue(row[field])))
    const group = groups.get(key) || []
    group.push(row)
    groups.set(key, group)
  }
  const issues: Record<string, string> = {}
  if (!details.length && rows.length) {
    const data = rows.map((row) => {
      const output = { ...row }
      for (const field of excluded) output[field] = null
      for (const field of Object.keys(plan.metrics)) {
        output[field] = null
        issues[field] = '仅有汇总行，缺少明细，无法重新计算'
      }
      return output
    })
    return { data, issues }
  }
  function aggregate(group: Record<string, any>[], isTotal = false) {
    const output: Record<string, any> = {}
    for (const field of plan.dimensions) output[field] = excluded.has(field) || isTotal ? null : group[0]?.[field]
    if (isTotal && summary) output[summary.field] = summary.value
    const metrics: Record<string, number | null> = {}
    for (const [field, config] of Object.entries(plan.metrics)) {
      if (config.kind !== 'aggregate') continue
      try {
        if (group.some((row) => !Object.prototype.hasOwnProperty.call(row, field))) throw new Error('已有数据缺少计算字段')
        const values = group.map((row) => numeric(row[field])).filter((value): value is number => value !== null)
        metrics[field] = values.length === 0 ? null
          : config.aggregation === 'sum' ? decimalSum(values)
          : config.aggregation === 'min' ? values.reduce((a, b) => Math.min(a, b))
          : values.reduce((a, b) => Math.max(a, b))
        if (metrics[field] !== null && (!Number.isFinite(metrics[field]) || (Number.isInteger(metrics[field]) && !Number.isSafeInteger(metrics[field])))) throw new Error('汇总值超出安全精度')
      } catch (error) {
        metrics[field] = null
        issues[field] = (error as Error).message
      }
    }
    for (const [field, config] of Object.entries(plan.metrics)) {
      if (config.kind === 'aggregate') continue
      try {
        if (config.kind === 'unavailable') throw new Error(config.reason)
        metrics[field] = evaluate(config.expression, metrics)
      } catch (error) {
        metrics[field] = null
        issues[field] = (error as Error).message
      }
    }
    Object.assign(output, metrics)
    return output
  }
  const data = Array.from(groups.values()).map((group) => aggregate(group))
  if (summary && remaining.includes(summary.field) && rows.some(isSummary) && details.length) {
    data.unshift(aggregate(details, true))
  }
  return { data, issues }
}

export function resolveLocalTableData(rows: Record<string, any>[], state: LocalTableGroupingState) {
  if (!state.plan || state.excludedFields.size === 0) {
    const data = applyTableFilters(rows, state.filters)
    return { data, groupedData: data, issues: {} }
  }
  const dimensionFilters = new Map(Array.from(state.filters).filter(([field]) => state.plan!.dimensions.includes(field)))
  const metricFilters = new Map(Array.from(state.filters).filter(([field]) => !state.plan!.dimensions.includes(field)))
  const grouped = regroupLocalChartData(applyTableFilters(rows, dimensionFilters), state.plan, state.excludedFields)
  return { ...grouped, groupedData: grouped.data, data: applyTableFilters(grouped.data, metricFilters) }
}
