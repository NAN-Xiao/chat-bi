import {defineStore} from 'pinia'
import {store} from "@/stores";

export const dashboardStore = defineStore('dashboard', {
    state: () => {
        return {
            curComponent: null,
            canvasStyle: {},
            componentData: [],
            dashboardInfo: {
                id: null,
                name: 'New Dashboard',
                pid: null,
                dataState: null,
                optType: null,
                status: null,
                type: null,
                mobileLayout: false
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
        },
        setComponentData(value: any) {
            this.componentData = value
        },
        setCanvasStyle(value: any) {
            this.canvasStyle = value
        }

    }
})


export const dashboardStoreWithOut = () => {
    return dashboardStore(store)
}