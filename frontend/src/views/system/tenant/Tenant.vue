<template>
  <div class="tenant-container professional-container">
    <div class="tool-left">
      <span class="page-title">{{ t('tenant.management') }}</span>
      <div class="search-bar">
        <el-input
          v-model="keyword"
          style="width: 260px; margin-right: 12px"
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

    <div class="section-title">{{ t('tenant.application_review') }}</div>
    <el-table :data="applications" class="tenant-table application-table" style="width: 100%">
      <el-table-column prop="tenant_name" :label="t('tenant.name')" min-width="160" show-overflow-tooltip />
      <el-table-column prop="tenant_code" :label="t('tenant.code')" min-width="130" show-overflow-tooltip />
      <el-table-column prop="applicant_name" :label="t('tenant.applicant')" min-width="150" show-overflow-tooltip>
        <template #default="scope">
          <div>
            <div>{{ scope.row.applicant_name || scope.row.applicant_account || '-' }}</div>
            <div class="muted">{{ scope.row.applicant_email || scope.row.applicant_account }}</div>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="requested_role" :label="t('tenant.requested_role')" width="130">
        <template #default="scope">
          {{ formatRequestedRole(scope.row.requested_role) }}
        </template>
      </el-table-column>
      <el-table-column prop="plan" :label="t('tenant.plan')" width="120">
        <template #default="scope">
          <el-tag size="small" type="info">{{ formatPlan(scope.row.plan) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="status" :label="t('tenant.application_status')" width="120">
        <template #default="scope">
          <el-tag size="small" :type="applicationStatusType(scope.row.status)">
            {{ formatApplicationStatus(scope.row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="reason" :label="t('tenant.apply_reason')" min-width="180" show-overflow-tooltip />
      <el-table-column prop="create_time" :label="t('tenant.apply_time')" width="180">
        <template #default="scope">
          <span>{{ formatTimestamp(scope.row.create_time, 'YYYY-MM-DD HH:mm:ss') }}</span>
        </template>
      </el-table-column>
      <el-table-column fixed="right" :label="t('ds.actions')" width="150">
        <template #default="scope">
          <div v-if="scope.row.status === 'pending'" class="review-actions">
            <el-button text :loading="reviewLoadingId === String(scope.row.id)" @click="reviewApplication(scope.row, true)">
              {{ t('tenant.approve') }}
            </el-button>
            <el-button text type="danger" @click="reviewApplication(scope.row, false)">
              {{ t('tenant.reject') }}
            </el-button>
          </div>
          <span v-else class="muted">{{ scope.row.review_comment || '-' }}</span>
        </template>
      </el-table-column>
      <template #empty>
        <EmptyBackground :description="t('tenant.no_applications')" img-type="tree" />
      </template>
    </el-table>

    <div class="section-title">{{ t('tenant.domain_review') }}</div>
    <el-table :data="domainRows" class="tenant-table application-table" style="width: 100%">
      <el-table-column prop="domain" :label="t('tenant.domain')" min-width="180" show-overflow-tooltip />
      <el-table-column prop="tenant_id" :label="t('tenant.tenant_id')" width="130" />
      <el-table-column prop="auto_join_role" :label="t('tenant.auto_join_role')" width="140">
        <template #default="scope">
          {{ formatRequestedRole(scope.row.auto_join_role) }}
        </template>
      </el-table-column>
      <el-table-column prop="status" :label="t('tenant.domain_status')" width="120">
        <template #default="scope">
          <el-tag size="small" :type="domainStatusType(scope.row.status)">
            {{ formatDomainStatus(scope.row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="create_time" :label="t('tenant.create_time')" width="180">
        <template #default="scope">
          <span>{{ formatOptionalTimestamp(scope.row.create_time) }}</span>
        </template>
      </el-table-column>
      <el-table-column fixed="right" :label="t('ds.actions')" width="150">
        <template #default="scope">
          <div v-if="scope.row.status === 'pending'" class="review-actions">
            <el-button text :loading="domainReviewLoadingId === String(scope.row.id)" @click="reviewDomain(scope.row, 'verified')">
              {{ t('tenant.verify') }}
            </el-button>
            <el-button text type="danger" @click="reviewDomain(scope.row, 'disabled')">
              {{ t('tenant.disable') }}
            </el-button>
          </div>
          <span v-else class="muted">-</span>
        </template>
      </el-table-column>
      <template #empty>
        <EmptyBackground :description="t('tenant.no_domain_bindings')" img-type="tree" />
      </template>
    </el-table>

    <div class="section-title">{{ t('tenant.data_request_review') }}</div>
    <el-table :data="dataRequestRows" class="tenant-table application-table" style="width: 100%">
      <el-table-column prop="tenant_id" :label="t('tenant.tenant_id')" width="130" />
      <el-table-column prop="request_type" :label="t('tenant.data_request_type')" width="130">
        <template #default="scope">
          {{ formatDataRequestType(scope.row.request_type) }}
        </template>
      </el-table-column>
      <el-table-column prop="status" :label="t('tenant.data_request_status')" width="120">
        <template #default="scope">
          <el-tag size="small" :type="dataRequestStatusType(scope.row.status)">
            {{ formatDataRequestStatus(scope.row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="reason" :label="t('tenant.apply_reason')" min-width="180" show-overflow-tooltip />
      <el-table-column prop="review_comment" :label="t('tenant.review_comment')" min-width="180" show-overflow-tooltip />
      <el-table-column prop="update_time" :label="t('tenant.update_time')" width="180">
        <template #default="scope">
          <span>{{ formatOptionalTimestamp(scope.row.update_time) }}</span>
        </template>
      </el-table-column>
      <el-table-column fixed="right" :label="t('ds.actions')" width="210">
        <template #default="scope">
          <div class="review-actions">
            <template v-if="scope.row.status === 'pending'">
              <el-button text :loading="dataRequestLoadingId === String(scope.row.id)" @click="reviewDataRequest(scope.row, true)">
                {{ t('tenant.approve') }}
              </el-button>
              <el-button text type="danger" @click="reviewDataRequest(scope.row, false)">
                {{ t('tenant.reject') }}
              </el-button>
            </template>
            <el-button
              v-else-if="scope.row.status === 'approved'"
              text
              :loading="dataRequestLoadingId === String(scope.row.id)"
              @click="completeDataRequest(scope.row)"
            >
              {{ t('tenant.complete') }}
            </el-button>
            <el-button v-if="scope.row.export_manifest" text @click="viewExportManifest(scope.row.export_manifest)">
              {{ t('tenant.view_manifest') }}
            </el-button>
          </div>
        </template>
      </el-table-column>
      <template #empty>
        <EmptyBackground :description="t('tenant.no_data_requests')" img-type="tree" />
      </template>
    </el-table>

    <div class="section-title">{{ t('tenant.workspace_list') }}</div>
    <el-table :data="filteredTenants" class="tenant-table" style="width: 100%">
      <el-table-column prop="name" :label="t('tenant.name')" min-width="180" show-overflow-tooltip />
      <el-table-column prop="code" :label="t('tenant.code')" min-width="140" show-overflow-tooltip />
      <el-table-column prop="plan" :label="t('tenant.plan')" width="140">
        <template #default="scope">
          <el-tag size="small" type="info">{{ formatPlan(scope.row.plan) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="subscription_status" :label="t('tenant.subscription_status')" width="150">
        <template #default="scope">
          <el-tag size="small" :type="subscriptionStatusType(scope.row.subscription_status)">
            {{ formatSubscriptionStatus(scope.row.subscription_status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="current_period_end_time" :label="t('tenant.current_period_end_time')" width="180">
        <template #default="scope">
          <span>{{ formatOptionalTimestamp(scope.row.current_period_end_time) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="status" :label="t('tenant.status')" width="140">
        <template #default="scope">
          <div class="tenant-status" :class="scope.row.status ? 'active' : 'disabled'">
            <span class="status-dot"></span>
            <span>{{ scope.row.status ? t('tenant.enabled') : t('tenant.disabled') }}</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="create_time" :label="t('tenant.create_time')" width="180">
        <template #default="scope">
          <span>{{ formatTimestamp(scope.row.create_time, 'YYYY-MM-DD HH:mm:ss') }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="update_time" :label="t('tenant.update_time')" width="180">
        <template #default="scope">
          <span>{{ formatTimestamp(scope.row.update_time, 'YYYY-MM-DD HH:mm:ss') }}</span>
        </template>
      </el-table-column>
      <el-table-column fixed="right" :label="t('ds.actions')" width="160">
        <template #default="scope">
          <div class="table-operate">
            <el-switch
              v-model="scope.row.status"
              :active-value="1"
              :inactive-value="0"
              :disabled="isDefaultTenant(scope.row) || statusLoadingId === String(scope.row.id)"
              size="small"
              @change="changeStatus(scope.row)"
            />
            <div class="line"></div>
            <el-button text @click="openDrawer(scope.row)">
              {{ t('datasource.edit') }}
            </el-button>
          </div>
        </template>
      </el-table-column>
      <template #empty>
        <EmptyBackground :description="t('tenant.empty')" img-type="tree" />
      </template>
    </el-table>

    <el-drawer
      v-model="drawerVisible"
      :title="form.id ? t('tenant.edit') : t('tenant.add')"
      destroy-on-close
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
        <el-form-item prop="code" :label="t('tenant.code')">
          <el-input v-model="form.code" :disabled="!!form.id" maxlength="64" clearable />
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
import { computed, onMounted, reactive, ref, shallowRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus-secondary'
import { useI18n } from 'vue-i18n'
import icon_add_outlined from '@/assets/svg/icon_add_outlined.svg'
import icon_searchOutline_outlined from '@/assets/svg/icon_search-outline_outlined.svg'
import EmptyBackground from '@/views/dashboard/common/EmptyBackground.vue'
import {
  tenantApi,
  type TenantApplicationInfo,
  type TenantDataRequestInfo,
  type TenantDomainInfo,
  type TenantInfo,
} from '@/api/tenant'
import { formatTimestamp } from '@/utils/date'
import { useUserStore } from '@/stores/user'

const { t } = useI18n()
const userStore = useUserStore()
const keyword = ref('')
const drawerVisible = ref(false)
const saving = ref(false)
const statusLoadingId = ref('')
const reviewLoadingId = ref('')
const domainReviewLoadingId = ref('')
const dataRequestLoadingId = ref('')
const formRef = ref()
const tenants = shallowRef<TenantInfo[]>([])
const applications = shallowRef<TenantApplicationInfo[]>([])
const domainRows = shallowRef<TenantDomainInfo[]>([])
const dataRequestRows = shallowRef<TenantDataRequestInfo[]>([])
const defaultForm = {
  id: '',
  code: '',
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
  code: [{ required: true, message: t('tenant.code_required'), trigger: 'blur' }],
  plan: [{ required: true, message: t('tenant.plan_required'), trigger: 'change' }],
  subscription_status: [
    { required: true, message: t('tenant.subscription_status_required'), trigger: 'change' },
  ],
}))

const filteredTenants = computed(() => {
  const value = keyword.value.trim().toLowerCase()
  if (!value) return tenants.value
  return tenants.value.filter((tenant) =>
    [tenant.name, tenant.code, tenant.plan].some((item) =>
      String(item || '').toLowerCase().includes(value)
    )
  )
})

const isDefaultTenant = (tenant: TenantInfo) => String(tenant.code || '') === 'default'

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

const subscriptionStatusType = (status?: string) => {
  if (status === 'suspended' || status === 'cancelled') return 'danger'
  if (status === 'past_due') return 'warning'
  if (status === 'trialing') return 'primary'
  return 'success'
}

const formatOptionalTimestamp = (value?: number | string | null) => {
  const timestamp = Number(value || 0)
  return timestamp ? formatTimestamp(timestamp, 'YYYY-MM-DD HH:mm:ss') : '-'
}

const normalizeTimestamp = (value?: number | string | null) => {
  if (value === undefined || value === null || value === '') return null
  const timestamp = Number(value)
  return Number.isFinite(timestamp) && timestamp > 0 ? timestamp : null
}

const formatRequestedRole = (role?: string) => {
  if (role === 'owner') return t('tenant.request_role_owner')
  if (role === 'admin') return t('tenant.request_role_admin')
  return t('tenant.request_role_member')
}

const formatApplicationStatus = (status?: string) => {
  const key = `tenant.application_status_${status || 'pending'}`
  const label = t(key)
  return label === key ? status || '-' : label
}

const applicationStatusType = (status?: string) => {
  if (status === 'approved') return 'success'
  if (status === 'rejected') return 'danger'
  return 'warning'
}

const formatDomainStatus = (status?: string) => {
  const key = `tenant.domain_status_${status || 'pending'}`
  const label = t(key)
  return label === key ? status || '-' : label
}

const domainStatusType = (status?: string) => {
  if (status === 'verified') return 'success'
  if (status === 'disabled') return 'info'
  return 'warning'
}

const formatDataRequestType = (type?: string) => {
  const key = `tenant.data_request_${type || 'export'}`
  const label = t(key)
  return label === key ? type || '-' : label
}

const formatDataRequestStatus = (status?: string) => {
  const key = `tenant.data_request_status_${status || 'pending'}`
  const label = t(key)
  return label === key ? status || '-' : label
}

const dataRequestStatusType = (status?: string) => {
  if (status === 'approved') return 'primary'
  if (status === 'completed') return 'success'
  if (status === 'rejected') return 'danger'
  return 'warning'
}

const loadTenants = async () => {
  tenants.value = await tenantApi.adminList()
}

const loadApplications = async () => {
  applications.value = await tenantApi.adminApplications()
}

const loadDomainReviews = async () => {
  domainRows.value = await tenantApi.adminDomains()
}

const loadDataRequests = async () => {
  dataRequestRows.value = await tenantApi.dataRequests()
}

const openDrawer = (tenant: TenantInfo | null) => {
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
  })
  drawerVisible.value = true
}

const closeDrawer = () => {
  Object.assign(form, defaultForm)
  drawerVisible.value = false
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
      }
      if (form.id) {
        await tenantApi.edit(form.id, payload)
      } else {
        await tenantApi.add({
          ...payload,
          code: form.code,
        })
      }
      ElMessage.success(t('common.save_success'))
      closeDrawer()
      await loadTenants()
      await loadApplications()
      await userStore.loadTenants(true)
    } finally {
      saving.value = false
    }
  })
}

const changeStatus = async (tenant: TenantInfo) => {
  const nextStatus = Number(tenant.status)
  const previousStatus = nextStatus ? 0 : 1
  statusLoadingId.value = String(tenant.id)
  try {
    if (!nextStatus) {
      await ElMessageBox.confirm(t('tenant.disable_confirm', { msg: tenant.name }), {
        confirmButtonType: 'danger',
        confirmButtonText: t('tenant.disable'),
        cancelButtonText: t('common.cancel'),
        customClass: 'confirm-no_icon',
        autofocus: false,
      })
    }
    await tenantApi.status(tenant.id, nextStatus)
    ElMessage.success(t('common.save_success'))
    await loadTenants()
    await userStore.loadTenants(true)
  } catch (error) {
    tenant.status = previousStatus
  } finally {
    statusLoadingId.value = ''
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

const reviewDomain = async (domain: TenantDomainInfo, status: 'verified' | 'disabled') => {
  domainReviewLoadingId.value = String(domain.id)
  try {
    if (status === 'verified') {
      await ElMessageBox.confirm(t('tenant.domain_verify_confirm', { msg: domain.domain }), {
        confirmButtonType: 'primary',
        confirmButtonText: t('tenant.verify'),
        cancelButtonText: t('common.cancel'),
        customClass: 'confirm-no_icon',
        autofocus: false,
      })
    } else {
      await ElMessageBox.confirm(t('tenant.domain_disable_confirm', { msg: domain.domain }), {
        confirmButtonType: 'danger',
        confirmButtonText: t('tenant.disable'),
        cancelButtonText: t('common.cancel'),
        customClass: 'confirm-no_icon',
        autofocus: false,
      })
    }
    await tenantApi.reviewDomain(domain.id, {
      status,
      auto_join_role: domain.auto_join_role === 'admin' ? 'admin' : 'member',
    })
    ElMessage.success(t('common.save_success'))
    await loadDomainReviews()
  } finally {
    domainReviewLoadingId.value = ''
  }
}

const reviewDataRequest = async (row: TenantDataRequestInfo, approved: boolean) => {
  dataRequestLoadingId.value = String(row.id)
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
      await ElMessageBox.confirm(t('tenant.data_request_approve_confirm'), {
        confirmButtonType: 'primary',
        confirmButtonText: t('tenant.approve'),
        cancelButtonText: t('common.cancel'),
        customClass: 'confirm-no_icon',
        autofocus: false,
      })
    }
    await tenantApi.reviewDataRequest(row.id, {
      approved,
      review_comment: reviewComment,
    })
    ElMessage.success(t('common.save_success'))
    await loadDataRequests()
  } finally {
    dataRequestLoadingId.value = ''
  }
}

const completeDataRequest = async (row: TenantDataRequestInfo) => {
  dataRequestLoadingId.value = String(row.id)
  try {
    const result = await ElMessageBox.prompt(
      t('tenant.data_request_complete_comment'),
      t('tenant.complete'),
      {
        confirmButtonType: 'primary',
        confirmButtonText: t('tenant.complete'),
        cancelButtonText: t('common.cancel'),
        inputType: 'textarea',
        customClass: 'confirm-no_icon',
        autofocus: false,
      }
    )
    await tenantApi.completeDataRequest(row.id, { complete_comment: result.value || '' })
    ElMessage.success(t('common.operation_success'))
    await loadDataRequests()
  } finally {
    dataRequestLoadingId.value = ''
  }
}

const viewExportManifest = (manifest: string) => {
  let content = manifest
  try {
    content = JSON.stringify(JSON.parse(manifest), null, 2)
  } catch {
    content = manifest
  }
  ElMessageBox.alert(content, t('tenant.export_manifest'), {
    customClass: 'tenant-manifest-dialog',
    confirmButtonText: t('common.confirm'),
  })
}

onMounted(() => {
  loadTenants()
  loadApplications()
  loadDomainReviews()
  loadDataRequests()
})
</script>

<style lang="less" scoped>
.tenant-container {
  width: 100%;
  height: 100%;
  position: relative;

  .tool-left {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 16px;

    .page-title {
      font-weight: 500;
      font-size: 20px;
      line-height: 28px;
    }
  }

  .search-bar {
    display: flex;
    align-items: center;
  }

  .tenant-table {
    max-height: calc(100vh - 150px);
    overflow-y: auto;
  }

  .application-table {
    margin-bottom: 20px;
  }

  .section-title {
    margin: 18px 0 10px;
    font-size: 15px;
    font-weight: 600;
    line-height: 22px;
    color: #1f2329;
  }

  .muted {
    color: #8f959e;
    font-size: 12px;
    line-height: 18px;
  }

  .review-actions {
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .tenant-status {
    display: flex;
    align-items: center;
    font-size: 14px;
    line-height: 22px;
    color: #646a73;

    .status-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      margin-right: 8px;
      background: #b8bdc6;
    }

    &.active {
      color: #24714d;

      .status-dot {
        background: #2ca86f;
      }
    }
  }

  .table-operate {
    display: flex;
    align-items: center;

    .line {
      margin: 0 10px 0 12px;
      height: 16px;
      width: 1px;
      background-color: #1f232926;
    }
  }
}
</style>
