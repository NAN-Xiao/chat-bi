import { defineStore } from 'pinia'
import { store } from '@/stores'

const getDefaultDashboardInfo = () => ({
  id: null,
  name: null,
  pid: null,
  datasource: null,
  status: null,
  source: null,
  dataState: null,
  createName: null,
  updateName: null,
  createTime: null,
  updateTime: null,
  contentId: null,
  type: null,
  canEdit: false,
  canShare: false,
  isPlatformDelegateDraft: false,
  canPublishDelegateDraft: false,
})

export const dashboardStore = defineStore('dashboard', {
  state: () => {
    return {
      tabCollisionActiveId: null,
      tabMoveInActiveId: null,
      curComponent: null,
      curComponentId: null,
      canvasStyleData: {},
      componentData: [],
      canvasViewInfo: {},
      fullscreenFlag: false,
      dataPrepareState: false,
      canvasEditingSourceKey: null as string | null,
      canvasChangedVersion: 0,
      canvasSavedVersion: 0,
      baseMatrixCount: {
        x: 72,
        y: 36,
      },
      dashboardInfo: getDefaultDashboardInfo(),
    }
  },
  getters: {
    getCurComponent(): any {
      return this.curComponent
    },
    hasUnsavedCanvasChanges(): boolean {
      return this.canvasChangedVersion !== this.canvasSavedVersion
    },
  },
  actions: {
    setFullscreenFlag(val: boolean) {
      this.fullscreenFlag = val
    },
    setCurComponent: function (value: any) {
      if (!value && this.curComponent) {
        // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
        this.curComponent.editing = false
      }
      this.curComponent = value
      this.curComponentId = value && value.id ? value.id : null
    },
    setDashboardInfo(value: any) {
      this.dashboardInfo = value || getDefaultDashboardInfo()
    },
    setComponentData(value: any) {
      this.componentData = value
    },
    setCanvasStyleData(value: any) {
      this.canvasStyleData = value
    },
    setTabCollisionActiveId(tabId: any) {
      this.tabCollisionActiveId = tabId
    },
    setTabMoveInActiveId(tabId: any) {
      this.tabMoveInActiveId = tabId
    },
    updateDashboardInfo(params: any) {
      Object.keys(params).forEach((key: string) => {
        if (params[key] !== undefined) {
          // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
          this.dashboardInfo[key] = params[key]
        }
      })
    },
    setCanvasViewInfo(params: any) {
      this.canvasViewInfo = params
    },
    addCanvasViewInfo(params: any) {
      // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
      this.canvasViewInfo[params.id] = params
    },
    setCanvasEditingSourceKey(value: string | null, resetVersion = true) {
      this.canvasEditingSourceKey = value
      if (resetVersion) {
        this.canvasChangedVersion = 0
        this.canvasSavedVersion = 0
      }
    },
    markCanvasChanged() {
      this.canvasChangedVersion += 1
    },
    markCanvasSaved() {
      this.canvasSavedVersion = this.canvasChangedVersion
    },
    canvasDataInit() {
      this.curComponent = null
      this.curComponentId = null
      this.canvasStyleData = {}
      this.componentData = []
      this.canvasViewInfo = {}
      this.dashboardInfo = getDefaultDashboardInfo()
      this.setCanvasEditingSourceKey(null)
    },
  },
})

export const dashboardStoreWithOut = () => {
  return dashboardStore(store)
}
