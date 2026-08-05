import type { ChartAxis, ChartData, ChartTypes } from '@/views/chat/component/BaseChart.ts'
import {
  buildInsightDataStructureKey,
  buildInsightLayoutStateKey,
  resolveInsightDisplay,
  type InsightDensity,
  type InsightDisplayStrategy,
  type InsightLayout,
  type TrendAggregateMetric,
  type TrendComparisonMetric,
} from '../../../chat/component/chartInsight.ts'
import type { InsightFrameSize } from './insightFrame.ts'

export type TabInsightControlsVariant = 'none' | 'pivot' | 'date' | 'combined'

export interface TabInsightConfig {
  enabled?: boolean
  comparison?: {
    enabled?: boolean
    metrics?: TrendComparisonMetric[]
  }
  aggregate?: {
    enabled?: boolean
    metrics?: TrendAggregateMetric[]
  }
}

export interface TabInsightLayoutInput {
  frame: InsightFrameSize | null
  viewId?: string | number | null
  chartType: ChartTypes
  data?: Array<ChartData>
  x?: Array<ChartAxis>
  y?: Array<ChartAxis>
  series?: Array<ChartAxis>
  insight?: TabInsightConfig
  controlsVariant: TabInsightControlsVariant
}

export interface TabInsightLayoutState {
  lastAttemptedSignature: string | null
  lastProcessedSignature: string | null
  layoutStateKey: string | null
  previousLayout: InsightLayout | undefined
  previousDensity: InsightDensity | undefined
  display: InsightDisplayStrategy | null
}

export interface TabInsightLayoutTransition {
  state: TabInsightLayoutState
  display: InsightDisplayStrategy | null
  processed: boolean
  error?: unknown
}

export type TabInsightDisplayResolver = typeof resolveInsightDisplay

const CONTROLS_RESERVE: Record<TabInsightControlsVariant, number> = {
  none: 0,
  pivot: 30,
  date: 36,
  combined: 36,
}

export function resolveTabInsightControlsVariant(input: {
  pivot: boolean
  date: boolean
}): TabInsightControlsVariant {
  if (input.pivot && input.date) return 'combined'
  if (input.pivot) return 'pivot'
  if (input.date) return 'date'
  return 'none'
}

export function resolveTabInsightControlsReserve(variant: TabInsightControlsVariant) {
  return CONTROLS_RESERVE[variant]
}

export function createTabInsightLayoutState(): TabInsightLayoutState {
  return {
    lastAttemptedSignature: null,
    lastProcessedSignature: null,
    layoutStateKey: null,
    previousLayout: undefined,
    previousDensity: undefined,
    display: null,
  }
}

function normalizeInsightConfig(insight: TabInsightConfig | undefined) {
  return [
    insight?.enabled !== false,
    insight?.comparison?.enabled !== false,
    insight?.comparison?.metrics || null,
    insight?.aggregate?.enabled !== false,
    insight?.aggregate?.metrics || null,
  ]
}

function buildTabInsightLayoutSignature(input: TabInsightLayoutInput) {
  if (
    !input.frame ||
    !Number.isFinite(input.frame.width) ||
    !Number.isFinite(input.frame.height) ||
    input.frame.width <= 0 ||
    input.frame.height <= 0
  ) {
    return null
  }
  return JSON.stringify([
    input.frame.width,
    input.frame.height,
    buildInsightLayoutStateKey({
      viewId: input.viewId,
      chartType: input.chartType,
      x: input.x,
      y: input.y,
      series: input.series,
      dashboard: true,
    }),
    normalizeInsightConfig(input.insight),
    input.controlsVariant,
    buildInsightDataStructureKey({
      chartType: input.chartType,
      data: input.data,
      x: input.x,
      y: input.y,
      series: input.series,
      dashboard: true,
    }),
  ])
}

export function transitionTabInsightLayout(
  state: TabInsightLayoutState,
  input: TabInsightLayoutInput,
  resolver: TabInsightDisplayResolver = resolveInsightDisplay
): TabInsightLayoutTransition {
  const signature = buildTabInsightLayoutSignature(input)
  if (!signature || signature === state.lastAttemptedSignature) {
    return { state, display: state.display, processed: false }
  }

  const layoutStateKey = buildInsightLayoutStateKey({
    viewId: input.viewId,
    chartType: input.chartType,
    x: input.x,
    y: input.y,
    series: input.series,
    dashboard: true,
  })
  const resetHistory = layoutStateKey !== state.layoutStateKey
  const attemptedState = { ...state, lastAttemptedSignature: signature }

  try {
    const resolved = resolver({
      chartType: input.chartType,
      data: input.data,
      x: input.x,
      y: input.y,
      series: input.series,
      width: input.frame!.width,
      height: input.frame!.height,
      dashboard: true,
      previousLayout: resetHistory ? undefined : state.previousLayout,
      previousDensity: resetHistory ? undefined : state.previousDensity,
    })
    const display =
      input.insight?.enabled === false
        ? { ...resolved, show: false, maxStats: 0 }
        : resolved
    const nextState: TabInsightLayoutState = {
      lastAttemptedSignature: signature,
      lastProcessedSignature: signature,
      layoutStateKey,
      previousLayout: display.layout,
      previousDensity: display.density,
      display,
    }
    return { state: nextState, display, processed: true }
  } catch (error) {
    return { state: attemptedState, display: state.display, processed: false, error }
  }
}
