import type { InjectionKey } from 'vue'
import {
  buildDashboardDateFilterRequest,
  createDashboardDateFilterState,
  getOrCreateDashboardDateFilterState,
  type DashboardDateFilterRequestConfig,
} from './dashboardDateFilter.ts'

type View = Record<string, any>
export type DashboardDateFilterSavePayload = {
  chart_id: string
  expected_sql: string
  expected_datasource: number | string
  date_filter: DashboardDateFilterRequestConfig
}
export type DashboardDateFilterSaver = (payload: DashboardDateFilterSavePayload) => Promise<void>
export const DASHBOARD_DATE_FILTER_SAVER: InjectionKey<DashboardDateFilterSaver> = Symbol('dashboard-date-filter-saver')

const resultKeys = ['dateFilter', 'dateFilterCapability', 'data', 'fields', 'status', 'dataState',
  'loadingProgress', 'refreshState', 'snapshotRefreshedAt', 'snapshotContext', 'message', 'error_type', 'reason']
function copy<T>(value: T): T {
  return value === undefined ? value : JSON.parse(JSON.stringify(value))
}

function ordered(value: any): any {
  if (Array.isArray(value)) return value.map(ordered)
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.keys(value).sort().map(key => [key, ordered(value[key])]))
  }
  return value
}

function restore(viewInfo: View, snapshot: Record<string, any>) {
  for (const key of resultKeys) {
    if (snapshot[key] === undefined) delete viewInfo[key]
    else viewInfo[key] = snapshot[key]
  }
}

export async function applyDashboardDateExpressionTransaction(
  viewInfo: View,
  expression: Record<string, unknown>,
  options: {
    refresh: (request: Record<string, unknown>) => Promise<boolean>
    persist?: DashboardDateFilterSaver
  }
): Promise<boolean> {
  const state = getOrCreateDashboardDateFilterState(viewInfo, viewInfo.dateFilterCapability)
  if (state.applying) return false
  const snapshot = Object.fromEntries(resultKeys.map(key => [key, copy(viewInfo[key])]))
  const previousState = copy(state)
  const config = {
    enabled: true,
    parameterType: viewInfo.dateFilter?.parameterType || viewInfo.dateFilterCapability?.parameterType,
    expression: copy(expression),
  }
  if (!config.parameterType) throw new Error('图表日期参数类型未配置')
  const request = buildDashboardDateFilterRequest(config, null)
  if (!request) throw new Error('图表日期配置无效')
  if (options.persist && !viewInfo.datasource) throw new Error('图表执行数据源未配置')
  const payload = { chart_id: String(viewInfo.id || ''), expected_sql: String(viewInfo.sql || ''),
    expected_datasource: viewInfo.datasource, date_filter: config }
  state.applying = true
  state.applyError = ''
  let committed = false
  try {
    if (!await options.refresh(request)) return false
    const capability = viewInfo.dateFilterCapability
    if (capability?.status !== 'available' || !capability.resolvedStart || !capability.resolvedEnd) {
      throw new Error('未取得新日期范围，日期设置未保存')
    }
    if (JSON.stringify(ordered(capability.expression)) !== JSON.stringify(ordered(expression))) {
      throw new Error('查询返回的日期表达式不一致，日期设置未保存')
    }
    const resolved = createDashboardDateFilterState(capability)
    if (resolved.appliedRange[0] !== capability.resolvedStart || resolved.appliedRange[1] !== capability.resolvedEnd) {
      throw new Error('查询返回的日期范围无效，日期设置未保存')
    }
    const refreshedSnapshot = Object.fromEntries(resultKeys.map(key => [key, copy(viewInfo[key])]))
    // Keep the last committed label and rows together until saving also succeeds.
    if (options.persist) {
      restore(viewInfo, snapshot)
      await options.persist(payload)
    }
    restore(viewInfo, refreshedSnapshot)
    viewInfo.configVersion = 2
    viewInfo.dateFilter = config
    if (viewInfo.data && typeof viewInfo.data === 'object') {
      delete viewInfo.data.source_data
      delete viewInfo.data.source_fields
    }
    if (viewInfo.pivot && typeof viewInfo.pivot === 'object') {
      Object.assign(viewInfo.pivot, { date_expression: copy(expression), range: 'source', custom_start: '', custom_end: '' })
    }
    const builder = viewInfo.sourceConfig?.sql?.builder
    if (builder && typeof builder === 'object') {
      Object.assign(builder, { timeRange: 'expression', timeExpression: copy(expression), timeCustomRange: [] })
    }
    Object.assign(state, resolved)
    committed = true
    return true
  } catch (error) {
    state.applyError = error instanceof Error ? error.message : '日期设置未保存'
    throw error
  } finally {
    if (!committed) {
      const message = state.applyError
      restore(viewInfo, snapshot)
      Object.assign(state, previousState, { applying: false, pendingRange: null, applyError: message })
    }
  }
}
