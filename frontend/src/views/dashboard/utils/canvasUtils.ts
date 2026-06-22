import { dashboardApi } from '@/api/dashboard.ts'
import { dashboardStoreWithOut } from '@/stores/dashboard/dashboard.ts'
import { storeToRefs } from 'pinia'
import { useDatasourceContextStore } from '@/stores/datasourceContext'
import {
  clearDashboardCanvasDraft,
  getDashboardCanvasSourceKey,
} from '@/views/dashboard/utils/canvasDraft.ts'

const dashboardStore = dashboardStoreWithOut()
const datasourceContext = useDatasourceContextStore()
const { componentData, canvasStyleData, canvasViewInfo } = storeToRefs(dashboardStore)

export const load_resource_prepare = (
  params: any,
  callBack: (obj: any) => void,
  options: { defaultMode?: boolean } = {}
) => {
  const loadRequest = options.defaultMode ? dashboardApi.default_load : dashboardApi.load_resource
  loadRequest(params)
    .then((canvasInfo: any) => {
      const dashboardInfo = {
        id: canvasInfo.id,
        name: canvasInfo.name,
        pid: canvasInfo.pid,
        datasource: canvasInfo.datasource,
        status: canvasInfo.status,
        type: canvasInfo.type,
        createName: canvasInfo.create_name,
        updateName: canvasInfo.update_name,
        createTime: canvasInfo.create_time,
        updateTime: canvasInfo.update_time,
        contentId: canvasInfo.content_id,
        canEdit: canvasInfo.can_edit,
        canShare: canvasInfo.can_share ?? canvasInfo.can_edit,
        isDefault: canvasInfo.is_default,
        canSetDefault: canvasInfo.can_set_default,
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
    dashboardStore.setCanvasEditingSourceKey(getDashboardCanvasSourceKey(result?.dashboardInfo?.id))
    callBack()
  })
}

// eslint-disable-next-line @typescript-eslint/no-unsafe-function-type
export const findNextComponentIndex = async (params: any, callBack: Function) => {
  load_resource_prepare(params, function (result: any) {
    let bottomPosition = 0
    const { dashboardInfo, canvasDataResult, canvasStyleResult, canvasViewInfoPreview } = result
    canvasDataResult.forEach((component: any) => {
      const componentBottom = component.y + component.sizeY
      if (componentBottom > bottomPosition) {
        bottomPosition = componentBottom
      }
    })
    callBack({
      bottomPosition,
      dashboardInfo,
      canvasDataResult,
      canvasStyleResult,
      canvasViewInfoPreview,
    })
  })
}

// eslint-disable-next-line @typescript-eslint/no-unsafe-function-type
export const saveDashboardResource = (params: any, callBack: Function) => {
  const commonParams = {
    componentData: componentData.value,
    canvasStyleData: canvasStyleData.value,
    canvasViewInfo: canvasViewInfo.value,
  }
  saveDashboardResourceTarget(params, commonParams, callBack)
}

// eslint-disable-next-line @typescript-eslint/no-unsafe-function-type
export const saveDashboardResourceTarget = (params: any, commonParams: any, callBack: Function) => {
  const requestBaseParams = {
    ...params,
    datasource:
      params.datasource || dashboardStore.dashboardInfo.datasource || datasourceContext.datasourceId,
  }
  dashboardApi.check_name(requestBaseParams).then((resCheck: any) => {
    if (resCheck) {
      if (requestBaseParams.opt === 'newLeaf') {
        // create canvas
        const requestParams = {
          ...requestBaseParams,
          component_data: JSON.stringify(commonParams.componentData),
          canvas_style_data: JSON.stringify(commonParams.canvasStyleData),
          canvas_view_info: JSON.stringify(commonParams.canvasViewInfo),
        }
        dashboardApi.create_canvas(requestParams).then((res: any) => {
          const previousSourceKey = dashboardStore.canvasEditingSourceKey
          dashboardStore.updateDashboardInfo({
            id: res.id,
            pid: requestBaseParams.pid,
            datasource: requestBaseParams.datasource,
            name: requestBaseParams.name,
            dataState: 'ready',
            canEdit: true,
          })
          clearDashboardCanvasDraft(previousSourceKey)
          clearDashboardCanvasDraft(getDashboardCanvasSourceKey(res.id))
          dashboardStore.setCanvasEditingSourceKey(getDashboardCanvasSourceKey(res.id))
          dashboardStore.markCanvasSaved()
          callBack(res)
        })
      } else if (requestBaseParams.opt === 'newFolder') {
        dashboardApi.create_resource(requestBaseParams).then((res: any) => {
          callBack(res)
        })
      } else if (requestBaseParams.opt === 'rename') {
        dashboardApi.update_resource(requestBaseParams).then((res: any) => {
          callBack(res)
        })
      } else if (requestBaseParams.opt === 'updateLeaf') {
        const requestParams = {
          ...requestBaseParams,
          component_data: JSON.stringify(commonParams.componentData),
          canvas_style_data: JSON.stringify(commonParams.canvasStyleData),
          canvas_view_info: JSON.stringify(commonParams.canvasViewInfo),
        }
        dashboardApi.update_canvas(requestParams).then((res: any) => {
          clearDashboardCanvasDraft(dashboardStore.canvasEditingSourceKey)
          dashboardStore.markCanvasSaved()
          callBack(res)
        })
      }
    } else {
      ElMessage({
        type: 'warning',
        message: '名称重复',
      })
    }
  })
}
