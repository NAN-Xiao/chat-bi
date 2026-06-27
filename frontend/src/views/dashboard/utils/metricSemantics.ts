import { axisLabel, type ChartAxis, type ChartData } from '@/views/chat/component/BaseChart.ts'

export type MetricType = 'additive' | 'average' | 'ratio' | 'snapshot' | 'derived'
export type PivotMetricAggregation = 'sum' | 'avg' | 'count' | 'min' | 'max'

export type MetricSemantics = {
  metricType: MetricType
  pivotAggregation: PivotMetricAggregation
  source: 'explicit' | 'inferred'
}

const RATIO_KEYWORDS = [
  'rate',
  'ratio',
  'percent',
  'percentage',
  'pct',
  'share',
  'margin',
  'roi',
  'roe',
  'roa',
  'conversion',
  'retention',
  'churn',
  'activation',
  'engagement',
  'open_rate',
  'click_rate',
  'response_rate',
  'utilization',
  'ctr',
  'cvr',
  'roas',
  '率',
  '占比',
  '比例',
  '百分',
  '转化',
  '轉化',
  '留存',
  '复购率',
  '復購率',
  '首付率',
  '%',
]

const AVERAGE_KEYWORDS = [
  'avg',
  'average',
  'mean',
  'arpu',
  'arppu',
  'ltv',
  'aov',
  'asp',
  'cpc',
  'cpm',
  'cpa',
  'average_order_value',
  'per ',
  'per_',
  'per-',
  'per_user',
  'per_payer',
  '客单价',
  '客單價',
  '人均',
  '单均',
  '單均',
  '平均',
  '每人',
  '每用户',
  '每用戶',
  '每付费',
  '每付費',
]

const ADDITIVE_KEYWORDS = [
  'revenue',
  'income',
  'sales',
  'amount',
  'gmv',
  'profit',
  'expense',
  'expenses',
  'cost',
  'spend',
  'fee',
  'fees',
  'tax',
  'taxes',
  'refund',
  'refunds',
  'cash_flow',
  'deposit',
  'withdrawal',
  'transactions',
  'transaction_count',
  'txn_count',
  'orders',
  'order_count',
  'payment_orders',
  'new_users',
  'signups',
  'installs',
  'downloads',
  'registrations',
  'messages',
  'message_count',
  'posts',
  'post_count',
  'comments',
  'comment_count',
  'likes',
  'like_count',
  'shares',
  'share_count',
  'reposts',
  'views',
  'impressions',
  'clicks',
  'sessions',
  'logins',
  'duration',
  'minutes',
  'hours',
  '收入',
  '流水',
  '金额',
  '金額',
  '成本',
  '费用',
  '費用',
  '利润',
  '利潤',
  '税',
  '退款',
  '现金流',
  '現金流',
  '存入',
  '取出',
  '交易',
  '消耗',
  '订单',
  '訂單',
  '次数',
  '次數',
  '新增',
  '注册',
  '註冊',
  '安装',
  '安裝',
  '下载',
  '下載',
  '付费次数',
  '付費次數',
  '购买次数',
  '購買次數',
  '数量',
  '數量',
  '总数',
  '總數',
]

const SNAPSHOT_KEYWORDS = [
  'dau',
  'wau',
  'mau',
  'uv',
  'pv',
  'active_users',
  'active user',
  'active_user_count',
  'user_count',
  'users',
  'members',
  'member_count',
  'customers',
  'customer_count',
  'accounts',
  'account_count',
  'subscribers',
  'subscriber_count',
  'followers',
  'follower_count',
  'friends',
  'friend_count',
  'fans',
  'headcount',
  'employees',
  'payers',
  'paying_users',
  'balance',
  'cash',
  'cash_balance',
  'assets',
  'liabilities',
  'equity',
  'receivable',
  'receivables',
  'payable',
  'payables',
  'aum',
  'nav',
  'loan_balance',
  'outstanding',
  'backlog',
  'stock',
  'inventory',
  'online',
  '活跃用户',
  '活躍用戶',
  '活跃人数',
  '活躍人數',
  '用户数',
  '用戶數',
  '人数',
  '人數',
  '付费人数',
  '付費人數',
  '留存用户',
  '留存用戶',
  '余额',
  '餘額',
  '资产',
  '資產',
  '负债',
  '負債',
  '现金',
  '現金',
  '应收',
  '應收',
  '应付',
  '應付',
  '库存',
  '庫存',
  '粉丝数',
  '粉絲數',
  '关注数',
  '關注數',
  '好友数',
  '好友數',
  '订阅数',
  '訂閱數',
  '员工数',
  '員工數',
  '在线',
  '在線',
]

function axisText(axis: ChartAxis) {
  return `${axisLabel(axis)} ${axis.value || ''}`.toLowerCase()
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function isAsciiKeyword(value: string) {
  return /^[a-z0-9_\-\s]+$/i.test(value)
}

function includesKeyword(text: string, keyword: string) {
  const value = keyword.toLowerCase()
  if (!isAsciiKeyword(value)) {
    return text.includes(value)
  }
  if (/[_\-\s]/.test(value)) {
    return text.includes(value)
  }
  return new RegExp(`(^|[^a-z0-9])${escapeRegExp(value)}([^a-z0-9]|$)`).test(text)
}

function includesAny(text: string, keywords: string[]) {
  return keywords.some((keyword) => includesKeyword(text, keyword))
}

function normalizeMetricType(value: unknown): MetricType | undefined {
  return ['additive', 'average', 'ratio', 'snapshot', 'derived'].includes(String(value))
    ? (String(value) as MetricType)
    : undefined
}

function normalizeAggregation(value: unknown): PivotMetricAggregation | undefined {
  return ['sum', 'avg', 'count', 'min', 'max'].includes(String(value))
    ? (String(value) as PivotMetricAggregation)
    : undefined
}

function explicitMetricType(axis: ChartAxis) {
  const raw = axis as any
  return normalizeMetricType(
    raw.metricType ||
      raw.metric_type ||
      raw.metricSemantics?.metricType ||
      raw.metricSemantics?.metric_type ||
      raw.metric_semantics?.metricType ||
      raw.metric_semantics?.metric_type ||
      raw.semantic?.metricType ||
      raw.semantic?.metric_type
  )
}

function explicitPivotAggregation(axis: ChartAxis) {
  const raw = axis as any
  return normalizeAggregation(
    raw.pivotAggregation ||
      raw.pivot_aggregation ||
      raw.metricSemantics?.pivotAggregation ||
      raw.metricSemantics?.pivot_aggregation ||
      raw.metric_semantics?.pivotAggregation ||
      raw.metric_semantics?.pivot_aggregation ||
      raw.semantic?.pivotAggregation ||
      raw.semantic?.pivot_aggregation
  )
}

function aggregationForMetricType(metricType: MetricType): PivotMetricAggregation {
  if (metricType === 'additive') {
    return 'sum'
  }
  return 'avg'
}

export function resolveMetricSemantics(axis: ChartAxis, data: ChartData[] = []): MetricSemantics {
  const explicitAggregation = explicitPivotAggregation(axis)
  const explicitType = explicitMetricType(axis)
  if (explicitType) {
    return {
      metricType: explicitType,
      pivotAggregation: explicitAggregation || aggregationForMetricType(explicitType),
      source: 'explicit',
    }
  }

  const text = axisText(axis)
  let metricType: MetricType = 'additive'
  if (includesAny(text, RATIO_KEYWORDS)) {
    metricType = 'ratio'
  } else if (includesAny(text, AVERAGE_KEYWORDS)) {
    metricType = 'average'
  } else if (includesAny(text, ADDITIVE_KEYWORDS)) {
    metricType = 'additive'
  } else if (includesAny(text, SNAPSHOT_KEYWORDS)) {
    metricType = 'snapshot'
  } else if (data.some((row) => typeof row?.[axis.value] === 'string' && String(row?.[axis.value]).trim().endsWith('%'))) {
    metricType = 'ratio'
  }

  return {
    metricType,
    pivotAggregation: explicitAggregation || aggregationForMetricType(metricType),
    source: explicitAggregation ? 'explicit' : 'inferred',
  }
}

export function withResolvedMetricSemantics(axis: ChartAxis, data: ChartData[] = []): ChartAxis {
  const semantics = resolveMetricSemantics(axis, data)
  return {
    ...axis,
    metricType: (axis as any).metricType || semantics.metricType,
    pivotAggregation: (axis as any).pivotAggregation || semantics.pivotAggregation,
  }
}

export function resolvePivotMetricAggregations(axes: ChartAxis[], data: ChartData[] = []) {
  return axes.reduce<Record<string, PivotMetricAggregation>>((result, axis) => {
    if (axis.value) {
      result[axis.value] = resolveMetricSemantics(axis, data).pivotAggregation
    }
    return result
  }, {})
}

export function defaultPivotAggregationForAxes(axes: ChartAxis[], data: ChartData[] = []): PivotMetricAggregation {
  const aggregations = axes.map((axis) => resolveMetricSemantics(axis, data).pivotAggregation)
  return aggregations[0] || 'sum'
}
