export type ReportTypeKey =
  | 'event'
  | 'retention'
  | 'funnel'
  | 'distribution'
  | 'interval'
  | 'path'
  | 'property'
  | 'attribution'
  | 'heatmap'
  | 'ranking'
  | 'revenue'

export type ReportField = {
  key: string
  label: string
  placeholder: string
}

export type ReportTypeDefinition = {
  key: ReportTypeKey
  label: string
  description: string
  fields: ReportField[]
}

export const REPORT_TYPES: ReportTypeDefinition[] = [
  {
    key: 'event',
    label: '事件分析',
    description: '按事件、用户和属性查看发生次数及趋势',
    fields: [{ key: 'event', label: '分析事件', placeholder: '请选择事件' }],
  },
  {
    key: 'retention',
    label: '留存分析',
    description: '比较初始事件用户在后续时间窗口的回访情况',
    fields: [
      { key: 'initialEvent', label: '初始事件', placeholder: '请选择初始事件' },
      { key: 'returnEvent', label: '回访事件', placeholder: '请选择回访事件' },
    ],
  },
  {
    key: 'funnel',
    label: '漏斗分析',
    description: '按固定步骤计算用户转化和流失',
    fields: [
      { key: 'step1', label: '步骤 1', placeholder: '请选择第一个步骤' },
      { key: 'step2', label: '步骤 2', placeholder: '请选择第二个步骤' },
    ],
  },
  {
    key: 'distribution',
    label: '分布分析',
    description: '查看用户或事件指标的区间分布',
    fields: [{ key: 'metric', label: '分布指标', placeholder: '请选择指标' }],
  },
  {
    key: 'interval',
    label: '间隔分析',
    description: '分析相邻事件或行为之间的时间间隔',
    fields: [
      { key: 'startEvent', label: '开始事件', placeholder: '请选择开始事件' },
      { key: 'endEvent', label: '结束事件', placeholder: '请选择结束事件' },
    ],
  },
  {
    key: 'path',
    label: '路径分析',
    description: '追踪事件前后用户行为路径和流向',
    fields: [{ key: 'pathEvent', label: '起始事件', placeholder: '请选择起始事件' }],
  },
  {
    key: 'property',
    label: '属性分析',
    description: '按用户属性拆分事件表现和用户规模',
    fields: [{ key: 'property', label: '用户属性', placeholder: '请选择用户属性' }],
  },
  {
    key: 'attribution',
    label: '归因分析',
    description: '对目标事件的来源、渠道和触点进行归因',
    fields: [{ key: 'targetEvent', label: '目标事件', placeholder: '请选择目标事件' }],
  },
  {
    key: 'heatmap',
    label: '热力地图',
    description: '按日期、时段或维度展示行为密度',
    fields: [{ key: 'heatmapMetric', label: '热力指标', placeholder: '请选择指标' }],
  },
  {
    key: 'ranking',
    label: '排行榜',
    description: '按指标对用户、商品或其他维度排序',
    fields: [{ key: 'rankDimension', label: '排行维度', placeholder: '请选择排行维度' }],
  },
  {
    key: 'revenue',
    label: '收入分析',
    description: '按收入事件、用户和商品维度观察营收表现',
    fields: [{ key: 'revenueEvent', label: '收入事件', placeholder: '请选择收入事件' }],
  },
]

export const getReportType = (key: ReportTypeKey) =>
  REPORT_TYPES.find((item) => item.key === key) || REPORT_TYPES[0]

export const createDefaultReportConfig = (type: ReportTypeKey) => {
  const definition = getReportType(type)
  const fields = Object.fromEntries(definition.fields.map((field) => [field.key, '']))
  return {
    type,
    fields,
    analysisUnit: '用户',
    useRelatedProperty: false,
    useIntervalDisplay: false,
    analysisWindowDays: 1,
    globalFilters: [],
    groupItems: [],
  }
}
