<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessage, ElMessageBox } from 'element-plus-secondary'
import { Plus } from '@element-plus/icons-vue'
import { useRoute } from 'vue-router'
import { roiCustomErrorRequestConfig, roiDashboardApi } from '@/api/roiDashboard'
import { useRoiDashboardStore } from '@/stores/roiDashboard'
import { useEmitt, WORKSPACE_CONTEXT_CHANGE_EVENT } from '@/utils/useEmitt'
import RoiChartGrid from './RoiChartGrid.vue'
import RoiSqlEditor from './RoiSqlEditor.vue'
import type { RoiChart, RoiChartEditorState, RoiDateRange, RoiLayoutSpan } from './types'
import {
  buildRoiChartOrderItems,
  buildRoiChartPreviewRequest,
  defaultRoiDateRange,
  hasRoiDateRangePlaceholders,
  canManageRoiChart,
  mergeReorderedRoiCharts,
  replaceRoiChartPreviewResult,
} from './roiChartGridBehavior'
import {
  canEditRoiConfig,
  closeRoiChartEditor,
  buildRoiPanelLoadPlan,
  createRoiConfigLoadCoordinator,
  refreshRoiChartsWithConfig,
  runRoiEnsureChartFlow,
} from './roiDashboardPanelBehavior'

const route = useRoute()
const roiDashboardStore = useRoiDashboardStore()
const { config, configLoaded, dashboard, charts } = storeToRefs(roiDashboardStore)

const editorState = ref<RoiChartEditorState>({
  visible: false,
  mode: 'create',
  dashboardId: '',
  chartId: null,
  initialValue: null,
  firstChart: false,
})
const createFlowRunning = ref(false)
const refreshingChartIds = ref<string[]>([])
const chartDateRanges = ref<Record<string, RoiDateRange>>({})

const routeMode = computed(() => {
  const value = Array.isArray(route.query.dashboardMode)
    ? route.query.dashboardMode[0]
    : route.query.dashboardMode
  return value === 'roi' ? 'roi' : 'ordinary'
})
const dashboardId = computed(() => (dashboard.value ? String(dashboard.value.id) : ''))
const currentCharts = computed(() => charts.value[dashboardId.value] || [])
const canExecute = computed(() => config.value?.can_execute === true)
const canEdit = computed(() => canEditRoiConfig(config.value))
const roiConfigLoadCoordinator = createRoiConfigLoadCoordinator({
  load: () => roiDashboardStore.loadConfig(),
  isLoaded: () => configLoaded.value,
})

async function loadPage(reason: 'mounted' | 'route-enter') {
  const plan = buildRoiPanelLoadPlan({
    reason,
    routeMode: routeMode.value,
  })
  if (!plan.length) return
  try {
    const [, loadedDashboard] = await Promise.all([
      plan.includes('config') ? roiConfigLoadCoordinator.refresh() : Promise.resolve(),
      plan.includes('dashboard')
        ? roiDashboardStore.loadDashboard()
        : Promise.resolve(dashboard.value),
    ])
    if (loadedDashboard) await roiDashboardStore.loadCharts(String(loadedDashboard.id))
  } catch {
    ElMessage.error('加载 ROI 看板失败，请稍后重试')
  }
}

async function ensureConfigLoaded() {
  if (configLoaded.value) return
  const plan = buildRoiPanelLoadPlan({
    reason: 'explicit-config',
    routeMode: routeMode.value,
  })
  if (plan.includes('config')) await roiConfigLoadCoordinator.ensure()
}

async function reloadCharts() {
  if (!dashboardId.value || routeMode.value !== 'roi') return
  try {
    await refreshRoiChartsWithConfig({
      loadCharts: () => roiDashboardStore.loadCharts(dashboardId.value),
      refreshConfig: roiConfigLoadCoordinator.refresh,
    })
  } catch {
    ElMessage.error('刷新 ROI 图表失败，请稍后重试')
  }
}

async function reloadChartsAfterConfigSave() {
  if (!dashboardId.value || routeMode.value !== 'roi') return
  try {
    await roiDashboardStore.loadCharts(dashboardId.value)
  } catch {
    ElMessage.error('刷新 ROI 图表失败，请稍后重试')
  }
}

async function openNewChartEditor() {
  if (createFlowRunning.value) return
  createFlowRunning.value = true
  try {
    await runRoiEnsureChartFlow({
      ensureConfigLoaded,
      getConfig: () => config.value,
      getDashboard: () => dashboard.value,
      onMissingConfig: () => ElMessage.warning('请联系 SaaS 管理员配置 ROI 数据源'),
      onForbiddenConfig: () => ElMessage.warning('当前账号无此数据源权限'),
      ensureDashboard: () => roiDashboardStore.ensureDashboard(),
      firstChart: currentCharts.value.length === 0,
      openEditor: (state) => {
        editorState.value = state
      },
    })
  } catch {
    ElMessage.error('新增 ROI 图表失败，请稍后重试')
  } finally {
    createFlowRunning.value = false
  }
}

function openEditChartEditor(chart: RoiChart) {
  if (!canManageRoiChart(chart, canEdit.value)) return
  editorState.value = {
    visible: true,
    mode: 'edit',
    dashboardId: dashboardId.value,
    chartId: String(chart.id),
    initialValue: chart,
    firstChart: false,
  }
}

function cancelChartEditor() {
  editorState.value = closeRoiChartEditor(editorState.value)
}

async function handleChartSaved() {
  editorState.value = closeRoiChartEditor(editorState.value)
  await reloadChartsAfterConfigSave()
}

async function refreshChart(
  chart: RoiChart,
  selectedDateRange?: RoiDateRange,
  notify = true
): Promise<boolean> {
  const chartId = String(chart.id)
  const dateRange = selectedDateRange || chartDateRanges.value[chartId] || defaultRoiDateRange()
  if (
    chart.can_execute === false ||
    !chart.sql?.trim() ||
    refreshingChartIds.value.includes(chartId)
  ) {
    return false
  }
  refreshingChartIds.value = [...refreshingChartIds.value, chartId]
  try {
    const result = await roiDashboardApi.previewChart(
      dashboardId.value,
      buildRoiChartPreviewRequest(
        chart,
        hasRoiDateRangePlaceholders(chart.sql) ? dateRange : undefined
      ),
      roiCustomErrorRequestConfig
    )
    if (result.status !== 'success') throw new Error(result.message)
    roiDashboardStore.publishCharts(
      dashboardId.value,
      replaceRoiChartPreviewResult(currentCharts.value, chartId, result)
    )
    if (notify) ElMessage.success('ROI 图表刷新成功')
    return true
  } catch {
    if (notify) ElMessage.error('刷新 ROI 图表失败，请稍后重试')
    return false
  } finally {
    refreshingChartIds.value = refreshingChartIds.value.filter((id) => id !== chartId)
  }
}

async function changeChartDateRange(chart: RoiChart, dateRange: RoiDateRange) {
  if (!hasRoiDateRangePlaceholders(chart.sql)) return
  const chartId = String(chart.id)
  chartDateRanges.value = { ...chartDateRanges.value, [chartId]: dateRange }
  await refreshChart(chart, dateRange)
}

async function removeChart(chart: RoiChart) {
  if (!canManageRoiChart(chart, canEdit.value)) return
  try {
    await ElMessageBox.confirm(`确定删除图表“${chart.title}”吗？`, '删除图表', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      confirmButtonType: 'danger',
      type: 'warning',
      autofocus: false,
      showClose: false,
    })
  } catch {
    return
  }
  try {
    await roiDashboardApi.removeChart(
      dashboardId.value,
      String(chart.id),
      roiCustomErrorRequestConfig
    )
    roiDashboardStore.publishCharts(
      dashboardId.value,
      currentCharts.value.filter((item) => String(item.id) !== String(chart.id))
    )
  } catch {
    ElMessage.error('删除 ROI 图表失败，请稍后重试')
  }
}

async function persistChartOrder(nextCharts: RoiChart[]) {
  if (!canEdit.value || nextCharts.some((chart) => !canManageRoiChart(chart, true))) return
  try {
    const updated = await roiDashboardApi.reorderCharts(
      dashboardId.value,
      { items: buildRoiChartOrderItems(nextCharts) },
      roiCustomErrorRequestConfig
    )
    roiDashboardStore.publishCharts(
      dashboardId.value,
      mergeReorderedRoiCharts(currentCharts.value, updated)
    )
  } catch {
    ElMessage.error('保存 ROI 图表排序失败，请稍后重试')
    await reloadCharts()
  }
}

function changeChartSpan(chart: RoiChart, layoutSpan: RoiLayoutSpan) {
  if (!canManageRoiChart(chart, canEdit.value) || chart.layout_span === layoutSpan) return
  const nextCharts = currentCharts.value.map((item) =>
    String(item.id) === String(chart.id) ? { ...item, layout_span: layoutSpan } : item
  )
  void persistChartOrder(nextCharts)
}

watch(
  () => currentCharts.value.map((chart) => String(chart.id)),
  (chartIds) => {
    const currentRanges = chartDateRanges.value
    const nextRanges: Record<string, RoiDateRange> = {}
    for (const chartId of chartIds) {
      nextRanges[chartId] = currentRanges[chartId] || defaultRoiDateRange()
    }
    chartDateRanges.value = nextRanges
  },
  { immediate: true }
)

watch(routeMode, (mode, previousMode) => {
  if (mode !== 'roi' || mode === previousMode) return
  chartDateRanges.value = {}
  void loadPage('route-enter')
})

useEmitt({
  name: WORKSPACE_CONTEXT_CHANGE_EVENT,
  callback: (event?: any) => {
    if (event?.phase === 'changing') {
      roiConfigLoadCoordinator.invalidate()
      roiDashboardStore.reset()
      chartDateRanges.value = {}
      return
    }
    if (event?.phase === 'changed' && routeMode.value === 'roi') {
      void loadPage('route-enter')
    }
  },
})

onMounted(() => {
  void loadPage('mounted')
})

onBeforeUnmount(() => {
  roiConfigLoadCoordinator.invalidate()
  roiDashboardStore.reset()
})
</script>

<template>
  <section v-loading="roiDashboardStore.loading" class="roi-dashboard-panel">
    <header class="roi-dashboard-panel__header">
      <div class="roi-dashboard-panel__identity">
        <h2>{{ dashboard?.name || 'ROI 看板' }}</h2>
        <span v-if="config?.datasource_name">{{ config.datasource_name }}</span>
      </div>
      <div class="roi-dashboard-panel__actions">
        <el-button type="primary" :icon="Plus" :disabled="!canEdit" @click="openNewChartEditor">
          添加图表
        </el-button>
      </div>
    </header>

    <div v-if="roiDashboardStore.permissionError" class="roi-dashboard-panel__state">
      {{ roiDashboardStore.permissionError }}
    </div>
    <div v-else-if="!config" class="roi-dashboard-panel__state is-permission">
      请联系 SaaS 管理员配置 ROI 数据源
    </div>
    <div v-else-if="config && !canExecute" class="roi-dashboard-panel__state is-permission">
      当前账号无此数据源权限
    </div>
    <div v-else-if="!currentCharts.length" class="roi-dashboard-panel__state">暂无图表</div>
    <RoiChartGrid
      v-else
      :charts="currentCharts"
      :can-edit="canEdit"
      :refreshing-chart-ids="refreshingChartIds"
      :chart-date-ranges="chartDateRanges"
      @refresh="refreshChart"
      @date-range-change="changeChartDateRange"
      @edit="openEditChartEditor"
      @remove="removeChart"
      @reorder="persistChartOrder"
      @span-change="changeChartSpan"
    />

    <RoiSqlEditor
      :model-value="editorState.visible"
      :dashboard-id="editorState.dashboardId"
      :chart="editorState.initialValue"
      :can-edit="canEdit"
      @saved="handleChartSaved"
      @cancelled="cancelChartEditor"
    />
  </section>
</template>

<style scoped lang="less">
.roi-dashboard-panel {
  box-sizing: border-box;
  width: 100%;
  min-height: 100%;
  padding: 20px;
  overflow: auto;
  background: var(--ed-fill-color-lighter);
}

.roi-dashboard-panel__header {
  display: flex;
  min-height: 48px;
  margin-bottom: 16px;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.roi-dashboard-panel__identity {
  min-width: 0;

  h2 {
    margin: 0;
    overflow: hidden;
    color: var(--ed-text-color-primary);
    font-size: 18px;
    line-height: 26px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  span {
    display: block;
    min-width: 0;
    margin-top: 2px;
    overflow: hidden;
    color: var(--ed-text-color-secondary);
    font-size: 12px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.roi-dashboard-panel__actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 8px;
}

.roi-dashboard-panel__state {
  display: grid;
  min-height: 320px;
  place-items: center;
  color: var(--ed-text-color-secondary);
  font-size: 14px;
}

@media (max-width: 720px) {
  .roi-dashboard-panel {
    padding: 12px;
  }

  .roi-dashboard-panel__header {
    align-items: flex-start;
    flex-direction: column;
  }

  .roi-dashboard-panel__actions {
    width: 100%;
    flex-wrap: wrap;
  }
}
</style>
