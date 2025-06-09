import {dashboardApi} from "@/api/dashboard.ts";
import {dashboardStoreWithOut} from "@/stores/dashboard/dashboard.ts";
import {storeToRefs} from "pinia";
const dashboardStore = dashboardStoreWithOut()
const {componentData,canvasStyle} = storeToRefs(dashboardStore)

export const initCanvasData = (params: any, callBack: Function) => {
    dashboardApi.getDashboardInfo(params).then((res: any) => {
        const canvasInfo = res.data;
        const dashboardInfo = {
            id: canvasInfo.id,
            name: canvasInfo.name,
            pid: canvasInfo.pid,
            workspaceId: canvasInfo.workspaceId,
            status: canvasInfo.status,
            type: canvasInfo.type,
            creatorName: canvasInfo.creatorName,
            updateName: canvasInfo.updateName,
            createTime: canvasInfo.createTime,
            updateTime: canvasInfo.updateTime,
            contentId: canvasInfo.contentId
        }
        const canvasDataResult = JSON.parse(canvasInfo.componentData)
        const canvasStyleResult = JSON.parse(canvasInfo.canvasStyleData)
        const canvasViewInfoPreview = canvasInfo.canvasViewInfo
        callBack({dashboardInfo, canvasDataResult, canvasStyleResult, canvasViewInfoPreview})
    })
}

export const saveDashboardResource = (params: any, callBack: Function) => {
    if(params.opt === 'newLeaf'){// create canvas
        const reqeustParams = {
            ...params,
            component_data:JSON.stringify(componentData.value),
            canvas_style_data:JSON.stringify(canvasStyle.value)
        }
        dashboardApi.saveCanvas(reqeustParams).then((res: any) => {
            dashboardStore.updateDashboardInfo({id:res.id,dataState:'ready'})
            callBack(res)
        })
    }else if(params.opt === 'newFolder'){
        dashboardApi.addResource(params).then((res: any) => {
            callBack(res)
        })
    }

}