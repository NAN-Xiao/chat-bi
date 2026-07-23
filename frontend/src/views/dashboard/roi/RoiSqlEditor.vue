<script lang="ts">
import type { RoiDashboardViewInfo } from './roiDashboardViewAdapter'
import type { RoiChart, RoiChartCreate, RoiChartUpdate, RoiLayoutSpan } from './types'

export type PersistRoiChartDependencies = {
  getDashboardId: () => string
  getChart: () => RoiChart | null
  toPayload: (
    viewInfo: RoiDashboardViewInfo,
    options: { version?: number; layoutSpan: RoiLayoutSpan }
  ) => RoiChartCreate | RoiChartUpdate
  createChart: (dashboardId: string, payload: RoiChartCreate) => Promise<RoiChart>
  updateChart: (
    dashboardId: string,
    chartId: string,
    payload: RoiChartUpdate
  ) => Promise<RoiChart>
  onSaved: (chart: RoiChart) => void
  onError: (error: unknown) => void
}

export function createPersistRoiChart(dependencies: PersistRoiChartDependencies) {
  return async function persistRoiChart(viewInfo: RoiDashboardViewInfo): Promise<boolean> {
    try {
      const chart = dependencies.getChart()
      const payload = dependencies.toPayload(
        viewInfo,
        chart
          ? { version: chart.version, layoutSpan: chart.layout_span || 'full' }
          : { layoutSpan: 'full' }
      )
      const saved = chart
        ? await dependencies.updateChart(
            dependencies.getDashboardId(),
            String(chart.id),
            payload as RoiChartUpdate
          )
        : await dependencies.createChart(
            dependencies.getDashboardId(),
            payload as RoiChartCreate
          )
      dependencies.onSaved(saved)
      return true
    } catch (error) {
      dependencies.onError(error)
      return false
    }
  }
}
</script>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessage } from 'element-plus-secondary'
import { roiCustomErrorRequestConfig, roiDashboardApi } from '@/api/roiDashboard'
import { useRoiDashboardStore } from '@/stores/roiDashboard'
import DashboardSqlEditor from '@/views/dashboard/common/DashboardSqlEditor.vue'
import { getRoiChartSaveErrorMessage } from './roiChartConfig'
import {
  createRoiDashboardViewInfo,
  dashboardViewInfoToRoiPayload,
  roiChartToDashboardViewInfo,
} from './roiDashboardViewAdapter'

const props = defineProps<{
  modelValue: boolean
  dashboardId: string
  chart: RoiChart | null
  canEdit: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  saved: [chart: RoiChart]
  cancelled: []
}>()

const roiDashboardStore = useRoiDashboardStore()
const { config } = storeToRefs(roiDashboardStore)
const draftViewInfo = ref<RoiDashboardViewInfo | null>(null)
const pendingSavedChart = ref<RoiChart | null>(null)
const appliedClosePending = ref(false)

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => {
    emit('update:modelValue', value)
    if (value) return
    if (appliedClosePending.value) {
      appliedClosePending.value = false
      return
    }
    emit('cancelled')
  },
})

const dashboardInfo = computed(() => ({
  id: props.dashboardId,
  tenant_id: config.value?.tenant_id,
}))

const persistRoiChart = createPersistRoiChart({
  getDashboardId: () => props.dashboardId,
  getChart: () => props.chart,
  toPayload: dashboardViewInfoToRoiPayload,
  createChart: (dashboardId, payload) =>
    roiDashboardApi.createChart(dashboardId, payload, roiCustomErrorRequestConfig),
  updateChart: (dashboardId, chartId, payload) =>
    roiDashboardApi.updateChart(dashboardId, chartId, payload, roiCustomErrorRequestConfig),
  onSaved: (chart) => {
    pendingSavedChart.value = chart
  },
  onError: (error) => {
    ElMessage.error(getRoiChartSaveErrorMessage(error))
  },
})

function initializeDraft() {
  pendingSavedChart.value = null
  appliedClosePending.value = false
  if (!props.modelValue || !config.value) {
    draftViewInfo.value = null
    return
  }
  draftViewInfo.value = props.chart
    ? roiChartToDashboardViewInfo(props.chart, config.value)
    : createRoiDashboardViewInfo(config.value)
}

function handleApplied() {
  const saved = pendingSavedChart.value
  if (!saved) return
  pendingSavedChart.value = null
  appliedClosePending.value = true
  emit('saved', saved)
}

watch(
  () => [
    props.modelValue,
    props.dashboardId,
    props.chart?.id,
    props.chart?.version,
    config.value?.id,
    config.value?.version,
    config.value?.datasource_id,
  ],
  initializeDraft,
  { immediate: true }
)
</script>

<template>
  <DashboardSqlEditor
    v-model="visible"
    :view-info="draftViewInfo"
    :dashboard-info="dashboardInfo"
    :can-edit-sql="canEdit"
    :fixed-datasource-id="config?.datasource_id"
    :allow-external-sources="false"
    :apply-executor="persistRoiChart"
    @applied="handleApplied"
  />
</template>
