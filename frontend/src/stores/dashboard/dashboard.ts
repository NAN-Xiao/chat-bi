import { defineStore } from 'pinia'

export const useDashboardStore = defineStore('dashboardStore', {
  state: () => {
    return {
      curComponent: null
    }
  },
  getters: {
    getCurComponent(): any {
      return this.curComponent
    }
  },
  actions: {
    setCurComponent(value: any) {
      this.curComponent = value
    }
  }
})
