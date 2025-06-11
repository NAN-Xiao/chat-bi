import {dashboardApi} from "@/api/dashboard.ts";
import {dashboardStoreWithOut} from "@/stores/dashboard/dashboard.ts";
import {storeToRefs} from "pinia";

const dashboardStore = dashboardStoreWithOut()
const {componentData, canvasStyleData} = storeToRefs(dashboardStore)

const workspace_id = 'default' // temp
export const load_resource_prepare = (params: any, callBack: Function) => {
    dashboardApi.load_resource(params).then((canvasInfo: any) => {
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
        const canvasDataResult = JSON.parse(canvasInfo.component_data)
        const canvasStyleResult = JSON.parse(canvasInfo.canvas_style_data)
        const canvasViewInfoPreview = canvasInfo.canvasViewInfo
        callBack({dashboardInfo, canvasDataResult, canvasStyleResult, canvasViewInfoPreview})
    })
}

export const initCanvasData = (params: any, callBack: Function) => {
    load_resource_prepare(params, function (result: any) {
        dashboardStore.setDashboardInfo(result.dashboardInfo)
        dashboardStore.setCanvasStyleData(result.canvasStyleResult)
        dashboardStore.setComponentData(result.canvasDataResult)
        dashboardStore.setCanvasViewInfo(result.canvasViewInfoPreview)
        callBack()
    })
}

export const saveDashboardResource = (params: any, callBack: Function) => {
    params['workspace_id'] = workspace_id
    dashboardApi.check_name(params).then((resCheck: any) => {
        if (resCheck) {
            if (params.opt === 'newLeaf') {// create canvas
                const reqeustParams = {
                    ...params,
                    component_data: JSON.stringify(componentData.value),
                    canvas_style_data: JSON.stringify(canvasStyleData.value)
                }
                dashboardApi.create_canvas(reqeustParams).then((res: any) => {
                    dashboardStore.updateDashboardInfo({id: res.id, dataState: 'ready'})
                    callBack(res)
                })
            } else if (params.opt === 'newFolder') {
                dashboardApi.create_resource(params).then((res: any) => {
                    callBack(res)
                })
            } else if (params.opt === 'rename') {
                dashboardApi.update_resource(params).then((res: any) => {
                    callBack(res)
                })
            }else if (params.opt === 'updateLeaf') {
                const reqeustParams = {
                    ...params,
                    component_data: JSON.stringify(componentData.value),
                    canvas_style_data: JSON.stringify(canvasStyleData.value)
                }
                dashboardApi.update_canvas(reqeustParams).then(() => {
                    callBack()
                })
            }
        } else {
            ElMessage({
                type: 'warning',
                message: 'Name Already In Use',
            })
        }
    })
}