export type FormulaOperator = '+' | '-' | '*' | '/'
export type FormulaParen = '(' | ')'
export type FormulaAtomicMetricFilter = {
  id: string
  type?: 'rule' | 'group'
  field: string
  operator: string
  value: string
  logic?: 'and' | 'or'
  children?: FormulaAtomicMetricFilter[]
}

export type FormulaAtomicMetric = {
  id: string
  field: string
  metric: string
  aggregation: string
  alias: string
  label?: string
  filterLogic: 'and' | 'or'
  filters: FormulaAtomicMetricFilter[]
}

export type FormulaToken =
  | { type: 'metric'; metricId: string }
  | { type: 'atomicMetric'; metric: FormulaAtomicMetric }
  | { type: 'operator'; value: FormulaOperator }
  | { type: 'paren'; value: FormulaParen }
  | { type: 'number'; value: string }

export type FormulaMetricOption = {
  label: string
  value: string
}

export type FormulaAtomicMetricDisplay = {
  label: string
  alias: string
}

export type FormulaValidationResult = {
  valid: boolean
  message: string
}

const operatorValues = new Set(['+', '-', '*', '/'])

function normalizeFilterLogic(value: unknown): 'and' | 'or' {
  return value === 'or' ? 'or' : 'and'
}

function normalizeAtomicMetricFilters(value: unknown): FormulaAtomicMetricFilter[] {
  if (!Array.isArray(value)) return []
  return value
    .map((item): FormulaAtomicMetricFilter | null => {
      if (!item || typeof item !== 'object') return null
      const filter = item as Record<string, unknown>
      const id = String(filter.id || '').trim()
      const type = filter.type === 'group' || Array.isArray(filter.children) ? 'group' : 'rule'
      if (type === 'group') {
        const children = normalizeAtomicMetricFilters(filter.children)
        return id && children.length
          ? {
              id,
              type: 'group',
              field: '',
              operator: '',
              value: '',
              logic: normalizeFilterLogic(filter.logic),
              children,
            }
          : null
      }
      const field = String(filter.field || '').trim()
      const operator = String(filter.operator || '').trim()
      if (!id || !field || !operator) return null
      return {
        id,
        type: 'rule',
        field,
        operator,
        value: String(filter.value ?? ''),
        logic: normalizeFilterLogic(filter.logic),
      }
    })
    .filter(Boolean) as FormulaAtomicMetricFilter[]
}

function tokenKind(token: FormulaToken | undefined): 'operand' | 'operator' | 'leftParen' | 'rightParen' | 'unknown' {
  if (!token) return 'unknown'
  if (token.type === 'metric' || token.type === 'atomicMetric' || token.type === 'number') return 'operand'
  if (token.type === 'operator') return 'operator'
  if (token.type === 'paren' && token.value === '(') return 'leftParen'
  if (token.type === 'paren' && token.value === ')') return 'rightParen'
  return 'unknown'
}

function isValidNumberToken(value: string) {
  return /^(?:\d+(?:\.\d*)?|\.\d+)$/.test(String(value || '').trim())
}

export function normalizeFormulaTokens(value: unknown): FormulaToken[] {
  if (!Array.isArray(value)) return []
  return value
    .map((item): FormulaToken | null => {
      if (!item || typeof item !== 'object') return null
      const token = item as Record<string, unknown>
      if (token.type === 'metric') {
        const metricId = String(token.metricId || '').trim()
        return metricId ? { type: 'metric', metricId } : null
      }
      if (token.type === 'atomicMetric' && token.metric && typeof token.metric === 'object') {
        const metric = token.metric as Record<string, unknown>
        const id = String(metric.id || '').trim()
        return id
          ? {
              type: 'atomicMetric',
              metric: {
                id,
                field: String(metric.field || '').trim(),
                metric: String(metric.metric || '').trim(),
                aggregation: String(metric.aggregation || 'count').trim(),
                alias: String(metric.alias || '').trim(),
                label: String(metric.label || '').trim(),
                filterLogic: metric.filterLogic === 'or' ? 'or' : 'and',
                filters: normalizeAtomicMetricFilters(metric.filters),
              },
            }
          : null
      }
      if (token.type === 'operator' && operatorValues.has(String(token.value))) {
        return { type: 'operator', value: token.value as FormulaOperator }
      }
      if (token.type === 'paren' && (token.value === '(' || token.value === ')')) {
        return { type: 'paren', value: token.value }
      }
      if (token.type === 'number') {
        const numberValue = String(token.value || '').trim()
        return numberValue ? { type: 'number', value: numberValue } : null
      }
      return null
    })
    .filter(Boolean) as FormulaToken[]
}

export function normalizeFormulaAtomicMetricDisplay(
  metric: FormulaAtomicMetric,
  display: FormulaAtomicMetricDisplay
): FormulaAtomicMetric {
  const label = String(display.label || '').trim()
  const alias = String(display.alias || '').trim()
  return {
    ...metric,
    label,
    alias,
  }
}

export function validateFormulaTokens(
  tokens: FormulaToken[],
  metricOptions: FormulaMetricOption[]
): FormulaValidationResult {
  const metricIds = new Set(metricOptions.map((item) => item.value))
  if (!tokens.length) {
    return { valid: false, message: '公式不能为空' }
  }

  let balance = 0
  let previousKind: ReturnType<typeof tokenKind> = 'unknown'
  let previousToken: FormulaToken | undefined

  for (const token of tokens) {
    const currentKind = tokenKind(token)
    if (token.type === 'metric' && !metricIds.has(token.metricId)) {
      return { valid: false, message: '公式引用的分析指标不存在' }
    }
    if (token.type === 'atomicMetric') {
      if (!token.metric?.field) {
        return { valid: false, message: '公式内事件指标缺少事件字段' }
      }
      if (token.metric.aggregation !== 'count' && !token.metric.metric) {
        return { valid: false, message: '公式内事件指标缺少计算字段' }
      }
    }
    if (token.type === 'number' && !isValidNumberToken(token.value)) {
      return { valid: false, message: '数字格式不正确' }
    }
    if (currentKind === 'leftParen') {
      if (previousKind === 'operand' || previousKind === 'rightParen') {
        return { valid: false, message: '括号前缺少运算符' }
      }
      balance += 1
    }
    if (currentKind === 'rightParen') {
      if (balance <= 0) {
        return { valid: false, message: '括号不配对' }
      }
      if (previousKind === 'operator' || previousKind === 'leftParen' || previousKind === 'unknown') {
        return { valid: false, message: '右括号前缺少指标或数字' }
      }
      balance -= 1
    }
    if (currentKind === 'operator') {
      if (previousKind === 'unknown' || previousKind === 'operator' || previousKind === 'leftParen') {
        return { valid: false, message: '运算符前缺少指标或数字' }
      }
    }
    if (currentKind === 'operand') {
      if (previousKind === 'operand' || previousKind === 'rightParen') {
        return { valid: false, message: '两个指标或数字之间缺少运算符' }
      }
    }
    previousKind = currentKind
    previousToken = token
  }

  if (balance !== 0) {
    return { valid: false, message: '括号不配对' }
  }
  if (previousKind === 'operator') {
    return {
      valid: false,
      message: previousToken?.type === 'operator' && previousToken.value === '/' ? '除号后缺少指标或数字' : '运算符后缺少指标或数字',
    }
  }
  if (previousKind === 'leftParen') {
    return { valid: false, message: '左括号后缺少指标或数字' }
  }

  return { valid: true, message: '' }
}

export function serializeFormulaTokensForContext(tokens: FormulaToken[], metricAliasById: Map<string, string>) {
  return tokens.map((token) => {
    if (token.type !== 'metric') return { ...token }
    return {
      type: 'metric' as const,
      metricId: token.metricId,
      metricAlias: metricAliasById.get(token.metricId) || '',
    }
  })
}

export function formulaTokensToText(tokens: FormulaToken[], metricOptions: FormulaMetricOption[]) {
  const metricLabelById = new Map(metricOptions.map((item) => [item.value, item.label]))
  return tokens
    .map((token) => {
      if (token.type === 'metric') return metricLabelById.get(token.metricId) || '未知指标'
      if (token.type === 'atomicMetric') return token.metric.label || token.metric.alias || '事件指标'
      if (token.type === 'operator' || token.type === 'paren' || token.type === 'number') return token.value
      return ''
    })
    .filter(Boolean)
    .join(' ')
}

export function insertFormulaTokenAt(tokens: FormulaToken[], index: number, token: FormulaToken) {
  const nextTokens = [...tokens]
  const safeIndex = Math.max(0, Math.min(index, nextTokens.length))
  nextTokens.splice(safeIndex, 0, token)
  return nextTokens
}
