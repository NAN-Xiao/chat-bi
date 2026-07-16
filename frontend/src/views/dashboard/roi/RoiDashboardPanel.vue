<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessage, ElMessageBox } from 'element-plus-secondary'
import { Plus, RefreshRight, Setting } from '@element-plus/icons-vue'
import { useRoute, useRouter } from 'vue-router'
import { roiCustomErrorRequestConfig, roiDashboardApi } from '@/api/roiDashboard'
import { useRoiDashboardStore } from '@/stores/roiDashboard'
import { useEmitt } from '@/utils/useEmitt'
import RoiChartGrid from './RoiChartGrid.vue'
import RoiDatasourceDialog from './RoiDatasourceDialog.vue'
import type { RoiChart, RoiChartEditorState, RoiConfig, RoiLayoutSpan } from './types'
import {
  buildRoiChartOrderItems,
  canManageRoiChart,
  mergeReorderedRoiCharts,
} from './roiChartGridBehavior'
import {
  closeRoiChartEditor,
  ROI_DASHBOARD_TREE_REFRESH_EVENT,
  runRoiDashboardCreateFlow,
} from './roiDashboardPanelBehavior'

const props = defineProps<{
  dashboardId: string
}>()

const route = useRoute()
const router = useRouter()
const roiDashboardStore = useRoiDashboardStore()
const { config, dashboards, charts, editorState: storeEditorState } = storeToRefs(roiDashboardStore)
const { emitter } = useEmitt()

const editorState = ref<RoiChartEditorState>({
  visible: false,
  mode: 'create',
  dashboardId: '',
  chartId: null,
  initialValue: null,
  firstChart: false,
})
const createFlowRunning = ref(false)
let datasourceResolution: ((saved: boolean) => void) | null = null

const routeMode = computed(() => {
  const value = Array.isArray(route.query.dashboardMode)
    ? route.query.dashboardMode[0]
    : route.query.dashboardMode
  return value === 'roi' ? 'roi' : 'ordinary'
})
const currentCharts = computed(() => charts.value[String(props.dashboardId)] || [])
const dashboard = computed(() =>
  dashboards.value.find((item) => String(item.id) === String(props.dashboardId))
)
const hasDatasourcePermission = computed(
  () => !currentCharts.value.some((chart) => chart.can_execute === false)
)
const canEdit = computed(() => Boolean(config.value) && hasDatasourcePermission.value)
const datasourceDialogOpen = computed(() => storeEditorState.value.datasourceDialogOpen)

async function loadPage() {
  try {
    await Promise.all([roiDashboardStore.loadConfig(), roiDashboardStore.loadDashboards()])
    if (routeMode.value === 'roi' && props.dashboardId) {
      await roiDashboardStore.loadCharts(String(props.dashboardId))
    }
  } catch {
    ElMessage.error('加载 ROI 看板失败，请稍后重试')
  }
}

async function reloadCharts() {
  if (!props.dashboardId || routeMode.value !== 'roi') return
  try {
    await roiDashboardStore.loadCharts(String(props.dashboardId))
  } catch {
    ElMessage.error('刷新 ROI 图表失败，请稍后重试')
  }
}

function ensureRoiDatasourceBeforeCreate() {
  if (config.value) return Promise.resolve(true)
  storeEditorState.value.datasourceDialogOpen = true
  return new Promise<boolean>((resolve) => {
    datasourceResolution?.(false)
    datasourceResolution = resolve
  })
}

async function openCreateDashboardNameDialog() {
  try {
    const result = await ElMessageBox.prompt('请输入 ROI 看板名称', '新建下属看板', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: 'ROI 看板名称不能为空',
      autofocus: false,
    })
    return result.value.trim()
  } catch {
    return null
  }
}

function openFirstChartEditor(dashboardId: string) {
  editorState.value = {
    visible: true,
    mode: 'create',
    dashboardId,
    chartId: null,
    initialValue: null,
    firstChart: true,
  }
}

async function createDashboard() {
  if (createFlowRunning.value) return
  createFlowRunning.value = true
  try {
    const created = await runRoiDashboardCreateFlow({
      config: config.value,
      requestDatasource: ensureRoiDatasourceBeforeCreate,
      requestName: openCreateDashboardNameDialog,
      createDashboard: (name) =>
        roiDashboardApi.create({ name }, roiCustomErrorRequestConfig),
      publishDashboard: (created) => {
        roiDashboardStore.publishDashboard(created)
        roiDashboardStore.publishCharts(String(created.id), [])
      },
      navigate: (target) => router.push(target),
      openEditor: (state) => openFirstChartEditor(state.dashboardId),
    })
    if (created) emitter.emit(ROI_DASHBOARD_TREE_REFRESH_EVENT)
  } catch {
    ElMessage.error('新建 ROI 看板失败，请稍后重试')
  } finally {
    createFlowRunning.value = false
  }
}

function handleDatasourceSaved(saved: RoiConfig) {
  config.value = saved
  storeEditorState.value.datasourceDialogOpen = false
  datasourceResolution?.(true)
  datasourceResolution = null
  if (routeMode.value === 'roi') void reloadCharts()
}

function handleDatasourceCancelled() {
  storeEditorState.value.datasourceDialogOpen = false
  datasourceResolution?.(false)
  datasourceResolution = null
}

function openNewChartEditor() {
  if (!canEdit.value || !props.dashboardId) return
  editorState.value = {
    visible: true,
    mode: 'create',
    dashboardId: String(props.dashboardId),
    chartId: null,
    initialValue: null,
    firstChart: currentCharts.value.length === 0,
  }
}

function openEditChartEditor(chart: RoiChart) {
  if (!canManageRoiChart(chart, canEdit.value)) return
  editorState.value = {
    visible: true,
    mode: 'edit',
    dashboardId: String(props.dashboardId),
    chartId: String(chart.id),
    initialValue: chart,
    firstChart: false,
  }
}

function cancelChartEditor() {
  editorState.value = closeRoiChartEditor(editorState.value)
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
      String(props.dashboardId),
      String(chart.id),
      roiCustomErrorRequestConfig
    )
    roiDashboardStore.publishCharts(
      String(props.dashboardId),
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
      String(props.dashboardId),
      { items: buildRoiChartOrderItems(nextCharts) },
      roiCustomErrorRequestConfig
    )
    roiDashboardStore.publishCharts(
      String(props.dashboardId),
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
  () => storeEditorState.value.createDashboardRequestId,
  (current, previous) => {
    if (current > previous) void createDashboard()
  }
)

watch(
  () => [props.dashboardId, routeMode.value],
  ([dashboardId, mode], previous) => {
    if (mode !== 'roi' || !dashboardId) return
    if (dashboardId === previous?.[0] && mode === previous?.[1]) return
    void reloadCharts()
  }
)

onMounted(() => {
  void loadPage()
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
        <el-tooltip content="设置数据源" placement="bottom">
          <el-button circle :icon="Setting" @click="roiDashboardStore.openDatasourceSettings()" />
        </el-tooltip>
        <el-tooltip content="刷新图表" placement="bottom">
          <el-button circle :icon="RefreshRight" @click="reloadCharts" />
        </el-tooltip>
        <el-button
          type="primary"
          :icon="Plus"
          :disabled="!canEdit"
          @click="openNewChartEditor"
        >
          添加图表
        </el-button>
      </div>
    </header>

    <div v-if="roiDashboardStore.permissionError" class="roi-dashboard-panel__state">
      {{ roiDashboardStore.permissionError }}
    </div>
    <div v-else-if="!currentCharts.length" class="roi-dashboard-panel__state">暂无图表</div>
    <RoiChartGrid
      v-else
      :charts="currentCharts"
      :can-edit="canEdit"
      @edit="openEditChartEditor"
      @remove="removeChart"
      @reorder="persistChartOrder"
      @span-change="changeChartSpan"
    />

    <RoiDatasourceDialog
      :model-value="datasourceDialogOpen"
      :config="config"
      @update:model-value="storeEditorState.datasourceDialogOpen = $event"
      @saved="handleDatasourceSaved"
      @cancelled="handleDatasourceCancelled"
    />

    <div v-if="editorState.visible" class="roi-editor-mount">
      <slot
        name="roi-editor"
        :state="editorState"
        :cancel="cancelChartEditor"
        :saved="reloadCharts"
      />
    </div>
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
    margin-top: 2px;
    color: var(--ed-text-color-secondary);
    font-size: 12px;
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

.roi-editor-mount {
  position: relative;
  z-index: 10;
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
