<script setup lang="ts">
import { computed } from 'vue'
import { Delete, Edit, Grid, Rank } from '@element-plus/icons-vue'
import ChartComponent from '@/views/chat/component/ChartComponent.vue'
import type { ChartAxis } from '@/views/chat/component/BaseChart'
import type { RoiChart, RoiLayoutSpan } from './types'
import { canManageRoiChart } from './roiChartGridBehavior'

const props = defineProps<{
  chart: RoiChart
  canEdit: boolean
}>()

const emit = defineEmits<{
  edit: [chart: RoiChart]
  remove: [chart: RoiChart]
  'span-change': [chart: RoiChart, span: RoiLayoutSpan]
}>()

const actionEnabled = computed(() => canManageRoiChart(props.chart, props.canEdit))
const config = computed(() => props.chart.chart_config || {})
const data = computed(() => props.chart.query_result?.data || [])

function normalizeAxes(value: unknown): ChartAxis[] {
  const values = Array.isArray(value) ? value : value ? [value] : []
  return values
    .map((item) => {
      if (typeof item === 'string') return { value: item }
      if (item && typeof item === 'object') {
        const axis = item as Record<string, unknown>
        const field = String(axis.value || axis.name || '').trim()
        return field ? ({ ...axis, value: field } as ChartAxis) : null
      }
      return null
    })
    .filter((item): item is ChartAxis => item !== null)
}

const columns = computed(() => normalizeAxes(config.value.columns))
const x = computed(() => normalizeAxes(config.value.x || config.value.xAxis))
const y = computed(() => normalizeAxes(config.value.y || config.value.yAxis))
const series = computed(() => normalizeAxes(config.value.series))
const showLabel = computed(() => config.value.showLabel === true)
const chartError = computed(() =>
  props.chart.can_execute === false
    ? '当前账号无此数据源权限'
    : props.chart.error || props.chart.query_result?.status === 'failed'
      ? 'ROI 图表加载失败'
      : ''
)
</script>

<template>
  <article class="roi-chart-card">
    <header class="roi-chart-card__header">
      <div class="roi-chart-card__title" :title="chart.title">{{ chart.title }}</div>
      <div class="roi-chart-card__actions">
        <el-tooltip content="拖动排序" placement="top">
          <el-button class="icon-button drag-handle" text circle :disabled="!actionEnabled">
            <el-icon><Rank /></el-icon>
          </el-button>
        </el-tooltip>
        <el-dropdown :disabled="!actionEnabled" trigger="click" @command="emit('span-change', chart, $event)">
          <el-button
            class="icon-button"
            text
            circle
            aria-label="设置宽度"
            title="设置宽度"
            :disabled="!actionEnabled"
          >
            <el-icon><Grid /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="full">整行</el-dropdown-item>
              <el-dropdown-item command="half">半行</el-dropdown-item>
              <el-dropdown-item command="third">三分之一行</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-tooltip content="编辑图表" placement="top">
          <el-button
            class="icon-button"
            text
            circle
            :disabled="!actionEnabled"
            @click="emit('edit', chart)"
          >
            <el-icon><Edit /></el-icon>
          </el-button>
        </el-tooltip>
        <el-tooltip content="删除图表" placement="top">
          <el-button
            class="icon-button"
            text
            circle
            :disabled="!actionEnabled"
            @click="emit('remove', chart)"
          >
            <el-icon><Delete /></el-icon>
          </el-button>
        </el-tooltip>
      </div>
    </header>
    <div class="roi-chart-card__body">
      <div v-if="chart.can_execute === false" class="roi-chart-card__state is-permission">
        当前账号无此数据源权限
      </div>
      <div v-else-if="chartError" class="roi-chart-card__state">{{ chartError }}</div>
      <ChartComponent
        v-else-if="data.length"
        :id="`roi-${chart.id}`"
        :type="chart.chart_type"
        :data="data"
        :columns="columns"
        :x="x"
        :y="y"
        :series="series"
        :show-label="showLabel"
      />
      <div v-else class="roi-chart-card__state">暂无数据</div>
    </div>
  </article>
</template>

<style scoped lang="less">
.roi-chart-card {
  display: flex;
  min-width: 0;
  min-height: 320px;
  overflow: hidden;
  flex-direction: column;
  border: 1px solid var(--ed-border-color-lighter);
  border-radius: 6px;
  background: var(--ed-bg-color);
}

.roi-chart-card__header {
  display: flex;
  min-height: 48px;
  padding: 0 8px 0 16px;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--ed-border-color-extra-light);
}

.roi-chart-card__title {
  min-width: 0;
  overflow: hidden;
  color: var(--ed-text-color-primary);
  font-size: 14px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.roi-chart-card__actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
}

.icon-button {
  width: 32px;
  height: 32px;
  padding: 0;
}

.drag-handle:not(.is-disabled) {
  cursor: grab;
}

.roi-chart-card__body {
  display: flex;
  min-height: 0;
  flex: 1 1 auto;
  padding: 10px;
}

.roi-chart-card__body :deep(.chart-container) {
  min-height: 240px;
  flex: 1 1 auto;
}

.roi-chart-card__state {
  display: grid;
  width: 100%;
  height: 100%;
  min-height: 240px;
  place-items: center;
  color: var(--ed-text-color-secondary);
  font-size: 14px;
  text-align: center;
}

.roi-chart-card__state.is-permission {
  color: var(--ed-color-danger);
}
</style>
