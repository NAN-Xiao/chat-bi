import type {
  ChartData,
  ChartForecastConfig,
  ChartForecastMethod,
} from '@/views/chat/component/BaseChart.ts'
import { parseTrendDateValue, type TrendTimeGranularity } from '@/views/chat/component/chartInsight.ts'
import { toNullableNumber } from '@/views/chat/component/charts/utils.ts'

interface TimelinePoint {
  key: string
  value: any
  sortValue: number
  kind: 'date' | 'number'
  granularity?: TrendTimeGranularity
}

interface SeriesPoint {
  timelineIndex: number
  xValue: any
  value: number
  sourceRow: ChartData
}

interface SeriesBucket {
  seriesValue: any
  pointsByX: Map<string, { sum: number; count: number; sourceRow: ChartData }>
}

interface ForecastModel {
  method: ForecastRuntimeMethod
  predict: (index: number) => number
}

interface ForecastTarget {
  xValue: any
  offset: number
}

const DEFAULT_FORECAST_PERIODS = 7
const MAX_FORECAST_PERIODS = 60
const MAX_HISTORY_WINDOW = 240
const EPSILON = 1e-9
type ForecastRuntimeMethod = Exclude<ChartForecastMethod, 'auto'> | 'damped_trend'
const METHOD_COMPLEXITY_PENALTY: Record<ForecastRuntimeMethod, number> = {
  damped_trend: 0,
  linear: 0.01,
  exponential: 0.015,
  logarithmic: 0.018,
  reciprocal: 0.018,
  power: 0.025,
  holt_winters: 0.03,
  polynomial: 0.06,
  logistic: 0.08,
  gompertz: 0.08,
}
const AUTO_FORECAST_METHODS: ForecastRuntimeMethod[] = [
  'damped_trend',
  'linear',
  'holt_winters',
  'logarithmic',
  'reciprocal',
]

export function normalizeForecastConfig(config?: ChartForecastConfig | null): Required<ChartForecastConfig> {
  const periods = Number(config?.periods)
  const historyWindow = Number(config?.historyWindow)
  return {
    enabled: config?.enabled === true,
    method: config?.method || 'auto',
    periods: Number.isFinite(periods)
      ? Math.max(1, Math.min(MAX_FORECAST_PERIODS, Math.round(periods)))
      : DEFAULT_FORECAST_PERIODS,
    historyWindow: Number.isFinite(historyWindow)
      ? Math.max(0, Math.min(MAX_HISTORY_WINDOW, Math.round(historyWindow)))
      : 0,
  }
}

export function buildForecastRows(options: {
  data: ChartData[]
  xField: string
  yField: string
  seriesField?: string
  forecast?: ChartForecastConfig | null
  isPercent?: boolean
}): ChartData[] {
  const config = normalizeForecastConfig(options.forecast)
  if (!config.enabled || !options.xField || !options.yField || options.data.length < 2) {
    return []
  }

  const timeline = buildTimeline(options.data, options.xField)
  if (!timeline || timeline.items.length < 2) {
    return []
  }

  const buckets = collectSeriesBuckets(options.data, options.xField, options.yField, options.seriesField, timeline)
  const rows: ChartData[] = []
  const finalActualIndex = resolveFinalActualTimelineIndex(buckets, timeline)
  if (finalActualIndex === null) {
    return []
  }
  const finalForecastIndex = finalActualIndex + config.periods

  buckets.forEach((bucket) => {
    const points = Array.from(bucket.pointsByX.entries())
      .map(([xKey, point]) => {
        const timelineIndex = timeline.indexByKey.get(xKey)
        if (timelineIndex === undefined) {
          return null
        }
        return {
          timelineIndex,
          xValue: timeline.items[timelineIndex].value,
          value: point.sum / point.count,
          sourceRow: point.sourceRow,
        } as SeriesPoint
      })
      .filter((point): point is SeriesPoint => point !== null)
      .sort((a, b) => a.timelineIndex - b.timelineIndex)

    if (points.length < 2) {
      return
    }

    const trainingPoints = config.historyWindow > 0 ? points.slice(-config.historyWindow) : points
    if (trainingPoints.length < 2) {
      return
    }

    const seriesIsPercent = options.isPercent || Boolean(trainingPoints[trainingPoints.length - 1].sourceRow?.shuzhi_auto_is_percent)
    const model = selectForecastModel(
      trainingPoints.map((point) => point.value),
      config.method,
      timeline.granularity
    )
    if (!model) {
      return
    }

    const lastPoint = trainingPoints[trainingPoints.length - 1]
    const targets = buildForecastTargets(timeline, lastPoint.timelineIndex, finalForecastIndex)
    if (targets.length === 0) {
      return
    }

    rows.push(buildForecastRow(lastPoint.xValue, lastPoint.value, bucket, options, lastPoint.sourceRow))
    targets.forEach((target) => {
      const rawValue = model.predict(trainingPoints.length + target.offset)
      const value = clampForecastValue(rawValue, trainingPoints, seriesIsPercent)
      if (value === null) {
        return
      }
      rows.push(buildForecastRow(target.xValue, value, bucket, options, lastPoint.sourceRow))
    })
  })

  return rows
}

function resolveFinalActualTimelineIndex(
  buckets: Map<string, SeriesBucket>,
  timeline: { indexByKey: Map<string, number> }
) {
  let finalIndex: number | null = null
  buckets.forEach((bucket) => {
    bucket.pointsByX.forEach((_point, xKey) => {
      const index = timeline.indexByKey.get(xKey)
      if (index === undefined) {
        return
      }
      finalIndex = finalIndex === null ? index : Math.max(finalIndex, index)
    })
  })
  return finalIndex
}

function buildForecastRow(
  xValue: any,
  value: number,
  bucket: SeriesBucket,
  options: { xField: string; yField: string; seriesField?: string },
  sourceRow: ChartData
): ChartData {
  const row: ChartData = {
    [options.xField]: xValue,
    [options.yField]: value,
    shuzhi_auto_forecast: true,
  }
  if (options.seriesField) {
    row[options.seriesField] = bucket.seriesValue
  }
  if (sourceRow?.shuzhi_auto_is_percent !== undefined) {
    row.shuzhi_auto_is_percent = sourceRow.shuzhi_auto_is_percent
  }
  return row
}

function collectSeriesBuckets(
  data: ChartData[],
  xField: string,
  yField: string,
  seriesField: string | undefined,
  timeline: { keyByRawValue: Map<any, string> }
) {
  const buckets = new Map<string, SeriesBucket>()
  data.forEach((row) => {
    const xKey = timeline.keyByRawValue.get(row?.[xField])
    const value = toNullableNumber(row?.[yField])
    if (!xKey || value === null) {
      return
    }
    const rawSeriesValue = seriesField ? row?.[seriesField] : '__default__'
    const seriesKey = normalizeSeriesKey(rawSeriesValue)
    let bucket = buckets.get(seriesKey)
    if (!bucket) {
      bucket = {
        seriesValue: rawSeriesValue,
        pointsByX: new Map(),
      }
      buckets.set(seriesKey, bucket)
    }
    const point = bucket.pointsByX.get(xKey)
    if (point) {
      point.sum += value
      point.count += 1
      point.sourceRow = row
    } else {
      bucket.pointsByX.set(xKey, { sum: value, count: 1, sourceRow: row })
    }
  })
  return buckets
}

function normalizeSeriesKey(value: any) {
  if (value === undefined || value === null || value === '') {
    return '__blank__'
  }
  return String(value)
}

function buildTimeline(data: ChartData[], xField: string) {
  const rawValues = data
    .map((row) => row?.[xField])
    .filter((value) => value !== undefined && value !== null && `${value}`.trim() !== '')
  const dateItems = rawValues.map(parseDateTimelinePoint).filter((item): item is TimelinePoint => item !== null)
  const numberItems = rawValues.map(parseNumberTimelinePoint).filter((item): item is TimelinePoint => item !== null)
  const useDate = dateItems.length >= 2 && dateItems.length / Math.max(rawValues.length, 1) >= 0.6
  const useNumber = !useDate && numberItems.length >= 2 && numberItems.length / Math.max(rawValues.length, 1) >= 0.6
  const sourceItems = useDate ? dateItems : useNumber ? numberItems : []
  if (sourceItems.length < 2) {
    return null
  }

  const itemByKey = new Map<string, TimelinePoint>()
  const keyByRawValue = new Map<any, string>()
  sourceItems.forEach((item) => {
    keyByRawValue.set(item.value, item.key)
    if (!itemByKey.has(item.key)) {
      itemByKey.set(item.key, item)
    }
  })

  const items = Array.from(itemByKey.values()).sort((a, b) => a.sortValue - b.sortValue)
  const indexByKey = new Map(items.map((item, index) => [item.key, index]))
  return {
    items,
    indexByKey,
    keyByRawValue,
    granularity: resolveTimelineGranularity(items),
  }
}

function parseDateTimelinePoint(value: any): TimelinePoint | null {
  const parsed = parseTrendDateValue(value)
  if (!parsed) {
    return null
  }
  return {
    key: parsed.label,
    value,
    sortValue: parsed.time,
    kind: 'date',
    granularity: parsed.granularity,
  }
}

function parseNumberTimelinePoint(value: any): TimelinePoint | null {
  if (value instanceof Date) {
    return null
  }
  if (typeof value !== 'number' && typeof value !== 'string') {
    return null
  }
  const text = String(value).trim()
  if (!text || parseTrendDateValue(text)) {
    return null
  }
  const numericValue = Number(text.replace(/,/g, ''))
  if (!Number.isFinite(numericValue)) {
    return null
  }
  return {
    key: String(numericValue),
    value,
    sortValue: numericValue,
    kind: 'number',
  }
}

function resolveTimelineGranularity(items: TimelinePoint[]): TrendTimeGranularity | undefined {
  const counts = new Map<TrendTimeGranularity, number>()
  items.forEach((item) => {
    if (item.granularity) {
      counts.set(item.granularity, (counts.get(item.granularity) || 0) + 1)
    }
  })
  return Array.from(counts.entries()).sort((a, b) => b[1] - a[1])[0]?.[0]
}

function buildForecastTargets(
  timeline: { items: TimelinePoint[] },
  lastActualIndex: number,
  finalForecastIndex: number
): ForecastTarget[] {
  const targets: ForecastTarget[] = []
  const targetCount = finalForecastIndex - lastActualIndex
  if (targetCount <= 0) {
    return targets
  }
  const existingFutureItems = timeline.items.slice(lastActualIndex + 1, finalForecastIndex + 1)
  existingFutureItems.forEach((item, index) => {
    targets.push({
      xValue: item.value,
      offset: index + 1,
    })
  })

  let current = existingFutureItems[existingFutureItems.length - 1] || timeline.items[lastActualIndex]
  while (targets.length < targetCount) {
    const next = nextTimelinePoint(current, timeline.items)
    if (!next) {
      break
    }
    targets.push({
      xValue: next.value,
      offset: targets.length + 1,
    })
    current = next
  }
  return targets
}

function nextTimelinePoint(current: TimelinePoint, allItems: TimelinePoint[]): TimelinePoint | null {
  if (current.kind === 'number') {
    const step = medianPositiveDiff(allItems.map((item) => item.sortValue)) || 1
    const numericValue = current.sortValue + step
    return {
      key: String(numericValue),
      value: preserveNumericFormat(current.value, numericValue),
      sortValue: numericValue,
      kind: 'number',
    }
  }

  const granularity = current.granularity || 'day'
  const date = new Date(current.sortValue)
  if (granularity === 'month') {
    date.setUTCMonth(date.getUTCMonth() + 1)
  } else if (granularity === 'year') {
    date.setUTCFullYear(date.getUTCFullYear() + 1)
  } else if (granularity === 'week') {
    date.setUTCDate(date.getUTCDate() + 7)
  } else {
    date.setUTCDate(date.getUTCDate() + 1)
  }
  const value = formatDateLike(date, granularity, current.value)
  const parsed = parseTrendDateValue(value)
  return {
    key: parsed?.label || String(value),
    value,
    sortValue: date.getTime(),
    kind: 'date',
    granularity,
  }
}

function preserveNumericFormat(sample: any, value: number) {
  if (typeof sample === 'number') {
    return value
  }
  if (Number.isInteger(value) && /^-?\d+$/.test(String(sample).trim())) {
    return String(value)
  }
  return String(Number(value.toFixed(6)))
}

function formatDateLike(date: Date, granularity: TrendTimeGranularity, sample: any) {
  const sampleText = String(sample).trim()
  const year = date.getUTCFullYear()
  const month = String(date.getUTCMonth() + 1).padStart(2, '0')
  const day = String(date.getUTCDate()).padStart(2, '0')
  const compact = sampleText.replace(/\D/g, '')
  const asNumber = typeof sample === 'number'

  if (granularity === 'year') {
    return asNumber ? year : String(year)
  }
  if (granularity === 'month') {
    const text = compact.length === 6 ? `${year}${month}` : `${year}-${month}`
    return asNumber && compact.length === 6 ? Number(text) : text
  }
  const text = compact.length === 8 ? `${year}${month}${day}` : `${year}-${month}-${day}`
  return asNumber && compact.length === 8 ? Number(text) : text
}

function medianPositiveDiff(values: number[]) {
  const sortedValues = values.slice().sort((a, b) => a - b)
  const diffs = sortedValues
    .slice(1)
    .map((value, index) => value - sortedValues[index])
    .filter((value) => value > EPSILON)
    .sort((a, b) => a - b)
  if (diffs.length === 0) {
    return null
  }
  return diffs[Math.floor(diffs.length / 2)]
}

function clampForecastValue(value: number, points: SeriesPoint[], isPercent: boolean): number | null {
  if (!Number.isFinite(value)) {
    return null
  }
  let nextValue = value
  const values = points.map((point) => point.value)
  if (values.every((item) => item >= 0)) {
    nextValue = Math.max(0, nextValue)
  }
  if (isPercent) {
    nextValue = Math.max(0, Math.min(100, nextValue))
  }
  return Number(nextValue.toFixed(6))
}

function selectForecastModel(
  values: number[],
  requestedMethod: ChartForecastMethod,
  granularity?: TrendTimeGranularity
): ForecastModel | null {
  const candidates =
    requestedMethod === 'auto'
      ? AUTO_FORECAST_METHODS
      : ([requestedMethod] as ForecastRuntimeMethod[])
  const scored = candidates
    .map((method) => scoreModel(method, values, granularity))
    .filter((item): item is { model: ForecastModel; score: number } => item !== null)
    .sort((a, b) => a.score - b.score)

  if (scored.length > 0) {
    return scored[0].model
  }
  return requestedMethod === 'auto' ? fitDampedTrend(values) : selectForecastModel(values, 'auto', granularity)
}

function scoreModel(
  method: ForecastRuntimeMethod,
  values: number[],
  granularity?: TrendTimeGranularity
) {
  const minimum =
    method === 'linear' || method === 'damped_trend'
      ? 2
      : method === 'exponential'
        ? 3
        : method === 'holt_winters'
          ? 4
          : 5
  if (values.length < minimum) {
    return null
  }
  const holdout = values.length >= 8 ? Math.min(6, Math.max(2, Math.round(values.length * 0.25))) : 1
  const trainValues = values.slice(0, values.length - holdout)
  const actualValues = values.slice(values.length - holdout)
  if (trainValues.length < minimum - 1) {
    return null
  }
  const validationModel = fitModel(method, trainValues, granularity)
  if (!validationModel) {
    return null
  }
  const predictions = actualValues.map((_, index) => validationModel.predict(trainValues.length + index + 1))
  const error = forecastError(actualValues, predictions)
  if (!Number.isFinite(error)) {
    return null
  }
  const fullModel = fitModel(method, values, granularity)
  if (!fullModel) {
    return null
  }
  return {
    model: fullModel,
    score: error + METHOD_COMPLEXITY_PENALTY[method],
  }
}

function fitModel(
  method: ForecastRuntimeMethod,
  values: number[],
  granularity?: TrendTimeGranularity
): ForecastModel | null {
  if (method === 'damped_trend') return fitDampedTrend(values)
  if (method === 'linear') return fitLinear(values)
  if (method === 'polynomial') return fitPolynomial(values)
  if (method === 'exponential') return fitExponential(values)
  if (method === 'logarithmic') return fitTransformedLinear(values, (x) => Math.log(x), 'logarithmic')
  if (method === 'power') return fitPower(values)
  if (method === 'reciprocal') return fitTransformedLinear(values, (x) => 1 / x, 'reciprocal')
  if (method === 'logistic') return fitBoundedGrowth(values, 'logistic')
  if (method === 'gompertz') return fitBoundedGrowth(values, 'gompertz')
  return fitHoltWinters(values, granularity)
}

function forecastError(actualValues: number[], predictions: number[]) {
  let smapeTotal = 0
  let mseTotal = 0
  const meanAbs = actualValues.reduce((sum, value) => sum + Math.abs(value), 0) / actualValues.length || 1
  actualValues.forEach((actual, index) => {
    const predicted = predictions[index]
    const denominator = Math.abs(actual) + Math.abs(predicted) + EPSILON
    smapeTotal += (2 * Math.abs(predicted - actual)) / denominator
    mseTotal += (predicted - actual) ** 2
  })
  const smape = smapeTotal / actualValues.length
  const normalizedRmse = Math.sqrt(mseTotal / actualValues.length) / (meanAbs + EPSILON)
  return smape * 0.7 + normalizedRmse * 0.3
}

function fitLinear(values: number[]): ForecastModel | null {
  if (values.length < 2) {
    return null
  }
  const fit = linearRegression(values.map((value, index) => ({ x: index + 1, y: value })))
  if (!fit) {
    return null
  }
  return {
    method: 'linear',
    predict: (index) => fit.intercept + fit.slope * index,
  }
}

function fitDampedTrend(values: number[]): ForecastModel | null {
  if (values.length < 2) {
    return null
  }
  const diffs = values.slice(1).map((value, index) => value - values[index])
  if (diffs.length === 0) {
    return null
  }
  const recentWindow = Math.min(8, diffs.length)
  const recentDiffs = clampExtremeDiffs(diffs).slice(-recentWindow)
  const weightedTotal = recentDiffs.reduce((sum, diff, index) => sum + diff * (index + 1), 0)
  const weightTotal = recentDiffs.reduce((sum, _diff, index) => sum + index + 1, 0)
  const recentTrend = weightedTotal / Math.max(weightTotal, 1)
  const fullFit = fitLinear(values)
  const fullSlope = fullFit ? fullFit.predict(values.length + 1) - fullFit.predict(values.length) : recentTrend
  const blendedTrend = recentTrend * 0.55 + fullSlope * 0.45
  const lastValue = values[values.length - 1]
  const recentValues = values.slice(-Math.min(6, values.length))
  const recentLevel = weightedAverage(recentValues)
  const damping = 0.9
  const reversionDamping = 0.82
  return {
    method: 'damped_trend',
    predict: (index) => {
      const steps = Math.max(0, index - values.length)
      if (steps === 0) {
        return lastValue
      }
      const dampedSteps = (1 - damping ** steps) / (1 - damping)
      const reversion = (recentLevel - lastValue) * (1 - reversionDamping ** steps)
      return lastValue + blendedTrend * dampedSteps + reversion
    },
  }
}

function weightedAverage(values: number[]) {
  const weightedTotal = values.reduce((sum, value, index) => sum + value * (index + 1), 0)
  const weightTotal = values.reduce((sum, _value, index) => sum + index + 1, 0)
  return weightedTotal / Math.max(weightTotal, 1)
}

function clampExtremeDiffs(diffs: number[]) {
  if (diffs.length < 4) {
    return diffs
  }
  const absDiffs = diffs.map((value) => Math.abs(value)).sort((a, b) => a - b)
  const medianAbsDiff = absDiffs[Math.floor(absDiffs.length / 2)]
  if (medianAbsDiff <= EPSILON) {
    return diffs
  }
  const limit = medianAbsDiff * 3
  return diffs.map((value) => Math.max(-limit, Math.min(limit, value)))
}

function fitPolynomial(values: number[]): ForecastModel | null {
  if (values.length < 5) {
    return null
  }
  const rows = values.map((value, index) => {
    const x = index + 1
    return [1, x, x * x, value]
  })
  const coeffs = solveLeastSquares(rows, 3)
  if (!coeffs) {
    return null
  }
  return {
    method: 'polynomial',
    predict: (index) => coeffs[0] + coeffs[1] * index + coeffs[2] * index * index,
  }
}

function fitExponential(values: number[]): ForecastModel | null {
  if (values.length < 3 || values.some((value) => value <= 0)) {
    return null
  }
  const fit = linearRegression(values.map((value, index) => ({ x: index + 1, y: Math.log(value) })))
  if (!fit) {
    return null
  }
  return {
    method: 'exponential',
    predict: (index) => Math.exp(fit.intercept + fit.slope * index),
  }
}

function fitTransformedLinear(
  values: number[],
  transformX: (x: number) => number,
  method: 'logarithmic' | 'reciprocal'
): ForecastModel | null {
  if (values.length < 4) {
    return null
  }
  const fit = linearRegression(values.map((value, index) => ({ x: transformX(index + 1), y: value })))
  if (!fit) {
    return null
  }
  return {
    method,
    predict: (index) => fit.intercept + fit.slope * transformX(index),
  }
}

function fitPower(values: number[]): ForecastModel | null {
  if (values.length < 4 || values.some((value) => value <= 0)) {
    return null
  }
  const fit = linearRegression(values.map((value, index) => ({ x: Math.log(index + 1), y: Math.log(value) })))
  if (!fit) {
    return null
  }
  return {
    method: 'power',
    predict: (index) => Math.exp(fit.intercept + fit.slope * Math.log(index)),
  }
}

function fitBoundedGrowth(values: number[], method: 'logistic' | 'gompertz'): ForecastModel | null {
  if (values.length < 6 || values.some((value) => value <= 0)) {
    return null
  }
  const maxValue = Math.max(...values)
  const minValue = Math.min(...values)
  if (maxValue - minValue <= EPSILON) {
    return null
  }
  const carryingCapacityCandidates = [1.05, 1.15, 1.3, 1.6, 2, 3].map((factor) => maxValue * factor)
  let bestModel: ForecastModel | null = null
  let bestError = Number.POSITIVE_INFINITY

  carryingCapacityCandidates.forEach((capacity) => {
    const transformed = values
      .map((value, index) => {
        if (value >= capacity) {
          return null
        }
        if (method === 'logistic') {
          return { x: index + 1, y: Math.log(value / (capacity - value)) }
        }
        const ratio = value / capacity
        if (ratio <= 0 || ratio >= 1) {
          return null
        }
        return { x: index + 1, y: Math.log(-Math.log(ratio)) }
      })
      .filter((point): point is { x: number; y: number } => point !== null && Number.isFinite(point.y))
    if (transformed.length < values.length) {
      return
    }
    const fit = linearRegression(transformed)
    if (!fit) {
      return
    }
    const model: ForecastModel = {
      method,
      predict: (index) => {
        if (method === 'logistic') {
          return capacity / (1 + Math.exp(-(fit.intercept + fit.slope * index)))
        }
        return capacity * Math.exp(-Math.exp(fit.intercept + fit.slope * index))
      },
    }
    const error = forecastError(values, values.map((_, index) => model.predict(index + 1)))
    if (error < bestError) {
      bestError = error
      bestModel = model
    }
  })

  return bestModel
}

function fitHoltWinters(values: number[], granularity?: TrendTimeGranularity): ForecastModel | null {
  if (values.length < 4) {
    return null
  }
  const period = resolveSeasonalPeriod(values.length, granularity)
  const seasonal = period ? estimateAdditiveSeasonality(values, period) : []
  const deseasonalized = seasonal.length
    ? values.map((value, index) => value - seasonal[index % seasonal.length])
    : values
  const holtModel = fitBestHoltLinear(deseasonalized)
  if (!holtModel) {
    return null
  }
  return {
    method: 'holt_winters',
    predict: (index) => {
      const seasonalValue = seasonal.length ? seasonal[(index - 1) % seasonal.length] : 0
      return holtModel.predict(index) + seasonalValue
    },
  }
}

function resolveSeasonalPeriod(length: number, granularity?: TrendTimeGranularity) {
  if (granularity === 'day' && length >= 14) return 7
  if (granularity === 'month' && length >= 24) return 12
  return 0
}

function estimateAdditiveSeasonality(values: number[], period: number) {
  const overall = values.reduce((sum, value) => sum + value, 0) / values.length
  return Array.from({ length: period }, (_, position) => {
    const bucket = values.filter((_, index) => index % period === position)
    if (bucket.length === 0) {
      return 0
    }
    return bucket.reduce((sum, value) => sum + value, 0) / bucket.length - overall
  })
}

function fitBestHoltLinear(values: number[]): ForecastModel | null {
  const smoothingValues = [0.2, 0.4, 0.6, 0.8]
  let bestState: { level: number; trend: number } | null = null
  let bestError = Number.POSITIVE_INFINITY
  smoothingValues.forEach((alpha) => {
    smoothingValues.forEach((beta) => {
      const state = runHoltLinear(values, alpha, beta)
      if (state.error < bestError) {
        bestError = state.error
        bestState = { level: state.level, trend: state.trend }
      }
    })
  })
  if (!bestState) {
    return null
  }
  const length = values.length
  return {
    method: 'holt_winters',
    predict: (index) => bestState!.level + (index - length) * bestState!.trend,
  }
}

function runHoltLinear(values: number[], alpha: number, beta: number) {
  let level = values[0]
  let trend = values[1] - values[0]
  let error = 0
  for (let index = 1; index < values.length; index += 1) {
    const forecast = level + trend
    error += (values[index] - forecast) ** 2
    const previousLevel = level
    level = alpha * values[index] + (1 - alpha) * (level + trend)
    trend = beta * (level - previousLevel) + (1 - beta) * trend
  }
  return { level, trend, error }
}

function linearRegression(points: Array<{ x: number; y: number }>) {
  if (points.length < 2) {
    return null
  }
  const n = points.length
  const sumX = points.reduce((sum, point) => sum + point.x, 0)
  const sumY = points.reduce((sum, point) => sum + point.y, 0)
  const sumXX = points.reduce((sum, point) => sum + point.x * point.x, 0)
  const sumXY = points.reduce((sum, point) => sum + point.x * point.y, 0)
  const denominator = n * sumXX - sumX * sumX
  if (Math.abs(denominator) < EPSILON) {
    return null
  }
  const slope = (n * sumXY - sumX * sumY) / denominator
  const intercept = (sumY - slope * sumX) / n
  if (!Number.isFinite(slope) || !Number.isFinite(intercept)) {
    return null
  }
  return { slope, intercept }
}

function solveLeastSquares(rows: number[][], size: number): number[] | null {
  const matrix = Array.from({ length: size }, () => Array(size + 1).fill(0))
  rows.forEach((row) => {
    for (let r = 0; r < size; r += 1) {
      for (let c = 0; c < size; c += 1) {
        matrix[r][c] += row[r] * row[c]
      }
      matrix[r][size] += row[r] * row[size]
    }
  })
  return gaussianElimination(matrix)
}

function gaussianElimination(matrix: number[][]): number[] | null {
  const size = matrix.length
  for (let pivot = 0; pivot < size; pivot += 1) {
    let maxRow = pivot
    for (let row = pivot + 1; row < size; row += 1) {
      if (Math.abs(matrix[row][pivot]) > Math.abs(matrix[maxRow][pivot])) {
        maxRow = row
      }
    }
    if (Math.abs(matrix[maxRow][pivot]) < EPSILON) {
      return null
    }
    ;[matrix[pivot], matrix[maxRow]] = [matrix[maxRow], matrix[pivot]]
    const pivotValue = matrix[pivot][pivot]
    for (let col = pivot; col <= size; col += 1) {
      matrix[pivot][col] /= pivotValue
    }
    for (let row = 0; row < size; row += 1) {
      if (row === pivot) {
        continue
      }
      const factor = matrix[row][pivot]
      for (let col = pivot; col <= size; col += 1) {
        matrix[row][col] -= factor * matrix[pivot][col]
      }
    }
  }
  const result = matrix.map((row) => row[size])
  return result.every(Number.isFinite) ? result : null
}
