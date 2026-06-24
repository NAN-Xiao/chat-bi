import type { ChartAxis, ChartData, ChartTypes } from '@/views/chat/component/BaseChart.ts'

export type InsightLayout = 'top' | 'side'
export type InsightDensity = 'regular' | 'compact' | 'mini' | 'basic'

export interface InsightDisplayStrategy {
  show: boolean
  layout: InsightLayout
  density: InsightDensity
  maxStats: number
}

const SIDE_LAYOUT_TYPES = new Set<ChartTypes>(['sankey', 'treemap'])
const WIDE_SIDE_MIN_WIDTH = 680
const SIDE_MIN_HEIGHT = 280
const TINY_MIN_WIDTH = 300
const TINY_MIN_HEIGHT = 250
const TOP_BASIC_MAX_WIDTH = 440
const TOP_BASIC_MAX_HEIGHT = 360
const TOP_MINI_MAX_WIDTH = 560
const TOP_MINI_MAX_HEIGHT = 430
const SIDE_MINI_MAX_WIDTH = 760
const SIDE_MINI_MAX_HEIGHT = 330
const SIDE_COMPACT_MAX_WIDTH = 900
const SIDE_COMPACT_MAX_HEIGHT = 390

function axisValues(axes?: Array<ChartAxis>) {
  return (axes || []).map((axis) => axis.value).filter(Boolean)
}

export function buildInsightColumns(
  data?: Array<ChartData>,
  knownAxes: Array<ChartAxis | undefined> = []
): Array<ChartAxis> {
  const rows = Array.isArray(data) ? data : []
  const knownValues = new Set(
    knownAxes.flatMap((axis) => (axis?.value ? [axis.value] : []))
  )
  const fields = new Set<string>()

  rows.slice(0, 20).forEach((row) => {
    Object.keys(row || {}).forEach((field) => {
      if (!knownValues.has(field)) {
        fields.add(field)
      }
    })
  })

  return Array.from(fields).map((field) => ({ name: field, value: field }))
}

export function resolveInsightLayout(params: {
  chartType: ChartTypes
  data?: Array<ChartData>
  x?: Array<ChartAxis>
  y?: Array<ChartAxis>
  series?: Array<ChartAxis>
}): InsightLayout {
  if (SIDE_LAYOUT_TYPES.has(params.chartType)) {
    return 'side'
  }

  const seriesAxis = params.series?.[0]
  const data = Array.isArray(params.data) ? params.data : []
  if (seriesAxis) {
    const groups = new Set(
      data
        .map((row) => row?.[seriesAxis.value])
        .filter((value) => value !== undefined && value !== null && value !== '')
        .map(String)
    )
    if (groups.size >= 6) {
      return 'side'
    }
  }

  const yValues = axisValues(params.y)
  if (yValues.length >= 4 && ['line', 'area', 'column', 'bar'].includes(params.chartType)) {
    return 'side'
  }

  return 'top'
}

export function resolveInsightDisplay(params: {
  chartType: ChartTypes
  data?: Array<ChartData>
  x?: Array<ChartAxis>
  y?: Array<ChartAxis>
  series?: Array<ChartAxis>
  width?: number
  height?: number
  dashboard?: boolean
}): InsightDisplayStrategy {
  const preferredLayout = resolveInsightLayout(params)
  const width = params.width || 0
  const height = params.height || 0

  if (!params.dashboard || width <= 0 || height <= 0) {
    return {
      show: true,
      layout: preferredLayout,
      density: params.dashboard ? 'compact' : 'regular',
      maxStats: preferredLayout === 'side' ? 4 : 3,
    }
  }

  const sideAllowed =
    preferredLayout === 'side' && width >= WIDE_SIDE_MIN_WIDTH && height >= SIDE_MIN_HEIGHT
  const layout: InsightLayout = sideAllowed ? 'side' : 'top'

  if (width < TINY_MIN_WIDTH || height < TINY_MIN_HEIGHT) {
    return {
      show: false,
      layout,
      density: 'basic',
      maxStats: 0,
    }
  }

  if (layout === 'top') {
    if (width < TOP_BASIC_MAX_WIDTH || height < TOP_BASIC_MAX_HEIGHT) {
      return {
        show: true,
        layout,
        density: 'basic',
        maxStats: 1,
      }
    }

    if (width < TOP_MINI_MAX_WIDTH || height < TOP_MINI_MAX_HEIGHT) {
      return {
        show: true,
        layout,
        density: 'mini',
        maxStats: 2,
      }
    }

    return {
      show: true,
      layout,
      density: 'compact',
      maxStats: 3,
    }
  }

  if (width < SIDE_MINI_MAX_WIDTH || height < SIDE_MINI_MAX_HEIGHT) {
    return {
      show: true,
      layout,
      density: 'mini',
      maxStats: 2,
    }
  }

  return {
    show: true,
    layout,
    density: width < SIDE_COMPACT_MAX_WIDTH || height < SIDE_COMPACT_MAX_HEIGHT ? 'compact' : 'regular',
    maxStats: width < SIDE_COMPACT_MAX_WIDTH || height < SIDE_COMPACT_MAX_HEIGHT ? 3 : 4,
  }
}
