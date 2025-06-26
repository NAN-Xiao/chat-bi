import { defineStore } from 'pinia'
import { store } from '@/stores'

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
      dashboardInfo: {
        id: null,
        name: null,
        pid: null,
        workspaceId: null,
        status: null,
        dataState: null,
        createName: null,
        updateName: null,
        createTime: null,
        updateTime: null,
        contentId: null,
        type: null,
      },
    }
  },
  getters: {
    getCurComponent(): any {
      return this.curComponent
    },
  },
  actions: {
    setCurComponent(value: any) {
      this.curComponent = value
      this.curComponentId = value && value.id ? value.id : null
    },
    setDashboardInfo(value: any) {
      this.dashboardInfo = value
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
        // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
        this.dashboardInfo[key] = params[key]
      })
    },
    setCanvasViewInfo(params: any) {
      this.canvasViewInfo = params
    },
    addCanvasViewInfo(params: any) {
      // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
      this.canvasViewInfo[params.id] = params
    },
    canvasDataInit() {
      this.curComponent = null
      this.curComponentId = null
      this.canvasStyleData = {}
      this.componentData = []
      this.canvasViewInfo = {}
      this.dashboardInfo = {
        id: null,
        name: null,
        pid: null,
        workspaceId: null,
        status: null,
        dataState: null,
        createName: null,
        updateName: null,
        createTime: null,
        updateTime: null,
        contentId: null,
        type: null,
      }
    },
  },
})

export const dashboardStoreWithOut = () => {
  return dashboardStore(store)
}
