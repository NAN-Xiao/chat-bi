import {dashboardApi} from "@/api/dashboard.ts";

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