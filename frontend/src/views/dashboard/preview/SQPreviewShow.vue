<script setup lang="ts">
import icon_add_outlined from '@/assets/svg/icon_add_outlined.svg'
import icon_sidebar_outlined from '@/assets/svg/icon_sidebar_outlined.svg'
import { reactive, ref, toRefs, onBeforeMount, onBeforeUnmount, computed, watch, nextTick } from 'vue'
import { load_resource_prepare } from '@/views/dashboard/utils/canvasUtils'
import { dashboardApi } from '@/api/dashboard.ts'
import ResourceTree from '@/views/dashboard/common/ResourceTree.vue'
import SQPreview from '@/views/dashboard/preview/SQPreview.vue'
import SQPreviewHead from '@/views/dashboard/preview/SQPreviewHead.vue'
import EmptyBackground from '@/views/dashboard/common/EmptyBackground.vue'
import EmptyBackgroundSvg from '@/views/dashboard/common/EmptyBackgroundSvg.vue'
import { dashboardStoreWithOut } from '@/stores/dashboard/dashboard.ts'
import { useDatasourceContextStore } from '@/stores/datasourceContext'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { useEmitt, WORKSPACE_CONTEXT_CHANGE_EVENT } from '@/utils/useEmitt'
import { resolveBusinessDashboardLandingTarget } from '@/utils/dashboardLanding'
import { useUserStore } from '@/stores/user'
const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const dashboardStore = dashboardStoreWithOut()
const datasourceContext = useDatasourceContextStore()
const userStore = useUserStore()
const previewCanvasContainer = ref(null)
const dashboardPreview = ref(null)
const slideShow = ref(true)
const dataInitState = ref(true)
const state = reactive({
  canvasDataPreview: [] as any[],
  canvasStylePreview: {} as Record<string, any>,
  canvasViewInfoPreview: {} as Record<string, any>,
  dashboardInfo: {} as Record<string, any>,
})

const props = defineProps({
  showPosition: {
    required: false,
    type: String,
    default: 'preview',
  },
  noClose: {
    required: false,
    type: Boolean,
    default: false,
  },
  defaultMode: {
    required: false,
    type: Boolean,
    default: false,
  },
})

const { showPosition } = toRefs(props)

const resourceTreeRef = ref()
let dashboardLoadVersion = 0
const loadingDashboardId = ref<string | null>(null)
let dashboardLoadController: AbortController | null = null
let chartRefreshTimer: number | undefined
let chartRefreshController: AbortController | null = null
let chartRefreshRetryCount = 0
const CHART_CACHE_LOOKUP_CONCURRENCY = 6
const CHART_DATABASE_REFRESH_CONCURRENCY = 4
const CHART_CACHE_LOOKUP_START_DELAY_MS = 180
const CHART_TRANSIENT_RETRY_DELAY_MS = 4000
const CHART_TRANSIENT_MAX_RETRIES = 6
const DASHBOARD_MODE_DEFAULT = 'default'
const DASHBOARD_MODE_MY = 'my'

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

const hasTreeData = computed(() => {
  return resourceTreeRef.value?.hasData
})
const mounted = computed(() => {
  return resourceTreeRef.value?.mounted
})
const canCreateDashboard = computed(() => {
  return !props.defaultMode && resourceTreeRef.value?.canCreateDashboard === true
})
const routeDashboardId = computed(() => {
  const resourceId = route.query.resourceId || route.query.dashboardId
  return Array.isArray(resourceId) ? resourceId[0] : resourceId
})
const routeDashboardMode = computed(() => {
  const mode = Array.isArray(route.query.dashboardMode)
    ? route.query.dashboardMode[0]
    : route.query.dashboardMode
  return mode === DASHBOARD_MODE_DEFAULT ? DASHBOARD_MODE_DEFAULT : DASHBOARD_MODE_MY
})

const stateInit = () => {
  state.canvasDataPreview = []
  state.canvasStylePreview = {}
  state.canvasViewInfoPreview = {}
  state.dashboardInfo = {}
}
const resetPreviewState = () => {
  cancelDashboardWork()
  dashboardLoadVersion += 1
  loadingDashboardId.value = null
  dataInitState.value = true
  stateInit()
}
const resolveDashboardMode = (params?: any) =>
  props.defaultMode || params?.dashboardScope === DASHBOARD_MODE_DEFAULT
    ? DASHBOARD_MODE_DEFAULT
    : DASHBOARD_MODE_MY

const currentDashboardMode = () =>
  (state.dashboardInfo as any)?.dashboardMode ||
  (props.defaultMode ? DASHBOARD_MODE_DEFAULT : routeDashboardMode.value)

const sameDashboard = (id: unknown, mode: string) =>
  id &&
  String((state.dashboardInfo as any)?.id || '') === String(id) &&
  currentDashboardMode() === mode

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

function cancelDashboardLoad() {
  if (dashboardLoadController) {
    dashboardLoadController.abort()
    dashboardLoadController = null
  }
}

function cancelDashboardWork() {
  cancelDashboardChartRefresh()
  cancelDashboardLoad()
}

function collectDashboardCharts(items: any[], entries: Array<{ component: any; viewInfo: any }> = []) {
  if (!Array.isArray(items)) {
    return entries
  }
  items.forEach((item) => {
    if (item?.component === 'SQView') {
      entries.push({
        component: item,
        viewInfo: state.canvasViewInfoPreview?.[item.id],
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

function hasUsableChartSnapshot(viewInfo: any) {
  return hasChartSnapshot(viewInfo)
}

function hasUsableResultSnapshot(result: any) {
  const rows = result?.data
  return Array.isArray(rows) && rows.length > 0
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

function resultRefreshedAt(result: any) {
  const timestamp = Number(result?.refreshed_at || result?.cache_refreshed_at || 0)
  return Number.isFinite(timestamp) && timestamp > 0 ? timestamp : Date.now()
}

function canLookupChartCache(viewInfo: any) {
  return !!(viewInfo?.datasource && viewInfo?.sql?.trim())
}

function applyChartResult(viewInfo: any, result: any, keepLoadingWhenEmpty = false) {
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
  if (viewInfo.status === 'failed' && hasPreviousSnapshot) {
    viewInfo.data.fields = previousDataFields
    viewInfo.data.data = previousData
    viewInfo.fields = previousFields
    viewInfo.status = 'success'
    viewInfo.message = ''
    viewInfo.dataState = 'ready'
  } else {
    viewInfo.dataState = viewInfo.status === 'failed' ? 'failed' : 'ready'
    if (keepLoadingWhenEmpty && viewInfo.status !== 'failed' && !data.length && !hasPreviousSnapshot) {
      viewInfo.status = 'loading'
      viewInfo.message = ''
      viewInfo.dataState = 'loading'
      setChartLoadingProgress(viewInfo, 5)
      viewInfo.refreshState = ''
      return false
    }
    if (viewInfo.status !== 'failed') {
      markChartSnapshotRefreshed(viewInfo, resultRefreshedAt(result))
    }
  }
  viewInfo.loadingProgress = 100
  viewInfo.refreshState = ''
  return viewInfo.status !== 'failed' && data.length > 0
}

function isDashboardCacheMiss(result: any) {
  return result?.status === 'failed' && result?.error_type === 'dashboard_cache_miss'
}

function isDashboardQueryBusy(result: any) {
  return result?.status === 'failed' && result?.error_type === 'dashboard_query_busy'
}

function keepChartLoadingState(viewInfo: any) {
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
  viewInfo.refreshState = ''
}

function keepChartSnapshotState(viewInfo: any) {
  if (!viewInfo) {
    return
  }
  if (!viewInfo.data || typeof viewInfo.data !== 'object') {
    viewInfo.data = {}
  }
  viewInfo.data.data = Array.isArray(viewInfo.data.data) ? viewInfo.data.data : []
  viewInfo.data.fields = Array.isArray(viewInfo.data.fields) ? viewInfo.data.fields : []
  viewInfo.fields = Array.isArray(viewInfo.fields) ? viewInfo.fields : viewInfo.data.fields
  if (hasChartShape(viewInfo)) {
    viewInfo.status = 'success'
  } else if (viewInfo.status === 'loading' || viewInfo.status === 'failed') {
    viewInfo.status = 'success'
  }
  viewInfo.message = ''
  viewInfo.dataState = 'ready'
  viewInfo.loadingProgress = 100
  viewInfo.refreshState = ''
}

function keepChartSnapshotOrLoading(viewInfo: any) {
  if (hasUsableChartSnapshot(viewInfo)) {
    keepChartSnapshotState(viewInfo)
  } else {
    keepChartLoadingState(viewInfo)
  }
}

function failChartWithoutSnapshot(viewInfo: any, result?: any) {
  if (!viewInfo) {
    return
  }
  if (hasUsableChartSnapshot(viewInfo)) {
    keepChartSnapshotState(viewInfo)
    return
  }
  if (!viewInfo.data || typeof viewInfo.data !== 'object') {
    viewInfo.data = {}
  }
  viewInfo.data.data = Array.isArray(viewInfo.data.data) ? viewInfo.data.data : []
  viewInfo.data.fields = Array.isArray(viewInfo.data.fields) ? viewInfo.data.fields : []
  viewInfo.fields = Array.isArray(viewInfo.fields) ? viewInfo.fields : viewInfo.data.fields
  viewInfo.status = 'failed'
  viewInfo.message = result?.message || t('dashboard.chart_refresh_failed')
  viewInfo.dataState = 'failed'
  viewInfo.loadingProgress = 100
  viewInfo.refreshState = ''
}

function prepareChartDatabaseRefreshState(viewInfo: any) {
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
  viewInfo.refreshState = ''
  if (hasUsableChartSnapshot(viewInfo)) {
    viewInfo.status = 'success'
    viewInfo.dataState = 'ready'
    viewInfo.loadingProgress = 100
    return
  }
  viewInfo.status = 'loading'
  viewInfo.dataState = 'loading'
  setChartLoadingProgress(viewInfo, 0)
}

function prepareChartPreviewState(viewInfo: any) {
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
  viewInfo.refreshState = ''
  if (hasUsableChartSnapshot(viewInfo)) {
    viewInfo.status = 'success'
    viewInfo.dataState = 'ready'
    viewInfo.loadingProgress = 100
  } else {
    viewInfo.status = 'loading'
    viewInfo.dataState = 'loading'
    setChartLoadingProgress(viewInfo, 0, true)
  }
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
  const cachedResult = await dashboardApi.preview_sql(
    {
      ...chartSqlPayload(viewInfo),
      cache_only: true,
    },
    requestConfig
  )
  return cachedResult
}

async function previewChartSqlFromDatabase(
  viewInfo: any,
  requestConfig: any = { requestOptions: { silent: true } }
) {
  return dashboardApi.preview_sql(
    {
      ...chartSqlPayload(viewInfo),
      force_refresh: true,
    },
    requestConfig
  )
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

async function refreshDashboardCharts(loadVersion: number, controller: AbortController) {
  const allChartEntries = collectDashboardCharts(state.canvasDataPreview)
  allChartEntries.forEach((entry) => {
    const viewInfo = entry.viewInfo
    if (!viewInfo) {
      return
    }
    if (!viewInfo.datasource) {
      failChartWithoutSnapshot(viewInfo, { message: t('dashboard.sql_editor_no_datasource') })
      return
    }
    if (!viewInfo.sql?.trim()) {
      failChartWithoutSnapshot(viewInfo, { message: t('dashboard.sql_editor_empty_sql') })
    }
  })
  const chartEntries = allChartEntries.filter((entry) => canLookupChartCache(entry.viewInfo))
  const total = chartEntries.length
  if (!total) {
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
    count = total,
    startProgress = 0,
    endProgress = 95
  ) => {
    const boundedCount = Math.max(1, count)
    const progressRatio = Math.max(0, Math.min(1, finished / boundedCount))
    const progress = Math.min(95, Math.round(startProgress + (endProgress - startProgress) * progressRatio))
    entries.forEach((entry) => {
      if (entry.viewInfo?.dataState === 'loading') {
        setChartLoadingProgress(entry.viewInfo, progress)
      }
    })
  }
  try {
    await runChartQueue(chartEntries, CHART_CACHE_LOOKUP_CONCURRENCY, async (entry) => {
      const { viewInfo } = entry
      try {
        if (loadVersion !== dashboardLoadVersion || controller.signal.aborted) {
          return
        }
        const cachedResult = await previewChartSqlCacheOnly(viewInfo, requestConfig)
        if (loadVersion !== dashboardLoadVersion || controller.signal.aborted) {
          return
        }
        if (
          isDashboardCacheMiss(cachedResult) ||
          cachedResult?.status === 'failed' ||
          !hasUsableResultSnapshot(cachedResult)
        ) {
          databaseRefreshEntries.push(entry)
        } else {
          applyChartResult(viewInfo, cachedResult)
        }
      } catch (error: any) {
        if (isAbortError(error) || controller.signal.aborted) {
          return
        }
        if (loadVersion === dashboardLoadVersion) {
          databaseRefreshEntries.push(entry)
        }
      } finally {
        cacheFinished += 1
        updateProgress(chartEntries, cacheFinished, total, 5, 45)
      }
    })

    const databaseTotal = databaseRefreshEntries.length
    if (!databaseTotal || loadVersion !== dashboardLoadVersion || controller.signal.aborted) {
      return
    }
    databaseRefreshEntries.forEach((entry) => prepareChartDatabaseRefreshState(entry.viewInfo))
    await runChartQueue(databaseRefreshEntries, CHART_DATABASE_REFRESH_CONCURRENCY, async (entry) => {
      const { viewInfo } = entry
      try {
        if (loadVersion !== dashboardLoadVersion || controller.signal.aborted) {
          return
        }
        const result = await previewChartSqlFromDatabase(viewInfo, requestConfig)
        if (loadVersion !== dashboardLoadVersion || controller.signal.aborted) {
          return
        }
        if (result?.status === 'failed') {
          if (isDashboardQueryBusy(result)) {
            keepChartSnapshotOrLoading(viewInfo)
            if (!hasUsableChartSnapshot(viewInfo)) {
              transientPendingCount += 1
            }
          } else {
            keepChartSnapshotOrLoading(viewInfo)
            if (!hasUsableChartSnapshot(viewInfo)) {
              transientPendingCount += 1
            }
          }
        } else {
          const usable = applyChartResult(viewInfo, result, true)
          if (!usable && !hasUsableChartSnapshot(viewInfo)) {
            transientPendingCount += 1
          }
        }
      } catch (error: any) {
        if (isAbortError(error) || controller.signal.aborted) {
          return
        }
        if (loadVersion === dashboardLoadVersion) {
          keepChartSnapshotOrLoading(viewInfo)
          if (!hasUsableChartSnapshot(viewInfo)) {
            transientPendingCount += 1
          }
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
      loadVersion === dashboardLoadVersion &&
      !controller.signal.aborted &&
      chartRefreshRetryCount < CHART_TRANSIENT_MAX_RETRIES
    ) {
      chartRefreshRetryCount += 1
      scheduleDashboardChartRefresh(loadVersion, CHART_TRANSIENT_RETRY_DELAY_MS)
    }
  }
}

function scheduleDashboardChartRefresh(loadVersion: number, delay = CHART_CACHE_LOOKUP_START_DELAY_MS) {
  cancelDashboardChartRefresh()
  const controller = new AbortController()
  chartRefreshController = controller
  chartRefreshTimer = window.setTimeout(() => {
    chartRefreshTimer = undefined
    if (loadVersion !== dashboardLoadVersion || controller.signal.aborted) {
      return
    }
    void refreshDashboardCharts(loadVersion, controller)
  }, delay)
}

const loadCanvasData = (params: any) => {
  const resourceId = params?.id ? String(params.id) : ''
  const dashboardMode = resolveDashboardMode(params)
  const loadingKey = `${dashboardMode}:${resourceId}`
  const forceReload = params?.forceReload === true
  if (
    !resourceId ||
    (!forceReload && sameDashboard(resourceId, dashboardMode)) ||
    loadingDashboardId.value === loadingKey
  ) return
  cancelDashboardWork()
  chartRefreshRetryCount = 0
  const loadVersion = ++dashboardLoadVersion
  const loadController = new AbortController()
  dashboardLoadController = loadController
  loadingDashboardId.value = loadingKey
  dataInitState.value = false
  load_resource_prepare(
    { id: resourceId },
    async function ({ dashboardInfo, canvasDataResult, canvasStyleResult, canvasViewInfoPreview }) {
      if (loadVersion !== dashboardLoadVersion) return
      if (dashboardLoadController === loadController) {
        dashboardLoadController = null
      }
      if (!dashboardInfo?.id) {
        stateInit()
        loadingDashboardId.value = null
        dataInitState.value = true
        if (showPosition.value === 'preview') {
          const target = await resolveBusinessDashboardLandingTarget(userStore)
          if (!isCurrentRouteTarget(target)) {
            await router.replace(target)
          }
        }
        return
      }
      if (
        dashboardInfo?.datasource &&
        String(datasourceContext.datasourceId || '') !== String(dashboardInfo.datasource)
      ) {
        await datasourceContext.activateDatasourceById(dashboardInfo.datasource, false)
        if (loadVersion !== dashboardLoadVersion) return
      }
      state.canvasDataPreview = canvasDataResult
      state.canvasStylePreview = canvasStyleResult
      state.canvasViewInfoPreview = canvasViewInfoPreview
      collectDashboardCharts(canvasDataResult).forEach((entry) => prepareChartPreviewState(entry.viewInfo))
      state.dashboardInfo = {
        ...dashboardInfo,
        dashboardMode,
      }
      loadingDashboardId.value = null
      dataInitState.value = true
      scheduleDashboardChartRefresh(loadVersion)
    },
    {
      defaultMode: dashboardMode === DASHBOARD_MODE_DEFAULT,
      includeData: false,
      requestConfig: {
        signal: loadController.signal,
        requestOptions: { silent: true },
      },
    }
  )
}

const isCurrentRouteTarget = (target: any) => {
  if (typeof target === 'string') {
    return target === route.fullPath || target === route.path
  }
  if (!target?.path || target.path !== route.path) return false
  const targetResourceId = target.query?.resourceId
  if (!targetResourceId) return true
  return String(targetResourceId) === String(route.query.resourceId || '')
}
const getPreviewStateInfo = () => {
  return state
}

const reload = (params: any) => {
  loadCanvasData({
    ...params,
    forceReload: true,
  })
}

const reloadCurrentDashboard = () => {
  if (!state.dashboardInfo?.id) return
  const resourceId = String(state.dashboardInfo.id)
  state.dashboardInfo = {}
  loadCanvasData({
    id: resourceId,
    dashboardScope: currentDashboardMode(),
    forceReload: true,
  })
}

const resourceNodeClick = (prams: any) => {
  loadCanvasData(prams)
}

const previewShowFlag = computed(() => !!state.dashboardInfo?.name)
onBeforeMount(() => {
  if (showPosition.value === 'preview') {
    dashboardStore.canvasDataInit()
  }
})
onBeforeUnmount(() => {
  cancelDashboardWork()
})
watch(
  () => [routeDashboardId.value, routeDashboardMode.value],
  ([resourceId, dashboardMode]) => {
    if (!props.defaultMode && resourceId) {
      loadCanvasData({ id: resourceId, dashboardScope: dashboardMode })
    }
  },
  { immediate: true }
)
useEmitt({
  name: WORKSPACE_CONTEXT_CHANGE_EVENT,
  callback: () => {
    resetPreviewState()
  },
})
const sideTreeStatus = ref(true)

function toggleSidebar() {
  sideTreeStatus.value = !sideTreeStatus.value
}

function createDashboard() {
  resourceTreeRef.value?.createNewObject()
}
defineExpose({
  getPreviewStateInfo,
})
</script>

<template>
  <div class="dv-preview dv-teleport-query no-padding">
    <div v-if="!sideTreeStatus" class="collapsed-dashboard-actions">
      <el-icon class="floating-icon-btn" size="18" @click="toggleSidebar">
        <icon_sidebar_outlined></icon_sidebar_outlined>
      </el-icon>
      <el-icon
        v-if="canCreateDashboard"
        class="floating-icon-btn create-icon-btn"
        size="18"
        @click="createDashboard"
      >
        <icon_add_outlined></icon_add_outlined>
      </el-icon>
    </div>
    <el-aside
      ref="node"
      class="resource-area"
      :class="{ 'close-side': !slideShow, retract: !sideTreeStatus }"
    >
      <resource-tree
        v-show="slideShow"
        ref="resourceTreeRef"
        :cur-canvas-type="'dashboard'"
        :show-position="showPosition"
        :default-mode="defaultMode"
        @node-click="resourceNodeClick"
        @delete-cur-resource="stateInit"
        @toggle-sidebar="toggleSidebar"
      />
    </el-aside>
    <section
      class="preview-area"
      :class="{
        'is-empty': !previewShowFlag,
        'sidebar-collapsed': !sideTreeStatus,
        'sidebar-collapsed-with-create': !sideTreeStatus && canCreateDashboard,
      }"
    >
      <div class="preview-stage">
        <SQPreviewHead
          :dashboard-info="previewShowFlag ? state.dashboardInfo : {}"
          :component-data="state.canvasDataPreview"
          :canvas-view-info="state.canvasViewInfoPreview"
          @reload="reload"
        />
        <div
          id="sq-preview-content"
          ref="previewCanvasContainer"
          class="content"
          :class="{ 'content--empty': !previewShowFlag }"
        >
          <SQPreview
            v-if="previewShowFlag && state.canvasStylePreview"
            ref="dashboardPreview"
            :dashboard-info="state.dashboardInfo"
            :component-data="state.canvasDataPreview"
            :canvas-style-data="state.canvasStylePreview"
            :canvas-view-info="state.canvasViewInfoPreview"
            :show-position="showPosition"
            @chart-moved="reloadCurrentDashboard"
          ></SQPreview>
          <EmptyBackgroundSvg
            v-else-if="hasTreeData && mounted"
            :description="
              defaultMode
                ? t('dashboard.select_default_dashboard_tips')
                : t('dashboard.select_dashboard_tips')
            "
          />
          <EmptyBackground
            v-else-if="mounted"
            :description="
              defaultMode ? t('dashboard.no_default_dashboard') : t('dashboard.no_dashboard_info')
            "
            img-type="none"
          />
        </div>
      </div>
    </section>
  </div>
</template>

<style lang="less">
.dv-preview {
  --dashboard-preview-card-bg: #ffffff;
  --dashboard-preview-canvas-bg: #fbfbff;
  --dashboard-preview-sidebar-bg: #f3f7fc;

  width: 100%;
  height: 100%;
  overflow: hidden;
  display: flex;
  background: var(--dashboard-preview-sidebar-bg);
  color: var(--workspace-text-primary, #1f2329);
  position: relative;
  font-family: 'PingFang SC', 'Microsoft YaHei', 'Helvetica Neue', Arial, sans-serif;

  .resource-area {
    --ed-aside-width: 280px;

    position: relative;
    height: 100%;
    padding: 0;
    background: var(--dashboard-preview-sidebar-bg);
    color: var(--workspace-text-primary, #1f2329);
    border-right: 1px solid var(--workspace-border, var(--theme-shell-border));
    z-index: 1;
    overflow: hidden;

    &.retract {
      display: none;
    }
  }

  .preview-area {
    flex: 1;
    display: flex;
    min-width: 0;
    min-height: 0;
    overflow-x: hidden;
    overflow-y: auto;
    position: relative;
    background: var(--dashboard-preview-canvas-bg);

    .preview-stage {
      display: flex;
      flex: 1;
      min-width: 0;
      min-height: 0;
      flex-direction: column;
      background: var(--dashboard-preview-canvas-bg);
    }

    .content {
      position: relative;
      display: flex;
      flex: 1;
      min-height: 0;
      width: 100%;
      overflow-x: hidden;
      overflow-y: auto;
      padding: 0;
      align-items: stretch;
      background: var(--dashboard-preview-canvas-bg);

      &.content--empty {
        align-items: center;
        justify-content: center;
      }
    }
  }

  .preview-area .preview-stage > .preview-head {
    position: relative;
    z-index: 2;
    background: var(--dashboard-preview-canvas-bg);
    border-bottom: 0;
  }
}

.preview-area.sidebar-collapsed {
  .preview-head {
    padding-left: 58px;
  }

  &.sidebar-collapsed-with-create .preview-head {
    padding-left: 94px;
  }
}

.preview-area.is-empty {
  .preview-stage {
    min-height: 0;
  }

  .content {
    min-height: 0;
  }
}

.preview-area .content.content--empty {
  :deep(.empty-info),
  :deep(.ed-empty) {
    width: 100%;
    height: 100%;
    padding-top: 0;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    background: var(--dashboard-preview-canvas-bg);
  }

  :deep(.ed-empty__description) {
    color: var(--workspace-text-secondary, #66758f);
  }
}

.collapsed-dashboard-actions {
  position: absolute;
  top: 14px;
  left: 14px;
  z-index: 199;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.floating-icon-btn {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  cursor: pointer;
  color: var(--workspace-text-primary, var(--theme-text-primary));
  transition:
    background-color 0.18s ease,
    color 0.18s ease;

  &:hover {
    background: var(--workspace-control-hover-bg, var(--theme-hover-bg));
  }

  &.create-icon-btn {
    color: var(--ed-color-primary, #2f6bff);

    &:hover {
      background: var(--workspace-primary-soft-bg, rgba(47, 107, 255, 0.1));
      color: var(--ed-color-primary, #2f6bff);
    }
  }

  svg,
  :deep(svg) {
    color: inherit;
  }

  :deep(svg path) {
    fill: currentColor !important;
  }
}

.close-side {
  width: 0 !important;
  padding: 0 !important;
}

.flexible-button-area {
  position: absolute;
  height: 60px;
  width: 16px;
  left: 0;
  top: calc(50% - 30px);
  background-color: var(--dashboard-preview-card-bg, #ffffff);
  border-radius: 0 8px 8px 0;
  cursor: pointer;
  z-index: 10;
  display: flex;
  align-items: center;
  border-top: 1px solid var(--workspace-border-soft, #eff4fa);
  border-right: 1px solid var(--workspace-border-soft, #eff4fa);
  border-bottom: 1px solid var(--workspace-border-soft, #eff4fa);
}
</style>
