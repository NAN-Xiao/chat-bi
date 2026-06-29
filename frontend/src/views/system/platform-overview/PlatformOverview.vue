<template>
  <div v-loading="loading" class="platform-overview-container professional-container">
    <div class="tool-left">
      <div class="title-block">
        <span class="page-title">{{ t('platform_overview.title') }}</span>
        <p class="page-subtitle">{{ t('platform_overview.subtitle') }}</p>
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
        <div class="hero-kicker">{{ t('platform_overview.platform_scope') }}</div>
        <div class="hero-title-row">
          <h2>{{ t('platform_overview.hero_title') }}</h2>
          <span class="hero-range">{{ selectedRangeLabel }}</span>
        </div>
        <p class="hero-note">{{ t('platform_overview.hero_note') }}</p>
        <div class="hero-highlight-row">
          <div class="hero-highlight">
            <span>{{ t('platform_overview.revenue_data') }}</span>
            <strong>{{ revenueDisplay }}</strong>
          </div>
          <div class="hero-highlight">
            <span>{{ t('platform_overview.paying_workspaces') }}</span>
            <strong>{{ formatNumber(summary.paying_tenant_count) }}</strong>
          </div>
        </div>
        <div class="risk-list">
          <div v-for="item in riskItems" :key="item.key" class="risk-item">
            <span :class="['risk-level', `is-${item.level}`]">{{ item.label }}</span>
            <span class="risk-text">{{ item.text }}</span>
            <strong>{{ item.value }}</strong>
          </div>
        </div>
      </div>

      <section class="chart-card hero-chart">
        <div class="chart-card-head">
          <span>{{ t('platform_overview.growth_trend') }}</span>
          <span class="muted">{{ selectedRangeLabel }}</span>
        </div>
        <div class="chart-surface chart-surface-hero">
          <ChartComponent
            v-if="trendRows.length"
            :id="'platform-overview-growth-trend-hero'"
            type="line"
            :data="trendRows"
            :x="trendXAxis"
            :y="growthTrendYAxis"
          />
          <EmptyBackground v-else :description="t('platform_overview.empty')" img-type="tree" />
        </div>
      </section>
    </section>

    <div class="summary-grid">
      <div
        v-for="item in summaryCards"
        :key="item.key"
        class="summary-card"
        :style="{ '--card-color': item.color, '--card-soft-color': item.softColor }"
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
        <div class="summary-value">{{ item.value }}</div>
        <div class="summary-progress" aria-hidden="true">
          <span :style="{ width: `${item.progress}%` }" />
        </div>
        <div class="summary-subvalue">{{ item.subValue }}</div>
      </div>
    </div>

    <div class="analytics-grid">
      <section class="chart-card">
        <div class="chart-card-head">
          <span>{{ t('platform_overview.enterprise_activity_trend') }}</span>
          <span class="muted">{{ t('platform_overview.by_day') }}</span>
        </div>
        <div class="chart-surface">
          <ChartComponent
            v-if="trendRows.length"
            :id="'platform-overview-enterprise-activity'"
            type="line"
            :data="trendRows"
            :x="trendXAxis"
            :y="activityTrendYAxis"
          />
          <EmptyBackground v-else :description="t('platform_overview.empty')" img-type="tree" />
        </div>
      </section>

      <section class="chart-card">
        <div class="chart-card-head">
          <span>{{ t('platform_overview.commercial_funnel') }}</span>
          <span class="muted">{{ t('platform_overview.all_workspaces') }}</span>
        </div>
        <div class="chart-surface">
          <ChartComponent
            v-if="subscriptionRows.length"
            :id="'platform-overview-subscriptions'"
            type="pie"
            :data="subscriptionRows"
            :y="countYAxis"
            :series="subscriptionSeries"
            :show-label="true"
          />
          <EmptyBackground v-else :description="t('platform_overview.empty')" img-type="tree" />
        </div>
      </section>

      <section class="chart-card">
        <div class="chart-card-head">
          <span>{{ t('platform_overview.plan_distribution') }}</span>
          <span class="muted">{{ t('platform_overview.all_workspaces') }}</span>
        </div>
        <div class="chart-surface">
          <ChartComponent
            v-if="planRows.length"
            :id="'platform-overview-plan-distribution'"
            type="pie"
            :data="planRows"
            :y="countYAxis"
            :series="planSeries"
            :show-label="true"
          />
          <EmptyBackground v-else :description="t('platform_overview.empty')" img-type="tree" />
        </div>
      </section>

      <section class="chart-card">
        <div class="chart-card-head">
          <span>{{ t('platform_overview.datasource_binding') }}</span>
          <span class="muted">{{ t('platform_overview.all_workspaces') }}</span>
        </div>
        <div class="chart-surface">
          <ChartComponent
            v-if="datasourceRows.length"
            :id="'platform-overview-datasource-binding'"
            type="pie"
            :data="datasourceRows"
            :y="countYAxis"
            :series="datasourceSeries"
            :show-label="true"
          />
          <EmptyBackground v-else :description="t('platform_overview.empty')" img-type="tree" />
        </div>
      </section>
    </div>

    <div class="detail-grid">
      <section class="ops-card">
        <div class="chart-card-head">
          <span>{{ t('platform_overview.top_active_workspaces') }}</span>
          <span class="muted">{{ t('platform_overview.top_by_requests') }}</span>
        </div>
        <div v-if="tenantUsageRows.length" class="ranking-list">
          <div v-for="(item, index) in tenantUsageRows" :key="item.tenant_id" class="ranking-item">
            <span class="rank-index">{{ index + 1 }}</span>
            <div class="rank-main">
              <div class="rank-title">{{ item.tenant_name || `#${item.tenant_id}` }}</div>
              <div class="rank-meta">
                {{ t('tenant.tenant_id') }}: {{ item.tenant_public_id || '-' }}
                ·
                {{ formatNumber(item.request_count) }} {{ t('platform_overview.requests') }}
                · {{ formatNumber(item.failure_count) }} {{ t('platform_overview.failures') }}
                · {{ formatNumber(item.total_tokens) }} {{ t('platform_overview.tokens') }}
              </div>
            </div>
            <strong>{{ formatNumber(item.request_count) }}</strong>
          </div>
        </div>
        <EmptyBackground v-else :description="t('platform_overview.empty')" img-type="tree" />
      </section>

      <section class="ops-card ops-card-wide">
        <div class="chart-card-head">
          <span>{{ t('platform_overview.new_customer_workspaces') }}</span>
          <span class="muted">{{ t('platform_overview.latest_created') }}</span>
        </div>
        <el-table :data="recentTenants" class="recent-table" style="width: 100%">
          <el-table-column prop="id" :label="t('tenant.tenant_id')" width="190" show-overflow-tooltip>
            <template #default="scope">{{ scope.row.public_id || '-' }}</template>
          </el-table-column>
          <el-table-column prop="name" :label="t('tenant.name')" min-width="180" show-overflow-tooltip>
            <template #default="scope">
              <div class="tenant-cell">
                <span>{{ scope.row.name }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="owner_account" :label="t('tenant.owner_or_applicant')" width="150" show-overflow-tooltip>
            <template #default="scope">{{ scope.row.owner_account || '-' }}</template>
          </el-table-column>
          <el-table-column prop="bound_datasource_name" :label="t('tenant.bound_datasource')" min-width="160" show-overflow-tooltip>
            <template #default="scope">{{ scope.row.bound_datasource_name || t('permission.no_data_source_bound') }}</template>
          </el-table-column>
          <el-table-column prop="plan" :label="t('tenant.plan')" width="120">
            <template #default="scope">{{ planLabel(scope.row.plan) }}</template>
          </el-table-column>
          <el-table-column prop="subscription_status" :label="t('tenant.subscription_status')" width="120">
            <template #default="scope">{{ subscriptionLabel(scope.row.subscription_status) }}</template>
          </el-table-column>
          <el-table-column prop="create_time" :label="t('tenant.create_time')" width="170">
            <template #default="scope">{{ formatTime(scope.row.create_time) }}</template>
          </el-table-column>
          <template #empty>
            <EmptyBackground :description="t('platform_overview.empty')" img-type="tree" />
          </template>
        </el-table>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, shallowRef } from 'vue'
import { ElMessage } from 'element-plus-secondary'
import { useI18n } from 'vue-i18n'
import icon_refresh_outlined from '@/assets/embedded/icon_refresh_outlined.svg'
import icon_chart_preview from '@/assets/svg/icon_chart_preview.svg'
import icon_done_outlined from '@/assets/svg/icon_done_outlined.svg'
import icon_error from '@/assets/svg/icon_error.svg'
import icon_user from '@/assets/svg/icon_user.svg'
import icon_dashboard_outlined from '@/assets/svg/chart/icon_dashboard_outlined.svg'
import EmptyBackground from '@/views/dashboard/common/EmptyBackground.vue'
import ChartComponent from '@/views/chat/component/ChartComponent.vue'
import { tenantApi, type PlatformOverviewInfo } from '@/api/tenant'
import type { ChartAxis } from '@/views/chat/component/BaseChart.ts'
import { formatTimestamp } from '@/utils/date'

const { t } = useI18n()
const loading = ref(false)
const selectedDays = ref(7)
const overview = shallowRef<PlatformOverviewInfo | null>(null)

const rangeOptions = computed(() => [
  { value: 7, label: t('platform_overview.range_7') },
  { value: 30, label: t('platform_overview.range_30') },
  { value: 90, label: t('platform_overview.range_90') },
])

const selectedRangeLabel = computed(
  () => rangeOptions.value.find((item) => item.value === selectedDays.value)?.label || t('platform_overview.range_7')
)

const summary = computed(
  () =>
    overview.value?.summary || {
      tenant_total: 0,
      active_tenant_count: 0,
      disabled_tenant_count: 0,
      user_total: 0,
      active_user_count: 0,
      platform_admin_count: 0,
      datasource_total: 0,
      bound_datasource_count: 0,
      dashboard_total: 0,
      new_tenant_count: 0,
      new_user_count: 0,
      paying_tenant_count: 0,
      trial_tenant_count: 0,
      past_due_tenant_count: 0,
      suspended_tenant_count: 0,
      cancelled_tenant_count: 0,
      contract_tenant_count: 0,
      active_usage_tenant_count: 0,
      revenue_data_ready: false,
      revenue_amount: null,
      pending_workspace_application_count: 0,
      pending_data_request_count: 0,
      request_count: 0,
      total_tokens: 0,
      failure_count: 0,
    }
)

const trendRows = computed(() => overview.value?.tenant_trend || [])
const tenantUsageRows = computed(() => overview.value?.top_tenant_usage || [])
const recentTenants = computed(() => overview.value?.recent_tenants || [])

const subscriptionRows = computed(() =>
  (overview.value?.subscription_distribution || [])
    .map((item) => ({ key: item.key, label: subscriptionLabel(item.key), count: Number(item.count || 0) }))
    .filter((item) => item.count > 0)
)

const planRows = computed(() =>
  (overview.value?.plan_distribution || [])
    .map((item) => ({ key: item.key, label: planLabel(item.key), count: Number(item.count || 0) }))
    .filter((item) => item.count > 0)
)

const datasourceRows = computed(() =>
  (overview.value?.datasource_distribution || [])
    .map((item) => ({ key: item.key, label: datasourceBindingLabel(item.key), count: Number(item.count || 0) }))
    .filter((item) => item.count > 0)
)

const formatNumber = (value?: number | string) => Number(value || 0).toLocaleString()
const clampPercent = (value: number) => Math.max(0, Math.min(100, Math.round(value)))
const ratioPercent = (numerator: number, denominator: number) =>
  denominator > 0 ? clampPercent((numerator / denominator) * 100) : 0
const formatPercentValue = (value: number) => `${clampPercent(value)}%`

const revenueDisplay = computed(() =>
  summary.value.revenue_data_ready && summary.value.revenue_amount !== null && summary.value.revenue_amount !== undefined
    ? formatCurrency(summary.value.revenue_amount)
    : t('platform_overview.revenue_not_connected')
)
const payingConversionRate = computed(() =>
  ratioPercent(Number(summary.value.paying_tenant_count || 0), Number(summary.value.tenant_total || 0))
)
const enterpriseActivityRate = computed(() =>
  ratioPercent(Number(summary.value.active_usage_tenant_count || 0), Number(summary.value.active_tenant_count || 0))
)
const userGrowthRate = computed(() =>
  ratioPercent(Number(summary.value.new_user_count || 0), Number(summary.value.user_total || 0))
)
const datasourceBindingRate = computed(() =>
  ratioPercent(Number(summary.value.bound_datasource_count || 0), Number(summary.value.tenant_total || 0))
)
const pendingTotal = computed(
  () =>
    Number(summary.value.pending_workspace_application_count || 0) +
    Number(summary.value.pending_data_request_count || 0)
)
const commercialRiskCount = computed(
  () =>
    Number(summary.value.past_due_tenant_count || 0) +
    Number(summary.value.suspended_tenant_count || 0) +
    Number(summary.value.cancelled_tenant_count || 0)
)

const riskItems = computed(() => [
  {
    key: 'commercial',
    label: commercialRiskCount.value > 0 ? t('platform_overview.attention') : t('platform_overview.healthy'),
    level: commercialRiskCount.value > 0 ? 'warning' : 'healthy',
    text: t('platform_overview.commercial_risk'),
    value: formatNumber(commercialRiskCount.value),
  },
  {
    key: 'pending',
    label: pendingTotal.value > 0 ? t('platform_overview.attention') : t('platform_overview.healthy'),
    level: pendingTotal.value > 0 ? 'attention' : 'healthy',
    text: t('platform_overview.pending_risk'),
    value: formatNumber(pendingTotal.value),
  },
])

const summaryCards = computed(() => [
  {
    key: 'paying_conversion',
    label: t('platform_overview.paying_conversion'),
    note: t('platform_overview.paying_conversion_hint'),
    value: formatPercentValue(payingConversionRate.value),
    subValue: t('platform_overview.paying_conversion_sub', {
      paying: formatNumber(summary.value.paying_tenant_count),
      trial: formatNumber(summary.value.trial_tenant_count),
      total: formatNumber(summary.value.tenant_total),
    }),
    progress: payingConversionRate.value,
    icon: icon_dashboard_outlined,
    color: '#2f6bff',
    softColor: 'rgba(47, 107, 255, 0.12)',
  },
  {
    key: 'user_growth',
    label: t('platform_overview.user_growth'),
    note: t('platform_overview.user_growth_hint', { days: selectedDays.value }),
    value: formatNumber(summary.value.new_user_count),
    subValue: t('platform_overview.user_growth_sub', {
      rate: formatPercentValue(userGrowthRate.value),
      total: formatNumber(summary.value.user_total),
    }),
    progress: userGrowthRate.value,
    icon: icon_user,
    color: '#39c98a',
    softColor: 'rgba(57, 201, 138, 0.14)',
  },
  {
    key: 'enterprise_activity',
    label: t('platform_overview.enterprise_activity'),
    note: t('platform_overview.enterprise_activity_hint', { days: selectedDays.value }),
    value: formatPercentValue(enterpriseActivityRate.value),
    subValue: t('platform_overview.enterprise_activity_sub', {
      active: formatNumber(summary.value.active_usage_tenant_count),
      total: formatNumber(summary.value.active_tenant_count),
    }),
    progress: enterpriseActivityRate.value,
    icon: icon_done_outlined,
    color: '#f5b74f',
    softColor: 'rgba(245, 183, 79, 0.16)',
  },
  {
    key: 'commercial_risk',
    label: t('platform_overview.commercial_risk_rate'),
    note: t('platform_overview.commercial_risk_hint'),
    value: formatNumber(commercialRiskCount.value),
    subValue: t('platform_overview.commercial_risk_sub', {
      pastDue: formatNumber(summary.value.past_due_tenant_count),
      suspended: formatNumber(summary.value.suspended_tenant_count),
      cancelled: formatNumber(summary.value.cancelled_tenant_count),
    }),
    progress: commercialRiskCount.value > 0 ? 100 : 0,
    icon: icon_error,
    color: '#f56c6c',
    softColor: 'rgba(245, 108, 108, 0.14)',
  },
  {
    key: 'contract_customers',
    label: t('platform_overview.contract_customers'),
    note: t('platform_overview.contract_customers_hint'),
    value: formatNumber(summary.value.contract_tenant_count),
    subValue: t('platform_overview.contract_customers_sub', {
      bound: formatNumber(summary.value.bound_datasource_count),
      rate: formatPercentValue(datasourceBindingRate.value),
    }),
    progress: ratioPercent(Number(summary.value.contract_tenant_count || 0), Number(summary.value.tenant_total || 0)),
    icon: icon_chart_preview,
    color: '#8c6bff',
    softColor: 'rgba(140, 107, 255, 0.14)',
  },
])

const trendXAxis = computed<ChartAxis[]>(() => [{ name: 'date', value: 'date' }])
const growthTrendYAxis = computed<ChartAxis[]>(() => [
  { name: t('platform_overview.created_workspaces'), value: 'tenant_created_count', 'multi-quota': true },
  { name: t('platform_overview.new_users'), value: 'user_created_count', 'multi-quota': true },
])
const activityTrendYAxis = computed<ChartAxis[]>(() => [
  { name: t('platform_overview.active_workspaces'), value: 'active_tenant_count', 'multi-quota': true },
  { name: t('platform_overview.requests'), value: 'request_count', 'multi-quota': true },
  { name: t('platform_overview.failures'), value: 'failure_count', 'multi-quota': true },
])
const countYAxis = computed<ChartAxis[]>(() => [{ name: 'count', value: 'count' }])
const subscriptionSeries = computed<ChartAxis[]>(() => [{ name: 'subscription', value: 'label' }])
const planSeries = computed<ChartAxis[]>(() => [{ name: 'plan', value: 'label' }])
const datasourceSeries = computed<ChartAxis[]>(() => [{ name: 'binding', value: 'label' }])

const subscriptionLabel = (status?: string) => {
  const key = `tenant.subscription_${status || 'active'}`
  const label = t(key)
  return label === key ? status || '-' : label
}

const planLabel = (plan?: string) => {
  const key = `tenant.plan_${plan || 'default'}`
  const label = t(key)
  return label === key ? plan || t('tenant.plan_default') : label
}

const datasourceBindingLabel = (key?: string) => {
  if (key === 'bound') return t('tenant.datasource_bound')
  if (key === 'unbound') return t('permission.no_data_source_bound')
  return key || '-'
}

const formatCurrency = (value?: number | string | null) => {
  const number = Number(value || 0)
  return number.toLocaleString(undefined, {
    style: 'currency',
    currency: 'CNY',
    maximumFractionDigits: 0,
  })
}

const formatTime = (timestamp?: number) => {
  const value = Number(timestamp || 0)
  return value ? formatTimestamp(value, 'YYYY-MM-DD HH:mm:ss') : '-'
}

const loadOverview = async () => {
  loading.value = true
  try {
    overview.value = await tenantApi.platformOverview(selectedDays.value)
  } finally {
    loading.value = false
  }
}

const refreshOverview = async () => {
  await loadOverview()
  ElMessage.success(t('platform_overview.refresh_success'))
}

onMounted(async () => {
  await loadOverview()
})
</script>

<style scoped lang="less">
.platform-overview-container {
  --overview-card-gap: 16px;
  --overview-section-gap: 18px;
  --overview-page-bottom-gap: 18px;
  --overview-bottom-card-min-height: 330px;

  width: 100%;
  min-height: 100%;
  padding-bottom: var(--overview-page-bottom-gap);
  position: relative;
  color-scheme: light;

  .tool-left {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 20px;
    margin-bottom: 16px;
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
    grid-template-columns: minmax(320px, 380px) minmax(0, 1fr);
    gap: var(--overview-card-gap);
    margin-bottom: var(--overview-section-gap);
  }

  .hero-copy,
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
      linear-gradient(180deg, rgba(248, 251, 255, 0.98), rgba(244, 249, 255, 0.98)),
      var(--theme-card-bg, #ffffff);
    border-color: #e2eaf4;
  }

  .hero-kicker {
    display: inline-flex;
    align-items: center;
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
    margin-top: 14px;

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
    margin: 12px 0 0;
    font-size: 14px;
    line-height: 22px;
    color: var(--theme-text-secondary);
  }

  .hero-highlight-row {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
    margin-top: 18px;
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

  .risk-list {
    display: flex;
    flex-direction: column;
    gap: 10px;
    margin-top: 18px;
  }

  .risk-item {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    border-radius: 8px;
    background: #f8fbff;
    border: 1px solid #edf2f8;
  }

  .risk-level {
    display: inline-flex;
    align-items: center;
    height: 24px;
    padding: 0 10px;
    border-radius: 999px;
    font-size: 12px;
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
  }

  .risk-text {
    min-width: 0;
    color: var(--theme-text-primary);
    font-size: 13px;
    line-height: 20px;
  }

  .hero-chart,
  .chart-card {
    padding: 18px;
    min-height: 320px;
    display: flex;
    flex-direction: column;
  }

  .summary-grid {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: var(--overview-card-gap);
    margin-bottom: var(--overview-section-gap);
  }

  .summary-card {
    padding: 18px;
    min-height: 148px;
    text-align: left;
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

  .summary-note,
  .summary-subvalue,
  .muted {
    color: var(--theme-text-secondary);
    font-size: 12px;
    line-height: 18px;
  }

  .summary-note {
    margin-top: 4px;
  }

  .summary-value {
    margin-top: 22px;
    font-size: 30px;
    line-height: 36px;
    font-weight: 600;
    color: var(--theme-text-primary);
  }

  .summary-progress {
    margin-top: 12px;
    height: 6px;
    border-radius: 999px;
    background: rgba(142, 154, 175, 0.14);
    overflow: hidden;

    span {
      display: block;
      height: 100%;
      min-width: 6px;
      max-width: 100%;
      border-radius: inherit;
      background: var(--card-color);
    }
  }

  .summary-subvalue {
    margin-top: 10px;
    word-break: break-word;
  }

  .analytics-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--overview-card-gap);
    margin-bottom: var(--overview-section-gap);
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

  .chart-surface {
    height: 300px;
  }

  .chart-surface-hero {
    flex: 1 1 auto;
    min-height: 252px;
    height: auto;
  }

  .detail-grid {
    display: grid;
    grid-template-columns: minmax(320px, 0.9fr) minmax(0, 1.6fr);
    align-items: stretch;
    gap: var(--overview-card-gap);
  }

  .ops-card {
    min-width: 0;
    padding: 18px;
    min-height: var(--overview-bottom-card-min-height);
    display: flex;
    flex-direction: column;
  }

  .ranking-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .ranking-item {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: center;
    gap: 12px;
    padding: 12px 14px;
    border-radius: 8px;
    background: var(--theme-hover-bg, #f8fafc);
    border: 1px solid rgba(15, 23, 42, 0.05);
  }

  .rank-index {
    width: 28px;
    height: 28px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: 8px;
    background: rgba(47, 107, 255, 0.12);
    color: #2f6bff;
    font-weight: 600;
  }

  .rank-main {
    min-width: 0;
  }

  .rank-title {
    font-size: 14px;
    line-height: 22px;
    font-weight: 500;
    color: var(--theme-text-primary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .rank-meta {
    margin-top: 4px;
    color: var(--theme-text-secondary);
    font-size: 12px;
    line-height: 18px;
  }

  .tenant-cell {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;

    span,
    em {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    em {
      color: var(--theme-text-secondary);
      font-style: normal;
      font-size: 12px;
      line-height: 18px;
    }
  }

  @media (max-width: 1440px) {
    .summary-grid {
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }
  }

  @media (max-width: 1080px) {
    .tool-left,
    .hero-panel,
    .analytics-grid,
    .detail-grid {
      grid-template-columns: 1fr;
      flex-direction: column;
    }

    .summary-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }

  @media (max-width: 720px) {
    .hero-copy,
    .chart-card,
    .ops-card,
    .summary-card {
      padding: 16px;
    }

    .hero-title-row,
    .tool-left {
      flex-direction: column;
      align-items: flex-start;
    }

    .hero-highlight-row,
    .summary-grid {
      grid-template-columns: 1fr;
    }

    .risk-item,
    .ranking-item {
      grid-template-columns: 1fr;
    }

    .chart-surface,
    .chart-surface-hero {
      height: 260px;
    }
  }
}
</style>
