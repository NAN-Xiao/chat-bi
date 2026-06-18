<template>
  <div class="tenant-usage-container professional-container">
    <div class="tool-left">
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
        <el-select
          v-if="isPlatformAdmin"
          v-model="filters.tenant_id"
          class="tenant-select"
          :placeholder="t('tenant_usage.all_tenants')"
          clearable
          filterable
        >
          <el-option
            v-for="tenant in tenants"
            :key="String(tenant.id)"
            :label="tenant.name || tenant.code"
            :value="String(tenant.id)"
          >
            <span>{{ tenant.name || tenant.code }}</span>
            <span class="option-meta">{{ tenant.code }}</span>
          </el-option>
        </el-select>
        <div v-else class="current-tenant">
          {{ currentTenantName }}
        </div>
        <el-select
          v-model="filters.metric"
          class="metric-select"
          :placeholder="t('tenant_usage.all_metrics')"
          clearable
          filterable
        >
          <el-option
            v-for="metric in metricOptions"
            :key="metric.value"
            :label="metric.label"
            :value="metric.value"
          />
        </el-select>
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

    <div class="summary-grid">
      <div v-for="item in summaryItems" :key="item.key" class="summary-item">
        <div class="summary-label">{{ item.label }}</div>
        <div class="summary-value">{{ formatNumber(item.value) }}</div>
        <div class="summary-bar">
          <span :style="{ width: `${item.percent}%` }"></span>
        </div>
      </div>
    </div>

    <div class="section-head">
      <span>{{ t('tenant_usage.detail') }}</span>
      <span class="muted">{{ t('tenant_usage.row_count', { count: usageRows.length }) }}</span>
    </div>

    <el-table
      v-loading="loading"
      :data="usageRows"
      class="usage-table"
      style="width: 100%"
      :default-sort="{ prop: 'usage_date', order: 'descending' }"
    >
      <el-table-column prop="usage_date" :label="t('tenant_usage.usage_date')" width="130" sortable />
      <el-table-column
        prop="tenant_id"
        :label="t('tenant_usage.tenant')"
        min-width="170"
        show-overflow-tooltip
      >
        <template #default="scope">
          <span>{{ tenantLabel(scope.row.tenant_id) }}</span>
        </template>
      </el-table-column>
      <el-table-column
        prop="metric"
        :label="t('tenant_usage.metric')"
        min-width="210"
        show-overflow-tooltip
      >
        <template #default="scope">
          <div class="metric-cell">
            <span>{{ metricLabel(scope.row.metric) }}</span>
            <span class="metric-key">{{ scope.row.metric }}</span>
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
      <el-table-column prop="task_count" :label="t('tenant_usage.tasks')" width="110" align="right" sortable>
        <template #default="scope">{{ formatNumber(scope.row.task_count) }}</template>
      </el-table-column>
      <el-table-column prop="update_time" :label="t('tenant.update_time')" width="180" sortable>
        <template #default="scope">
          <span>{{ formatTimestamp(Number(scope.row.update_time || 0), 'YYYY-MM-DD HH:mm:ss') }}</span>
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
import { computed, onMounted, reactive, ref, shallowRef } from 'vue'
import { useI18n } from 'vue-i18n'
import icon_searchOutline_outlined from '@/assets/svg/icon_search-outline_outlined.svg'
import EmptyBackground from '@/views/dashboard/common/EmptyBackground.vue'
import { tenantApi, type TenantInfo, type TenantUsageDailyInfo } from '@/api/tenant'
import { useUserStore } from '@/stores/user'
import { formatTimestamp } from '@/utils/date'

const { t } = useI18n()
const userStore = useUserStore()
const loading = ref(false)
const tenants = shallowRef<TenantInfo[]>([])
const usageRows = shallowRef<TenantUsageDailyInfo[]>([])
const dateRange = ref<[string, string] | null>([
  dayjs().subtract(13, 'day').format('YYYY-MM-DD'),
  dayjs().format('YYYY-MM-DD'),
])

const filters = reactive<{
  tenant_id: string | number | ''
  metric: string
}>({
  tenant_id: '',
  metric: '',
})

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

const isPlatformAdmin = computed(() => userStore.isSystemAdminUser)
const currentTenantName = computed(() => userStore.getTenantName || t('tenant.default_tenant'))

const tenantMap = computed(() =>
  tenants.value.reduce<Record<string, TenantInfo>>((result, tenant) => {
    result[String(tenant.id)] = tenant
    return result
  }, {})
)

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

const summaryItems = computed(() => {
  const items = [
    { key: 'request_count', label: t('tenant_usage.requests'), value: summary.value.request_count },
    { key: 'success_count', label: t('tenant_usage.success'), value: summary.value.success_count },
    { key: 'failure_count', label: t('tenant_usage.failure'), value: summary.value.failure_count },
    { key: 'total_tokens', label: t('tenant_usage.tokens'), value: summary.value.total_tokens },
    { key: 'task_count', label: t('tenant_usage.tasks'), value: summary.value.task_count },
  ]
  const maxValue = Math.max(...items.map((item) => item.value), 1)
  return items.map((item) => ({
    ...item,
    percent: Math.max(4, Math.round((item.value / maxValue) * 100)),
  }))
})

const formatNumber = (value?: number | string) => Number(value || 0).toLocaleString()

const metricLabel = (metric?: string) => {
  if (!metric) return '-'
  return metricLabelMap.value[metric] || metric
}

const tenantLabel = (tenantId: string | number) => {
  const tenant = tenantMap.value[String(tenantId)]
  if (tenant) return `${tenant.name || tenant.code} #${tenant.id}`
  if (!isPlatformAdmin.value && String(tenantId) === String(userStore.getTenantId || '')) {
    return `${currentTenantName.value} #${tenantId}`
  }
  return `#${tenantId}`
}

const loadTenants = async () => {
  if (isPlatformAdmin.value) {
    tenants.value = await tenantApi.adminList()
    return
  }
  tenants.value = userStore.getTenantId
    ? [
        {
          id: userStore.getTenantId,
          code: userStore.tenantCode,
          name: currentTenantName.value,
          role: userStore.getTenantRole,
        },
      ]
    : []
}

const loadUsage = async () => {
  loading.value = true
  try {
    const [startDate, endDate] = dateRange.value || []
    usageRows.value = await tenantApi.usage({
      tenant_id: filters.tenant_id || undefined,
      start_date: startDate,
      end_date: endDate,
      metric: filters.metric || undefined,
      limit: 1000,
    })
  } finally {
    loading.value = false
  }
}

const resetFilters = () => {
  filters.tenant_id = ''
  filters.metric = ''
  dateRange.value = [dayjs().subtract(13, 'day').format('YYYY-MM-DD'), dayjs().format('YYYY-MM-DD')]
  loadUsage()
}

onMounted(async () => {
  await loadTenants()
  await loadUsage()
})
</script>

<style lang="less" scoped>
.tenant-usage-container {
  width: 100%;
  height: 100%;
  position: relative;

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
  }

  .toolbar {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    flex-wrap: wrap;
    gap: 10px;
  }

  .tenant-select {
    width: 220px;
  }

  .metric-select {
    width: 230px;
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

  .option-meta {
    float: right;
    color: #8f959e;
    font-size: 12px;
    margin-left: 20px;
  }

  .summary-grid {
    display: grid;
    grid-template-columns: repeat(5, minmax(120px, 1fr));
    gap: 12px;
    margin-bottom: 18px;
  }

  .summary-item {
    min-width: 0;
    border: 1px solid #eff0f1;
    border-radius: 8px;
    padding: 12px;
    background: #fff;
  }

  .summary-label {
    color: #646a73;
    font-size: 12px;
    line-height: 18px;
  }

  .summary-value {
    margin-top: 6px;
    color: #1f2329;
    font-size: 22px;
    font-weight: 600;
    line-height: 30px;
  }

  .summary-bar {
    height: 4px;
    margin-top: 10px;
    border-radius: 999px;
    background: #eef1f7;
    overflow: hidden;

    span {
      display: block;
      height: 100%;
      border-radius: inherit;
      background: #2f6bff;
    }
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
    max-height: calc(100vh - 250px);
    overflow-y: auto;
  }

  .metric-cell {
    display: flex;
    flex-direction: column;
    min-width: 0;
    line-height: 20px;
  }

  .metric-key {
    color: #8f959e;
    font-size: 12px;
  }

  .danger {
    color: #d93026;
    font-weight: 500;
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

    .summary-grid {
      grid-template-columns: repeat(2, minmax(140px, 1fr));
    }
  }
}
</style>
