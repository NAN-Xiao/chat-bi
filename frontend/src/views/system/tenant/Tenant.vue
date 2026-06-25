<template>
  <div class="zhishu-table-container professional-container">
    <div class="tool-left">
      <span class="page-title">{{ t('tenant.management') }}</span>
      <div class="search-bar">
        <el-input
          v-model="keyword"
          class="tenant-search-input"
          :placeholder="t('tenant.search_placeholder')"
          clearable
        >
          <template #prefix>
            <el-icon>
              <icon_searchOutline_outlined />
            </el-icon>
          </template>
        </el-input>
        <el-button type="primary" @click="openDrawer(null)">
          <template #icon>
            <icon_add_outlined />
          </template>
          {{ t('tenant.add') }}
        </el-button>
      </div>
    </div>

    <div class="zhishu-table_user">
      <el-table :data="enterpriseRows" style="width: 100%">
        <el-table-column prop="name" :label="t('tenant.enterprise_user')" width="280">
          <template #default="scope">
            <div class="table-two-line-cell">
              <div class="enterprise-user-name ellipsis" :title="scope.row.name">
                {{ scope.row.name }}
              </div>
              <div v-if="scope.row.row_type === 'application'" class="table-secondary-text">
                {{ t('tenant.application_status_pending') }}
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="id" :label="t('tenant.tenant_id')" width="220" show-overflow-tooltip>
          <template #default="scope">
            <span>{{ scope.row.row_type === 'tenant' ? tenantDisplayId(scope.row) : '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('tenant.owner_or_applicant')" min-width="210">
          <template #default="scope">
            <div class="table-two-line-cell">
              <div class="table-primary-text ellipsis" :title="scope.row.contact_name">
                {{ scope.row.contact_name || '-' }}
              </div>
              <div
                v-if="scope.row.contact_detail"
                class="table-secondary-text ellipsis"
                :title="scope.row.contact_detail"
              >
                {{ scope.row.contact_detail }}
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column :label="t('tenant.member_stats')" width="140">
          <template #default="scope">
            <div v-if="scope.row.row_type === 'tenant'" class="table-two-line-cell">
              <span class="table-primary-text">
                {{ t('tenant.admin_count', { msg: scope.row.admin_count || 0 }) }}
              </span>
              <span class="table-secondary-text">
                {{ t('tenant.member_count', { msg: scope.row.member_count || 0 }) }}
              </span>
            </div>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('tenant.plan_subscription')" width="160">
          <template #default="scope">
            <span v-if="scope.row.row_type === 'application'" class="muted">
              {{ formatPlan(scope.row.plan) }}
            </span>
            <div v-else class="plan-subscription-cell">
              <span class="tenant-plain-text" :class="planTextClass(scope.row.plan)">
                {{ formatPlan(scope.row.plan) }}
              </span>
              <span
                class="tenant-plain-text"
                :class="subscriptionStatusClass(scope.row.subscription_status)"
              >
                {{ formatSubscriptionStatus(scope.row.subscription_status) }}
              </span>
            </div>
          </template>
        </el-table-column>
        <el-table-column :label="t('tenant.datasource_binding_status')" width="130">
          <template #default="scope">
            <span v-if="scope.row.row_type === 'tenant'" class="table-primary-text">
              {{ scope.row.bound_datasource_id ? t('tenant.datasource_bound') : '-' }}
            </span>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="status" :label="t('tenant.status')" width="140">
          <template #default="scope">
            <span
              v-if="scope.row.row_type === 'application'"
              class="tenant-plain-text"
              :class="applicationStatusClass(scope.row.application_status)"
            >
              {{ formatApplicationStatus(scope.row.application_status) }}
            </span>
            <div
              v-else
              class="user-status-container"
              :class="scope.row.status ? 'active' : 'disabled'"
            >
              <el-icon size="16">
                <SuccessFilled v-if="scope.row.status" />
                <CircleCloseFilled v-else />
              </el-icon>
              <span>{{ scope.row.status ? t('tenant.enabled') : t('tenant.disabled') }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column :label="t('tenant.usage_summary')" width="190">
          <template #default="scope">
            <div v-if="scope.row.row_type === 'tenant'" class="usage-status-cell">
              <el-progress
                type="circle"
                :width="36"
                :stroke-width="4"
                :show-text="false"
                :percentage="usageHealthPercent(scope.row.id)"
                :status="usageProgressStatus(scope.row.id)"
              />
              <div class="usage-summary-text">
                <span>{{ t('tenant.requests') }} {{ usageRequestCount(scope.row.id) }}</span>
                <span class="muted"
                  >{{ t('tenant.failure') }} {{ usageFailureCount(scope.row.id) }}</span
                >
              </div>
            </div>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
        <el-table-column
          prop="current_period_end_time"
          :label="t('tenant.current_period_end_time')"
          width="180"
        >
          <template #default="scope">
            <span>{{ formatOptionalTimestamp(scope.row.current_period_end_time) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="create_time" :label="t('tenant.create_time')" width="180">
          <template #default="scope">
            <span>{{ formatOptionalTimestamp(scope.row.create_time) }}</span>
          </template>
        </el-table-column>
        <el-table-column fixed="right" :label="t('ds.actions')" width="180">
          <template #default="scope">
            <div v-if="scope.row.row_type === 'application'" class="review-actions">
              <el-button
                text
                :loading="reviewLoadingId === String(scope.row.application_id)"
                @click="reviewApplication(scope.row.source, true)"
              >
                {{ t('tenant.approve') }}
              </el-button>
              <div class="line"></div>
              <el-button text type="danger" @click="reviewApplication(scope.row.source, false)">
                {{ t('tenant.reject') }}
              </el-button>
            </div>
            <div v-else class="table-operate">
              <el-tooltip
                :offset="14"
                effect="dark"
                :content="t('tenant.enter_workspace_delegate')"
                placement="top"
              >
                <el-icon class="action-btn" size="16" @click="openWorkspaceAdmin(scope.row.source)">
                  <icon_into_item_outlined />
                </el-icon>
              </el-tooltip>
              <div class="line"></div>
              <el-tooltip
                :offset="14"
                effect="dark"
                :content="t('datasource.edit')"
                placement="top"
              >
                <el-icon class="action-btn" size="16" @click="openDrawer(scope.row.source)">
                  <IconOpeEdit />
                </el-icon>
              </el-tooltip>
              <div class="line"></div>
              <el-tooltip
                :offset="14"
                effect="dark"
                :content="scope.row.status ? t('tenant.stop_service') : t('tenant.restore_service')"
                placement="top"
              >
                <el-icon
                  class="action-btn"
                  :class="{ disabled: isDefaultTenant(scope.row) }"
                  size="16"
                  @click="handleServiceStatus(scope.row.source)"
                >
                  <IconLock />
                </el-icon>
              </el-tooltip>
              <div class="line"></div>
              <el-tooltip
                :offset="14"
                effect="dark"
                :content="t('tenant.delete_tenant')"
                placement="top"
              >
                <el-icon
                  class="action-btn"
                  :class="{
                    disabled:
                      isDefaultTenant(scope.row) || deleteLoadingId === String(scope.row.id),
                  }"
                  size="16"
                  @click="deleteTenantHandler(scope.row.source)"
                >
                  <IconOpeDelete />
                </el-icon>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
        <template #empty>
          <EmptyBackground :description="t('tenant.empty')" img-type="tree" />
        </template>
      </el-table>
    </div>

    <el-drawer
      v-model="drawerVisible"
      :title="form.id ? t('tenant.edit') : t('tenant.add')"
      destroy-on-close
      modal-class="tenant-add-class"
      size="520px"
      :before-close="closeDrawer"
    >
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        class="form-content_error"
        @submit.prevent
      >
        <el-form-item prop="name" :label="t('tenant.name')">
          <el-input v-model="form.name" maxlength="255" clearable />
        </el-form-item>
        <el-form-item prop="plan" :label="t('tenant.plan')">
          <el-select v-model="form.plan" style="width: 240px">
            <el-option
              v-for="item in planOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item prop="subscription_status" :label="t('tenant.subscription_status')">
          <el-select v-model="form.subscription_status" style="width: 240px">
            <el-option
              v-for="item in subscriptionStatusOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item prop="billing_mode" :label="t('tenant.billing_mode')">
          <el-select v-model="form.billing_mode" style="width: 240px">
            <el-option
              v-for="item in billingModeOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('tenant.bound_datasource')">
          <el-select
            v-model="form.datasource_id"
            clearable
            filterable
            :disabled="isDefaultTenantForm"
            :loading="datasourceLoading"
            style="width: 100%"
            :placeholder="t('tenant.select_datasource')"
          >
            <el-option
              v-for="datasource in datasourceOptions"
              :key="datasource.id"
              :label="datasource.name"
              :value="datasource.id"
            >
              <div class="datasource-option">
                <span class="datasource-name ellipsis">{{ datasource.name }}</span>
                <span class="datasource-type ellipsis">{{
                  datasource.type_name || datasource.type
                }}</span>
              </div>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item :label="t('tenant.trial_end_time')">
          <el-date-picker
            v-model="form.trial_end_time"
            type="datetime"
            value-format="x"
            clearable
            style="width: 240px"
          />
        </el-form-item>
        <el-form-item :label="t('tenant.current_period_end_time')">
          <el-date-picker
            v-model="form.current_period_end_time"
            type="datetime"
            value-format="x"
            clearable
            style="width: 240px"
          />
        </el-form-item>
        <el-form-item :label="t('tenant.contract_no')">
          <el-input v-model="form.contract_no" maxlength="128" clearable />
        </el-form-item>
        <el-form-item :label="t('tenant.billing_contact')">
          <el-input v-model="form.billing_contact" maxlength="128" clearable />
        </el-form-item>
        <el-form-item :label="t('tenant.billing_email')">
          <el-input v-model="form.billing_email" maxlength="128" clearable />
        </el-form-item>
        <el-form-item :label="t('tenant.subscription_note')">
          <el-input v-model="form.subscription_note" type="textarea" :rows="4" maxlength="2000" />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button secondary @click="closeDrawer">{{ t('common.cancel') }}</el-button>
          <el-button type="primary" :loading="saving" @click="saveTenant">
            {{ t('common.save') }}
          </el-button>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import dayjs from 'dayjs'
import { computed, onMounted, reactive, ref, shallowRef } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus-secondary'
import { useI18n } from 'vue-i18n'
import SuccessFilled from '@/assets/svg/gou_icon.svg'
import CircleCloseFilled from '@/assets/svg/icon_ban_filled.svg'
import IconLock from '@/assets/svg/icon-key_outlined.svg'
import IconOpeEdit from '@/assets/svg/icon_edit_outlined.svg'
import IconOpeDelete from '@/assets/svg/icon_delete.svg'
import icon_add_outlined from '@/assets/svg/icon_add_outlined.svg'
import icon_into_item_outlined from '@/assets/svg/icon_into-item_outlined.svg'
import icon_searchOutline_outlined from '@/assets/svg/icon_search-outline_outlined.svg'
import EmptyBackground from '@/views/dashboard/common/EmptyBackground.vue'
import { datasourceApi } from '@/api/datasource'
import {
  tenantApi,
  type TenantApplicationInfo,
  type TenantInfo,
  type TenantUsageDailyInfo,
} from '@/api/tenant'
import { useUserStore } from '@/stores/user'
import { formatTimestamp } from '@/utils/date'
import {
  PLATFORM_WORKSPACE_DELEGATE_QUERY_KEY,
  PLATFORM_WORKSPACE_DELEGATE_TENANT_QUERY_KEY,
} from '@/utils/platformWorkspaceDelegate'

const { t } = useI18n()
const router = useRouter()
const userStore = useUserStore()
const keyword = ref('')
const drawerVisible = ref(false)
const saving = ref(false)
const statusLoadingId = ref('')
const deleteLoadingId = ref('')
const reviewLoadingId = ref('')
const datasourceLoading = ref(false)
const formRef = ref()
const tenants = shallowRef<TenantInfo[]>([])
const applications = shallowRef<TenantApplicationInfo[]>([])
const usageRows = shallowRef<TenantUsageDailyInfo[]>([])
const datasourceOptions = shallowRef<any[]>([])
const defaultForm = {
  id: '',
  name: '',
  plan: 'default',
  subscription_status: 'active',
  billing_mode: 'manual',
  trial_end_time: null as number | string | null,
  current_period_end_time: null as number | string | null,
  contract_no: '',
  billing_contact: '',
  billing_email: '',
  subscription_note: '',
  datasource_id: '' as number | string,
}
const form = reactive({ ...defaultForm })

const planOptions = computed(() => [
  { value: 'default', label: t('tenant.plan_default') },
  { value: 'basic', label: t('tenant.plan_basic') },
  { value: 'enterprise', label: t('tenant.plan_enterprise') },
])

const subscriptionStatusOptions = computed(() => [
  { value: 'active', label: t('tenant.subscription_active') },
  { value: 'trialing', label: t('tenant.subscription_trialing') },
  { value: 'past_due', label: t('tenant.subscription_past_due') },
  { value: 'suspended', label: t('tenant.subscription_suspended') },
  { value: 'cancelled', label: t('tenant.subscription_cancelled') },
])

const billingModeOptions = computed(() => [
  { value: 'manual', label: t('tenant.billing_manual') },
  { value: 'contract', label: t('tenant.billing_contract') },
  { value: 'offline', label: t('tenant.billing_offline') },
])

const rules = computed(() => ({
  name: [{ required: true, message: t('tenant.name_required'), trigger: 'blur' }],
  plan: [{ required: true, message: t('tenant.plan_required'), trigger: 'change' }],
  subscription_status: [
    { required: true, message: t('tenant.subscription_status_required'), trigger: 'change' },
  ],
}))

const filteredTenants = computed(() => {
  const value = keyword.value.trim().toLowerCase()
  const rows = [
    ...applications.value
      .filter((application) => application.status === 'pending')
      .map((application) => ({
        row_type: 'application',
        id: `application-${application.id}`,
        application_id: application.id,
        name: application.tenant_name,
        plan: application.plan,
        subscription_status: '',
        current_period_end_time: null,
        status: null,
        application_status: application.status,
        contact_name: application.applicant_name || application.applicant_account || '',
        contact_detail: application.applicant_email || application.applicant_account || '',
        create_time: application.create_time,
        update_time: application.update_time,
        source: application,
      })),
    ...tenants.value.map((tenant) => ({
      ...tenant,
      row_type: 'tenant',
      application_status: '',
      contact_name: tenant.owner_name || tenant.owner_account || '',
      contact_detail: tenant.owner_email || tenant.owner_account || '',
      bound_datasource_id: normalizeBoundDatasourceId(tenant),
      bound_datasource_name: normalizeBoundDatasourceName(tenant),
      admin_count: tenant.admin_count || 0,
      member_count: tenant.member_count || 0,
      source: tenant,
    })),
  ]
  if (!value) return rows
  return rows.filter((row) =>
    [row.name, row.row_type === 'tenant' ? tenantDisplayId(row) : ''].some((item) =>
      String(item || '')
        .toLowerCase()
        .includes(value)
    )
  )
})

const enterpriseRows = filteredTenants

const tenantDisplayId = (tenant?: { id?: number | string; public_id?: string } | null) =>
  String(tenant?.public_id || '')

const tenantUsageMap = computed(() => {
  return usageRows.value.reduce<
    Record<string, { requests: number; failures: number; success: number }>
  >((result, row) => {
    const tenantId = String(row.tenant_id || '')
    if (!tenantId) return result
    if (!result[tenantId]) {
      result[tenantId] = { requests: 0, failures: 0, success: 0 }
    }
    result[tenantId].requests += Number(row.request_count || 0)
    result[tenantId].failures += Number(row.failure_count || 0)
    result[tenantId].success += Number(row.success_count || 0)
    return result
  }, {})
})

const isDefaultTenant = (tenant: TenantInfo) => Number(tenant.id) === 1
const isDefaultTenantForm = computed(() => Number(form.id) === 1)

const normalizeBoundDatasourceId = (tenant?: TenantInfo | null) =>
  tenant?.bound_datasource_id || tenant?.bound_project_id || ''

const normalizeBoundDatasourceName = (tenant?: TenantInfo | null) =>
  tenant?.bound_datasource_name || tenant?.bound_project_name || ''

const formatPlan = (plan?: string) => {
  const key = `tenant.plan_${plan || 'default'}`
  const label = t(key)
  return label === key ? plan || t('tenant.plan_default') : label
}

const formatSubscriptionStatus = (status?: string) => {
  const key = `tenant.subscription_${status || 'active'}`
  const label = t(key)
  return label === key ? status || t('tenant.subscription_active') : label
}

const planTextClass = (plan?: string) => {
  if (plan === 'enterprise') return 'is-enterprise'
  if (plan === 'basic') return 'is-basic'
  return 'is-default'
}

const subscriptionStatusClass = (status?: string) => {
  if (status === 'suspended' || status === 'cancelled') return 'is-danger'
  if (status === 'past_due') return 'is-warning'
  if (status === 'trialing') return 'is-primary'
  return 'is-success'
}

const applicationStatusClass = (status?: string) => {
  if (status === 'approved') return 'is-success'
  if (status === 'rejected' || status === 'cancelled') return 'is-danger'
  return 'is-warning'
}

const usageHealthPercent = (tenantId: string | number) => {
  const usage = tenantUsageMap.value[String(tenantId)]
  if (!usage || usage.requests <= 0) return 0
  return Math.max(1, Math.round((usage.success / usage.requests) * 100))
}

const usageProgressStatus = (tenantId: string | number) => {
  const usage = tenantUsageMap.value[String(tenantId)]
  if (!usage || usage.requests <= 0) return undefined
  const percent = usageHealthPercent(tenantId)
  if (percent >= 98) return 'success'
  if (percent >= 90) return 'warning'
  return 'exception'
}

const usageRequestCount = (tenantId: string | number) => {
  const usage = tenantUsageMap.value[String(tenantId)]
  return usage ? usage.requests.toLocaleString() : '0'
}

const usageFailureCount = (tenantId: string | number) => {
  const usage = tenantUsageMap.value[String(tenantId)]
  return usage ? usage.failures.toLocaleString() : '0'
}

const normalizeTimestamp = (value?: number | string | null) => {
  if (value === undefined || value === null || value === '') return null
  const timestamp = Number(value)
  return Number.isFinite(timestamp) && timestamp > 0 ? timestamp : null
}

const formatOptionalTimestamp = (value?: number | string | null) => {
  const timestamp = normalizeTimestamp(value)
  return timestamp ? formatTimestamp(timestamp, 'YYYY-MM-DD HH:mm:ss') : '-'
}

const formatApplicationStatus = (status?: string) => {
  const key = `tenant.application_status_${status || 'pending'}`
  const label = t(key)
  return label === key ? status || '-' : label
}

const loadTenants = async () => {
  tenants.value = await tenantApi.adminList()
}

const loadApplications = async () => {
  applications.value = await tenantApi.adminApplications()
}

const loadDatasourceOptions = async () => {
  if (datasourceOptions.value.length) return
  datasourceLoading.value = true
  try {
    datasourceOptions.value = await datasourceApi.list()
  } finally {
    datasourceLoading.value = false
  }
}

const loadUsageSnapshot = async () => {
  usageRows.value = await tenantApi.usage({
    start_date: dayjs().subtract(13, 'day').format('YYYY-MM-DD'),
    end_date: dayjs().format('YYYY-MM-DD'),
    limit: 5000,
  })
}

const reloadEnterpriseRows = async () => {
  await loadTenants()
  await loadUsageSnapshot()
  await loadApplications()
  await userStore.loadTenants(true)
}

const openDrawer = async (tenant: TenantInfo | null) => {
  await loadDatasourceOptions()
  Object.assign(form, {
    ...defaultForm,
    ...(tenant || {}),
    id: tenant?.id ? String(tenant.id) : '',
    plan: tenant?.plan || 'default',
    subscription_status: tenant?.subscription_status || 'active',
    billing_mode: tenant?.billing_mode || 'manual',
    trial_end_time: tenant?.trial_end_time || null,
    current_period_end_time: tenant?.current_period_end_time || null,
    contract_no: tenant?.contract_no || '',
    billing_contact: tenant?.billing_contact || '',
    billing_email: tenant?.billing_email || '',
    subscription_note: tenant?.subscription_note || '',
    datasource_id: normalizeBoundDatasourceId(tenant),
  })
  drawerVisible.value = true
}

const closeDrawer = () => {
  Object.assign(form, defaultForm)
  drawerVisible.value = false
}

const openWorkspaceAdmin = (tenant: TenantInfo) => {
  router.push({
    path: '/default-dashboard/index',
    query: {
      [PLATFORM_WORKSPACE_DELEGATE_QUERY_KEY]: '1',
      [PLATFORM_WORKSPACE_DELEGATE_TENANT_QUERY_KEY]: String(tenant.id),
      tenant_public_id: tenantDisplayId(tenant),
      tenant_name: tenant.name || '',
    },
  })
}

const saveTenant = () => {
  formRef.value?.validate(async (valid: boolean) => {
    if (!valid) return
    saving.value = true
    try {
      const payload = {
        name: form.name,
        plan: form.plan,
        subscription_status: form.subscription_status,
        billing_mode: form.billing_mode,
        trial_end_time: normalizeTimestamp(form.trial_end_time),
        current_period_end_time: normalizeTimestamp(form.current_period_end_time),
        contract_no: form.contract_no,
        billing_contact: form.billing_contact,
        billing_email: form.billing_email,
        subscription_note: form.subscription_note,
        ...(!isDefaultTenantForm.value ? { datasource_id: form.datasource_id || null } : {}),
      }
      if (form.id) {
        await tenantApi.edit(form.id, payload)
      } else {
        await tenantApi.add(payload)
      }
      ElMessage.success(t('common.save_success'))
      closeDrawer()
      await reloadEnterpriseRows()
    } finally {
      saving.value = false
    }
  })
}

const confirmStopService = async (tenant: TenantInfo) => {
  await ElMessageBox.confirm(t('tenant.stop_service_confirm', { msg: tenant.name }), {
    confirmButtonType: 'danger',
    confirmButtonText: t('tenant.stop_service'),
    cancelButtonText: t('common.cancel'),
    customClass: 'confirm-no_icon',
    autofocus: false,
  })
  await ElMessageBox.confirm(t('tenant.stop_service_second_confirm', { msg: tenant.name }), {
    confirmButtonType: 'danger',
    confirmButtonText: t('tenant.confirm_stop_service'),
    cancelButtonText: t('common.cancel'),
    customClass: 'confirm-no_icon',
    autofocus: false,
  })
}

const handleServiceStatus = async (tenant: TenantInfo) => {
  if (isDefaultTenant(tenant)) return
  const nextStatus = Number(tenant.status) ? 0 : 1
  statusLoadingId.value = String(tenant.id)
  try {
    if (!nextStatus) {
      await confirmStopService(tenant)
    } else {
      await ElMessageBox.confirm(t('tenant.restore_service_confirm', { msg: tenant.name }), {
        confirmButtonType: 'primary',
        confirmButtonText: t('tenant.restore_service'),
        cancelButtonText: t('common.cancel'),
        customClass: 'confirm-no_icon',
        autofocus: false,
      })
    }
    await tenantApi.status(tenant.id, nextStatus)
    ElMessage.success(t('common.save_success'))
    await reloadEnterpriseRows()
  } finally {
    statusLoadingId.value = ''
  }
}

const deleteTenantHandler = async (tenant: TenantInfo) => {
  if (isDefaultTenant(tenant)) return
  if (Number(tenant.status) !== 0) {
    await ElMessageBox.alert(t('tenant.delete_requires_disabled', { msg: tenant.name }), {
      confirmButtonText: t('common.confirm'),
      customClass: 'confirm-no_icon',
      autofocus: false,
    })
    return
  }
  await ElMessageBox.confirm(t('tenant.delete_tenant_confirm', { msg: tenant.name }), {
    confirmButtonType: 'danger',
    confirmButtonText: t('tenant.delete_tenant'),
    cancelButtonText: t('common.cancel'),
    customClass: 'confirm-no_icon',
    autofocus: false,
  })
  const result = await ElMessageBox.prompt(
    t('tenant.delete_tenant_id_confirm', { id: tenantDisplayId(tenant) }),
    t('tenant.delete_tenant'),
    {
      confirmButtonType: 'danger',
      confirmButtonText: t('tenant.confirm_delete_tenant'),
      cancelButtonText: t('common.cancel'),
      inputPlaceholder: tenantDisplayId(tenant),
      customClass: 'confirm-no_icon',
      autofocus: false,
    }
  )
  if ((result.value || '').trim() !== tenantDisplayId(tenant).trim()) {
    ElMessage.error(t('tenant.delete_tenant_id_mismatch'))
    return
  }
  deleteLoadingId.value = String(tenant.id)
  try {
    await tenantApi.delete(tenant.id)
    ElMessage.success(t('common.delete_success'))
    await reloadEnterpriseRows()
  } finally {
    deleteLoadingId.value = ''
  }
}

const reviewApplication = async (application: TenantApplicationInfo, approved: boolean) => {
  reviewLoadingId.value = String(application.id)
  try {
    let reviewComment = ''
    if (!approved) {
      const result = await ElMessageBox.prompt(t('tenant.reject_reason'), t('tenant.reject'), {
        confirmButtonType: 'danger',
        confirmButtonText: t('tenant.reject'),
        cancelButtonText: t('common.cancel'),
        inputType: 'textarea',
        customClass: 'confirm-no_icon',
        autofocus: false,
      })
      reviewComment = result.value || ''
    } else {
      await ElMessageBox.confirm(t('tenant.approve_confirm', { msg: application.tenant_name }), {
        confirmButtonType: 'primary',
        confirmButtonText: t('tenant.approve'),
        cancelButtonText: t('common.cancel'),
        customClass: 'confirm-no_icon',
        autofocus: false,
      })
    }
    await tenantApi.reviewApplication(application.id, {
      approved,
      review_comment: reviewComment,
    })
    ElMessage.success(t('common.save_success'))
    await loadApplications()
    await loadTenants()
    await userStore.loadTenants(true)
  } finally {
    reviewLoadingId.value = ''
  }
}

onMounted(() => {
  loadTenants()
  loadUsageSnapshot()
  loadApplications()
})
</script>

<style lang="less" scoped>
.zhishu-table-container {
  width: 100%;
  height: 100%;
  position: relative;

  .tool-left {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 16px;
    gap: 16px;

    .page-title {
      flex: 0 0 auto;
      font-weight: 500;
      font-size: 20px;
      line-height: 28px;
      white-space: nowrap;
    }
  }

  .search-bar {
    flex: 0 0 auto;
    display: flex;
    align-items: center;

    .tenant-search-input {
      width: 260px;
      margin-right: 12px;
    }
  }

  .zhishu-table_user {
    width: 100%;
    max-height: calc(100vh - 156px);
    overflow: auto;

    :deep(.ed-popper.is-dark) {
      max-width: 400px;
    }

    :deep(.ed-table) {
      --el-table-header-bg-color: #f5f7fa;
      --el-table-border-color: #ebeef5;
      --el-table-header-text-color: #606266;
      background: #fff;

      th {
        font-weight: 600;
        height: 48px;
        background: #f7f9fc;
      }

      td {
        height: 52px;
      }

      .ed-table__row {
        transition: background-color 0.16s ease;
      }

      .ed-table__row:hover > td {
        background-color: #f8fbff;
      }
    }

    .muted {
      color: #8f959e;
      font-size: 12px;
      line-height: 18px;
    }

    .tenant-plain-text {
      font-size: 14px;
      font-weight: 500;
      line-height: 22px;

      &.is-default {
        color: #646a73;
        font-weight: 400;
      }

      &.is-basic {
        color: #245bdb;
      }

      &.is-enterprise {
        color: #8f3f11;
      }

      &.is-primary {
        color: #245bdb;
      }

      &.is-success {
        color: #24714d;
      }

      &.is-warning {
        color: #b76e00;
      }

      &.is-danger {
        color: #c42a2a;
      }
    }

    .plan-subscription-cell,
    .table-two-line-cell {
      min-width: 0;
      display: flex;
      flex-direction: column;
      gap: 2px;
    }

    .plan-subscription-cell {
      gap: 0;
    }

    .table-primary-text,
    .enterprise-user-name {
      max-width: 100%;
      color: #1f2329;
      font-size: 14px;
      font-weight: 500;
      line-height: 22px;
    }

    .table-secondary-text {
      max-width: 100%;
      color: #8f959e;
      font-size: 12px;
      line-height: 18px;
    }

    .review-actions,
    .table-operate {
      display: flex;
      align-items: center;
      height: 24px;
      line-height: 24px;

      .line {
        margin: 0 10px 0 12px;
        height: 16px;
        width: 1px;
        background-color: #1f232926;
      }
    }

    .review-actions {
      .ed-button {
        height: 24px;
        padding: 0 4px;
      }
    }

    .table-operate {
      .ed-icon + .ed-icon {
        margin-left: 12px;
      }

      .ed-icon {
        position: relative;
        cursor: pointer;
        color: #646a73;

        &.disabled {
          cursor: not-allowed;
          color: #b8bdc6;

          &::after {
            display: none !important;
          }
        }

        &::after {
          content: '';
          background-color: #1f23291a;
          position: absolute;
          border-radius: 6px;
          width: 24px;
          height: 24px;
          transform: translate(-50%, -50%);
          top: 50%;
          left: 50%;
          display: none;
        }

        &:hover {
          &::after {
            display: block;
          }
        }
      }
    }

    .usage-status-cell {
      display: flex;
      align-items: center;
      gap: 10px;
      min-width: 0;
    }

    .usage-summary-text {
      display: flex;
      flex-direction: column;
      min-width: 0;
      color: #1f2329;
      font-size: 13px;
      line-height: 18px;
    }
  }
}

.user-status-container {
  display: flex;
  align-items: center;
  font-weight: 400;
  font-size: 14px;
  line-height: 22px;

  .ed-icon {
    margin-right: 8px;
  }

  &.active {
    color: #24714d;
  }

  &.disabled {
    color: #8f959e;
  }
}

.datasource-option {
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;

  .datasource-name {
    min-width: 0;
  }

  .datasource-type {
    max-width: 120px;
    color: #8f959e;
    font-size: 12px;
  }
}
</style>

<style lang="less">
.tenant-add-class {
  .ed-drawer,
  .ed-drawer__header,
  .ed-drawer__body,
  .ed-drawer__footer {
    background: #fff !important;
    color: #1f2329 !important;
  }

  .ed-drawer__header {
    border-bottom: 1px solid #dee0e3;
    margin-bottom: 0;
    padding-bottom: 16px;
  }

  .ed-drawer__body {
    padding-top: 16px;
  }

  .ed-drawer__footer {
    border-top: 1px solid #dee0e3;
  }

  .ed-form-item__label,
  .ed-select__selected-item,
  .ed-input__inner,
  .ed-textarea__inner {
    color: #1f2329 !important;
    -webkit-text-fill-color: #1f2329 !important;
  }

  .ed-input__wrapper,
  .ed-select__wrapper,
  .ed-textarea__inner,
  .ed-date-editor {
    background-color: #fff !important;
    border-color: #d0d3d6 !important;
    box-shadow: 0 0 0 1px #d0d3d6 inset !important;
  }

  .ed-input__inner::placeholder,
  .ed-textarea__inner::placeholder {
    color: #8f959e !important;
    -webkit-text-fill-color: #8f959e !important;
  }

  .ed-input.is-disabled .ed-input__wrapper {
    background-color: #f5f6f7 !important;
    box-shadow: 0 0 0 1px #dee0e3 inset !important;
  }

  .ed-input.is-disabled .ed-input__inner {
    color: #8f959e !important;
    -webkit-text-fill-color: #8f959e !important;
  }

  .ed-button.is-secondary {
    background-color: #fff !important;
    border-color: #d0d3d6 !important;
    color: #1f2329 !important;
  }
}

:root[data-theme='dark'] {
  .tenant-add-class {
    color-scheme: light;
  }
}
</style>
