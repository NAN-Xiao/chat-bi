<script setup lang="ts">
import { computed } from 'vue'
import { Delete, Edit, Grid, Rank, RefreshRight } from '@element-plus/icons-vue'
import ChartComponent from '@/views/chat/component/ChartComponent.vue'
import type { ChartAxis } from '@/views/chat/component/BaseChart'
import type { RoiChart, RoiDateRange, RoiLayoutSpan } from './types'
import { canManageRoiChart, hasRoiDateRangePlaceholders } from './roiChartGridBehavior'

const props = defineProps<{
  chart: RoiChart
  canEdit: boolean
  refreshing: boolean
  dateRange: RoiDateRange
}>()

const emit = defineEmits<{
  edit: [chart: RoiChart]
  remove: [chart: RoiChart]
  refresh: [chart: RoiChart]
  'date-range-change': [chart: RoiChart, dateRange: RoiDateRange]
  'span-change': [chart: RoiChart, span: RoiLayoutSpan]
}>()

const actionEnabled = computed(() => canManageRoiChart(props.chart, props.canEdit))
const dateRangeEnabled = computed(
  () => props.chart.can_execute !== false && hasRoiDateRangePlaceholders(props.chart.sql)
)
const dateRangeHint = computed(() =>
  dateRangeEnabled.value ? '选择日期后重新执行 SQL' : 'SQL 需同时配置开始和结束日期占位符'
)
const refreshEnabled = computed(
  () => props.chart.can_execute !== false && Boolean(props.chart.sql?.trim())
)
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

function handleDateRangeChange(value: unknown) {
  if (
    !dateRangeEnabled.value ||
    props.refreshing ||
    !Array.isArray(value) ||
    value.length !== 2 ||
    value.some((item) => typeof item !== 'string')
  ) {
    return
  }
  emit('date-range-change', props.chart, [value[0], value[1]])
}
</script>

<template>
  <article class="roi-chart-card">
    <header class="roi-chart-card__header">
      <div class="roi-chart-card__title" :title="chart.title">{{ chart.title }}</div>
      <div class="roi-chart-card__date-range">
        <el-tooltip :content="dateRangeHint" placement="top">
          <span>
            <el-date-picker
              :model-value="dateRange"
              type="daterange"
              value-format="YYYY-MM-DD"
              format="YYYY-MM-DD"
              range-separator="至"
              start-placeholder="开始日期"
              end-placeholder="结束日期"
              :clearable="false"
              :disabled="!dateRangeEnabled || refreshing"
              @update:model-value="handleDateRangeChange"
            />
          </span>
        </el-tooltip>
      </div>
      <div class="roi-chart-card__actions">
        <el-tooltip content="重新执行 SQL" placement="top">
          <el-button
            class="icon-button"
            text
            circle
            :loading="refreshing"
            :disabled="!refreshEnabled || refreshing"
            aria-label="重新执行 SQL"
            @click="emit('refresh', chart)"
          >
            <el-icon v-if="!refreshing"><RefreshRight /></el-icon>
          </el-button>
        </el-tooltip>
        <el-tooltip content="拖动排序" placement="top">
          <el-button class="icon-button drag-handle" text circle :disabled="!actionEnabled">
            <el-icon><Rank /></el-icon>
          </el-button>
        </el-tooltip>
        <el-dropdown
          :disabled="!actionEnabled"
          trigger="click"
          @command="emit('span-change', chart, $event)"
        >
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
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
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
  flex: 1 1 0;
}

.roi-chart-card__date-range {
  display: flex;
  min-width: 0;
  flex: 0 1 250px;
  justify-content: center;
  padding: 0 8px;

  span,
  :deep(.ed-date-editor) {
    width: 100%;
  }
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
  width: 100%;
  flex: 1 1 auto;
  overflow: hidden;
  padding: 10px;
}

.roi-chart-card__body :deep(.chart-container) {
  width: 100%;
  height: 100%;
  min-height: 0;
  flex: 1 1 auto;
  overflow: hidden;
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
