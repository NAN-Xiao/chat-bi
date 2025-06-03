import {defineStore} from 'pinia'
import {store} from "@/stores";

export const dashboardStore = defineStore('dashboard', {
    state: () => {
        return {
            tabCollisionActiveId: null,
            tabMoveInActiveId: null,
            curComponent: null,
            curComponentId: null,
            canvasStyle: {},
            componentData: [],
            fullscreenFlag: false,
            dashboardInfo: {
                id: null,
                name: null,
                pid: null,
                workspaceId: null,
                status: null,
                type: null,
                creatorName: null,
                updateName: null,
                createTime: null,
                updateTime: null,
                contentId: null
            }
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
            this.curComponentId = value && value.id ? value.id : null
        },
        setDashboardInfo(value: any) {
            this.dashboardInfo = value
        },
        setComponentData(value: any) {
            this.componentData = value
        },
        setCanvasStyle(value: any) {
            this.canvasStyle = value
        },
        setTabCollisionActiveId(tabId: any) {
            this.tabCollisionActiveId = tabId
        },
        setTabMoveInActiveId(tabId: any) {
            this.tabMoveInActiveId = tabId
        },
        canvasDataInit(){

        }

    }
})


export const dashboardStoreWithOut = () => {
    return dashboardStore(store)
}