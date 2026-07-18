import { request, type FullRequestConfig } from '@/utils/request'
import type {
  RoiChart,
  RoiChartCreate,
  RoiChartPreviewRequest,
  RoiChartPreviewResponse,
  RoiChartReorderRequest,
  RoiChartUpdate,
  RoiConfig,
  RoiDashboard,
  RoiDashboardCreate,
  RoiDashboardReorderRequest,
  RoiDashboardUpdate,
} from '@/views/dashboard/roi/types'

export const roiCustomErrorRequestConfig: FullRequestConfig = {
  requestOptions: { customError: true },
}

export const roiDashboardApi = {
  getConfig: (config?: FullRequestConfig) =>
    request.get<RoiConfig | null>('/dashboard/roi/config', config),
  list: (config?: FullRequestConfig) => request.get<RoiDashboard[]>('/dashboard/roi/list', config),
  create: (payload: RoiDashboardCreate, config?: FullRequestConfig) =>
    request.post<RoiDashboard>('/dashboard/roi', payload, config),
  update: (id: string, payload: RoiDashboardUpdate, config?: FullRequestConfig) =>
    request.patch<RoiDashboard>(`/dashboard/roi/${id}`, payload, config),
  remove: (id: string, config?: FullRequestConfig) =>
    request.delete<boolean>(`/dashboard/roi/${id}`, config),
  reorder: (payload: RoiDashboardReorderRequest, config?: FullRequestConfig) =>
    request.post<RoiDashboard[]>('/dashboard/roi/reorder', payload, config),
  listCharts: (id: string, config?: FullRequestConfig) =>
    request.get<RoiChart[]>(`/dashboard/roi/${id}/charts`, config),
  previewChart: (id: string, payload: RoiChartPreviewRequest, config?: FullRequestConfig) =>
    request.post<RoiChartPreviewResponse>(`/dashboard/roi/${id}/charts/preview`, payload, config),
  createChart: (id: string, payload: RoiChartCreate, config?: FullRequestConfig) =>
    request.post<RoiChart>(`/dashboard/roi/${id}/charts`, payload, config),
  updateChart: (
    id: string,
    chartId: string,
    payload: RoiChartUpdate,
    config?: FullRequestConfig
  ) => request.put<RoiChart>(`/dashboard/roi/${id}/charts/${chartId}`, payload, config),
  removeChart: (id: string, chartId: string, config?: FullRequestConfig) =>
    request.delete<boolean>(`/dashboard/roi/${id}/charts/${chartId}`, config),
  reorderCharts: (id: string, payload: RoiChartReorderRequest, config?: FullRequestConfig) =>
    request.post<RoiChart[]>(`/dashboard/roi/${id}/charts/reorder`, payload, config),
}
