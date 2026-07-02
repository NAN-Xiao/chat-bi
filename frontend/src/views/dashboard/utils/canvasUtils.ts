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
type DashboardResourceCallback = (response: any) => void

export const load_resource_prepare = (
  params: any,
  callBack: (obj: any) => void,
  options: { defaultMode?: boolean; includeData?: boolean; platformTemplate?: boolean; requestConfig?: any } = {}
) => {
  const loadRequest = options.platformTemplate
    ? dashboardApi.platform_template_admin_load
    : options.defaultMode
      ? dashboardApi.default_load
      : dashboardApi.load_resource
  const requestParams =
    typeof options.includeData === 'boolean'
      ? { ...params, include_data: options.includeData }
      : params
  loadRequest(requestParams, options.requestConfig)
    .then((canvasInfo: any) => {
      const dashboardInfo = {
        id: canvasInfo.id,
        name: canvasInfo.name,
        pid: canvasInfo.pid,
        datasource: canvasInfo.datasource,
        status: canvasInfo.status,
        source: canvasInfo.source,
        contentId: canvasInfo.content_id,
        type: canvasInfo.type,
        createName: canvasInfo.create_name,
        updateName: canvasInfo.update_name,
        createTime: canvasInfo.create_time,
        updateTime: canvasInfo.update_time,
        canEdit: canvasInfo.can_edit,
        canShare: canvasInfo.can_share ?? canvasInfo.can_edit,
        isDefault: canvasInfo.is_default,
        canSetDefault: canvasInfo.can_set_default,
        dashboardRefreshPolicy: canvasInfo.dashboard_refresh_policy || null,
      }
      const canvasDataResult = JSON.parse(canvasInfo.component_data)
      const canvasStyleResult = JSON.parse(canvasInfo.canvas_style_data)
      const canvasViewInfoPreview = JSON.parse(canvasInfo.canvas_view_info || '{}')
      callBack({ dashboardInfo, canvasDataResult, canvasStyleResult, canvasViewInfoPreview })
    })
    .catch((err) => {
      if (
        options.requestConfig?.signal?.aborted ||
        err?.name === 'CanceledError' ||
        err?.code === 'ERR_CANCELED' ||
        err?.message === 'canceled'
      ) {
        return
      }
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

export const findNextComponentIndex = async (params: any, callBack: DashboardResourceCallback) => {
  const { onError, ...requestParams } = params || {}
  load_resource_prepare(
    requestParams,
    function (result: any) {
      const { dashboardInfo, canvasDataResult, canvasStyleResult, canvasViewInfoPreview } = result || {}
      if (!dashboardInfo?.id || !Array.isArray(canvasDataResult)) {
        onError?.(result)
        return
      }
      let bottomPosition = 0
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
    },
    { includeData: false }
  )
}

export const saveDashboardResource = (params: any, callBack: DashboardResourceCallback) => {
  const commonParams = {
    componentData: componentData.value,
    canvasStyleData: canvasStyleData.value,
    canvasViewInfo: canvasViewInfo.value,
  }
  saveDashboardResourceTarget(params, commonParams, callBack)
}

export const savePlatformTemplateResource = (params: any, callBack: DashboardResourceCallback) => {
  const requestParams = {
    id: params.id,
    name: params.name || dashboardStore.dashboardInfo.name,
    pid: 'root',
    datasource: dashboardStore.dashboardInfo.datasource || null,
    node_type: 'leaf',
    type: dashboardStore.dashboardInfo.type || 'dashboard',
    component_data: JSON.stringify(componentData.value || []),
    canvas_style_data: JSON.stringify(canvasStyleData.value || {}),
    canvas_view_info: JSON.stringify(canvasViewInfo.value || {}),
  }
  dashboardApi.platform_template_admin_update(requestParams).then((res: any) => {
    clearDashboardCanvasDraft(dashboardStore.canvasEditingSourceKey)
    dashboardStore.updateDashboardInfo({
      id: res.id,
      name: res.name || requestParams.name,
      datasource: res.datasource ?? requestParams.datasource,
      status: res.status,
      source: res.source,
      contentId: res.content_id,
      canEdit: true,
    })
    dashboardStore.markCanvasSaved()
    callBack(res)
  })
}

export const saveDashboardResourceTarget = (
  params: any,
  commonParams: any,
  callBack: DashboardResourceCallback
) => {
  const hasDatasourceParam = Object.prototype.hasOwnProperty.call(params, 'datasource')
  const requestBaseParams = {
    ...params,
    datasource: hasDatasourceParam
      ? params.datasource
      : dashboardStore.dashboardInfo.datasource || datasourceContext.datasourceId,
  }
  return dashboardApi.check_name(requestBaseParams).then((resCheck: any) => {
    if (resCheck) {
      if (requestBaseParams.opt === 'newLeaf') {
        // create canvas
        const requestParams = {
          ...requestBaseParams,
          component_data: JSON.stringify(commonParams.componentData),
          canvas_style_data: JSON.stringify(commonParams.canvasStyleData),
          canvas_view_info: JSON.stringify(commonParams.canvasViewInfo),
        }
        return dashboardApi.create_canvas(requestParams).then((res: any) => {
          const previousSourceKey = dashboardStore.canvasEditingSourceKey
          dashboardStore.updateDashboardInfo({
            id: res.id,
            pid: requestBaseParams.pid,
            datasource: requestBaseParams.datasource,
            name: requestBaseParams.name,
            status: res.status,
            source: res.source,
            contentId: res.content_id,
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
        return dashboardApi.create_resource(requestBaseParams).then((res: any) => {
          callBack(res)
        })
      } else if (requestBaseParams.opt === 'rename') {
        return dashboardApi.update_resource(requestBaseParams).then((res: any) => {
          callBack(res)
        })
      } else if (requestBaseParams.opt === 'updateLeaf') {
        const requestParams = {
          ...requestBaseParams,
          component_data: JSON.stringify(commonParams.componentData),
          canvas_style_data: JSON.stringify(commonParams.canvasStyleData),
          canvas_view_info: JSON.stringify(commonParams.canvasViewInfo),
        }
        return dashboardApi.update_canvas(requestParams).then((res: any) => {
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
