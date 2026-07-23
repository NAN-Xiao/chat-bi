export type RoiLayoutSpan = 'full' | 'half' | 'third'
export type RoiDateRange = [string, string]

export interface RoiConfig {
  id: string
  tenant_id: string
  datasource_id: number
  datasource_name: string | null
  version: number
  can_execute: boolean
  can_edit: boolean
}

export interface RoiDashboard {
  id: string
  tenant_id: string
  name: string
  sort: number
  status: number
  version: number
  create_by: string | null
  update_by: string | null
  create_time: number
  update_time: number
}

export interface RoiChartPreviewResponse {
  status: string
  fields: string[]
  data: Array<Record<string, unknown>>
  message: string
}

export interface RoiChart {
  id: string
  tenant_id: string
  roi_dashboard_id: string
  title: string
  sql: string | null
  chart_type: string
  chart_config: Record<string, unknown>
  layout_span: RoiLayoutSpan
  sort: number
  status: number
  version: number
  create_by: string | null
  update_by: string | null
  create_time: number
  update_time: number
  can_execute?: boolean
  can_edit?: boolean
  error?: string | null
  query_result?: RoiChartPreviewResponse | null
}

export interface RoiDashboardCreate {
  name: string
}

export interface RoiDashboardUpdate {
  name?: string
  status?: number
  version: number
}

export interface RoiChartPreviewRequest {
  title: string
  sql: string
  chart_type: string
  chart_config?: Record<string, unknown>
  layout_span?: RoiLayoutSpan
  start_date?: string
  end_date?: string
}

export interface RoiChartCreate extends RoiChartPreviewRequest {
  sort?: number
}

export interface RoiChartUpdate extends RoiChartCreate {
  version: number
}

export interface RoiDashboardOrderItem {
  id: string
  sort: number
  version: number
}

export interface RoiDashboardReorderRequest {
  items: RoiDashboardOrderItem[]
}

export interface RoiChartOrderItem {
  id: string
  sort: number
  layout_span: RoiLayoutSpan
  version: number
}

export interface RoiChartReorderRequest {
  items: RoiChartOrderItem[]
}

export interface RoiChartEditorState {
  visible: boolean
  mode: 'create' | 'edit'
  dashboardId: string
  chartId: string | null
  initialValue: RoiChart | null
  firstChart: boolean
}
