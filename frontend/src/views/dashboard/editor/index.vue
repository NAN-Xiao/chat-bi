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
import {
  createPermissionDeniedChartRegistry,
  dashboardChartFailureResultFromError,
  dashboardCacheRefreshDisposition,
  nextDashboardChartRetryDelayMs,
  isPermissionDeniedRefreshResult as isPermissionDeniedResult,
  shouldRetryDashboardChartFailure,
} from '@/views/dashboard/utils/dashboardPermissionRefresh'
import {
  applyDashboardDateFilterCapability,
  beginDashboardChartRequest,
  buildDashboardDateFilterRequestForView,
  canShowDashboardDateFilter,
  getOrCreateDashboardDateFilterState,
  isDashboardChartRequestCurrent,
} from '@/views/dashboard/utils/dashboardDateFilter.ts'
import {
  resolveOrdinaryDashboardMode,
  type OrdinaryDashboardMode,
} from '@/views/dashboard/utils/dashboardRouteMode'
import { createRouteLoadLifecycle } from '@/views/dashboard/editor/routeLoadLifecycle'
import { consumeCanvasRouteHandoff } from '@/views/dashboard/editor/canvasRouteHandoff'
import {
  hasDashboardChartSnapshot,
  prepareDashboardChartRefreshState,
} from '@/views/dashboard/utils/dashboardChartLifecycle'

const { t } = useI18n()
const dashboardStore = dashboardStoreWithOut()
const datasourceContext = useDatasourceContextStore()
const { dashboardInfo, componentData, canvasStyleData, canvasViewInfo, fullscreenFlag, baseMatrixCount } =
  storeToRefs(dashboardStore)

function firstQueryValue(value: unknown) {
  if (Array.isArray(value)) {
    return value[0] ? String(value[0]) : null
  }
  return value ? String(value) : null
}

const initialPlatformTemplateId = firstQueryValue(router.currentRoute.value.query.platformTemplateId)
const initialResourceId = firstQueryValue(router.currentRoute.value.query.resourceId)
const initialRouteSourceKey = initialPlatformTemplateId
  ? getPlatformTemplateCanvasSourceKey(initialPlatformTemplateId)
  : getDashboardCanvasSourceKey(initialResourceId)
const initialCanvasRouteHandoff = consumeCanvasRouteHandoff(initialRouteSourceKey)
if (initialCanvasRouteHandoff) {
  dashboardStore.setDashboardInfo({
    ...initialCanvasRouteHandoff.dashboardInfo,
    ...(initialPlatformTemplateId ? { canEdit: true, canShare: false } : {}),
  })
  dashboardStore.setCanvasStyleData(initialCanvasRouteHandoff.canvasStyleResult || {})
  dashboardStore.setComponentData(initialCanvasRouteHandoff.canvasDataResult || [])
  dashboardStore.setCanvasViewInfo(initialCanvasRouteHandoff.canvasViewInfoPreview || {})
  dashboardStore.setCanvasEditingSourceKey(initialCanvasRouteHandoff.sourceKey)
  dashboardStore.markCanvasSaved()
}

const dataInitState = ref(false)
if (initialCanvasRouteHandoff) {
  dataInitState.value = true
}
const state = reactive({
  routerPid: null as string | null,
  resourceId: initialResourceId,
  platformTemplateId: initialPlatformTemplateId,
  opt: null as string | null,
  datasource: null as number | string | null | undefined,
  dashboardMode: resolveOrdinaryDashboardMode(
    router.currentRoute.value.query.dashboardMode
  ) as OrdinaryDashboardMode,
})

const dashboardEditorInnerRef = ref(null)
let canvasStateReady = Boolean(initialCanvasRouteHandoff)
let prefetchedRouteSourceKey = initialCanvasRouteHandoff?.sourceKey || null
let applyingCanvasState = false
let suppressCanvasStateChange = 0
let draftSaveTimer: number | null = null
const routeLoadLifecycle = createRouteLoadLifecycle()
let chartRefreshTimer: number | undefined
let chartRefreshController: AbortController | null = null
let chartRefreshRetryCount = 0

const CHART_CACHE_LOOKUP_CONCURRENCY = 6
const CHART_DATABASE_REFRESH_CONCURRENCY = 4
const CHART_CACHE_LOOKUP_START_DELAY_MS = 160
const CHART_TRANSIENT_MAX_RETRIES = 3
const permissionDeniedCharts = createPermissionDeniedChartRegistry()

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

function hasChartShape(viewInfo: any) {
  return (
    hasDashboardChartSnapshot(viewInfo) ||
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

function normalizePermissionDeniedChart(viewInfo: any) {
  if (!viewInfo) {
    return
  }
  if (!viewInfo.data || typeof viewInfo.data !== 'object') {
    viewInfo.data = {}
  }
  viewInfo.data.data = []
  viewInfo.data.fields = []
  viewInfo.fields = []
  viewInfo.status = 'failed'
  viewInfo.message = viewInfo.message || '没有查看权限'
  viewInfo.error_type = 'permission_denied'
  viewInfo.dataState = 'failed'
  viewInfo.loadingProgress = 100
  viewInfo.refreshState = ''
}

function chartSqlPayload(viewInfo: any) {
  const dateFilterState = canShowDashboardDateFilter(viewInfo.dateFilterCapability)
    ? getOrCreateDashboardDateFilterState(viewInfo, viewInfo.dateFilterCapability)
    : null
  return {
    datasource: viewInfo.datasource,
    sql: viewInfo.sql.trim(),
    pivot: viewInfo.pivot?.enabled === true ? viewInfo.pivot : undefined,
    date_filter: buildDashboardDateFilterRequestForView(viewInfo, dateFilterState?.appliedRange),
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
  if (!viewInfo) {
    return
  }
  if (isPermissionDeniedResult(viewInfo)) {
    normalizePermissionDeniedChart(viewInfo)
    return
  }
  const canRefreshChart = isMixedChart(viewInfo) ? canRefreshMixedChart(viewInfo) : Boolean(viewInfo.sql?.trim())
  if (!canRefreshChart) {
    return
  }
  prepareDashboardChartRefreshState(viewInfo, 'waiting')
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
  applyDashboardDateFilterCapability(viewInfo, result)
  if (!viewInfo) {
    return false
  }
  const fields = getResultFields(result)
  const data = Array.isArray(result?.data) ? result.data : []
  const previousData = Array.isArray(viewInfo?.data?.data) ? [...viewInfo.data.data] : []
  const previousDataFields = Array.isArray(viewInfo?.data?.fields) ? [...viewInfo.data.fields] : []
  const previousFields = Array.isArray(viewInfo?.fields) ? [...viewInfo.fields] : []
  const hasPreviousSnapshot = hasDashboardChartSnapshot(viewInfo)
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

async function runChartQueue<T extends { component: any; viewInfo: any }>(
  entries: T[],
  concurrency: number,
  worker: (entry: T) => Promise<void>
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
    if (!routeLoadLifecycle.isCurrent(loadVersion) || controller.signal.aborted) {
      return
    }
    void refreshEditorCharts(loadVersion, controller)
  }, delay)
}

async function refreshEditorCharts(loadVersion: number, controller: AbortController) {
  const chartEntries = collectDashboardCharts(componentData.value)
    .filter(
      (entry) =>
        !permissionDeniedCharts.has(entry) &&
        Boolean(
          isMixedChart(entry.viewInfo)
            ? canRefreshMixedChart(entry.viewInfo)
            : !isExternalSnapshotChart(entry.viewInfo) &&
              entry.viewInfo?.datasource &&
              entry.viewInfo?.sql?.trim()
        )
    )
    .flatMap((entry) => {
      const requestVersion = beginDashboardChartRequest(entry.viewInfo, 'background')
      return requestVersion === null ? [] : [{ ...entry, requestVersion }]
    })
  if (!chartEntries.length) {
    return
  }
  await nextTick()

  let cacheFinished = 0
  let databaseFinished = 0
  let transientPendingCount = 0
  const databaseRefreshEntries: Array<{ component: any; viewInfo: any; requestVersion: number }> = []
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
        if (
          entry.viewInfo?.dataState === 'loading'
          && isDashboardChartRequestCurrent(entry.viewInfo, entry.requestVersion)
        ) {
          setChartLoadingProgress(entry.viewInfo, progress)
        }
      })
    })
  }
  try {
    withAutoChartUpdate(() => {
      chartEntries.forEach((entry) => {
        if (
          isDashboardChartRequestCurrent(entry.viewInfo, entry.requestVersion)
          && !hasDashboardChartSnapshot(entry.viewInfo)
        ) {
          keepChartLoadingState(entry.viewInfo, 'waiting')
        }
      })
    })
    await runChartQueue(chartEntries, CHART_CACHE_LOOKUP_CONCURRENCY, async (entry) => {
      const { viewInfo, requestVersion } = entry
      try {
        if (
          !routeLoadLifecycle.isCurrent(loadVersion)
          || controller.signal.aborted
          || !isDashboardChartRequestCurrent(viewInfo, requestVersion)
        ) {
          return
        }
        const cachedResult = await previewChartSqlCacheOnly(viewInfo, requestConfig)
        if (
          !routeLoadLifecycle.isCurrent(loadVersion)
          || controller.signal.aborted
          || !isDashboardChartRequestCurrent(viewInfo, requestVersion)
        ) {
          return
        }
        const cacheDisposition = dashboardCacheRefreshDisposition(
          cachedResult,
          hasUsableResultSnapshot(cachedResult)
        )
        if (cacheDisposition === 'permission_denied') {
          permissionDeniedCharts.mark(entry)
          withAutoChartUpdate(() => applyChartResult(viewInfo, cachedResult))
        } else if (cacheDisposition === 'refresh_database') {
          if (isMixedChart(viewInfo) || !hasDashboardChartSnapshot(viewInfo)) {
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
        if (
          routeLoadLifecycle.isCurrent(loadVersion)
          && isDashboardChartRequestCurrent(viewInfo, requestVersion)
          && (isMixedChart(viewInfo) || !hasDashboardChartSnapshot(viewInfo))
        ) {
          databaseRefreshEntries.push(entry)
        }
      } finally {
        cacheFinished += 1
        updateProgress(chartEntries, cacheFinished, chartEntries.length, 5, 45)
      }
    })

    const databaseTotal = databaseRefreshEntries.length
    if (!databaseTotal || !routeLoadLifecycle.isCurrent(loadVersion) || controller.signal.aborted) {
      return
    }
    withAutoChartUpdate(() => {
      databaseRefreshEntries.forEach((entry) => {
        if (isDashboardChartRequestCurrent(entry.viewInfo, entry.requestVersion)) {
          prepareDashboardChartRefreshState(entry.viewInfo, 'loading')
        }
      })
    })
    await runChartQueue(databaseRefreshEntries, CHART_DATABASE_REFRESH_CONCURRENCY, async (entry) => {
      const { viewInfo, requestVersion } = entry
      try {
        if (
          !routeLoadLifecycle.isCurrent(loadVersion)
          || controller.signal.aborted
          || !isDashboardChartRequestCurrent(viewInfo, requestVersion)
        ) {
          return
        }
        const result = await previewChartSqlFromDatabase(viewInfo, requestConfig)
        if (
          !routeLoadLifecycle.isCurrent(loadVersion)
          || controller.signal.aborted
          || !isDashboardChartRequestCurrent(viewInfo, requestVersion)
        ) {
          return
        }
        withAutoChartUpdate(() => {
          if (result?.status === 'failed') {
            if (isPermissionDeniedResult(result)) {
              permissionDeniedCharts.mark(entry)
              applyChartResult(viewInfo, result)
            } else {
              if (shouldRetryDashboardChartFailure(result, hasDashboardChartSnapshot(viewInfo))) {
                keepChartSnapshotOrLoading(viewInfo)
                transientPendingCount += 1
              } else {
                applyChartResult(viewInfo, result)
              }
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
        if (
          routeLoadLifecycle.isCurrent(loadVersion)
          && isDashboardChartRequestCurrent(viewInfo, requestVersion)
        ) {
          withAutoChartUpdate(() => {
            const failureResult = dashboardChartFailureResultFromError(error)
            if (shouldRetryDashboardChartFailure(failureResult, hasDashboardChartSnapshot(viewInfo))) {
              keepChartSnapshotOrLoading(viewInfo)
              transientPendingCount += 1
            } else {
              applyChartResult(viewInfo, failureResult)
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
      routeLoadLifecycle.isCurrent(loadVersion) &&
      !controller.signal.aborted &&
      chartRefreshRetryCount < CHART_TRANSIENT_MAX_RETRIES
    ) {
      const retryDelay = nextDashboardChartRetryDelayMs(chartRefreshRetryCount)
      if (retryDelay !== null) {
        chartRefreshRetryCount += 1
        scheduleEditorChartRefresh(loadVersion, retryDelay)
      }
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
  state.dashboardMode = resolveOrdinaryDashboardMode(query.dashboardMode)
}

const applyLoadedCanvasResource = async (
  resourceId: string | number,
  result: any,
  loadVersion: number,
  sourceKeyOverride?: string | null
) => {
  if (!routeLoadLifecycle.isCurrent(loadVersion)) {
    return false
  }
  if (
    result?.dashboardInfo?.datasource &&
    String(datasourceContext.datasourceId || '') !== String(result.dashboardInfo.datasource)
  ) {
    await datasourceContext.activateDatasourceById(result.dashboardInfo.datasource, false)
  }
  if (!routeLoadLifecycle.isCurrent(loadVersion)) {
    return false
  }
  await pauseCanvasStateWatch(() => {
    if (!routeLoadLifecycle.isCurrent(loadVersion)) return
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
  return routeLoadLifecycle.isCurrent(loadVersion)
}

const resetCanvasAfterLoadFailure = async (loadVersion: number) => {
  if (!routeLoadLifecycle.isCurrent(loadVersion)) return false
  await pauseCanvasStateWatch(() => {
    if (!routeLoadLifecycle.isCurrent(loadVersion)) return
    dashboardStore.canvasDataInit()
  })
  return routeLoadLifecycle.isCurrent(loadVersion)
}

const loadCanvasFromRoute = async () => {
  const loadVersion = routeLoadLifecycle.begin()
  let routeStateApplied = false
  persistCanvasDraft()
  cancelDashboardChartRefresh()
  permissionDeniedCharts.reset()
  chartRefreshRetryCount = 0
  canvasStateReady = false
  syncRouteState()

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
    dataInitState.value = true
    canvasStateReady = true
    return
  }

  const keepPrefetchedCanvasVisible = prefetchedRouteSourceKey === sourceKey
  prefetchedRouteSourceKey = null
  if (keepPrefetchedCanvasVisible) {
    dataInitState.value = true
  } else {
    dataInitState.value = false
  }
  try {
    if (!state.platformTemplateId) {
      await datasourceContext.loadDatasources()
      if (!routeLoadLifecycle.isCurrent(loadVersion)) return
    }
    if (state.platformTemplateId && sourceKey) {
      const templateId = state.platformTemplateId
      const result = await loadPlatformTemplateResource(templateId)
      if (!routeLoadLifecycle.isCurrent(loadVersion)) return
      if (!result?.dashboardInfo?.id) {
        routeStateApplied = await resetCanvasAfterLoadFailure(loadVersion)
        return
      }
      const applied = await applyLoadedCanvasResource(templateId, result, loadVersion, sourceKey)
      if (!applied) return
      dashboardStore.updateDashboardInfo({
        canEdit: true,
        canShare: false,
      })
      dashboardStore.markCanvasSaved()
      routeStateApplied = true
    } else if (state.opt === 'create') {
      const createSourceKey = getCreateCanvasSourceKey(state.datasource, state.routerPid)
      await pauseCanvasStateWatch(() => {
        if (!routeLoadLifecycle.isCurrent(loadVersion)) return
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
      if (!routeLoadLifecycle.isCurrent(loadVersion)) return
      const restored = await restoreCanvasDraft(createSourceKey, loadVersion)
      if (!routeLoadLifecycle.isCurrent(loadVersion)) return
      if (!restored) {
        dashboardStore.markCanvasSaved()
      }
      routeStateApplied = true
    } else if (state.resourceId && sourceKey) {
      const resourceId = state.resourceId
      const result = await loadCanvasResource(resourceId)
      if (!routeLoadLifecycle.isCurrent(loadVersion)) return
      if (!result?.dashboardInfo?.id) {
        routeStateApplied = await resetCanvasAfterLoadFailure(loadVersion)
        return
      }
      const applied = await applyLoadedCanvasResource(resourceId, result, loadVersion)
      if (!applied) return
      dashboardStore.markCanvasSaved()
      scheduleEditorChartRefresh(loadVersion)
      routeStateApplied = true
    } else {
      routeStateApplied = await resetCanvasAfterLoadFailure(loadVersion)
    }
  } catch (error) {
    if (!routeLoadLifecycle.isCurrent(loadVersion)) return
    if (!isAbortError(error)) {
      console.error('load_canvas_from_route', error)
    }
    routeStateApplied = await resetCanvasAfterLoadFailure(loadVersion)
  } finally {
    if (routeLoadLifecycle.isCurrent(loadVersion) && routeStateApplied) {
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

const restoreCanvasDraft = async (sourceKey: string, loadVersion: number) => {
  if (!canUseCanvasDraft(sourceKey)) return false
  if (!routeLoadLifecycle.isCurrent(loadVersion)) return false
  const draft = loadDashboardCanvasDraft(sourceKey)
  if (!draft) return false
  await pauseCanvasStateWatch(() => {
    if (!routeLoadLifecycle.isCurrent(loadVersion)) return
    dashboardStore.setDashboardInfo(buildDraftDashboardInfo(draft.dashboardInfo))
    dashboardStore.setCanvasStyleData(cloneDeep(draft.canvasStyleData || {}))
    dashboardStore.setComponentData(cloneDeep(draft.componentData || []))
    dashboardStore.setCanvasViewInfo(cloneDeep(draft.canvasViewInfo || {}))
    dashboardStore.setCanvasEditingSourceKey(sourceKey)
  })
  if (!routeLoadLifecycle.isCurrent(loadVersion)) return false
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
  routeLoadLifecycle.dispose()
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
    dashboardMode: state.dashboardMode,
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
    <div class="editor-main" :aria-busy="!dataInitState">
      <template v-if="dataInitState">
        <Toolbar
          :base-params="baseParams"
          :find-position-x="findPositionX"
          @add-components="addComponents"
        ></Toolbar>
        <DashboardEditor
          ref="dashboardEditorInnerRef"
          :dashboard-info="dashboardInfo"
          :canvas-component-data="componentData"
          :canvas-view-info="canvasViewInfo"
          :can-edit-sql="dashboardInfo.canEdit !== false"
          :platform-template="Boolean(state.platformTemplateId)"
        >
        </DashboardEditor>
      </template>
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
