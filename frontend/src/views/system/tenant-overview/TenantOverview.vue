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
            <h2>{{ currentTenantName }}</h2>
            <span class="hero-range">{{ selectedRangeLabel }}</span>
          </div>
          <div class="hero-identity-row">
            <span>{{ t('tenant.tenant_id') }}: {{ currentTenantId || '-' }}</span>
          </div>
          <p class="hero-note">{{ t('tenant_overview.activity_hint') }}</p>
        </div>
        <div class="hero-highlight-row">
          <div class="hero-highlight">
            <span>{{ t('tenant_overview.summary_active_members') }}</span>
            <strong>{{ formatNumber(summary.active_member_count) }}</strong>
          </div>
          <button v-if="hasPendingApplications" type="button" class="hero-highlight is-actionable" @click="openReviewDialog">
            <span>{{ t('tenant_overview.summary_pending') }}</span>
            <strong :class="{ danger: summary.pending_member_application_count > 0 }">
              {{ formatNumber(summary.pending_member_application_count) }}
            </strong>
            <em>{{ t('tenant_overview.action_review_applications') }}</em>
          </button>
          <div v-else class="hero-highlight">
            <span>{{ t('tenant_overview.summary_pending') }}</span>
            <strong>{{ formatNumber(summary.pending_member_application_count) }}</strong>
          </div>
        </div>
        <div class="hero-focus-card">
          <div class="hero-focus-head">
            <span>{{ t('tenant_overview.todos_title') }}</span>
            <span class="muted">{{ t('tenant_overview.todos_hint') }}</span>
          </div>
          <div v-if="heroFocusItems.length" class="hero-focus-list">
            <div
              v-for="item in heroFocusItems"
              :key="item.key"
              class="hero-focus-item"
            >
              <span :class="['todo-level', `is-${item.level || 'normal'}`]">
                {{ todoLevelLabel(item.level) }}
              </span>
              <span class="hero-focus-text">{{ todoLabel(item.key) }}</span>
              <span v-if="item.count !== undefined && item.count !== null" class="hero-focus-tail">
                <strong v-if="item.count !== undefined && item.count !== null" class="hero-focus-count">
                  {{ formatNumber(item.count) }}
                </strong>
              </span>
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
        <div class="summary-value" :class="{ danger: item.emphasize }">{{ item.value }}</div>
        <div class="summary-progress" aria-hidden="true">
          <span :style="{ width: `${item.progress}%` }" />
        </div>
        <div class="summary-subvalue">{{ item.subValue }}</div>
      </div>
    </div>

    <div class="analytics-grid">
      <section class="chart-card">
        <div class="chart-card-head">
          <span>{{ t('tenant_overview.assets_title') }}</span>
          <span class="muted">{{ t('tenant_overview.assets_hint') }}</span>
        </div>
        <div class="chart-surface chart-surface-assets">
          <ChartComponent
            v-if="assetRows.length"
            :id="'tenant-overview-assets'"
            type="bar"
            :data="assetRows"
            :x="assetXAxis"
            :y="assetYAxis"
            :hide-value-axis="true"
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
          <div
            v-for="item in todoRows"
            :key="item.key"
            class="todo-item"
          >
            <div class="todo-main">
              <div class="todo-title">{{ todoLabel(item.key) }}</div>
              <div class="todo-meta">
                <span :class="['todo-level', `is-${item.level}`]">{{ todoLevelLabel(item.level) }}</span>
                <span v-if="item.count !== undefined && item.count !== null" class="todo-count">
                  {{ formatNumber(item.count) }} {{ t('tenant_overview.todo_count_suffix') }}
                </span>
              </div>
            </div>
          </div>
        </div>
        <EmptyBackground v-else :description="t('tenant_overview.empty')" img-type="tree" />
      </section>

      <section class="ops-card ops-card-wide">
        <div class="chart-card-head">
          <span>{{ t('tenant_overview.member_activity_title') }}</span>
          <span class="muted">{{ t('tenant_overview.member_activity_hint') }}</span>
        </div>
        <div v-if="memberActivityRows.length" class="event-list">
          <div v-for="item in memberActivityRows" :key="item.user_id" class="event-item">
            <div class="event-time">{{ formatMemberActivityTime(item.last_active_time) }}</div>
            <div class="event-content">
              <div class="event-title">{{ memberDisplayName(item) }}</div>
              <div class="event-description">{{ formatTenantRole(item.tenant_role) }}</div>
              <div class="event-meta">
                <span>{{ t('user.account') }}: {{ item.account || '-' }}</span>
              </div>
            </div>
          </div>
        </div>
        <EmptyBackground v-else :description="t('tenant_overview.empty')" img-type="tree" />
      </section>
    </div>

    <el-dialog
      v-model="reviewDialogVisible"
      class="workspace-light-dialog access-review-dialog"
      :title="t('tenant.join_application_review')"
      width="860"
    >
      <el-table v-loading="applicationLoading" :data="accessRequests" class="access-table" style="width: 100%">
        <el-table-column prop="applicant_account" :label="t('user.account')" min-width="160" show-overflow-tooltip />
        <el-table-column prop="applicant_name" :label="t('user.name')" min-width="140" show-overflow-tooltip>
          <template #default="scope">
            {{ scope.row.applicant_name || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="application_type" :label="t('tenant.access_type')" width="130">
          <template #default="scope">
            <el-tag size="small" :type="scope.row.application_type === 'invite' ? 'primary' : 'warning'">
              {{ formatApplicationType(scope.row.application_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="requested_role" :label="t('tenant.requested_role')" width="130">
          <template #default="scope">
            {{ formatTenantRole(scope.row.requested_role) }}
          </template>
        </el-table-column>
        <el-table-column prop="reason" :label="t('tenant.apply_reason')" min-width="180" show-overflow-tooltip />
        <el-table-column fixed="right" :label="t('ds.actions')" width="150">
          <template #default="scope">
            <div
              v-if="scope.row.status === 'pending' && scope.row.application_type !== 'invite'"
              class="review-actions"
            >
              <el-button
                text
                :loading="joinReviewLoadingId === String(scope.row.id)"
                @click="reviewJoinApplication(scope.row, true)"
              >
                {{ t('tenant.approve') }}
              </el-button>
              <el-button text type="danger" @click="reviewJoinApplication(scope.row, false)">
                {{ t('tenant.reject') }}
              </el-button>
            </div>
            <el-button
              v-else-if="scope.row.status === 'pending'"
              text
              type="danger"
              :loading="inviteCancelingId === String(scope.row.id)"
              @click="cancelInvitation(scope.row)"
            >
              {{ t('tenant.cancel_invitation') }}
            </el-button>
          </template>
        </el-table-column>
        <template #empty>
          <EmptyBackground :description="t('tenant.no_access_requests')" img-type="tree" />
        </template>
      </el-table>
      <template #footer>
        <div class="dialog-footer">
          <el-button secondary @click="reviewDialogVisible = false">{{ t('common.cancel') }}</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, shallowRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus-secondary'
import { useI18n } from 'vue-i18n'
import icon_refresh_outlined from '@/assets/embedded/icon_refresh_outlined.svg'
import icon_chart_preview from '@/assets/svg/icon_chart_preview.svg'
import icon_done_outlined from '@/assets/svg/icon_done_outlined.svg'
import icon_error from '@/assets/svg/icon_error.svg'
import icon_user from '@/assets/svg/icon_user.svg'
import icon_dashboard_outlined from '@/assets/svg/chart/icon_dashboard_outlined.svg'
import EmptyBackground from '@/views/dashboard/common/EmptyBackground.vue'
import ChartComponent from '@/views/chat/component/ChartComponent.vue'
import { tenantApi, type TenantApplicationInfo, type TenantOverviewInfo } from '@/api/tenant'
import type { ChartAxis } from '@/views/chat/component/BaseChart.ts'
import { useUserStore } from '@/stores/user'
import { formatTimestamp } from '@/utils/date'

const { t } = useI18n()
const userStore = useUserStore()

const loading = ref(false)
const applicationLoading = ref(false)
const selectedDays = ref(7)
const overview = shallowRef<TenantOverviewInfo | null>(null)
const reviewDialogVisible = ref(false)
const joinReviewLoadingId = ref('')
const inviteCancelingId = ref('')
const joinApplications = shallowRef<TenantApplicationInfo[]>([])
const invitations = shallowRef<TenantApplicationInfo[]>([])

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
const memberActivityRows = computed(() => overview.value?.member_last_activities || [])
const heroFocusItems = computed(() => todoRows.value.slice(0, 2))
const hasPendingApplications = computed(() => Number(summary.value.pending_member_application_count || 0) > 0)
const accessRequests = computed(() =>
  [...joinApplications.value, ...invitations.value].sort(
    (a, b) => Number(b.create_time || 0) - Number(a.create_time || 0)
  )
)
const currentTenantName = computed(() => overview.value?.tenant_name || userStore.getTenantName || '-')
const currentTenantId = computed(() =>
  String(overview.value?.tenant_public_id || userStore.getTenantPublicId || '').trim()
)

const assetCount = (key: string) => Number(assetRows.value.find((item) => item.key === key)?.count || 0)

const clampPercent = (value: number) => Math.max(0, Math.min(100, Math.round(value)))

const ratioPercent = (numerator: number, denominator: number) =>
  denominator > 0 ? clampPercent((numerator / denominator) * 100) : 0

const formatPercentValue = (value: number) => `${clampPercent(value)}%`

const activityRate = computed(() =>
  ratioPercent(Number(summary.value.active_member_count || 0), Number(summary.value.member_total || 0))
)

const reusableAssetCount = computed(() =>
  ['dashboard', 'data_skill', 'custom_agent', 'embedded'].reduce(
    (result, key) => result + assetCount(key),
    0
  )
)

const assetUsability = computed(() => {
  const readinessChecks = [
    Number(summary.value.datasource_total || 0) > 0,
    Number(summary.value.dashboard_total || 0) > 0,
    assetCount('custom_agent') > 0 || assetCount('embedded') > 0,
  ]
  return ratioPercent(readinessChecks.filter(Boolean).length, readinessChecks.length)
})

const analysisMaturity = computed(() => {
  const maturityChecks = [
    Number(summary.value.dashboard_total || 0) > 0,
    assetCount('data_skill') > 0,
  ]
  return ratioPercent(maturityChecks.filter(Boolean).length, maturityChecks.length)
})

const pendingResolutionRate = computed(() =>
  Number(summary.value.pending_member_application_count || 0) > 0 ? 0 : 100
)

const managerCoverage = computed(() => {
  const total = roleRows.value.reduce((result, item) => result + Number(item.count || 0), 0)
  const managers = roleRows.value
    .filter((item) => item.role === 'owner' || item.role === 'admin')
    .reduce((result, item) => result + Number(item.count || 0), 0)
  return ratioPercent(managers, total)
})

const summaryCards = computed(() => [
  {
    key: 'activity_rate',
    label: t('tenant_overview.efficiency_activity_rate'),
    note: t('tenant_overview.efficiency_activity_rate_hint', { days: selectedDays.value }),
    value: formatPercentValue(activityRate.value),
    subValue: t('tenant_overview.efficiency_active_members_ratio', {
      active: formatNumber(summary.value.active_member_count),
      total: formatNumber(summary.value.member_total),
    }),
    progress: activityRate.value,
    icon: icon_user,
    color: '#2f6bff',
    softColor: 'rgba(47, 107, 255, 0.12)',
    emphasize: false,
  },
  {
    key: 'asset_usability',
    label: t('tenant_overview.efficiency_asset_usability'),
    note: t('tenant_overview.efficiency_asset_usability_hint'),
    value: formatPercentValue(assetUsability.value),
    subValue: t('tenant_overview.efficiency_reusable_assets', {
      count: formatNumber(reusableAssetCount.value),
    }),
    progress: assetUsability.value,
    icon: icon_done_outlined,
    color: '#39c98a',
    softColor: 'rgba(57, 201, 138, 0.14)',
    emphasize: false,
  },
  {
    key: 'analysis_maturity',
    label: t('tenant_overview.efficiency_analysis_maturity'),
    note: t('tenant_overview.efficiency_analysis_maturity_hint'),
    value: formatPercentValue(analysisMaturity.value),
    subValue: t('tenant_overview.efficiency_analysis_assets', {
      dashboards: formatNumber(assetCount('dashboard')),
      skills: formatNumber(assetCount('data_skill')),
    }),
    progress: analysisMaturity.value,
    icon: icon_chart_preview,
    color: '#f5b74f',
    softColor: 'rgba(245, 183, 79, 0.16)',
    emphasize: false,
  },
  {
    key: 'pending_resolution_rate',
    label: t('tenant_overview.efficiency_pending_resolution'),
    note: t('tenant_overview.efficiency_pending_resolution_hint'),
    value: formatPercentValue(pendingResolutionRate.value),
    subValue: t('tenant_overview.efficiency_pending_count', {
      count: formatNumber(summary.value.pending_member_application_count),
    }),
    progress: pendingResolutionRate.value,
    icon: icon_dashboard_outlined,
    color: '#8c6bff',
    softColor: 'rgba(140, 107, 255, 0.14)',
    emphasize: Number(summary.value.pending_member_application_count || 0) > 0,
  },
  {
    key: 'manager_coverage',
    label: t('tenant_overview.efficiency_manager_coverage'),
    note: t('tenant_overview.efficiency_manager_coverage_hint'),
    value: formatPercentValue(managerCoverage.value),
    subValue: t('tenant_overview.efficiency_manager_member_ratio', {
      managers: formatNumber(
        roleRows.value
          .filter((item) => item.role === 'owner' || item.role === 'admin')
          .reduce((result, item) => result + Number(item.count || 0), 0)
      ),
      total: formatNumber(summary.value.member_total),
    }),
    progress: managerCoverage.value,
    icon: icon_error,
    color: '#f56c6c',
    softColor: 'rgba(245, 108, 108, 0.14)',
    emphasize: managerCoverage.value <= 0 && Number(summary.value.member_total || 0) > 0,
  },
])

const activityXAxis = computed<ChartAxis[]>(() => [{ name: 'date', value: 'date' }])
const activityYAxis = computed<ChartAxis[]>(() => [
  { name: t('tenant_overview.trend_active_members'), value: 'active_member_count', 'multi-quota': true },
  { name: t('tenant_overview.trend_activity_count'), value: 'activity_count', 'multi-quota': true },
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
    case 'data_skill':
      return t('tenant_overview.asset_terminology')
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

const formatApplicationType = (type?: string) => {
  if (type === 'invite') return t('tenant.application_type_invite')
  return t('tenant.application_type_join')
}

const formatTenantRole = (role?: string) => {
  if (role === 'owner') return t('user.tenant_role_owner')
  if (role === 'admin') return t('user.tenant_role_admin')
  return t('user.tenant_role_member')
}

const memberDisplayName = (member: { name?: string | null; account?: string | null; user_id?: number | string }) =>
  member.name || member.account || `#${member.user_id}`

const formatMemberActivityTime = (timestamp?: number) => {
  const value = Number(timestamp || 0)
  return value ? formatTimestamp(value, 'YYYY-MM-DD HH:mm:ss') : t('tenant_overview.member_activity_never')
}

const loadApplications = async () => {
  applicationLoading.value = true
  try {
    const [joinRows, invitationRows] = await Promise.all([
      tenantApi.tenantApplications('pending'),
      tenantApi.invitations('pending'),
    ])
    joinApplications.value = joinRows || []
    invitations.value = invitationRows || []
  } finally {
    applicationLoading.value = false
  }
}

const openReviewDialog = async () => {
  reviewDialogVisible.value = true
  await loadApplications()
}

const reviewJoinApplication = async (application: TenantApplicationInfo, approved: boolean) => {
  joinReviewLoadingId.value = String(application.id)
  try {
    let reviewComment = ''
    if (approved) {
      await ElMessageBox.confirm(
        t('tenant.approve_join_confirm', {
          msg: application.applicant_name || application.applicant_account,
        }),
        {
          confirmButtonType: 'primary',
          confirmButtonText: t('tenant.approve'),
          cancelButtonText: t('common.cancel'),
          customClass: 'confirm-no_icon',
          autofocus: false,
        }
      )
    } else {
      const result = await ElMessageBox.prompt(t('tenant.reject_reason'), t('tenant.reject'), {
        confirmButtonType: 'danger',
        confirmButtonText: t('tenant.reject'),
        cancelButtonText: t('common.cancel'),
        inputType: 'textarea',
        customClass: 'confirm-no_icon',
        autofocus: false,
      })
      reviewComment = result.value || ''
    }
    await tenantApi.reviewTenantApplication(application.id, {
      approved,
      review_comment: reviewComment,
    })
    ElMessage.success(t('common.save_success'))
    await Promise.all([loadApplications(), loadOverview()])
  } finally {
    joinReviewLoadingId.value = ''
  }
}

const cancelInvitation = async (invitation: TenantApplicationInfo) => {
  inviteCancelingId.value = String(invitation.id)
  try {
    await ElMessageBox.confirm(
      t('tenant.cancel_invitation_confirm', {
        msg: invitation.applicant_name || invitation.applicant_account,
      }),
      {
        confirmButtonType: 'danger',
        confirmButtonText: t('tenant.cancel_invitation'),
        cancelButtonText: t('common.cancel'),
        customClass: 'confirm-no_icon',
        autofocus: false,
      }
    )
    await tenantApi.cancelInvitation(invitation.id)
    ElMessage.success(t('common.operation_success'))
    await Promise.all([loadApplications(), loadOverview()])
  } finally {
    inviteCancelingId.value = ''
  }
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

  .hero-identity-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: -4px;

    span {
      min-width: 0;
      max-width: 100%;
      padding: 3px 8px;
      border-radius: 6px;
      background: rgba(47, 107, 255, 0.08);
      color: var(--theme-text-secondary);
      font-size: 12px;
      line-height: 18px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
      word-break: break-all;
    }
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
    text-align: left;

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

    em {
      display: block;
      margin-top: 8px;
      font-style: normal;
      font-size: 12px;
      line-height: 18px;
      color: #2f6bff;
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
    text-align: left;
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

  .hero-focus-tail {
    display: flex;
    align-items: center;
    gap: 8px;
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

  .summary-note {
    margin-top: 4px;
    font-size: 12px;
    line-height: 18px;
    color: var(--theme-text-secondary);
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
      transition: width 180ms ease;
    }
  }

  .summary-subvalue {
    margin-top: 10px;
    color: var(--theme-text-secondary);
    font-size: 12px;
    line-height: 18px;
    word-break: break-word;
  }

  .is-actionable {
    appearance: none;
    border: none;
    cursor: pointer;
    font-family: inherit;
    transition:
      border-color 160ms ease,
      box-shadow 160ms ease,
      transform 160ms ease,
      background 160ms ease;

    &:hover {
      border-color: rgba(47, 107, 255, 0.35);
      box-shadow: 0 12px 28px rgba(47, 107, 255, 0.1);
      transform: translateY(-1px);
    }
  }

  .danger {
    color: #f56c6c !important;
  }

  .analytics-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 16px;
    margin-bottom: 18px;
  }

  .chart-card {
    padding: 18px;
    min-height: 360px;
    display: flex;
    flex-direction: column;
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

  .chart-surface-assets {
    flex: 1 1 auto;
    min-height: 300px;
    height: auto;
  }

  .ops-grid {
    display: grid;
    grid-template-columns: minmax(0, 1.2fr) minmax(300px, 0.9fr) minmax(300px, 0.9fr);
    gap: 16px;
  }

  .ops-card {
    padding: 18px;
    min-height: 320px;
  }

  .ops-card-wide {
    grid-column: span 2;
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
    text-align: left;
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

    .ops-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .ops-card-wide {
      grid-column: span 1;
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

    .ops-card-wide {
      grid-column: auto;
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

    .todo-item {
      align-items: flex-start;
      flex-direction: column;
    }
  }
}
</style>
