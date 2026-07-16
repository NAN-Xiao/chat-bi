import { request } from '@/utils/request'
import type {
  RoiChart,
  RoiChartCreate,
  RoiChartPreviewRequest,
  RoiChartPreviewResponse,
  RoiChartReorderRequest,
  RoiChartUpdate,
  RoiConfig,
  RoiConfigUpdate,
  RoiDashboard,
  RoiDashboardCreate,
  RoiDashboardReorderRequest,
  RoiDashboardUpdate,
  RoiDatasourceOption,
} from '@/views/dashboard/roi/types'

export const roiDashboardApi = {
  listDatasources: () => request.get<RoiDatasourceOption[]>('/dashboard/roi/datasources'),
  getConfig: () => request.get<RoiConfig | null>('/dashboard/roi/config'),
  updateConfig: (payload: RoiConfigUpdate) =>
    request.put<RoiConfig>('/dashboard/roi/config', payload),
  list: () => request.get<RoiDashboard[]>('/dashboard/roi/list'),
  create: (payload: RoiDashboardCreate) => request.post<RoiDashboard>('/dashboard/roi', payload),
  update: (id: string, payload: RoiDashboardUpdate) =>
    request.patch<RoiDashboard>(`/dashboard/roi/${id}`, payload),
  remove: (id: string) => request.delete<boolean>(`/dashboard/roi/${id}`),
  reorder: (payload: RoiDashboardReorderRequest) =>
    request.post<RoiDashboard[]>('/dashboard/roi/reorder', payload),
  listCharts: (id: string) => request.get<RoiChart[]>(`/dashboard/roi/${id}/charts`),
  previewChart: (id: string, payload: RoiChartPreviewRequest) =>
    request.post<RoiChartPreviewResponse>(`/dashboard/roi/${id}/charts/preview`, payload),
  createChart: (id: string, payload: RoiChartCreate) =>
    request.post<RoiChart>(`/dashboard/roi/${id}/charts`, payload),
  updateChart: (id: string, chartId: string, payload: RoiChartUpdate) =>
    request.put<RoiChart>(`/dashboard/roi/${id}/charts/${chartId}`, payload),
  removeChart: (id: string, chartId: string) =>
    request.delete<boolean>(`/dashboard/roi/${id}/charts/${chartId}`),
  reorderCharts: (id: string, payload: RoiChartReorderRequest) =>
    request.post<RoiChart[]>(`/dashboard/roi/${id}/charts/reorder`, payload),
}
