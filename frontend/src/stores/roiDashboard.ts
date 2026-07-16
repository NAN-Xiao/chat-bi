import { defineStore } from 'pinia'
import { roiDashboardApi } from '@/api/roiDashboard'
import type { RoiChart, RoiConfig, RoiDashboard, RoiEditorState } from '@/views/dashboard/roi/types'

const createEditorState = (): RoiEditorState => ({
  datasourceDialogOpen: false,
  chartDialogOpen: false,
  dashboardId: null,
  chartId: null,
})

const errorStatus = (error: unknown) =>
  Number((error as { response?: { status?: number } })?.response?.status || 0)

export const useRoiDashboardStore = defineStore('roiDashboard', {
  state: () => ({
    config: null as RoiConfig | null,
    dashboards: [] as RoiDashboard[],
    charts: {} as Record<string, RoiChart[]>,
    loading: false,
    permissionError: '',
    editorState: createEditorState(),
  }),
  actions: {
    async loadConfig() {
      this.loading = true
      this.permissionError = ''
      try {
        this.config = await roiDashboardApi.getConfig()
        return this.config
      } catch (error) {
        if (errorStatus(error) === 403) this.permissionError = '没有管理 ROI 看板的权限'
        throw error
      } finally {
        this.loading = false
      }
    },
    async loadDashboards() {
      this.loading = true
      this.permissionError = ''
      try {
        this.dashboards = await roiDashboardApi.list()
        return this.dashboards
      } catch (error) {
        if (errorStatus(error) === 403) this.permissionError = '没有管理 ROI 看板的权限'
        throw error
      } finally {
        this.loading = false
      }
    },
    async loadCharts(dashboardId: string) {
      this.loading = true
      this.permissionError = ''
      try {
        const result = await roiDashboardApi.listCharts(dashboardId)
        this.charts[dashboardId] = result
        return result
      } catch (error) {
        if (errorStatus(error) === 403) this.permissionError = '没有执行 ROI 图表的权限'
        throw error
      } finally {
        this.loading = false
      }
    },
    openDatasourceSettings() {
      this.editorState.datasourceDialogOpen = true
    },
    reset() {
      this.config = null
      this.dashboards = []
      this.charts = {}
      this.loading = false
      this.permissionError = ''
      this.editorState = createEditorState()
    },
  },
})
