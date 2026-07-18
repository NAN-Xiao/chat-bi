import { defineStore } from 'pinia'
import { roiCustomErrorRequestConfig, roiDashboardApi } from '@/api/roiDashboard'
import type { RoiChart, RoiConfig, RoiDashboard, RoiEditorState } from '@/views/dashboard/roi/types'
import {
  beginRoiRequest,
  createRoiRequestState,
  finishRoiRequest,
  getRoiPermissionError,
  isLatestRoiRequest,
  isRoiRequestLoading,
  resetRoiRequests,
  setRoiPermissionError,
} from '@/stores/roiRequestCoordinator'

const createEditorState = (): RoiEditorState => ({
  chartDialogOpen: false,
  dashboardId: null,
  chartId: null,
  createDashboardRequestId: 0,
})

const errorStatus = (error: unknown) =>
  Number((error as { response?: { status?: number } })?.response?.status || 0)

export const useRoiDashboardStore = defineStore('roiDashboard', {
  state: () => ({
    config: null as RoiConfig | null,
    configLoaded: false,
    dashboards: [] as RoiDashboard[],
    charts: {} as Record<string, RoiChart[]>,
    loading: false,
    permissionError: '',
    editorState: createEditorState(),
    requestState: createRoiRequestState(),
  }),
  actions: {
    syncRequestState() {
      this.loading = isRoiRequestLoading(this.requestState)
      this.permissionError = getRoiPermissionError(this.requestState)
    },
    async loadConfig() {
      const request = beginRoiRequest(this.requestState, 'config')
      this.syncRequestState()
      try {
        const result = await roiDashboardApi.getConfig(roiCustomErrorRequestConfig)
        if (isLatestRoiRequest(this.requestState, request)) {
          this.config = result
          this.configLoaded = true
        }
        return result
      } catch (error) {
        if (errorStatus(error) === 403) {
          setRoiPermissionError(this.requestState, request, '没有管理 ROI 看板的权限')
        }
        throw error
      } finally {
        if (finishRoiRequest(this.requestState, request)) this.syncRequestState()
      }
    },
    async loadDashboards() {
      const request = beginRoiRequest(this.requestState, 'dashboards')
      this.syncRequestState()
      try {
        const result = await roiDashboardApi.list(roiCustomErrorRequestConfig)
        if (isLatestRoiRequest(this.requestState, request)) this.dashboards = result
        return result
      } catch (error) {
        if (errorStatus(error) === 403) {
          setRoiPermissionError(this.requestState, request, '没有管理 ROI 看板的权限')
        }
        throw error
      } finally {
        if (finishRoiRequest(this.requestState, request)) this.syncRequestState()
      }
    },
    async loadCharts(dashboardId: string) {
      const request = beginRoiRequest(this.requestState, `charts:${dashboardId}`, 'charts')
      this.syncRequestState()
      try {
        const result = await roiDashboardApi.listCharts(dashboardId, roiCustomErrorRequestConfig)
        if (isLatestRoiRequest(this.requestState, request)) this.charts[dashboardId] = result
        return result
      } catch (error) {
        if (errorStatus(error) === 403) {
          setRoiPermissionError(this.requestState, request, '没有执行 ROI 图表的权限')
        }
        throw error
      } finally {
        if (finishRoiRequest(this.requestState, request)) this.syncRequestState()
      }
    },
    requestDashboardCreation() {
      this.editorState.createDashboardRequestId += 1
    },
    publishDashboard(dashboard: RoiDashboard) {
      const index = this.dashboards.findIndex((item) => String(item.id) === String(dashboard.id))
      if (index >= 0) this.dashboards[index] = dashboard
      else this.dashboards.push(dashboard)
    },
    publishCharts(dashboardId: string, charts: RoiChart[]) {
      this.charts[String(dashboardId)] = charts
    },
    reset() {
      resetRoiRequests(this.requestState)
      this.config = null
      this.configLoaded = false
      this.dashboards = []
      this.charts = {}
      this.loading = false
      this.permissionError = ''
      this.editorState = createEditorState()
    },
  },
})
