<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, computed, reactive, watch, nextTick } from 'vue'
import Toolbar from '@/views/dashboard/editor/Toolbar.vue'
import DashboardEditor from '@/views/dashboard/editor/DashboardEditor.vue'
import { findNewComponentFromList } from '@/views/dashboard/components/component-list.ts'
import { guid } from '@/utils/canvas.ts'
import cloneDeep from 'lodash/cloneDeep'
import { storeToRefs } from 'pinia'
import { dashboardStoreWithOut } from '@/stores/dashboard/dashboard.ts'
import router from '@/router'
import { load_resource_prepare } from '@/views/dashboard/utils/canvasUtils.ts'
import { dashboardApi } from '@/api/dashboard.ts'
import { useI18n } from 'vue-i18n'
import { useDatasourceContextStore } from '@/stores/datasourceContext'
import {
  getCreateCanvasSourceKey,
  getDashboardCanvasSourceKey,
  getPlatformTemplateCanvasSourceKey,
  loadDashboardCanvasDraft,
  saveDashboardCanvasDraft,
  clearDashboardCanvasDraft,
} from '@/views/dashboard/utils/canvasDraft.ts'
import { applyRecommendedChartComponentSize } from '@/views/dashboard/utils/chartSizing.ts'
import {
  applyMixedChartResult,
  canRefreshMixedChart,
  isExternalMcpSnapshotChart,
  isMixedChart,
  refreshMixedChartData,
} from '@/views/dashboard/utils/mixedChartData'

const { t } = useI18n()
const dashboardStore = dashboardStoreWithOut()
const datasourceContext = useDatasourceContextStore()
const { dashboardInfo, componentData, canvasStyleData, canvasViewInfo, fullscreenFlag, baseMatrixCount } =
  storeToRefs(dashboardStore)

const dataInitState = ref(true)
const state = reactive({
  routerPid: null as string | null,
  resourceId: null as string | null,
  platformTemplateId: null as string | null,
  opt: null as string | null,
  datasource: null as number | string | null | undefined,
})

const dashboardEditorInnerRef = ref(null)
let canvasStateReady = false
let applyingCanvasState = false
let suppressCanvasStateChange = 0
let draftSaveTimer: number | null = null
let routeLoadVersion = 0
let chartRefreshTimer: number | undefined
let chartRefreshController: AbortController | null = null
let chartRefreshRetryCount = 0

const CHART_CACHE_LOOKUP_CONCURRENCY = 6
const CHART_DATABASE_REFRESH_CONCURRENCY = 4
const CHART_CACHE_LOOKUP_START_DELAY_MS = 160
const CHART_TRANSIENT_RETRY_DELAY_MS = 4000
const CHART_TRANSIENT_MAX_RETRIES = 6

const canUseCanvasDraft = (sourceKey?: string | null) => Boolean(sourceKey?.startsWith('create:'))

const loadCanvasResource = (id: string | number) =>
  new Promise<any>((resolve) => {
    load_resource_prepare(
      { id, include_data: false },
      function (result: any) {
        resolve(result)
      },
      {
        includeData: false,
        requestConfig: {
          requestOptions: { silent: true },
        },
      }
    )
  })

const loadPlatformTemplateResource = (id: string | number) =>
  new Promise<any>((resolve) => {
    load_resource_prepare(
      { id, include_data: false },
      function (result: any) {
        resolve(result)
      },
      { platformTemplate: true, includeData: false }
    )
  })

const firstQueryValue = (value: unknown) => {
  if (Array.isArray(value)) {
    return value[0] ? String(value[0]) : null
  }
  return value ? String(value) : null
}

function clampChartLoadingProgress(progress: unknown) {
  const numericProgress = Number(progress)
  if (!Number.isFinite(numericProgress)) {
    return 0
  }
  return Math.max(0, Math.min(100, Math.round(numericProgress)))
}

function setChartLoadingProgress(viewInfo: any, progress: number, allowDecrease = false) {
  if (!viewInfo) {
    return
  }
  const nextProgress = clampChartLoadingProgress(progress)
  const currentProgress = clampChartLoadingProgress(viewInfo.loadingProgress)
  viewInfo.loadingProgress = allowDecrease ? nextProgress : Math.max(currentProgress, nextProgress)
}

function unique(values: Array<string | undefined | null>) {
  return Array.from(
    new Set(
      values
        .filter((value) => value !== undefined && value !== null && `${value}`.trim() !== '')
        .map((value) => `${value}`)
    )
  )
}

function getResultFields(result: any) {
  return unique([
    ...(Array.isArray(result?.fields) ? result.fields : []),
    ...((result?.data || [])[0] ? Object.keys((result?.data || [])[0]) : []),
  ])
}

function isAbortError(error: any) {
  return (
    error?.name === 'CanceledError' ||
    error?.code === 'ERR_CANCELED' ||
    error?.message === 'canceled' ||
    error?.message === 'Request canceled'
  )
}

function hasChartSnapshot(viewInfo: any) {
  const rows = viewInfo?.data?.data
  return Array.isArray(rows) && rows.length > 0
}

function hasChartShape(viewInfo: any) {
  return (
    hasChartSnapshot(viewInfo) ||
    (Array.isArray(viewInfo?.data?.fields) && viewInfo.data.fields.length > 0) ||
    (Array.isArray(viewInfo?.fields) && viewInfo.fields.length > 0)
  )
}

function isExternalSnapshotChart(viewInfo: any) {
  return isExternalMcpSnapshotChart(viewInfo)
}

function hasUsableResultSnapshot(result: any) {
  if (result?.status === 'failed') {
    return false
  }
  const rows = result?.data
  return (
    (Array.isArray(rows) && rows.length > 0) ||
    (Array.isArray(result?.fields) && result.fields.length > 0)
  )
}

function resultRefreshedAt(result: any) {
  const timestamp = Number(result?.refreshed_at || result?.cache_refreshed_at || 0)
  return Number.isFinite(timestamp) && timestamp > 0 ? timestamp : Date.now()
}

function markChartSnapshotRefreshed(viewInfo: any, refreshedAt = Date.now()) {
  if (!viewInfo || typeof viewInfo !== 'object') {
    return
  }
  if (!viewInfo.data || typeof viewInfo.data !== 'object') {
    viewInfo.data = {}
  }
  viewInfo.snapshotRefreshedAt = refreshedAt
  viewInfo.data.snapshotRefreshedAt = refreshedAt
}

function isDashboardCacheMiss(result: any) {
  return result?.status === 'failed' && result?.error_type === 'dashboard_cache_miss'
}

function isDashboardQueryBusy(result: any) {
  return result?.status === 'failed' && result?.error_type === 'dashboard_query_busy'
}

function isPermissionDeniedResult(result: any) {
  return result?.status === 'failed' && result?.error_type === 'permission_denied'
}

function chartSqlPayload(viewInfo: any) {
  return {
    datasource: viewInfo.datasource,
    sql: viewInfo.sql.trim(),
    pivot: viewInfo.pivot?.enabled === true ? viewInfo.pivot : undefined,
  }
}

async function previewChartSqlCacheOnly(
  viewInfo: any,
  requestConfig: any = { requestOptions: { silent: true } }
) {
  if (isMixedChart(viewInfo)) {
    return refreshMixedChartData(viewInfo, {
      cacheOnly: true,
      requestConfig,
    })
  }
  return dashboardApi.preview_sql(
    {
      ...chartSqlPayload(viewInfo),
      cache_only: true,
    },
    requestConfig
  )
}

async function previewChartSqlFromDatabase(
  viewInfo: any,
  requestConfig: any = { requestOptions: { silent: true } }
) {
  if (isMixedChart(viewInfo)) {
    return refreshMixedChartData(viewInfo, {
      forceRefresh: true,
      requestConfig,
    })
  }
  return dashboardApi.preview_sql(
    {
      ...chartSqlPayload(viewInfo),
      force_refresh: true,
    },
    requestConfig
  )
}

function collectDashboardCharts(items: any[], entries: Array<{ component: any; viewInfo: any }> = []) {
  if (!Array.isArray(items)) {
    return entries
  }
  items.forEach((item) => {
    if (item?.component === 'SQView') {
      entries.push({
        component: item,
        viewInfo: (canvasViewInfo.value as Record<string, any>)?.[item.id],
      })
      return
    }
    if (item?.component === 'SQTab') {
      const tabs = Array.isArray(item.propValue) ? item.propValue : []
      tabs.forEach((tab: any) => collectDashboardCharts(tab?.componentData || [], entries))
      return
    }
    if (Array.isArray(item?.componentData)) {
      collectDashboardCharts(item.componentData, entries)
    }
  })
  return entries
}

function prepareEditorChartState(viewInfo: any) {
  if (isExternalSnapshotChart(viewInfo)) {
    keepChartSnapshotOrLoading(viewInfo)
    return
  }
  if (!viewInfo || !viewInfo.sql?.trim()) {
    return
  }
  if (!viewInfo.data || typeof viewInfo.data !== 'object') {
    viewInfo.data = {}
  }
  viewInfo.data.data = Array.isArray(viewInfo.data.data) ? viewInfo.data.data : []
  viewInfo.data.fields = Array.isArray(viewInfo.data.fields) ? viewInfo.data.fields : []
  viewInfo.fields = Array.isArray(viewInfo.fields) ? viewInfo.fields : viewInfo.data.fields
  viewInfo.message = ''
  if (hasChartSnapshot(viewInfo)) {
    viewInfo.status = 'success'
    viewInfo.dataState = 'ready'
    viewInfo.loadingProgress = 100
    viewInfo.refreshState = ''
  } else {
    viewInfo.status = 'loading'
    viewInfo.dataState = 'loading'
    setChartLoadingProgress(viewInfo, 0, true)
    viewInfo.refreshState = 'waiting'
  }
}

function keepChartLoadingState(viewInfo: any, refreshState = 'loading') {
  if (!viewInfo) {
    return
  }
  if (!viewInfo.data || typeof viewInfo.data !== 'object') {
    viewInfo.data = {}
  }
  viewInfo.data.data = Array.isArray(viewInfo.data.data) ? viewInfo.data.data : []
  viewInfo.data.fields = Array.isArray(viewInfo.data.fields) ? viewInfo.data.fields : []
  viewInfo.fields = Array.isArray(viewInfo.fields) ? viewInfo.fields : viewInfo.data.fields
  viewInfo.status = 'loading'
  viewInfo.message = ''
  viewInfo.dataState = 'loading'
  setChartLoadingProgress(viewInfo, 5)
  viewInfo.refreshState = refreshState
}

function keepChartSnapshotOrLoading(viewInfo: any) {
  if (!viewInfo) {
    return
  }
  if (hasChartShape(viewInfo)) {
    viewInfo.status = 'success'
    viewInfo.message = ''
    viewInfo.dataState = 'ready'
    viewInfo.loadingProgress = 100
    viewInfo.refreshState = ''
    return
  }
  keepChartLoadingState(viewInfo)
}

function applyChartResult(viewInfo: any, result: any) {
  if (!viewInfo) {
    return false
  }
  const fields = getResultFields(result)
  const data = Array.isArray(result?.data) ? result.data : []
  const previousData = Array.isArray(viewInfo?.data?.data) ? [...viewInfo.data.data] : []
  const previousDataFields = Array.isArray(viewInfo?.data?.fields) ? [...viewInfo.data.fields] : []
  const previousFields = Array.isArray(viewInfo?.fields) ? [...viewInfo.fields] : []
  const hasPreviousSnapshot = hasChartSnapshot(viewInfo)
  if (!viewInfo.data || typeof viewInfo.data !== 'object') {
    viewInfo.data = {}
  }
  viewInfo.data.fields = fields
  viewInfo.data.data = data
  viewInfo.fields = fields
  viewInfo.status = result?.status || 'success'
  viewInfo.message = result?.message || ''
  if (viewInfo.status === 'failed' && hasPreviousSnapshot && !isPermissionDeniedResult(result)) {
    viewInfo.data.fields = previousDataFields
    viewInfo.data.data = previousData
    viewInfo.fields = previousFields
    viewInfo.status = 'success'
    viewInfo.message = ''
    viewInfo.dataState = 'ready'
  } else {
    viewInfo.dataState = viewInfo.status === 'failed' ? 'failed' : 'ready'
    if (viewInfo.status !== 'failed') {
      markChartSnapshotRefreshed(viewInfo, resultRefreshedAt(result))
    }
  }
  viewInfo.loadingProgress = 100
  viewInfo.refreshState = ''
  return viewInfo.status !== 'failed' && data.length > 0
}

async function runChartQueue(
  entries: Array<{ component: any; viewInfo: any }>,
  concurrency: number,
  worker: (entry: { component: any; viewInfo: any }) => Promise<void>
) {
  let nextIndex = 0
  const runNext = async (): Promise<void> => {
    while (nextIndex < entries.length) {
      const entry = entries[nextIndex]
      nextIndex += 1
      await worker(entry)
    }
  }
  await Promise.all(
    Array.from({ length: Math.min(Math.max(1, concurrency), entries.length) }, () => runNext())
  )
}

function withAutoChartUpdate(task: () => void) {
  suppressCanvasStateChange += 1
  try {
    task()
  } finally {
    suppressCanvasStateChange = Math.max(0, suppressCanvasStateChange - 1)
  }
}

function cancelDashboardChartRefresh() {
  if (chartRefreshTimer) {
    window.clearTimeout(chartRefreshTimer)
    chartRefreshTimer = undefined
  }
  if (chartRefreshController) {
    chartRefreshController.abort()
    chartRefreshController = null
  }
}

function scheduleEditorChartRefresh(loadVersion: number, delay = CHART_CACHE_LOOKUP_START_DELAY_MS) {
  cancelDashboardChartRefresh()
  const controller = new AbortController()
  chartRefreshController = controller
  chartRefreshTimer = window.setTimeout(() => {
    chartRefreshTimer = undefined
    if (loadVersion !== routeLoadVersion || controller.signal.aborted) {
      return
    }
    void refreshEditorCharts(loadVersion, controller)
  }, delay)
}

async function refreshEditorCharts(loadVersion: number, controller: AbortController) {
  const chartEntries = collectDashboardCharts(componentData.value).filter((entry) =>
    Boolean(
      isMixedChart(entry.viewInfo)
        ? canRefreshMixedChart(entry.viewInfo)
        : !isExternalSnapshotChart(entry.viewInfo) && entry.viewInfo?.datasource && entry.viewInfo?.sql?.trim()
    )
  )
  if (!chartEntries.length) {
    return
  }
  await nextTick()

  let cacheFinished = 0
  let databaseFinished = 0
  let transientPendingCount = 0
  const databaseRefreshEntries: Array<{ component: any; viewInfo: any }> = []
  const requestConfig = {
    signal: controller.signal,
    requestOptions: { silent: true },
  }
  const updateProgress = (
    entries = chartEntries,
    finished = cacheFinished,
    count = chartEntries.length,
    startProgress = 0,
    endProgress = 95
  ) => {
    const boundedCount = Math.max(1, count)
    const progressRatio = Math.max(0, Math.min(1, finished / boundedCount))
    const progress = Math.min(95, Math.round(startProgress + (endProgress - startProgress) * progressRatio))
    withAutoChartUpdate(() => {
      entries.forEach((entry) => {
        if (entry.viewInfo?.dataState === 'loading') {
          setChartLoadingProgress(entry.viewInfo, progress)
        }
      })
    })
  }
  try {
    withAutoChartUpdate(() => {
      chartEntries.forEach((entry) => {
        if (!hasChartSnapshot(entry.viewInfo)) {
          keepChartLoadingState(entry.viewInfo, 'waiting')
        }
      })
    })
    await runChartQueue(chartEntries, CHART_CACHE_LOOKUP_CONCURRENCY, async (entry) => {
      const { viewInfo } = entry
      try {
        if (loadVersion !== routeLoadVersion || controller.signal.aborted) {
          return
        }
        const cachedResult = await previewChartSqlCacheOnly(viewInfo, requestConfig)
        if (loadVersion !== routeLoadVersion || controller.signal.aborted) {
          return
        }
        if (
          isDashboardCacheMiss(cachedResult) ||
          cachedResult?.status === 'failed' ||
          !hasUsableResultSnapshot(cachedResult)
        ) {
          if (isMixedChart(viewInfo) || !hasChartSnapshot(viewInfo)) {
            databaseRefreshEntries.push(entry)
          }
        } else {
          withAutoChartUpdate(() => {
            if (isMixedChart(viewInfo)) {
              applyMixedChartResult(viewInfo, cachedResult)
              markChartSnapshotRefreshed(viewInfo, resultRefreshedAt(cachedResult))
            } else {
              applyChartResult(viewInfo, cachedResult)
            }
          })
        }
      } catch (error: any) {
        if (isAbortError(error) || controller.signal.aborted) {
          return
        }
        if (loadVersion === routeLoadVersion && (isMixedChart(viewInfo) || !hasChartSnapshot(viewInfo))) {
          databaseRefreshEntries.push(entry)
        }
      } finally {
        cacheFinished += 1
        updateProgress(chartEntries, cacheFinished, chartEntries.length, 5, 45)
      }
    })

    const databaseTotal = databaseRefreshEntries.length
    if (!databaseTotal || loadVersion !== routeLoadVersion || controller.signal.aborted) {
      return
    }
    withAutoChartUpdate(() => {
      databaseRefreshEntries.forEach((entry) => keepChartLoadingState(entry.viewInfo, 'loading'))
    })
    await runChartQueue(databaseRefreshEntries, CHART_DATABASE_REFRESH_CONCURRENCY, async (entry) => {
      const { viewInfo } = entry
      try {
        if (loadVersion !== routeLoadVersion || controller.signal.aborted) {
          return
        }
        const result = await previewChartSqlFromDatabase(viewInfo, requestConfig)
        if (loadVersion !== routeLoadVersion || controller.signal.aborted) {
          return
        }
        withAutoChartUpdate(() => {
          if (result?.status === 'failed') {
            if (isPermissionDeniedResult(result)) {
              applyChartResult(viewInfo, result)
            } else {
              keepChartSnapshotOrLoading(viewInfo)
            }
            if (!hasChartSnapshot(viewInfo) && isDashboardQueryBusy(result)) {
              transientPendingCount += 1
            } else if (!hasChartSnapshot(viewInfo)) {
              transientPendingCount += 1
            }
          } else {
            if (isMixedChart(viewInfo)) {
              applyMixedChartResult(viewInfo, result)
              markChartSnapshotRefreshed(viewInfo, resultRefreshedAt(result))
            } else {
              applyChartResult(viewInfo, result)
            }
          }
        })
      } catch (error: any) {
        if (isAbortError(error) || controller.signal.aborted) {
          return
        }
        if (loadVersion === routeLoadVersion) {
          withAutoChartUpdate(() => {
            keepChartSnapshotOrLoading(viewInfo)
            if (!hasChartSnapshot(viewInfo)) {
              transientPendingCount += 1
            }
          })
        }
      } finally {
        databaseFinished += 1
        updateProgress(databaseRefreshEntries, databaseFinished, databaseTotal, 45, 95)
      }
    })
  } finally {
    if (chartRefreshController === controller) {
      chartRefreshController = null
    }
    if (
      transientPendingCount > 0 &&
      loadVersion === routeLoadVersion &&
      !controller.signal.aborted &&
      chartRefreshRetryCount < CHART_TRANSIENT_MAX_RETRIES
    ) {
      chartRefreshRetryCount += 1
      scheduleEditorChartRefresh(loadVersion, CHART_TRANSIENT_RETRY_DELAY_MS)
    }
  }
}

const syncRouteState = () => {
  const query = router.currentRoute.value.query
  state.opt = firstQueryValue(query.opt)
  state.resourceId = firstQueryValue(query.resourceId)
  state.platformTemplateId = firstQueryValue(query.platformTemplateId)
  state.routerPid = firstQueryValue(query.pid)
  state.datasource = firstQueryValue(query.datasource) || datasourceContext.datasourceId
}

const applyLoadedCanvasResource = async (
  resourceId: string | number,
  result: any,
  sourceKeyOverride?: string | null
) => {
  if (
    result?.dashboardInfo?.datasource &&
    String(datasourceContext.datasourceId || '') !== String(result.dashboardInfo.datasource)
  ) {
    await datasourceContext.activateDatasourceById(result.dashboardInfo.datasource, false)
  }
  await pauseCanvasStateWatch(() => {
    dashboardStore.setDashboardInfo(result?.dashboardInfo)
    dashboardStore.setCanvasStyleData(result?.canvasStyleResult || {})
    dashboardStore.setComponentData(result?.canvasDataResult || [])
    const loadedViewInfo = result?.canvasViewInfoPreview || {}
    if (!state.platformTemplateId) {
      Object.values(loadedViewInfo).forEach((viewInfo: any) => prepareEditorChartState(viewInfo))
    }
    dashboardStore.setCanvasViewInfo(loadedViewInfo)
    dashboardStore.setCanvasEditingSourceKey(
      sourceKeyOverride || getDashboardCanvasSourceKey(result?.dashboardInfo?.id || resourceId)
    )
  })
}

const loadCanvasFromRoute = async () => {
  const loadVersion = ++routeLoadVersion
  persistCanvasDraft()
  cancelDashboardChartRefresh()
  chartRefreshRetryCount = 0
  canvasStateReady = false
  syncRouteState()
  if (!state.platformTemplateId) {
    await datasourceContext.loadDatasources()
    if (loadVersion !== routeLoadVersion) return
  }

  const sourceKey =
    state.platformTemplateId
      ? getPlatformTemplateCanvasSourceKey(state.platformTemplateId)
      : state.opt === 'create'
      ? getCreateCanvasSourceKey(state.datasource, state.routerPid)
      : getDashboardCanvasSourceKey(state.resourceId)
  if (sourceKey && !canUseCanvasDraft(sourceKey)) {
    clearDashboardCanvasDraft(sourceKey)
  }
  if (
    sourceKey &&
    canUseCanvasDraft(sourceKey) &&
    dashboardStore.canvasEditingSourceKey === sourceKey &&
    dashboardStore.hasUnsavedCanvasChanges
  ) {
    canvasStateReady = true
    return
  }

  dataInitState.value = false
  try {
    if (state.platformTemplateId && sourceKey) {
      const templateId = state.platformTemplateId
      const result = await loadPlatformTemplateResource(templateId)
      if (loadVersion !== routeLoadVersion) return
      await applyLoadedCanvasResource(templateId, result, sourceKey)
      dashboardStore.updateDashboardInfo({
        canEdit: true,
        canShare: false,
      })
      dashboardStore.markCanvasSaved()
    } else if (state.opt === 'create') {
      const createSourceKey = getCreateCanvasSourceKey(state.datasource, state.routerPid)
      await pauseCanvasStateWatch(() => {
        dashboardStore.canvasDataInit()
        dashboardStore.updateDashboardInfo({
          dataState: 'prepare',
          name: t('dashboard.new_dashboard'),
          pid: state.routerPid,
          datasource: state.datasource,
          canEdit: true,
          canShare: true,
        })
        dashboardStore.setCanvasEditingSourceKey(createSourceKey)
      })
      const restored = await restoreCanvasDraft(createSourceKey)
      if (!restored) {
        dashboardStore.markCanvasSaved()
      }
    } else if (state.resourceId && sourceKey) {
      const resourceId = state.resourceId
      const result = await loadCanvasResource(resourceId)
      if (loadVersion !== routeLoadVersion) return
      await applyLoadedCanvasResource(resourceId, result)
      dashboardStore.markCanvasSaved()
      scheduleEditorChartRefresh(loadVersion)
    } else {
      await pauseCanvasStateWatch(() => {
        dashboardStore.canvasDataInit()
      })
    }
  } finally {
    if (loadVersion === routeLoadVersion) {
      dataInitState.value = true
      canvasStateReady = true
    }
  }
}

const pauseCanvasStateWatch = async (task: () => void | Promise<void>) => {
  applyingCanvasState = true
  try {
    await task()
    await nextTick()
  } finally {
    applyingCanvasState = false
  }
}

const buildDraftDashboardInfo = (draftInfo: any) => {
  const latestInfo = cloneDeep(dashboardStore.dashboardInfo) || {}
  return {
    ...latestInfo,
    ...(draftInfo || {}),
    id: latestInfo.id ?? draftInfo?.id,
    pid: latestInfo.pid ?? draftInfo?.pid,
    datasource: latestInfo.datasource ?? draftInfo?.datasource,
    dataState: latestInfo.dataState ?? draftInfo?.dataState,
    contentId: latestInfo.contentId ?? draftInfo?.contentId,
    canEdit: latestInfo.canEdit ?? draftInfo?.canEdit,
    canShare: latestInfo.canShare ?? draftInfo?.canShare,
  }
}

const restoreCanvasDraft = async (sourceKey: string) => {
  if (!canUseCanvasDraft(sourceKey)) return false
  const draft = loadDashboardCanvasDraft(sourceKey)
  if (!draft) return false
  await pauseCanvasStateWatch(() => {
    dashboardStore.setDashboardInfo(buildDraftDashboardInfo(draft.dashboardInfo))
    dashboardStore.setCanvasStyleData(cloneDeep(draft.canvasStyleData || {}))
    dashboardStore.setComponentData(cloneDeep(draft.componentData || []))
    dashboardStore.setCanvasViewInfo(cloneDeep(draft.canvasViewInfo || {}))
    dashboardStore.setCanvasEditingSourceKey(sourceKey)
  })
  dashboardStore.markCanvasChanged()
  return true
}

const persistCanvasDraft = () => {
  const sourceKey = dashboardStore.canvasEditingSourceKey
  if (!sourceKey || !canUseCanvasDraft(sourceKey) || !dashboardStore.hasUnsavedCanvasChanges) return
  saveDashboardCanvasDraft(sourceKey, {
    sourceKey,
    savedAt: Date.now(),
    dashboardInfo: cloneDeep(dashboardInfo.value),
    componentData: cloneDeep(componentData.value),
    canvasStyleData: cloneDeep(canvasStyleData.value),
    canvasViewInfo: cloneDeep(canvasViewInfo.value),
  })
}

const scheduleCanvasDraftSave = () => {
  if (draftSaveTimer) {
    window.clearTimeout(draftSaveTimer)
  }
  draftSaveTimer = window.setTimeout(() => {
    draftSaveTimer = null
    persistCanvasDraft()
  }, 300)
}

const handleBeforeUnload = (event: BeforeUnloadEvent) => {
  persistCanvasDraft()
  if (!dashboardStore.hasUnsavedCanvasChanges) return
  event.preventDefault()
  event.returnValue = ''
}

watch(
  () => ({
    dashboardInfo: dashboardInfo.value,
    componentData: componentData.value,
    canvasStyleData: canvasStyleData.value,
    canvasViewInfo: canvasViewInfo.value,
  }),
  () => {
    if (
      !canvasStateReady ||
      applyingCanvasState ||
      suppressCanvasStateChange > 0 ||
      !dashboardStore.canvasEditingSourceKey
    ) {
      return
    }
    dashboardStore.markCanvasChanged()
    scheduleCanvasDraftSave()
  },
  { deep: true, flush: 'sync' }
)

const addComponents = (componentType: string, views?: any, options: { openEditor?: boolean } = {}) => {
  const component = cloneDeep(findNewComponentFromList(componentType))
  if (!component) {
    return
  }
  component.x = findPositionX(component.sizeX)
  const defaultSizeY = component.sizeY
  if (views) {
    const viewList = Array.isArray(views) ? views : [views]
    viewList.forEach((view: any, index: number) => {
      const target = cloneDeep(view)
      delete target.chart.sourceType
      if (index > 0) {
        component.x = ((component.x + component.sizeX - 1) % baseMatrixCount.value.x) + 1
      }
      component.sizeY = defaultSizeY
      applyRecommendedChartComponentSize(component, target)
      addComponent(component, target)
    })
  } else {
    const added = addComponent(component)
    if (options.openEditor && added?.component === 'SQView') {
      nextTick(() => {
        // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
        dashboardEditorInnerRef.value?.openSqlEditor?.(added.id)
      })
    }
  }
}
const addComponent = (componentSource: any, viewInfo?: any) => {
  const component = cloneDeep(componentSource)
  if (component && dashboardEditorInnerRef.value) {
    component.id = guid()
    // add view
    if (component?.component === 'SQView') {
      const nextViewInfo = viewInfo ? cloneDeep(viewInfo) : createEmptyViewInfo(component.id)
      if (viewInfo) {
        nextViewInfo['sourceId'] = nextViewInfo['id']
      }
      nextViewInfo['id'] = component.id
      dashboardStore.addCanvasViewInfo(nextViewInfo)
    } else if (component.component === 'SQTab') {
      const subTabName = guid('tab')
      component.propValue[0].name = subTabName
      component.propValue[0].title = t('dashboard.new_tab')
      component.activeTabName = subTabName
    }
    component.y = maxYComponentCount() + 2
    // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
    dashboardEditorInnerRef.value.addItemToBox(component)
    return component
  }
  return null
}

const createEmptyViewInfo = (id: string) => ({
  id,
  sourceConfig: {
    sources: ['sql'],
    primarySource: 'sql',
    sql: {
      datasource: state.platformTemplateId ? null : state.datasource || datasourceContext.datasourceId,
      sql: '',
    },
    mcp: null,
  },
  sources: ['sql'],
  primarySource: 'sql',
  sql: '',
  datasource: state.platformTemplateId ? null : state.datasource || datasourceContext.datasourceId,
  data: {
    fields: [],
    data: [],
  },
  fields: [],
  status: 'success',
  dataState: 'ready',
  loadingProgress: 100,
  message: '',
  chart: {
    id,
    type: 'table',
    sourceType: 'table',
    title: t('dashboard.view'),
    columns: [],
    xAxis: [],
    yAxis: [],
    series: [],
  },
})

const maxYComponentCount = () => {
  if (componentData.value.length === 0) {
    return 1
  } else {
    return componentData.value
      .filter((item) => item['y'])
      .map((item) => item['y'] + item['sizeY']) // Calculate the y+sizeY of each element
      .reduce((max, current) => Math.max(max, current), 0)
  }
}

onMounted(async () => {
  window.addEventListener('beforeunload', handleBeforeUnload)
  await loadCanvasFromRoute()
})

watch(
  () => router.currentRoute.value.fullPath,
  () => {
    if (router.currentRoute.value.path === '/canvas') {
      loadCanvasFromRoute()
    }
  }
)

onBeforeUnmount(() => {
  persistCanvasDraft()
  cancelDashboardChartRefresh()
  if (draftSaveTimer) {
    window.clearTimeout(draftSaveTimer)
    draftSaveTimer = null
  }
  window.removeEventListener('beforeunload', handleBeforeUnload)
})

const baseParams = computed(() => {
  return {
    opt: state.opt,
    resourceId: state.resourceId,
    platformTemplate: Boolean(state.platformTemplateId),
    platformTemplateId: state.platformTemplateId,
    pid: state.routerPid,
    datasource: state.datasource,
    canUseChatHistory: !state.platformTemplateId,
  }
})
const findPositionX = (width: number) => {
  // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
  return dashboardEditorInnerRef.value.findPositionX(width)
}
</script>

<template>
  <div class="editor-content" :class="{ 'editor-content-fullscreen': fullscreenFlag }">
    <div class="editor-main">
      <Toolbar
        :base-params="baseParams"
        :find-position-x="findPositionX"
        @add-components="addComponents"
      ></Toolbar>
      <DashboardEditor
        v-if="dataInitState"
        ref="dashboardEditorInnerRef"
        :canvas-component-data="componentData"
        :canvas-view-info="canvasViewInfo"
        :platform-template="Boolean(state.platformTemplateId)"
      >
      </DashboardEditor>
    </div>
  </div>
</template>

<style scoped lang="less">
.editor-content {
  width: 100vw;
  height: 100vh;
  background: var(--workspace-panel-bg, #f6f9fd);
  overflow: hidden;
}

.editor-content-fullscreen {
  padding: 0 !important;
}
.editor-main {
  position: relative;
  background: var(--workspace-panel-bg, #f6f9fd);
  overflow: hidden;
  width: 100%;
  height: 100%;
}
</style>
