<template>
  <div class="tenant-access-container professional-container">
    <div class="tool-left">
      <span class="page-title">{{ t('tenant.member_access') }}</span>
      <div class="toolbar">
        <el-button secondary @click="loadAccessRequests">{{ t('common.refresh') }}</el-button>
        <el-button secondary @click="openBulkInviteDialog">{{ t('tenant.bulk_invite') }}</el-button>
        <el-button secondary @click="openDomainDialog">{{ t('tenant.bind_domain') }}</el-button>
        <el-button secondary @click="openDataRequestDialog">{{ t('tenant.submit_data_request') }}</el-button>
        <el-button type="primary" @click="openInviteDialog">
          <template #icon>
            <icon_add_outlined />
          </template>
          {{ t('user.invite_existing_user') }}
        </el-button>
      </div>
    </div>

    <div class="access-grid">
      <section class="access-panel">
        <div class="panel-head">
          <span>{{ t('tenant.join_application_review') }}</span>
        </div>
        <el-table :data="joinApplications" class="access-table" style="width: 100%">
          <el-table-column prop="applicant_name" :label="t('tenant.applicant')" min-width="160" show-overflow-tooltip>
            <template #default="scope">
              <div>
                <div>{{ scope.row.applicant_name || scope.row.applicant_account || '-' }}</div>
                <div class="muted">{{ scope.row.applicant_email || scope.row.applicant_account }}</div>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="requested_role" :label="t('tenant.requested_role')" width="140">
            <template #default="scope">
              {{ formatRequestedRole(scope.row.requested_role) }}
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
          <el-table-column fixed="right" :label="t('ds.actions')" width="150">
            <template #default="scope">
              <div v-if="scope.row.status === 'pending'" class="review-actions">
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
              <span v-else class="muted">{{ scope.row.review_comment || '-' }}</span>
            </template>
          </el-table-column>
          <template #empty>
            <EmptyBackground :description="t('tenant.no_join_applications')" img-type="tree" />
          </template>
        </el-table>
      </section>

      <section class="access-panel">
        <div class="panel-head">
          <span>{{ t('tenant.pending_invitations') }}</span>
        </div>
        <el-table :data="invitations" class="access-table" style="width: 100%">
          <el-table-column prop="applicant_name" :label="t('user.name')" min-width="160" show-overflow-tooltip>
            <template #default="scope">
              <div>
                <div>{{ scope.row.applicant_name || scope.row.applicant_account || '-' }}</div>
                <div class="muted">{{ scope.row.applicant_email || scope.row.applicant_account }}</div>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="requested_role" :label="t('tenant.requested_role')" width="140">
            <template #default="scope">
              {{ formatRequestedRole(scope.row.requested_role) }}
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
          <el-table-column fixed="right" :label="t('ds.actions')" width="130">
            <template #default="scope">
              <el-button
                v-if="scope.row.status === 'pending'"
                text
                type="danger"
                :loading="inviteCancelingId === String(scope.row.id)"
                @click="cancelInvitation(scope.row)"
              >
                {{ t('tenant.cancel_invitation') }}
              </el-button>
              <span v-else class="muted">{{ scope.row.review_comment || '-' }}</span>
            </template>
          </el-table-column>
          <template #empty>
            <EmptyBackground :description="t('tenant.no_pending_invitations')" img-type="tree" />
          </template>
        </el-table>
      </section>

      <section class="access-panel">
        <div class="panel-head">
          <span>{{ t('tenant.domain_bindings') }}</span>
        </div>
        <el-table :data="domainRows" class="access-table compact-table" style="width: 100%">
          <el-table-column prop="domain" :label="t('tenant.domain')" min-width="180" show-overflow-tooltip />
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
              {{ formatOptionalTimestamp(scope.row.create_time) }}
            </template>
          </el-table-column>
          <template #empty>
            <EmptyBackground :description="t('tenant.no_domain_bindings')" img-type="tree" />
          </template>
        </el-table>
      </section>

      <section class="access-panel">
        <div class="panel-head">
          <span>{{ t('tenant.security_policy') }}</span>
        </div>
        <el-form label-position="top" class="security-form" @submit.prevent>
          <el-form-item :label="t('tenant.ip_whitelist')">
            <el-input v-model="securityForm.ip_whitelist" type="textarea" :rows="3" maxlength="4000" />
          </el-form-item>
          <div class="security-row">
            <el-form-item :label="t('tenant.sso_required')">
              <el-switch v-model="securityForm.sso_required" />
            </el-form-item>
            <el-form-item :label="t('tenant.session_timeout_minutes')">
              <el-input-number
                v-model="securityForm.session_timeout_minutes"
                :min="5"
                :max="10080"
                :step="5"
                controls-position="right"
              />
            </el-form-item>
          </div>
          <div class="panel-actions">
            <el-button type="primary" :loading="securitySaving" @click="saveSecurityPolicy">
              {{ t('common.save') }}
            </el-button>
          </div>
        </el-form>
      </section>

      <section class="access-panel access-panel-wide">
        <div class="panel-head">
          <span>{{ t('tenant.data_requests') }}</span>
        </div>
        <el-table :data="dataRequestRows" class="access-table compact-table" style="width: 100%">
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
              {{ formatOptionalTimestamp(scope.row.update_time) }}
            </template>
          </el-table-column>
          <template #empty>
            <EmptyBackground :description="t('tenant.no_data_requests')" img-type="tree" />
          </template>
        </el-table>
      </section>
    </div>

    <el-dialog
      v-model="inviteDialogVisible"
      class="workspace-light-dialog"
      :title="t('user.invite_existing_user')"
      width="520"
      :before-close="closeInviteDialog"
    >
      <el-form
        ref="inviteFormRef"
        :model="inviteForm"
        :rules="inviteRules"
        label-position="top"
        class="form-content_error"
        @submit.prevent
      >
        <el-form-item prop="account" :label="t('user.account')">
          <el-input
            v-model="inviteForm.account"
            maxlength="100"
            clearable
            :placeholder="t('user.invite_account_placeholder')"
          />
        </el-form-item>
        <el-form-item prop="requested_role" :label="t('user.tenant_role')">
          <el-select v-model="inviteForm.requested_role" style="width: 240px">
            <el-option
              v-for="item in inviteRoleOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('tenant.apply_reason')">
          <el-input v-model="inviteForm.reason" type="textarea" maxlength="2000" :rows="4" show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button secondary @click="closeInviteDialog">{{ t('common.cancel') }}</el-button>
          <el-button type="primary" :loading="inviteSubmitting" @click="submitInvitation">
            {{ t('tenant.send_invitation') }}
          </el-button>
        </div>
      </template>
    </el-dialog>

    <el-dialog
      v-model="bulkInviteDialogVisible"
      class="workspace-light-dialog"
      :title="t('tenant.bulk_invite')"
      width="560"
      :before-close="closeBulkInviteDialog"
    >
      <el-form label-position="top" class="form-content_error" @submit.prevent>
        <el-form-item :label="t('tenant.bulk_invite_accounts')">
          <el-input v-model="bulkInviteForm.accountsText" type="textarea" :rows="6" maxlength="4000" />
        </el-form-item>
        <el-form-item :label="t('user.tenant_role')">
          <el-select v-model="bulkInviteForm.requested_role" style="width: 240px">
            <el-option
              v-for="item in inviteRoleOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('tenant.apply_reason')">
          <el-input v-model="bulkInviteForm.reason" type="textarea" maxlength="2000" :rows="3" show-word-limit />
        </el-form-item>
      </el-form>
      <el-table v-if="bulkInviteResults.length" :data="bulkInviteResults" class="bulk-result-table">
        <el-table-column prop="account" :label="t('user.account')" min-width="160" show-overflow-tooltip />
        <el-table-column prop="status" :label="t('tenant.status')" width="110">
          <template #default="scope">
            <el-tag size="small" :type="scope.row.status === 'created' ? 'success' : 'danger'">
              {{ scope.row.status === 'created' ? t('tenant.invite_created') : t('tenant.invite_failed') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="message" :label="t('tenant.review_comment')" min-width="180" show-overflow-tooltip />
      </el-table>
      <template #footer>
        <div class="dialog-footer">
          <el-button secondary @click="closeBulkInviteDialog">{{ t('common.cancel') }}</el-button>
          <el-button type="primary" :loading="bulkInviteSubmitting" @click="submitBulkInvitation">
            {{ t('tenant.send_invitation') }}
          </el-button>
        </div>
      </template>
    </el-dialog>

    <el-dialog
      v-model="domainDialogVisible"
      class="workspace-light-dialog"
      :title="t('tenant.bind_domain')"
      width="480"
      :before-close="closeDomainDialog"
    >
      <el-form ref="domainFormRef" :model="domainForm" :rules="domainRules" label-position="top" @submit.prevent>
        <el-form-item prop="domain" :label="t('tenant.domain')">
          <el-input v-model="domainForm.domain" maxlength="255" clearable />
        </el-form-item>
        <el-form-item prop="auto_join_role" :label="t('tenant.auto_join_role')">
          <el-select v-model="domainForm.auto_join_role" style="width: 240px">
            <el-option
              v-for="item in inviteRoleOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button secondary @click="closeDomainDialog">{{ t('common.cancel') }}</el-button>
          <el-button type="primary" :loading="domainSubmitting" @click="submitDomainBinding">
            {{ t('tenant.submit_for_review') }}
          </el-button>
        </div>
      </template>
    </el-dialog>

    <el-dialog
      v-model="dataRequestDialogVisible"
      class="workspace-light-dialog"
      :title="t('tenant.submit_data_request')"
      width="480"
      :before-close="closeDataRequestDialog"
    >
      <el-form ref="dataRequestFormRef" :model="dataRequestForm" :rules="dataRequestRules" label-position="top" @submit.prevent>
        <el-form-item prop="request_type" :label="t('tenant.data_request_type')">
          <el-select v-model="dataRequestForm.request_type" style="width: 240px">
            <el-option :label="t('tenant.data_request_cancel')" value="cancel" :disabled="!canSubmitOwnerDataRequest" />
            <el-option :label="t('tenant.data_request_export')" value="export" />
            <el-option :label="t('tenant.data_request_delete')" value="delete" :disabled="!canSubmitOwnerDataRequest" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('tenant.apply_reason')">
          <el-input v-model="dataRequestForm.reason" type="textarea" maxlength="2000" :rows="4" show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button secondary @click="closeDataRequestDialog">{{ t('common.cancel') }}</el-button>
          <el-button type="primary" :loading="dataRequestSubmitting" @click="submitDataRequest">
            {{ t('tenant.submit_request') }}
          </el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, shallowRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus-secondary'
import icon_add_outlined from '@/assets/svg/icon_add_outlined.svg'
import EmptyBackground from '@/views/dashboard/common/EmptyBackground.vue'
import {
  tenantApi,
  type TenantApplicationInfo,
  type TenantBulkInviteResult,
  type TenantDataRequestInfo,
  type TenantDomainInfo,
} from '@/api/tenant'
import { formatTimestamp } from '@/utils/date'
import { useUserStore } from '@/stores/user'

const { t } = useI18n()
const userStore = useUserStore()
const inviteDialogVisible = ref(false)
const bulkInviteDialogVisible = ref(false)
const domainDialogVisible = ref(false)
const dataRequestDialogVisible = ref(false)
const inviteFormRef = ref()
const domainFormRef = ref()
const dataRequestFormRef = ref()
const inviteSubmitting = ref(false)
const bulkInviteSubmitting = ref(false)
const domainSubmitting = ref(false)
const dataRequestSubmitting = ref(false)
const securitySaving = ref(false)
const joinReviewLoadingId = ref('')
const inviteCancelingId = ref('')
const joinApplications = shallowRef<TenantApplicationInfo[]>([])
const invitations = shallowRef<TenantApplicationInfo[]>([])
const domainRows = shallowRef<TenantDomainInfo[]>([])
const dataRequestRows = shallowRef<TenantDataRequestInfo[]>([])
const bulkInviteResults = shallowRef<TenantBulkInviteResult[]>([])

const inviteForm = reactive({
  account: '',
  requested_role: 'member' as 'admin' | 'member',
  reason: '',
})

const bulkInviteForm = reactive({
  accountsText: '',
  requested_role: 'member' as 'admin' | 'member',
  reason: '',
})

const domainForm = reactive({
  domain: '',
  auto_join_role: 'member' as 'admin' | 'member',
})

const dataRequestForm = reactive({
  request_type: 'export' as 'cancel' | 'export' | 'delete',
  reason: '',
})

const securityForm = reactive({
  ip_whitelist: '',
  sso_required: false,
  session_timeout_minutes: null as number | null,
})

const inviteRoleOptions = computed(() => [
  { value: 'member', label: t('user.tenant_role_member') },
  { value: 'admin', label: t('user.tenant_role_admin') },
])

const inviteRules = {
  account: [
    {
      required: true,
      message: t('datasource.please_enter') + t('common.empty') + t('user.account'),
      trigger: 'blur',
    },
  ],
  requested_role: [
    {
      required: true,
      message: t('tenant.request_role_required'),
      trigger: 'change',
    },
  ],
}

const domainRules = {
  domain: [
    {
      required: true,
      message: t('tenant.domain_required'),
      trigger: 'blur',
    },
  ],
  auto_join_role: [
    {
      required: true,
      message: t('tenant.request_role_required'),
      trigger: 'change',
    },
  ],
}

const dataRequestRules = {
  request_type: [
    {
      required: true,
      message: t('tenant.data_request_type_required'),
      trigger: 'change',
    },
  ],
}

const canSubmitOwnerDataRequest = computed(() =>
  ['owner'].includes(String(userStore.tenantRole || '').trim().toLowerCase()) || userStore.isSystemAdminUser
)

const formatApplicationStatus = (status?: string) => {
  const key = `tenant.application_status_${status || 'pending'}`
  const label = t(key)
  return label === key ? status || '-' : label
}

const applicationStatusType = (status?: string) => {
  if (status === 'approved') return 'success'
  if (status === 'rejected') return 'danger'
  if (status === 'cancelled') return 'info'
  return 'warning'
}

const formatOptionalTimestamp = (value?: number | string | null) => {
  const timestamp = Number(value || 0)
  return timestamp ? formatTimestamp(timestamp, 'YYYY-MM-DD HH:mm:ss') : '-'
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

const formatRequestedRole = (role?: string) => {
  if (role === 'owner') return t('tenant.request_role_owner')
  if (role === 'admin') return t('tenant.request_role_admin')
  return t('tenant.request_role_member')
}

const loadAccessRequests = async () => {
  const [joinRows, invitationRows, domains, dataRequests, securityPolicy] = await Promise.all([
    tenantApi.tenantApplications('pending'),
    tenantApi.invitations('pending'),
    tenantApi.domains(),
    tenantApi.dataRequests(),
    tenantApi.security(),
  ])
  joinApplications.value = joinRows || []
  invitations.value = invitationRows || []
  domainRows.value = domains || []
  dataRequestRows.value = dataRequests || []
  Object.assign(securityForm, {
    ip_whitelist: securityPolicy?.ip_whitelist || '',
    sso_required: Boolean(securityPolicy?.sso_required),
    session_timeout_minutes: securityPolicy?.session_timeout_minutes || null,
  })
}

const openInviteDialog = () => {
  Object.assign(inviteForm, {
    account: '',
    requested_role: 'member',
    reason: '',
  })
  inviteDialogVisible.value = true
}

const closeInviteDialog = () => {
  inviteDialogVisible.value = false
}

const submitInvitation = () => {
  inviteFormRef.value?.validate(async (valid: boolean) => {
    if (!valid) return
    inviteSubmitting.value = true
    try {
      await tenantApi.invite({
        account: inviteForm.account.trim(),
        requested_role: inviteForm.requested_role,
        reason: inviteForm.reason,
      })
      ElMessage.success(t('tenant.invitation_sent'))
      closeInviteDialog()
      await loadAccessRequests()
    } finally {
      inviteSubmitting.value = false
    }
  })
}

const openBulkInviteDialog = () => {
  Object.assign(bulkInviteForm, {
    accountsText: '',
    requested_role: 'member',
    reason: '',
  })
  bulkInviteResults.value = []
  bulkInviteDialogVisible.value = true
}

const closeBulkInviteDialog = () => {
  bulkInviteDialogVisible.value = false
}

const parseBulkInviteAccounts = () =>
  bulkInviteForm.accountsText
    .split(/[\n,;]+/)
    .map((item) => item.trim())
    .filter(Boolean)

const submitBulkInvitation = async () => {
  const accounts = Array.from(new Set(parseBulkInviteAccounts()))
  if (!accounts.length) {
    ElMessage.warning(t('tenant.bulk_invite_accounts_required'))
    return
  }
  bulkInviteSubmitting.value = true
  try {
    const results = await tenantApi.bulkInvite({
      accounts,
      requested_role: bulkInviteForm.requested_role,
      reason: bulkInviteForm.reason,
    })
    bulkInviteResults.value = results || []
    const created = bulkInviteResults.value.filter((item) => item.status === 'created').length
    ElMessage.success(t('tenant.bulk_invite_finished', { created, total: bulkInviteResults.value.length }))
    await loadAccessRequests()
  } finally {
    bulkInviteSubmitting.value = false
  }
}

const openDomainDialog = () => {
  Object.assign(domainForm, {
    domain: '',
    auto_join_role: 'member',
  })
  domainDialogVisible.value = true
}

const closeDomainDialog = () => {
  domainDialogVisible.value = false
}

const submitDomainBinding = () => {
  domainFormRef.value?.validate(async (valid: boolean) => {
    if (!valid) return
    domainSubmitting.value = true
    try {
      await tenantApi.bindDomain({
        domain: domainForm.domain.trim(),
        auto_join_role: domainForm.auto_join_role,
      })
      ElMessage.success(t('tenant.domain_submitted'))
      closeDomainDialog()
      await loadAccessRequests()
    } finally {
      domainSubmitting.value = false
    }
  })
}

const saveSecurityPolicy = async () => {
  securitySaving.value = true
  try {
    await tenantApi.updateSecurity({
      ip_whitelist: securityForm.ip_whitelist,
      sso_required: securityForm.sso_required,
      session_timeout_minutes: securityForm.session_timeout_minutes,
    })
    ElMessage.success(t('common.save_success'))
    await loadAccessRequests()
  } finally {
    securitySaving.value = false
  }
}

const openDataRequestDialog = () => {
  Object.assign(dataRequestForm, {
    request_type: 'export',
    reason: '',
  })
  dataRequestDialogVisible.value = true
}

const closeDataRequestDialog = () => {
  dataRequestDialogVisible.value = false
}

const submitDataRequest = () => {
  dataRequestFormRef.value?.validate(async (valid: boolean) => {
    if (!valid) return
    if (dataRequestForm.request_type === 'cancel' || dataRequestForm.request_type === 'delete') {
      const confirmKey =
        dataRequestForm.request_type === 'cancel'
          ? 'tenant.tenant_cancel_request_confirm'
          : 'tenant.data_delete_request_confirm'
      await ElMessageBox.confirm(t(confirmKey), {
        confirmButtonType: 'danger',
        confirmButtonText: t('tenant.submit_request'),
        cancelButtonText: t('common.cancel'),
        customClass: 'confirm-no_icon',
        autofocus: false,
      })
    }
    dataRequestSubmitting.value = true
    try {
      await tenantApi.submitDataRequest({
        request_type: dataRequestForm.request_type,
        reason: dataRequestForm.reason,
      })
      ElMessage.success(t('tenant.data_request_submitted'))
      closeDataRequestDialog()
      await loadAccessRequests()
    } finally {
      dataRequestSubmitting.value = false
    }
  })
}

const reviewJoinApplication = async (application: TenantApplicationInfo, approved: boolean) => {
  joinReviewLoadingId.value = String(application.id)
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
    }
    await tenantApi.reviewTenantApplication(application.id, {
      approved,
      review_comment: reviewComment,
    })
    ElMessage.success(t('common.save_success'))
    await loadAccessRequests()
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
    await loadAccessRequests()
  } finally {
    inviteCancelingId.value = ''
  }
}

onMounted(() => {
  loadAccessRequests()
})
</script>

<style lang="less" scoped>
.tenant-access-container {
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

  .toolbar {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .access-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 16px;
  }

  .access-panel {
    min-width: 0;
    border: 1px solid #dee0e3;
    border-radius: 8px;
    background: #fff;
    overflow: hidden;
  }

  .access-panel-wide {
    grid-column: 1 / -1;
  }

  .panel-head {
    height: 48px;
    padding: 0 16px;
    display: flex;
    align-items: center;
    border-bottom: 1px solid #dee0e3;
    background: #f8f9fa;
    font-size: 15px;
    font-weight: 600;
    color: #1f2329;
  }

  .access-table {
    max-height: calc(100vh - 190px);
    overflow-y: auto;
  }

  .compact-table {
    max-height: 320px;
  }

  .security-form {
    padding: 16px;
  }

  .security-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(180px, 220px);
    gap: 16px;
  }

  .panel-actions {
    display: flex;
    justify-content: flex-end;
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
}

@media (max-width: 1200px) {
  .tenant-access-container {
    .access-grid {
      grid-template-columns: 1fr;
    }

    .access-panel-wide {
      grid-column: auto;
    }

    .security-row {
      grid-template-columns: 1fr;
    }
  }
}

.bulk-result-table {
  margin-top: 12px;
  max-height: 240px;
  overflow-y: auto;
}
</style>
