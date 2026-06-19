<template>
  <div class="tenant-overview-container professional-container">
    <div class="tool-left">
      <div class="title-block">
        <span class="page-title">{{ t('tenant_overview.title') }}</span>
        <p class="page-subtitle">{{ t('tenant_overview.subtitle') }}</p>
      </div>
      <div class="toolbar">
        <el-radio-group v-model="selectedDays" class="range-group" size="default" @change="loadOverview">
          <el-radio-button v-for="item in rangeOptions" :key="item.value" :label="item.value">
            {{ item.label }}
          </el-radio-button>
        </el-radio-group>
        <el-button secondary :loading="loading" @click="refreshOverview">
          <template #icon>
            <icon_refresh_outlined />
          </template>
          {{ t('common.refresh') }}
        </el-button>
      </div>
    </div>

    <section class="hero-panel">
      <div class="hero-copy">
        <div class="hero-copy-top">
          <div class="hero-kicker">{{ t('tenant_overview.current_tenant') }}</div>
          <div class="hero-title-row">
            <h2>{{ overview?.tenant_name || userStore.getTenantName || '-' }}</h2>
            <span class="hero-range">{{ selectedRangeLabel }}</span>
          </div>
          <p class="hero-note">{{ t('tenant_overview.activity_hint') }}</p>
        </div>
        <div class="hero-highlight-row">
          <div class="hero-highlight">
            <span>{{ t('tenant_overview.summary_active_members') }}</span>
            <strong>{{ formatNumber(summary.active_member_count) }}</strong>
          </div>
          <div class="hero-highlight">
            <span>{{ t('tenant_overview.summary_pending') }}</span>
            <strong :class="{ danger: summary.pending_member_application_count > 0 }">
              {{ formatNumber(summary.pending_member_application_count) }}
            </strong>
          </div>
        </div>
        <div class="hero-focus-card">
          <div class="hero-focus-head">
            <span>{{ t('tenant_overview.todos_title') }}</span>
            <span class="muted">{{ t('tenant_overview.todos_hint') }}</span>
          </div>
          <div v-if="heroFocusItems.length" class="hero-focus-list">
            <div v-for="item in heroFocusItems" :key="item.key" class="hero-focus-item">
              <span :class="['todo-level', `is-${item.level || 'normal'}`]">
                {{ todoLevelLabel(item.level) }}
              </span>
              <span class="hero-focus-text">{{ todoLabel(item.key) }}</span>
              <strong v-if="item.count !== undefined && item.count !== null" class="hero-focus-count">
                {{ formatNumber(item.count) }}
              </strong>
            </div>
          </div>
          <div v-else class="hero-focus-empty">
            {{ todoLabel('space_ready') }}
          </div>
        </div>
      </div>
      <div class="hero-chart">
        <div class="chart-card-head">
          <span>{{ t('tenant_overview.activity_title') }}</span>
          <span class="muted">{{ selectedRangeLabel }}</span>
        </div>
        <div class="chart-surface chart-surface-hero">
          <ChartComponent
            v-if="activityTrendRows.length"
            :id="'tenant-overview-activity-hero'"
            type="line"
            :data="activityTrendRows"
            :x="activityXAxis"
            :y="activityYAxis"
            :show-label="true"
          />
          <EmptyBackground v-else :description="t('tenant_overview.empty')" img-type="tree" />
        </div>
      </div>
    </section>

    <div class="summary-grid">
      <div
        v-for="item in summaryCards"
        :key="item.key"
        class="summary-card"
        :style="{
          '--card-color': item.color,
          '--card-soft-color': item.softColor,
        }"
      >
        <div class="summary-card-top">
          <div class="summary-icon">
            <component :is="item.icon" />
          </div>
          <div class="summary-meta">
            <div class="summary-label">{{ item.label }}</div>
            <div class="summary-note">{{ item.note }}</div>
          </div>
        </div>
        <div class="summary-value" :class="{ danger: item.emphasize }">{{ formatNumber(item.value) }}</div>
      </div>
    </div>

    <div class="analytics-grid">
      <section class="chart-card chart-card-wide">
        <div class="chart-card-head">
          <span>{{ t('tenant_overview.activity_title') }}</span>
          <span class="muted">{{ t('tenant_overview.activity_hint') }}</span>
        </div>
        <div class="chart-surface">
          <ChartComponent
            v-if="activityTrendRows.length"
            :id="'tenant-overview-activity'"
            type="line"
            :data="activityTrendRows"
            :x="activityXAxis"
            :y="activityYAxis"
          />
          <EmptyBackground v-else :description="t('tenant_overview.empty')" img-type="tree" />
        </div>
      </section>

      <section class="chart-card">
        <div class="chart-card-head">
          <span>{{ t('tenant_overview.assets_title') }}</span>
          <span class="muted">{{ t('tenant_overview.assets_hint') }}</span>
        </div>
        <div class="chart-surface">
          <ChartComponent
            v-if="assetRows.length"
            :id="'tenant-overview-assets'"
            type="bar"
            :data="assetRows"
            :x="assetXAxis"
            :y="assetYAxis"
            :show-label="true"
          />
          <EmptyBackground v-else :description="t('tenant_overview.empty')" img-type="tree" />
        </div>
      </section>

      <section class="chart-card">
        <div class="chart-card-head">
          <span>{{ t('tenant_overview.roles_title') }}</span>
          <span class="muted">{{ t('tenant_overview.roles_hint') }}</span>
        </div>
        <div class="chart-surface">
          <ChartComponent
            v-if="roleRows.length"
            :id="'tenant-overview-roles'"
            type="pie"
            :data="roleRows"
            :y="roleYAxis"
            :series="roleSeries"
            :show-label="true"
          />
          <EmptyBackground v-else :description="t('tenant_overview.empty')" img-type="tree" />
        </div>
      </section>
    </div>

    <div class="ops-grid">
      <section class="ops-card">
        <div class="chart-card-head">
          <span>{{ t('tenant_overview.todos_title') }}</span>
          <span class="muted">{{ t('tenant_overview.todos_hint') }}</span>
        </div>
        <div v-if="todoRows.length" class="todo-list">
          <div v-for="item in todoRows" :key="item.key" class="todo-item">
            <div class="todo-main">
              <div class="todo-title">{{ todoLabel(item.key) }}</div>
              <div class="todo-meta">
                <span :class="['todo-level', `is-${item.level}`]">{{ todoLevelLabel(item.level) }}</span>
                <span v-if="item.count !== undefined && item.count !== null" class="todo-count">
                  {{ formatNumber(item.count) }} {{ t('tenant_overview.todo_count_suffix') }}
                </span>
              </div>
            </div>
            <el-button v-if="item.route" text @click="goRoute(item.route)">
              {{ t('tenant_overview.jump_to') }}
            </el-button>
          </div>
        </div>
        <EmptyBackground v-else :description="t('tenant_overview.empty')" img-type="tree" />
      </section>

      <section class="ops-card ops-card-wide">
        <div class="chart-card-head">
          <span>{{ t('tenant_overview.events_title') }}</span>
          <span class="muted">{{ t('tenant_overview.events_hint') }}</span>
        </div>
        <div v-if="recentEvents.length" class="event-list">
          <div v-for="item in recentEvents" :key="item.id" class="event-item">
            <div class="event-time">{{ formatEventTime(item.create_time) }}</div>
            <div class="event-content">
              <div class="event-title">{{ item.title }}</div>
              <div v-if="item.description" class="event-description">{{ item.description }}</div>
              <div class="event-meta">
                <span v-if="item.operator_name">{{ t('tenant_overview.event_operator') }}: {{ item.operator_name }}</span>
                <span v-if="item.module">{{ t('tenant_overview.event_module') }}: {{ item.module }}</span>
              </div>
            </div>
          </div>
        </div>
        <EmptyBackground v-else :description="t('tenant_overview.empty')" img-type="tree" />
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, shallowRef } from 'vue'
import { ElMessage } from 'element-plus-secondary'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import icon_refresh_outlined from '@/assets/embedded/icon_refresh_outlined.svg'
import icon_chart_preview from '@/assets/svg/icon_chart_preview.svg'
import icon_done_outlined from '@/assets/svg/icon_done_outlined.svg'
import icon_error from '@/assets/svg/icon_error.svg'
import icon_user from '@/assets/svg/icon_user.svg'
import icon_dashboard_outlined from '@/assets/svg/chart/icon_dashboard_outlined.svg'
import EmptyBackground from '@/views/dashboard/common/EmptyBackground.vue'
import ChartComponent from '@/views/chat/component/ChartComponent.vue'
import { tenantApi, type TenantOverviewInfo } from '@/api/tenant'
import type { ChartAxis } from '@/views/chat/component/BaseChart.ts'
import { useUserStore } from '@/stores/user'
import { formatTimestamp } from '@/utils/date'

const { t } = useI18n()
const router = useRouter()
const userStore = useUserStore()

const loading = ref(false)
const selectedDays = ref(7)
const overview = shallowRef<TenantOverviewInfo | null>(null)

const rangeOptions = computed(() => [
  { value: 7, label: t('tenant_overview.range_7') },
  { value: 14, label: t('tenant_overview.range_14') },
  { value: 30, label: t('tenant_overview.range_30') },
])

const selectedRangeLabel = computed(
  () => rangeOptions.value.find((item) => item.value === selectedDays.value)?.label || t('tenant_overview.range_7')
)

const summary = computed(
  () =>
    overview.value?.summary || {
      member_total: 0,
      active_member_count: 0,
      datasource_total: 0,
      dashboard_total: 0,
      pending_member_application_count: 0,
    }
)

const activityTrendRows = computed(() => overview.value?.activity_trend || [])

const assetRows = computed(() =>
  (overview.value?.assets || [])
    .map((item) => ({
      key: item.key,
      label: assetLabel(item.key),
      count: Number(item.count || 0),
    }))
    .sort((prev, next) => next.count - prev.count)
)

const roleRows = computed(() =>
  (overview.value?.role_distribution || [])
    .map((item) => ({
      role: item.role,
      label: roleLabel(item.role),
      count: Number(item.count || 0),
    }))
    .filter((item) => item.count > 0)
)

const todoRows = computed(() => overview.value?.todos || [])
const recentEvents = computed(() => overview.value?.recent_events || [])
const heroFocusItems = computed(() => todoRows.value.slice(0, 2))

const summaryCards = computed(() => [
  {
    key: 'member_total',
    label: t('tenant_overview.summary_members'),
    note: t('tenant_overview.roles_hint'),
    value: summary.value.member_total,
    icon: icon_user,
    color: '#2f6bff',
    softColor: 'rgba(47, 107, 255, 0.12)',
    emphasize: false,
  },
  {
    key: 'active_member_count',
    label: t('tenant_overview.summary_active_members'),
    note: t('tenant_overview.summary_active_hint', { days: selectedDays.value }),
    value: summary.value.active_member_count,
    icon: icon_done_outlined,
    color: '#39c98a',
    softColor: 'rgba(57, 201, 138, 0.14)',
    emphasize: false,
  },
  {
    key: 'datasource_total',
    label: t('tenant_overview.summary_datasources'),
    note: t('tenant_overview.summary_datasource_hint'),
    value: summary.value.datasource_total,
    icon: icon_chart_preview,
    color: '#f5b74f',
    softColor: 'rgba(245, 183, 79, 0.16)',
    emphasize: false,
  },
  {
    key: 'dashboard_total',
    label: t('tenant_overview.summary_dashboards'),
    note: t('tenant_overview.summary_dashboard_hint'),
    value: summary.value.dashboard_total,
    icon: icon_dashboard_outlined,
    color: '#8c6bff',
    softColor: 'rgba(140, 107, 255, 0.14)',
    emphasize: false,
  },
  {
    key: 'pending_member_application_count',
    label: t('tenant_overview.summary_pending'),
    note: t('tenant_overview.summary_pending_hint'),
    value: summary.value.pending_member_application_count,
    icon: icon_error,
    color: '#f56c6c',
    softColor: 'rgba(245, 108, 108, 0.14)',
    emphasize: summary.value.pending_member_application_count > 0,
  },
])

const activityXAxis = computed<ChartAxis[]>(() => [{ name: 'date', value: 'date' }])
const activityYAxis = computed<ChartAxis[]>(() => [
  { name: t('tenant_overview.trend_active_members'), value: 'active_member_count', 'multi-quota': true },
  { name: t('tenant_overview.trend_login_count'), value: 'login_count', 'multi-quota': true },
])
const assetXAxis = computed<ChartAxis[]>(() => [{ name: t('tenant_overview.assets_title'), value: 'label' }])
const assetYAxis = computed<ChartAxis[]>(() => [{ name: 'count', value: 'count' }])
const roleYAxis = computed<ChartAxis[]>(() => [{ name: 'count', value: 'count' }])
const roleSeries = computed<ChartAxis[]>(() => [{ name: 'role', value: 'label' }])

const formatNumber = (value?: number | string) => Number(value || 0).toLocaleString()

const roleLabel = (role?: string) => {
  if (role === 'owner') return t('tenant_overview.role_owner')
  if (role === 'admin') return t('tenant_overview.role_admin')
  return t('tenant_overview.role_member')
}

const assetLabel = (key?: string) => {
  switch (key) {
    case 'datasource':
      return t('tenant_overview.asset_datasource')
    case 'dashboard':
      return t('tenant_overview.asset_dashboard')
    case 'terminology':
      return t('tenant_overview.asset_terminology')
    case 'training':
      return t('tenant_overview.asset_training')
    case 'custom_agent':
      return t('tenant_overview.asset_custom_agent')
    case 'embedded':
      return t('tenant_overview.asset_embedded')
    default:
      return key || '-'
  }
}

const todoLabel = (key?: string) => {
  switch (key) {
    case 'pending_member_application_count':
      return t('tenant_overview.todo_pending_member_application_count')
    case 'missing_datasource':
      return t('tenant_overview.todo_missing_datasource')
    case 'missing_dashboard':
      return t('tenant_overview.todo_missing_dashboard')
    case 'unverified_domain':
      return t('tenant_overview.todo_unverified_domain')
    case 'space_ready':
      return t('tenant_overview.todo_space_ready')
    default:
      return key || '-'
  }
}

const todoLevelLabel = (level?: string) => {
  switch (level) {
    case 'warning':
      return t('tenant_overview.todo_level_warning')
    case 'attention':
      return t('tenant_overview.todo_level_attention')
    case 'healthy':
      return t('tenant_overview.todo_level_healthy')
    default:
      return t('tenant_overview.todo_level_normal')
  }
}

const formatEventTime = (timestamp?: number) => formatTimestamp(Number(timestamp || 0), 'YYYY-MM-DD HH:mm:ss')

const goRoute = (path: string) => {
  router.push(path)
}

const loadOverview = async () => {
  loading.value = true
  try {
    overview.value = await tenantApi.overview(selectedDays.value)
  } finally {
    loading.value = false
  }
}

const refreshOverview = async () => {
  await loadOverview()
  ElMessage.success(t('tenant_overview.refresh_success'))
}

onMounted(async () => {
  await loadOverview()
})
</script>

<style scoped lang="less">
.tenant-overview-container {
  width: 100%;
  height: 100%;
  position: relative;
  color-scheme: light;

  .tool-left {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 20px;
    margin-bottom: 16px;
  }

  .title-block {
    min-width: 0;
  }

  .page-title {
    display: block;
    font-size: 20px;
    line-height: 28px;
    font-weight: 500;
    color: var(--theme-text-primary);
  }

  .page-subtitle {
    margin: 6px 0 0;
    font-size: 13px;
    line-height: 20px;
    color: var(--theme-text-secondary);
  }

  .toolbar {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    flex-wrap: wrap;
    gap: 10px;
  }

  .range-group {
    :deep(.el-radio-button__inner) {
      min-width: 78px;
    }
  }

  .hero-panel {
    display: grid;
    grid-template-columns: minmax(320px, 360px) minmax(0, 1fr);
    gap: 16px;
    margin-bottom: 18px;
  }

  .hero-chart,
  .chart-card,
  .ops-card,
  .summary-card {
    background: var(--theme-card-bg, #ffffff);
    border: 1px solid var(--theme-border-color, #ebeef5);
    border-radius: 8px;
    box-shadow: 0 10px 30px rgba(15, 23, 42, 0.04);
  }

  .hero-copy {
    min-height: 320px;
    padding: 18px;
    background:
      linear-gradient(180deg, rgba(248, 251, 255, 0.98), rgba(243, 248, 255, 0.98)),
      var(--theme-card-bg, #ffffff);
    border: 1px solid #e2eaf4;
    border-radius: 8px;
    box-shadow: 0 10px 30px rgba(15, 23, 42, 0.04);
    display: flex;
    flex-direction: column;
    gap: 14px;
  }

  .hero-copy-top {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .hero-kicker {
    display: inline-flex;
    align-items: center;
    width: fit-content;
    height: 24px;
    padding: 0 10px;
    border-radius: 999px;
    background: rgba(47, 107, 255, 0.1);
    color: #2f6bff;
    font-size: 12px;
    line-height: 24px;
    font-weight: 600;
  }

  .hero-title-row {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;

    h2 {
      margin: 0;
      font-size: 28px;
      line-height: 36px;
      font-weight: 600;
      color: var(--theme-text-primary);
      word-break: break-word;
    }
  }

  .hero-range {
    flex: 0 0 auto;
    padding: 6px 12px;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.88);
    color: var(--theme-text-secondary);
    font-size: 12px;
    line-height: 18px;
    border: 1px solid rgba(222, 232, 246, 0.9);
  }

  .hero-note {
    margin: 0;
    font-size: 14px;
    line-height: 22px;
    color: var(--theme-text-secondary);
  }

  .hero-highlight-row {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
  }

  .hero-highlight {
    padding: 14px 16px;
    border-radius: 8px;
    background: rgba(255, 255, 255, 0.92);
    border: 1px solid #e6edf6;

    span {
      display: block;
      font-size: 12px;
      line-height: 18px;
      color: var(--theme-text-secondary);
    }

    strong {
      display: block;
      margin-top: 8px;
      font-size: 26px;
      line-height: 32px;
      color: var(--theme-text-primary);
    }
  }

  .hero-focus-card {
    flex: 1 1 auto;
    min-height: 0;
    padding: 14px 16px;
    border-radius: 8px;
    background: rgba(255, 255, 255, 0.94);
    border: 1px solid #e6edf6;
    display: flex;
    flex-direction: column;
  }

  .hero-focus-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    color: var(--theme-text-primary);
    font-size: 14px;
    line-height: 22px;
    font-weight: 500;
  }

  .hero-focus-list {
    display: flex;
    flex-direction: column;
    gap: 10px;
    margin-top: 12px;
  }

  .hero-focus-item {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    border-radius: 8px;
    background: #f8fbff;
    border: 1px solid #edf2f8;
  }

  .hero-focus-text {
    min-width: 0;
    font-size: 13px;
    line-height: 20px;
    color: var(--theme-text-primary);
    word-break: break-word;
  }

  .hero-focus-count {
    color: var(--theme-text-primary);
    font-size: 18px;
    line-height: 24px;
    font-weight: 600;
  }

  .hero-focus-empty {
    flex: 1 1 auto;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--theme-text-secondary);
    font-size: 13px;
    line-height: 20px;
    text-align: center;
  }

  .hero-chart {
    padding: 18px;
    min-height: 320px;
    display: flex;
    flex-direction: column;
  }

  .summary-grid {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 16px;
    margin-bottom: 18px;
  }

  .summary-card {
    padding: 18px;
    min-height: 148px;
    background:
      linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(255, 255, 255, 0.94)),
      var(--theme-card-bg, #ffffff);
  }

  .summary-card-top {
    display: flex;
    align-items: flex-start;
    gap: 12px;
  }

  .summary-icon {
    width: 42px;
    height: 42px;
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--card-soft-color);
    color: var(--card-color);
    flex: 0 0 auto;

    :deep(svg) {
      width: 20px;
      height: 20px;
    }

    :deep(path) {
      fill: currentColor;
    }
  }

  .summary-meta {
    min-width: 0;
  }

  .summary-label {
    font-size: 14px;
    line-height: 22px;
    font-weight: 500;
    color: var(--theme-text-primary);
  }

  .summary-note {
    margin-top: 4px;
    font-size: 12px;
    line-height: 18px;
    color: var(--theme-text-secondary);
  }

  .summary-value {
    margin-top: 24px;
    font-size: 30px;
    line-height: 36px;
    font-weight: 600;
    color: var(--theme-text-primary);
  }

  .danger {
    color: #f56c6c !important;
  }

  .analytics-grid {
    display: grid;
    grid-template-columns: minmax(0, 1.2fr) minmax(300px, 0.9fr) minmax(300px, 0.9fr);
    gap: 16px;
    margin-bottom: 18px;
  }

  .chart-card {
    padding: 18px;
    min-height: 360px;
  }

  .chart-card-wide {
    min-width: 0;
  }

  .chart-card-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 14px;
    color: var(--theme-text-primary);
    font-size: 15px;
    line-height: 22px;
    font-weight: 500;
  }

  .muted {
    color: var(--theme-text-secondary);
    font-size: 12px;
    line-height: 18px;
    font-weight: 400;
  }

  .chart-surface {
    height: 300px;
  }

  .chart-surface-hero {
    flex: 1 1 auto;
    min-height: 252px;
    height: auto;
  }

  .ops-grid {
    display: grid;
    grid-template-columns: minmax(320px, 0.85fr) minmax(0, 1.15fr);
    gap: 16px;
  }

  .ops-card {
    padding: 18px;
    min-height: 320px;
  }

  .ops-card-wide {
    min-width: 0;
  }

  .todo-list,
  .event-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .todo-item,
  .event-item {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    padding: 14px 16px;
    border-radius: 8px;
    background: var(--theme-hover-bg, #f8fafc);
    border: 1px solid rgba(15, 23, 42, 0.05);
  }

  .todo-main,
  .event-content {
    min-width: 0;
    flex: 1 1 auto;
  }

  .todo-title,
  .event-title {
    font-size: 14px;
    line-height: 22px;
    font-weight: 500;
    color: var(--theme-text-primary);
  }

  .todo-meta,
  .event-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    margin-top: 6px;
    font-size: 12px;
    line-height: 18px;
    color: var(--theme-text-secondary);
  }

  .todo-level {
    display: inline-flex;
    align-items: center;
    height: 24px;
    padding: 0 10px;
    border-radius: 999px;
    font-weight: 500;

    &.is-warning {
      background: rgba(245, 108, 108, 0.12);
      color: #f56c6c;
    }

    &.is-attention {
      background: rgba(245, 183, 79, 0.15);
      color: #b97a00;
    }

    &.is-healthy {
      background: rgba(57, 201, 138, 0.14);
      color: #1f9f66;
    }

    &.is-normal {
      background: rgba(47, 107, 255, 0.12);
      color: #2f6bff;
    }
  }

  .event-time {
    flex: 0 0 142px;
    font-size: 12px;
    line-height: 18px;
    color: var(--theme-text-secondary);
    padding-top: 2px;
  }

  .event-description {
    margin-top: 6px;
    font-size: 13px;
    line-height: 20px;
    color: var(--theme-text-secondary);
    word-break: break-word;
  }

  @media (max-width: 1440px) {
    .summary-grid {
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }

    .analytics-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }

  @media (max-width: 1080px) {
    .tool-left,
    .hero-panel,
    .ops-grid,
    .analytics-grid {
      grid-template-columns: 1fr;
      flex-direction: column;
    }

    .tool-left {
      align-items: stretch;
    }

    .toolbar {
      justify-content: flex-start;
    }

    .summary-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .event-item {
      flex-direction: column;
    }

    .event-time {
      flex-basis: auto;
    }
  }

  @media (max-width: 720px) {
    .hero-panel,
    .hero-copy,
    .hero-chart,
    .chart-card,
    .ops-card,
    .summary-card {
      padding: 16px;
    }

    .hero-title-row {
      flex-direction: column;
      align-items: flex-start;
    }

    .hero-highlight-row,
    .summary-grid {
      grid-template-columns: 1fr;
    }

    .hero-focus-head,
    .hero-focus-item {
      grid-template-columns: 1fr;
    }

    .chart-surface,
    .chart-surface-hero {
      height: 260px;
    }
  }
}
</style>
