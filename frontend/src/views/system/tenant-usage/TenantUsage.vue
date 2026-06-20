<template>
  <div class="tenant-usage-container professional-container">
    <div class="tool-left" :class="{ 'is-embedded': embedded }">
      <span class="page-title">{{ t('tenant_usage.title') }}</span>
      <div class="toolbar">
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          value-format="YYYY-MM-DD"
          :start-placeholder="t('tenant_usage.start_date')"
          :end-placeholder="t('tenant_usage.end_date')"
          :range-separator="t('tenant_usage.to')"
          clearable
        />
        <div class="current-tenant">
          {{ currentTenantName }}
        </div>
        <el-button type="primary" :loading="loading" @click="loadUsage">
          <template #icon>
            <icon_searchOutline_outlined />
          </template>
          {{ t('common.search') }}
        </el-button>
        <el-button secondary @click="resetFilters">
          {{ t('common.reset') }}
        </el-button>
        <el-button secondary :loading="loading" @click="loadUsage">
          {{ t('common.refresh') }}
        </el-button>
      </div>
    </div>

    <section class="overview-shell">
      <div class="overview-panel">
        <div class="overview-copy">
          <div class="overview-kicker">{{ t('tenant_usage.overview') }}</div>
          <div class="overview-title-row">
            <h2>{{ currentScopeLabel }}</h2>
            <span class="overview-range">{{ dateRangeLabel }}</span>
          </div>
          <p class="overview-subtitle">{{ selectedMetricLabel }}</p>
          <div class="overview-total">
            <span class="overview-total-label">{{ t('tenant_usage.total_token_consumption') }}</span>
            <strong>{{ formatNumber(summary.total_tokens) }}</strong>
          </div>
          <div class="overview-highlights">
            <div v-for="item in overviewHighlights" :key="item.label" class="overview-highlight">
              <span class="overview-highlight-label">{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
            </div>
          </div>
        </div>

        <div class="overview-visual">
          <div class="chart-card-head">
            <span>{{ t('tenant_usage.user_token_ranking') }}</span>
            <span class="muted">{{ t('tenant_usage.by_user') }}</span>
          </div>
          <div class="chart-surface chart-surface-hero">
            <ChartComponent
              v-if="userChartRows.length"
              :id="'tenant-usage-user-ranking'"
              type="bar"
              :data="userChartRows"
              :x="userTokenXAxis"
              :y="userTokenYAxis"
            />
            <div v-else class="hero-empty-state" :aria-label="t('tenant_usage.empty')">
              <div class="hero-empty-grid" aria-hidden="true">
                <span v-for="line in 4" :key="line" class="hero-empty-grid-line" />
              </div>
              <svg class="hero-empty-trace" viewBox="0 0 100 32" preserveAspectRatio="none" aria-hidden="true">
                <path
                  class="hero-empty-area"
                  d="M 0 28 L 16 24 L 32 25 L 48 18 L 64 20 L 80 12 L 100 14 L 100 32 L 0 32 Z"
                />
                <path
                  class="hero-empty-line"
                  d="M 0 28 L 16 24 L 32 25 L 48 18 L 64 20 L 80 12 L 100 14"
                />
              </svg>
              <div class="hero-empty-axis" aria-hidden="true">
                <span class="hero-empty-axis-line" />
                <div class="hero-empty-axis-ticks">
                  <span v-for="tick in 7" :key="tick" />
                </div>
              </div>
              <div class="hero-empty-copy">
                <div class="hero-empty-pill">
                  <span class="hero-empty-dot" />
                  <span>{{ t('tenant_usage.empty') }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <div class="summary-grid">
      <div
        v-for="item in summaryItems"
        :key="item.key"
        class="summary-item"
        :style="{
          '--summary-color': item.color,
          '--summary-soft-color': item.softColor,
        }"
      >
        <div class="summary-top">
          <div class="summary-icon">
            <component :is="item.icon" />
          </div>
          <div class="summary-meta">
            <div class="summary-label">{{ item.label }}</div>
            <div class="summary-note">{{ item.note }}</div>
          </div>
        </div>
        <div class="summary-value">{{ formatNumber(item.value) }}</div>
        <div class="summary-sparkline" aria-hidden="true">
          <svg viewBox="0 0 100 32" preserveAspectRatio="none">
            <path :d="item.areaPath" class="sparkline-area" />
            <path :d="item.path" class="sparkline-line" />
          </svg>
        </div>
      </div>
    </div>

    <div class="analytics-grid">
      <section class="chart-card">
        <div class="chart-card-head">
          <span>{{ t('tenant_usage.request_failure_trend') }}</span>
          <span class="muted">{{ t('tenant_usage.by_day') }}</span>
        </div>
        <div class="chart-surface">
          <ChartComponent
            v-if="usageRows.length"
            :id="'tenant-usage-request-trend'"
            type="line"
            :data="dailyRows"
            :x="dateAxis"
            :y="requestTrendAxis"
          />
          <EmptyBackground v-else :description="t('tenant_usage.empty')" img-type="tree" />
        </div>
      </section>

      <section class="chart-card">
        <div class="chart-card-head">
          <span>{{ t('tenant_usage.token_trend') }}</span>
          <span class="muted">{{ t('tenant_usage.by_day') }}</span>
        </div>
        <div class="chart-surface">
          <ChartComponent
            v-if="usageRows.length"
            :id="'tenant-usage-token-trend'"
            type="line"
            :data="dailyRows"
            :x="dateAxis"
            :y="tokenTrendAxis"
          />
          <EmptyBackground v-else :description="t('tenant_usage.empty')" img-type="tree" />
        </div>
      </section>

      <section class="chart-card">
        <div class="chart-card-head">
          <span>{{ t('tenant_usage.token_breakdown') }}</span>
          <span class="muted">{{ t('tenant_usage.top_by_tokens') }}</span>
        </div>
        <div class="chart-surface">
          <ChartComponent
            v-if="metricBreakdownRows.length"
            :id="'tenant-usage-metric-breakdown'"
            type="bar"
            :data="metricBreakdownRows"
            :x="metricBreakdownXAxis"
            :y="metricBreakdownYAxis"
          />
          <EmptyBackground v-else :description="t('tenant_usage.empty')" img-type="tree" />
        </div>
      </section>
    </div>

    <div class="section-head">
      <span>{{ t('tenant_usage.user_detail') }}</span>
      <span class="muted">{{ t('tenant_usage.row_count', { count: userUsageRows.length }) }}</span>
    </div>

    <el-table
      v-loading="loading"
      :data="userUsageRows"
      class="usage-table"
      style="width: 100%"
      :default-sort="{ prop: 'total_tokens', order: 'descending' }"
    >
      <el-table-column
        prop="user_label"
        :label="t('tenant_usage.user')"
        min-width="220"
        show-overflow-tooltip
      >
        <template #default="scope">
          <div class="user-cell">
            <span>{{ scope.row.user_label }}</span>
            <span class="user-key">#{{ scope.row.user_id }}</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="request_count" :label="t('tenant_usage.requests')" width="120" align="right" sortable>
        <template #default="scope">{{ formatNumber(scope.row.request_count) }}</template>
      </el-table-column>
      <el-table-column prop="success_count" :label="t('tenant_usage.success')" width="110" align="right" sortable>
        <template #default="scope">{{ formatNumber(scope.row.success_count) }}</template>
      </el-table-column>
      <el-table-column prop="failure_count" :label="t('tenant_usage.failure')" width="110" align="right" sortable>
        <template #default="scope">
          <span :class="{ danger: Number(scope.row.failure_count || 0) > 0 }">
            {{ formatNumber(scope.row.failure_count) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="total_tokens" :label="t('tenant_usage.tokens')" width="130" align="right" sortable>
        <template #default="scope">{{ formatNumber(scope.row.total_tokens) }}</template>
      </el-table-column>
      <el-table-column prop="last_used_time" :label="t('tenant_usage.last_used_time')" width="180" sortable>
        <template #default="scope">
          <span>{{ formatUsageTime(scope.row.last_used_time) }}</span>
        </template>
      </el-table-column>
      <template #empty>
        <EmptyBackground :description="t('tenant_usage.empty')" img-type="tree" />
      </template>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import dayjs from 'dayjs'
import { computed, onMounted, ref, shallowRef } from 'vue'
import { useI18n } from 'vue-i18n'
import icon_searchOutline_outlined from '@/assets/svg/icon_search-outline_outlined.svg'
import icon_chart_preview from '@/assets/svg/icon_chart_preview.svg'
import icon_done_outlined from '@/assets/svg/icon_done_outlined.svg'
import icon_error from '@/assets/svg/icon_error.svg'
import icon_dashboard_outlined from '@/assets/svg/chart/icon_dashboard_outlined.svg'
import EmptyBackground from '@/views/dashboard/common/EmptyBackground.vue'
import ChartComponent from '@/views/chat/component/ChartComponent.vue'
import { tenantApi, type TenantUsageDailyInfo, type TenantUsageUserInfo } from '@/api/tenant'
import type { ChartAxis } from '@/views/chat/component/BaseChart.ts'
import { useUserStore } from '@/stores/user'
import { formatTimestamp } from '@/utils/date'

const { t } = useI18n()
const props = defineProps({
  embedded: {
    type: Boolean,
    default: false,
  },
})
const embedded = computed(() => props.embedded)
const userStore = useUserStore()
const loading = ref(false)
const usageRows = shallowRef<TenantUsageDailyInfo[]>([])
const rawUserUsageRows = shallowRef<TenantUsageUserInfo[]>([])
const dateRange = ref<[string, string] | null>([
  dayjs().subtract(6, 'day').format('YYYY-MM-DD'),
  dayjs().format('YYYY-MM-DD'),
])

const metricOptions = computed(() => [
  { value: 'chat.generate_sql', label: t('tenant_usage.metric_chat_generate_sql') },
  { value: 'chat.execute_sql', label: t('tenant_usage.metric_chat_execute_sql') },
  { value: 'chat.generate_chart', label: t('tenant_usage.metric_chat_generate_chart') },
  { value: 'chat.analysis', label: t('tenant_usage.metric_chat_analysis') },
  { value: 'chat.predict', label: t('tenant_usage.metric_chat_predict') },
  { value: 'chat.recommend', label: t('tenant_usage.metric_chat_recommend') },
  { value: 'analysis_assistant.request', label: t('tenant_usage.metric_analysis_assistant') },
  { value: 'task.enqueued', label: t('tenant_usage.metric_task_enqueued') },
  { value: 'task.succeeded', label: t('tenant_usage.metric_task_succeeded') },
  { value: 'task.failed', label: t('tenant_usage.metric_task_failed') },
])

const metricLabelMap = computed(() =>
  metricOptions.value.reduce<Record<string, string>>((result, item) => {
    result[item.value] = item.label
    return result
  }, {})
)

const currentTenantName = computed(() => userStore.getTenantName || t('tenant.default_tenant'))
const currentScopeLabel = computed(() => currentTenantName.value)

const selectedMetricLabel = computed(() => t('tenant_usage.current_workspace_scope'))

const summary = computed(() =>
  usageRows.value.reduce(
    (result, row) => {
      result.request_count += Number(row.request_count || 0)
      result.success_count += Number(row.success_count || 0)
      result.failure_count += Number(row.failure_count || 0)
      result.total_tokens += Number(row.total_tokens || 0)
      result.task_count += Number(row.task_count || 0)
      return result
    },
    {
      request_count: 0,
      success_count: 0,
      failure_count: 0,
      total_tokens: 0,
      task_count: 0,
    }
  )
)

const rangeDates = computed(() => {
  const [startDate, endDate] = dateRange.value || []
  if (!startDate || !endDate) {
    return Array.from(new Set(usageRows.value.map((row) => row.usage_date))).sort()
  }
  const list: string[] = []
  let cursor = dayjs(startDate)
  const end = dayjs(endDate)
  while (cursor.isBefore(end, 'day') || cursor.isSame(end, 'day')) {
    list.push(cursor.format('YYYY-MM-DD'))
    cursor = cursor.add(1, 'day')
  }
  return list
})

const dailyRows = computed(() => {
  const byDate = usageRows.value.reduce<Record<string, any>>((result, row) => {
    const key = row.usage_date
    if (!result[key]) {
      result[key] = {
        usage_date: key,
        request_count: 0,
        success_count: 0,
        failure_count: 0,
        total_tokens: 0,
        task_count: 0,
      }
    }
    result[key].request_count += Number(row.request_count || 0)
    result[key].success_count += Number(row.success_count || 0)
    result[key].failure_count += Number(row.failure_count || 0)
    result[key].total_tokens += Number(row.total_tokens || 0)
    result[key].task_count += Number(row.task_count || 0)
    return result
  }, {})

  return rangeDates.value.map((date) => {
    const existing = byDate[date]
    return (
      existing || {
        usage_date: date,
        request_count: 0,
        success_count: 0,
        failure_count: 0,
        total_tokens: 0,
        task_count: 0,
      }
    )
  })
})

const metricBreakdownRows = computed(() => {
  const byMetric = usageRows.value.reduce<Record<string, any>>((result, row) => {
    const key = row.metric || '-'
    if (!result[key]) {
      result[key] = {
        metric: key,
        metric_label: metricLabel(key),
        request_count: 0,
        success_count: 0,
        failure_count: 0,
        total_tokens: 0,
        task_count: 0,
      }
    }
    result[key].request_count += Number(row.request_count || 0)
    result[key].success_count += Number(row.success_count || 0)
    result[key].failure_count += Number(row.failure_count || 0)
    result[key].total_tokens += Number(row.total_tokens || 0)
    result[key].task_count += Number(row.task_count || 0)
    return result
  }, {})

  return Object.values(byMetric)
    .sort((a, b) => b.total_tokens - a.total_tokens || b.request_count - a.request_count)
    .slice(0, 8)
})

const formatNumber = (value?: number | string) => Number(value || 0).toLocaleString()

const formatPercent = (value: number) => `${(value * 100).toFixed(value * 100 >= 10 ? 1 : 2)}%`

const metricLabel = (metric?: string) => {
  if (!metric) return '-'
  return metricLabelMap.value[metric] || metric
}

const userLabel = (row: TenantUsageUserInfo) => {
  const account = row.user_account || ''
  const name = row.user_name || ''
  if (name && account) return `${name} (${account})`
  return name || account || `#${row.user_id}`
}

const userUsageRows = computed(() =>
  rawUserUsageRows.value.map((row) => ({
    ...row,
    user_label: userLabel(row),
  }))
)

const userChartRows = computed(() => userUsageRows.value.slice(0, 12))

const formatUsageTime = (value?: number | string) => {
  const timestamp = Number(value || 0)
  return timestamp ? formatTimestamp(timestamp, 'YYYY-MM-DD HH:mm:ss') : '-'
}

const averageDailyRequests = computed(() =>
  dailyRows.value.length ? summary.value.request_count / dailyRows.value.length : 0
)

const averageDailyTasks = computed(() =>
  dailyRows.value.length ? summary.value.task_count / dailyRows.value.length : 0
)

const successRateValue = computed(() =>
  summary.value.request_count > 0 ? summary.value.success_count / summary.value.request_count : 0
)

const failureRateValue = computed(() =>
  summary.value.request_count > 0 ? summary.value.failure_count / summary.value.request_count : 0
)

const tokenPerRequest = computed(() =>
  summary.value.request_count > 0 ? summary.value.total_tokens / summary.value.request_count : 0
)

const activeDayCount = computed(() =>
  dailyRows.value.filter(
    (row) =>
      Number(row.request_count || 0) > 0 ||
      Number(row.total_tokens || 0) > 0 ||
      Number(row.task_count || 0) > 0
  ).length
)

const dateRangeLabel = computed(() => {
  const [startDate, endDate] = dateRange.value || []
  if (!startDate || !endDate) return '-'
  return `${startDate} ${t('tenant_usage.to')} ${endDate}`
})

const overviewHighlights = computed(() => [
  {
    label: t('tenant_usage.active_users'),
    value: formatNumber(userUsageRows.value.length),
  },
  {
    label: t('tenant_usage.token_per_request'),
    value: formatNumber(Math.round(tokenPerRequest.value)),
  },
  {
    label: t('tenant_usage.active_days'),
    value: formatNumber(activeDayCount.value),
  },
])

const createSparkline = (values: number[]) => {
  if (!values.length) {
    return { path: '', areaPath: '' }
  }

  const max = Math.max(...values)
  const min = Math.min(...values)
  const range = max - min
  const step = values.length === 1 ? 100 : 100 / (values.length - 1)

  const points = values.map((value, index) => {
    const x = Number((index * step).toFixed(2))
    const y =
      range === 0
        ? 16
        : Number((26 - ((value - min) / range) * 20).toFixed(2))
    return { x, y }
  })

  const path = points
    .map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`)
    .join(' ')
  const areaPath = `${path} L ${points[points.length - 1].x} 32 L ${points[0].x} 32 Z`

  return { path, areaPath }
}

const summaryItems = computed(() => {
  const items = [
    {
      key: 'request_count',
      label: t('tenant_usage.requests'),
      value: summary.value.request_count,
      note: `${t('tenant_usage.daily_average')} ${formatNumber(Math.round(averageDailyRequests.value))}`,
      trend: dailyRows.value.map((row) => Number(row.request_count || 0)),
      color: '#2f6bff',
      softColor: 'rgba(47, 107, 255, 0.12)',
      icon: icon_chart_preview,
    },
    {
      key: 'success_count',
      label: t('tenant_usage.success'),
      value: summary.value.success_count,
      note: `${t('tenant_usage.success_rate')} ${formatPercent(successRateValue.value)}`,
      trend: dailyRows.value.map((row) => Number(row.success_count || 0)),
      color: '#39c98a',
      softColor: 'rgba(57, 201, 138, 0.14)',
      icon: icon_done_outlined,
    },
    {
      key: 'failure_count',
      label: t('tenant_usage.failure'),
      value: summary.value.failure_count,
      note: `${t('tenant_usage.failure_share')} ${formatPercent(failureRateValue.value)}`,
      trend: dailyRows.value.map((row) => Number(row.failure_count || 0)),
      color: '#f56c6c',
      softColor: 'rgba(245, 108, 108, 0.14)',
      icon: icon_error,
    },
    {
      key: 'task_count',
      label: t('tenant_usage.tasks'),
      value: summary.value.task_count,
      note: `${t('tenant_usage.daily_average')} ${formatNumber(Math.round(averageDailyTasks.value))}`,
      trend: dailyRows.value.map((row) => Number(row.task_count || 0)),
      color: '#f5b74f',
      softColor: 'rgba(245, 183, 79, 0.16)',
      icon: icon_dashboard_outlined,
    },
  ]

  return items.map((item) => ({
    ...item,
    ...createSparkline(item.trend),
  }))
})

const dateAxis = computed<ChartAxis[]>(() => [
  { name: t('tenant_usage.usage_date'), value: 'usage_date' },
])

const requestTrendAxis = computed<ChartAxis[]>(() => [
  { name: t('tenant_usage.requests'), value: 'request_count', 'multi-quota': true },
  { name: t('tenant_usage.failure'), value: 'failure_count', 'multi-quota': true },
])

const tokenTrendAxis = computed<ChartAxis[]>(() => [
  { name: t('tenant_usage.tokens'), value: 'total_tokens' },
])

const metricBreakdownXAxis = computed<ChartAxis[]>(() => [
  { name: t('tenant_usage.metric'), value: 'metric_label' },
])

const metricBreakdownYAxis = computed<ChartAxis[]>(() => [
  { name: t('tenant_usage.tokens'), value: 'total_tokens' },
])

const userTokenXAxis = computed<ChartAxis[]>(() => [
  { name: t('tenant_usage.user'), value: 'user_label' },
])

const userTokenYAxis = computed<ChartAxis[]>(() => [
  { name: t('tenant_usage.tokens'), value: 'total_tokens' },
])

const loadUsage = async () => {
  loading.value = true
  try {
    const [startDate, endDate] = dateRange.value || []
    const query = {
      start_date: startDate,
      end_date: endDate,
    }
    const [dailyRowsResult, userRowsResult] = await Promise.all([
      tenantApi.usage({
        ...query,
        limit: 1000,
      }),
      tenantApi.usageByUser({
        ...query,
        limit: 100,
      }),
    ])
    usageRows.value = dailyRowsResult
    rawUserUsageRows.value = userRowsResult
  } finally {
    loading.value = false
  }
}

const resetFilters = () => {
  dateRange.value = [dayjs().subtract(6, 'day').format('YYYY-MM-DD'), dayjs().format('YYYY-MM-DD')]
  loadUsage()
}

onMounted(async () => {
  await loadUsage()
})
</script>

<style lang="less" scoped>
.tenant-usage-container {
  width: 100%;
  height: 100%;
  position: relative;
  color-scheme: light;

  .tool-left {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 16px;

    .page-title {
      flex: 0 0 auto;
      font-weight: 500;
      font-size: 20px;
      line-height: 28px;
    }

    &.is-embedded {
      justify-content: flex-end;

      .page-title {
        display: none;
      }
    }
  }

  .toolbar {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    flex-wrap: wrap;
    gap: 10px;
  }

  .current-tenant {
    max-width: 220px;
    height: 32px;
    display: flex;
    align-items: center;
    padding: 0 12px;
    border: 1px solid #dee0e3;
    border-radius: 6px;
    color: #1f2329;
    background: #f8f9fb;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .overview-shell {
    margin-bottom: 16px;
  }

  .overview-panel {
    display: grid;
    grid-template-columns: minmax(260px, 320px) minmax(0, 1fr);
    gap: 16px;
    padding: 18px;
    border: 1px solid #e2eaf4;
    border-radius: 8px;
    background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
    box-shadow:
      0 18px 42px rgba(24, 46, 86, 0.05),
      0 3px 10px rgba(24, 46, 86, 0.04);
  }

  .overview-copy {
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    gap: 16px;
    min-width: 0;
  }

  .overview-kicker {
    color: #5c7cfa;
    font-size: 12px;
    font-weight: 600;
    line-height: 18px;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }

  .overview-title-row {
    display: flex;
    flex-direction: column;
    gap: 10px;

    h2 {
      color: #1b2a41;
      font-size: 26px;
      font-weight: 600;
      line-height: 34px;
      word-break: break-word;
    }
  }

  .overview-range {
    width: fit-content;
    padding: 6px 10px;
    border-radius: 999px;
    background: #eef4ff;
    color: #4e6fb8;
    font-size: 12px;
    line-height: 18px;
  }

  .overview-subtitle {
    color: #6b7a90;
    font-size: 14px;
    line-height: 22px;
  }

  .overview-total {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 16px 18px;
    border: 1px solid #dfe9fb;
    border-radius: 8px;
    background: linear-gradient(180deg, rgba(91, 143, 249, 0.08) 0%, rgba(91, 143, 249, 0.02) 100%);

    strong {
      color: #1b2a41;
      font-size: 34px;
      font-weight: 700;
      line-height: 40px;
      word-break: break-word;
    }
  }

  .overview-total-label {
    color: #4f6fb7;
    font-size: 12px;
    font-weight: 600;
    line-height: 18px;
  }

  .overview-highlights {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 10px;
  }

  .overview-highlight {
    min-width: 0;
    padding: 12px;
    border: 1px solid #edf2f8;
    border-radius: 8px;
    background: rgba(255, 255, 255, 0.88);
    display: flex;
    flex-direction: column;
    gap: 6px;

    strong {
      color: #1b2a41;
      font-size: 18px;
      font-weight: 600;
      line-height: 26px;
    }
  }

  .overview-highlight-label {
    color: #8a97aa;
    font-size: 12px;
    line-height: 18px;
  }

  .overview-visual,
  .chart-card {
    min-width: 0;
    border: 1px solid #e6edf6;
    border-radius: 8px;
    background: #ffffff;
    overflow: hidden;
  }

  .overview-visual {
    padding: 14px 16px 12px;
  }

  .chart-card {
    padding: 14px 16px 12px;
  }

  .chart-card-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 12px;
    color: #1f2329;
    font-size: 14px;
    font-weight: 600;
    line-height: 22px;
  }

  .chart-surface {
    height: 248px;
    border-radius: 8px;
    background: linear-gradient(180deg, #fcfdff 0%, #f7faff 100%);
    overflow: hidden;
  }

  .chart-surface-hero {
    height: 320px;
  }

  .hero-empty-state {
    position: relative;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
  }

  .hero-empty-grid {
    position: absolute;
    inset: 18px 20px 20px 18px;
    display: grid;
    grid-template-rows: repeat(4, 1fr);
    pointer-events: none;
  }

  .hero-empty-grid-line {
    border-top: 1px dashed rgba(114, 136, 178, 0.16);
  }

  .hero-empty-trace {
    position: absolute;
    left: 22px;
    right: 22px;
    bottom: 28px;
    height: 118px;
    width: calc(100% - 44px);
    pointer-events: none;
  }

  .hero-empty-area {
    fill: rgba(91, 124, 250, 0.08);
  }

  .hero-empty-line {
    fill: none;
    stroke: #b7cbff;
    stroke-width: 2;
    stroke-linecap: round;
    stroke-linejoin: round;
  }

  .hero-empty-axis {
    position: absolute;
    left: 22px;
    right: 22px;
    bottom: 18px;
    height: 14px;
    pointer-events: none;
  }

  .hero-empty-axis-line {
    position: absolute;
    left: 0;
    right: 0;
    bottom: 0;
    height: 1px;
    background: rgba(114, 136, 178, 0.2);
  }

  .hero-empty-axis-ticks {
    position: absolute;
    inset: 0 0 0 0;
    display: grid;
    grid-template-columns: repeat(7, 1fr);

    span {
      justify-self: start;
      align-self: end;
      width: 1px;
      height: 6px;
      background: rgba(114, 136, 178, 0.18);
    }
  }

  .hero-empty-copy {
    position: relative;
    z-index: 1;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .hero-empty-pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    border: 1px solid rgba(91, 124, 250, 0.16);
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.92);
    box-shadow: 0 10px 28px rgba(24, 46, 86, 0.08);
    color: #66758d;
    font-size: 13px;
    line-height: 20px;
  }

  .hero-empty-dot {
    width: 6px;
    height: 6px;
    border-radius: 999px;
    background: #8fb0ff;
    box-shadow: 0 0 0 4px rgba(91, 124, 250, 0.08);
  }

  .summary-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(180px, 1fr));
    gap: 12px;
    margin-bottom: 18px;
  }

  .summary-item {
    min-width: 0;
    border: 1px solid #e2eaf4;
    border-radius: 8px;
    padding: 14px 14px 12px;
    background: #ffffff;
    box-shadow: 0 10px 24px rgba(17, 37, 73, 0.05);
  }

  .summary-top {
    display: flex;
    align-items: flex-start;
    gap: 12px;
  }

  .summary-icon {
    flex: 0 0 auto;
    width: 36px;
    height: 36px;
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--summary-soft-color);
    color: var(--summary-color);

    :deep(svg) {
      width: 18px;
      height: 18px;
    }
  }

  .summary-meta {
    min-width: 0;
  }

  .summary-label {
    color: #5b6676;
    font-size: 12px;
    line-height: 18px;
  }

  .summary-note {
    margin-top: 2px;
    color: #9aa6b8;
    font-size: 12px;
    line-height: 18px;
  }

  .summary-value {
    margin-top: 14px;
    color: #1b2a41;
    font-size: 28px;
    font-weight: 600;
    line-height: 34px;
  }

  .summary-sparkline {
    height: 42px;
    margin-top: 10px;

    svg {
      width: 100%;
      height: 100%;
      overflow: visible;
    }
  }

  .sparkline-area {
    fill: var(--summary-soft-color);
    stroke: none;
  }

  .sparkline-line {
    fill: none;
    stroke: var(--summary-color);
    stroke-width: 2;
    stroke-linecap: round;
    stroke-linejoin: round;
  }

  .analytics-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 16px;
    margin-bottom: 18px;
  }

  .section-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin: 8px 0 10px;
    font-size: 15px;
    font-weight: 600;
    line-height: 22px;
    color: #1f2329;
  }

  .muted {
    color: #8f959e;
    font-size: 12px;
    font-weight: 400;
  }

  .usage-table {
    max-height: calc(100vh - 340px);
    overflow-y: auto;
  }

  .user-cell {
    display: flex;
    flex-direction: column;
    min-width: 0;
    line-height: 20px;
  }

  .user-key {
    color: #8f959e;
    font-size: 12px;
  }

  .danger {
    color: #d93026;
    font-weight: 500;
  }
}

@media (max-width: 1280px) {
  .tenant-usage-container {
    .summary-grid {
      grid-template-columns: repeat(2, minmax(180px, 1fr));
    }

    .analytics-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }
}

@media (max-width: 1100px) {
  .tenant-usage-container {
    .tool-left {
      align-items: flex-start;
      flex-direction: column;
    }

    .toolbar {
      justify-content: flex-start;
    }

    .overview-panel {
      grid-template-columns: 1fr;
    }

    .overview-highlights {
      grid-template-columns: 1fr;
    }

    .summary-grid,
    .analytics-grid {
      grid-template-columns: 1fr;
    }
  }
}
</style>
