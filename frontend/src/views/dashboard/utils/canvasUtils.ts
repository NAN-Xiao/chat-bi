import { dashboardApi } from '@/api/dashboard.ts'
import { dashboardStoreWithOut } from '@/stores/dashboard/dashboard.ts'
import { storeToRefs } from 'pinia'

const dashboardStore = dashboardStoreWithOut()
const { componentData, canvasStyleData, canvasViewInfo } = storeToRefs(dashboardStore)

const workspace_id = 'default' // temp
export const load_resource_prepare = (params: any, callBack: (obj: any) => void) => {
  dashboardApi
    .load_resource(params)
    .then((canvasInfo: any) => {
      const dashboardInfo = {
        id: canvasInfo.id,
        name: canvasInfo.name,
        pid: canvasInfo.pid,
        workspaceId: canvasInfo.workspace_id,
        status: canvasInfo.status,
        type: canvasInfo.type,
        createName: canvasInfo.create_name,
        updateName: canvasInfo.update_name,
        createTime: canvasInfo.create_time,
        updateTime: canvasInfo.update_time,
        contentId: canvasInfo.content_id,
      }
      const canvasDataResult = JSON.parse(canvasInfo.component_data)
      const canvasStyleResult = JSON.parse(canvasInfo.canvas_style_data)
      const canvasViewInfoPreview = JSON.parse(canvasInfo.canvas_view_info || '{}')
      callBack({ dashboardInfo, canvasDataResult, canvasStyleResult, canvasViewInfoPreview })
    })
    .catch((err) => {
      console.error('load_resource_prepare', err)
      callBack({})
    })
}

export const isMainCanvas = (canvasId: string) => {
  return canvasId === 'canvas-main'
}

export const initCanvasData = (params: any, callBack: () => void) => {
  load_resource_prepare(params, function (result: any) {
    dashboardStore.setDashboardInfo(result?.dashboardInfo)
    dashboardStore.setCanvasStyleData(result?.canvasStyleResult)
    dashboardStore.setComponentData(result?.canvasDataResult)
    dashboardStore.setCanvasViewInfo(result?.canvasViewInfoPreview)
    callBack()
  })
}

// eslint-disable-next-line @typescript-eslint/no-unsafe-function-type
export const saveDashboardResource = (params: any, callBack: Function) => {
  params['workspace_id'] = workspace_id
  dashboardApi.check_name(params).then((resCheck: any) => {
    if (resCheck) {
      if (params.opt === 'newLeaf') {
        // create canvas
        const requestParams = {
          ...params,
          component_data: JSON.stringify(componentData.value),
          canvas_style_data: JSON.stringify(canvasStyleData.value),
          canvas_view_info: JSON.stringify(canvasViewInfo.value),
        }
        dashboardApi.create_canvas(requestParams).then((res: any) => {
          dashboardStore.updateDashboardInfo({ id: res.id, dataState: 'ready' })
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
      } else if (params.opt === 'updateLeaf') {
        const requestParams = {
          ...params,
          component_data: JSON.stringify(componentData.value),
          canvas_style_data: JSON.stringify(canvasStyleData.value),
          canvas_view_info: JSON.stringify(canvasViewInfo.value),
        }
        dashboardApi.update_canvas(requestParams).then(() => {
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
