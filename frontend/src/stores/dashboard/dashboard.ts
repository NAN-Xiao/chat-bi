import {defineStore} from 'pinia'
import {store} from "@/stores";

export const dashboardStore = defineStore('dashboard', {
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


export const dashboardStoreWithOut = () => {
    return dashboardStore(store)
}