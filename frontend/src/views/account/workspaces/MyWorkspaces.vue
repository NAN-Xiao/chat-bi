<template>
  <div class="my-workspaces professional-container">
    <div class="page-head">
      <div>
        <div class="page-title">{{ t('tenant.my_workspaces') }}</div>
        <div class="page-subtitle">{{ t('tenant.workspace_access_hint') }}</div>
      </div>
      <el-button secondary @click="refreshAll">{{ t('common.refresh') }}</el-button>
    </div>

    <div class="workspace-grid">
      <section class="workspace-section joined-section">
        <div class="section-head">
          <span>{{ t('tenant.joined_workspaces') }}</span>
          <el-tag v-if="currentTenantName" size="small" type="info">
            {{ t('tenant.current_workspace') }}: {{ currentTenantName }}
          </el-tag>
        </div>
        <el-table :data="tenantList" class="workspace-table" style="width: 100%">
          <el-table-column prop="name" :label="t('tenant.name')" min-width="180" show-overflow-tooltip>
            <template #default="scope">
              <div class="workspace-name">{{ scope.row.name || scope.row.code }}</div>
              <div class="muted">{{ scope.row.id }} / {{ scope.row.code }}</div>
            </template>
          </el-table-column>
          <el-table-column prop="role" :label="t('user.tenant_role')" width="140">
            <template #default="scope">
              {{ formatTenantRole(scope.row.role) }}
            </template>
          </el-table-column>
          <el-table-column prop="plan" :label="t('tenant.plan')" width="120">
            <template #default="scope">
              <el-tag size="small" type="info">{{ formatPlan(scope.row.plan) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column fixed="right" :label="t('ds.actions')" width="190">
            <template #default="scope">
              <div class="workspace-actions">
                <el-button
                  v-if="String(scope.row.id) !== String(userStore.getTenantId)"
                  text
                  :loading="tenantSwitchingId === String(scope.row.id)"
                  @click="switchTenant(scope.row)"
                >
                  {{ t('tenant.switch_workspace') }}
                </el-button>
                <span v-else class="active-text">{{ t('tenant.active_workspace') }}</span>
                <el-tooltip
                  :disabled="normalizeTenantRole(scope.row.role) !== 'owner'"
                  :content="t('tenant.transfer_owner_before_leave')"
                  placement="top"
                >
                  <span>
                    <el-button
                      text
                      type="danger"
                      :disabled="normalizeTenantRole(scope.row.role) === 'owner'"
                      :loading="tenantLeavingId === String(scope.row.id)"
                      @click="leaveWorkspace(scope.row)"
                    >
                      {{ t('tenant.leave_workspace') }}
                    </el-button>
                  </span>
                </el-tooltip>
              </div>
            </template>
          </el-table-column>
          <template #empty>
            <EmptyBackground :description="t('tenant.no_joined_workspaces')" img-type="tree" />
          </template>
        </el-table>
      </section>

      <section class="workspace-section application-section">
        <div class="section-head">
          <span>{{ t('tenant.apply_workspace') }}</span>
        </div>
        <el-form
          ref="applicationFormRef"
          :model="applicationForm"
          :rules="applicationRules"
          label-position="top"
          class="form-content_error"
          @submit.prevent
        >
          <el-radio-group
            v-model="applicationMode"
            class="application-mode"
            @change="changeApplicationMode"
          >
            <el-radio-button label="create">{{ t('tenant.application_type_create') }}</el-radio-button>
            <el-radio-button label="join">{{ t('tenant.application_type_join') }}</el-radio-button>
          </el-radio-group>
          <el-form-item prop="tenant_name" :label="t('tenant.name')">
            <el-input
              v-if="applicationMode === 'create'"
              v-model="applicationForm.tenant_name"
              maxlength="255"
              clearable
            />
            <el-input
              v-else
              v-model="applicationForm.tenant_name"
              disabled
              :placeholder="t('tenant.search_tenant_first')"
            />
          </el-form-item>
          <el-form-item prop="tenant_code" :label="t('tenant.code')">
            <el-input
              v-if="applicationMode === 'create'"
              v-model="applicationForm.tenant_code"
              maxlength="64"
              clearable
            />
            <el-input
              v-else
              v-model="applicationForm.tenant_code"
              maxlength="64"
              clearable
              :placeholder="t('tenant.join_search_placeholder')"
              @keydown.enter.exact.prevent="searchTenantTargets"
            >
              <template #append>
                <el-button :loading="tenantSearchLoading" @click="searchTenantTargets">
                  {{ t('common.search') }}
                </el-button>
              </template>
            </el-input>
            <div v-if="applicationMode === 'join' && tenantSearchResults.length" class="tenant-search-results">
              <button
                v-for="tenant in tenantSearchResults"
                :key="tenant.id"
                type="button"
                class="tenant-search-result"
                :class="String(applicationForm.tenant_id) === String(tenant.id) && 'selected'"
                :disabled="tenant.already_joined"
                @click="selectTenantTarget(tenant)"
              >
                <span class="tenant-search-name">{{ tenant.name }}</span>
                <span class="tenant-search-code">{{ tenant.id }} / {{ tenant.code }}</span>
                <span v-if="tenant.already_joined" class="tenant-search-state">
                  {{ t('tenant.already_joined') }}
                </span>
              </button>
            </div>
          </el-form-item>
          <el-form-item prop="requested_role" :label="t('tenant.requested_role')">
            <el-select v-model="applicationForm.requested_role" style="width: 240px">
              <el-option
                v-for="item in applicationMode === 'create' ? createRoleOptions : joinRoleOptions"
                :key="item.value"
                :label="item.label"
                :value="item.value"
              />
            </el-select>
          </el-form-item>
          <el-form-item v-if="applicationMode === 'create'" prop="plan" :label="t('tenant.plan')">
            <el-select v-model="applicationForm.plan" style="width: 240px">
              <el-option
                v-for="item in planOptions"
                :key="item.value"
                :label="item.label"
                :value="item.value"
              />
            </el-select>
          </el-form-item>
          <el-form-item :label="t('tenant.apply_reason')">
            <el-input
              v-model="applicationForm.reason"
              type="textarea"
              maxlength="2000"
              :rows="4"
              show-word-limit
            />
          </el-form-item>
          <div class="form-actions">
            <el-button type="primary" :loading="applicationSubmitting" @click="submitApplication">
              {{ t('common.confirm') }}
            </el-button>
          </div>
        </el-form>
      </section>
    </div>

    <div class="workspace-grid lower-grid">
      <section class="workspace-section">
        <div class="section-head">
          <span>{{ t('tenant.my_pending_applications') }}</span>
        </div>
        <el-table :data="pendingApplications" class="workspace-table" style="width: 100%">
          <el-table-column prop="tenant_name" :label="t('tenant.name')" min-width="160" show-overflow-tooltip>
            <template #default="scope">
              <div>{{ scope.row.tenant_name || scope.row.tenant_code }}</div>
              <div class="muted">{{ formatApplicationType(scope.row.application_type) }}</div>
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
          <el-table-column fixed="right" :label="t('ds.actions')" width="120">
            <template #default="scope">
              <el-button
                v-if="scope.row.status === 'pending'"
                text
                :loading="applicationCancelingId === String(scope.row.id)"
                @click="cancelApplication(scope.row)"
              >
                {{ t('tenant.cancel_application') }}
              </el-button>
              <span v-else class="muted">-</span>
            </template>
          </el-table-column>
          <template #empty>
            <span class="empty-text">{{ t('tenant.no_pending_applications') }}</span>
          </template>
        </el-table>
      </section>

      <section class="workspace-section">
        <div class="section-head">
          <span>{{ t('tenant.my_invitations') }}</span>
        </div>
        <el-table :data="pendingInvitations" class="workspace-table" style="width: 100%">
          <el-table-column prop="tenant_name" :label="t('tenant.name')" min-width="160" show-overflow-tooltip>
            <template #default="scope">
              <div>{{ scope.row.tenant_name || scope.row.tenant_code }}</div>
              <div class="muted">{{ scope.row.inviter_name || scope.row.inviter_account || '-' }}</div>
            </template>
          </el-table-column>
          <el-table-column prop="requested_role" :label="t('tenant.requested_role')" width="140">
            <template #default="scope">
              {{ formatRequestedRole(scope.row.requested_role) }}
            </template>
          </el-table-column>
          <el-table-column fixed="right" :label="t('ds.actions')" width="160">
            <template #default="scope">
              <div class="invitation-actions">
                <el-button
                  text
                  :loading="invitationRespondingId === String(scope.row.id)"
                  @click="respondInvitation(scope.row, true)"
                >
                  {{ t('tenant.accept_invitation') }}
                </el-button>
                <el-button
                  text
                  type="danger"
                  :disabled="invitationRespondingId === String(scope.row.id)"
                  @click="respondInvitation(scope.row, false)"
                >
                  {{ t('tenant.reject_invitation') }}
                </el-button>
              </div>
            </template>
          </el-table-column>
          <template #empty>
            <span class="empty-text">{{ t('tenant.no_invitations') }}</span>
          </template>
        </el-table>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, shallowRef } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus-secondary'
import EmptyBackground from '@/views/dashboard/common/EmptyBackground.vue'
import {
  tenantApi,
  type TenantApplicationInfo,
  type TenantInfo,
  type TenantSearchInfo,
} from '@/api/tenant'
import { useUserStore } from '@/stores/user'
import { useDatasourceContextStore } from '@/stores/datasourceContext'
import { dashboardStoreWithOut } from '@/stores/dashboard/dashboard'
import { useEmitt } from '@/utils/useEmitt'

const router = useRouter()
const { t } = useI18n()
const userStore = useUserStore()
const datasourceContext = useDatasourceContextStore()
const dashboardStore = dashboardStoreWithOut()

const applicationFormRef = ref()
const applicationMode = ref<'create' | 'join'>('create')
const applicationSubmitting = ref(false)
const tenantSearchLoading = ref(false)
const tenantSwitchingId = ref('')
const tenantLeavingId = ref('')
const applicationCancelingId = ref('')
const invitationRespondingId = ref('')
const tenantSearchResults = shallowRef<TenantSearchInfo[]>([])
const applications = shallowRef<TenantApplicationInfo[]>([])
const invitations = shallowRef<TenantApplicationInfo[]>([])

const applicationForm = reactive({
  tenant_id: '',
  tenant_code: '',
  tenant_name: '',
  plan: 'default',
  requested_role: 'owner',
  reason: '',
})

const tenantList = computed(() => userStore.getTenants)
const currentTenantName = computed(() => userStore.getTenantName || t('common.default_tenant'))
const pendingApplications = computed(() =>
  applications.value.filter((item) => item.status === 'pending' && item.application_type !== 'invite')
)
const pendingInvitations = computed(() => invitations.value.filter((item) => item.status === 'pending'))

const planOptions = computed(() => [
  { value: 'default', label: t('tenant.plan_default') },
  { value: 'basic', label: t('tenant.plan_basic') },
  { value: 'enterprise', label: t('tenant.plan_enterprise') },
])

const createRoleOptions = computed(() => [
  { value: 'owner', label: t('tenant.request_role_owner') },
  { value: 'admin', label: t('tenant.request_role_admin') },
])

const joinRoleOptions = computed(() => [
  { value: 'member', label: t('tenant.request_role_member') },
  { value: 'admin', label: t('tenant.request_role_admin') },
])

const applicationRules = computed(() => ({
  tenant_code: [{ required: true, message: t('tenant.code_required'), trigger: 'blur' }],
  tenant_name: [
    {
      required: applicationMode.value === 'create',
      message: t('tenant.name_required'),
      trigger: 'blur',
    },
  ],
  requested_role: [{ required: true, message: t('tenant.request_role_required'), trigger: 'change' }],
}))

const formatPlan = (plan?: string) => {
  const key = `tenant.plan_${plan || 'default'}`
  const label = t(key)
  return label === key ? plan || t('tenant.plan_default') : label
}

const formatTenantRole = (role?: string) => {
  const key = `common.tenant_role_${role || 'member'}`
  const label = t(key)
  return label === key ? role || t('common.tenant_role_member') : label
}

const normalizeTenantRole = (role?: string) => {
  const normalized = String(role || 'member').trim().toLowerCase()
  return ['owner', 'admin', 'member'].includes(normalized) ? normalized : 'member'
}

const formatRequestedRole = (role?: string) => {
  if (role === 'owner') return t('tenant.request_role_owner')
  if (role === 'admin') return t('tenant.request_role_admin')
  return t('tenant.request_role_member')
}

const formatApplicationType = (type?: string) => {
  if (type === 'join') return t('tenant.application_type_join')
  if (type === 'invite') return t('tenant.application_type_invite')
  return t('tenant.application_type_create')
}

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

const resetApplicationForm = () => {
  tenantSearchResults.value = []
  Object.assign(applicationForm, {
    tenant_id: '',
    tenant_code: '',
    tenant_name: '',
    plan: 'default',
    requested_role: applicationMode.value === 'create' ? 'owner' : 'member',
    reason: '',
  })
}

const changeApplicationMode = () => {
  resetApplicationForm()
}

const selectTenantTarget = (tenant: TenantSearchInfo) => {
  applicationForm.tenant_id = String(tenant.id || '')
  applicationForm.tenant_code = tenant.code || String(tenant.id || '')
  applicationForm.tenant_name = tenant.name || tenant.code || ''
}

const searchTenantTargets = async () => {
  const keyword = applicationForm.tenant_code.trim()
  if (!keyword) return
  tenantSearchLoading.value = true
  try {
    tenantSearchResults.value = await tenantApi.search(keyword)
  } finally {
    tenantSearchLoading.value = false
  }
}

const loadApplications = async () => {
  applications.value = await tenantApi.myApplications()
}

const loadInvitations = async () => {
  invitations.value = await tenantApi.myInvitations()
}

const refreshAll = async () => {
  await Promise.all([userStore.loadTenants(true), loadApplications(), loadInvitations()])
}

const submitApplication = () => {
  applicationFormRef.value?.validate(async (valid: boolean) => {
    if (!valid) return
    applicationSubmitting.value = true
    const mode = applicationMode.value
    try {
      if (mode === 'create') {
        await tenantApi.submitApplication({
          application_type: 'create',
          tenant_code: applicationForm.tenant_code,
          tenant_name: applicationForm.tenant_name,
          plan: applicationForm.plan,
          requested_role: applicationForm.requested_role,
          reason: applicationForm.reason,
        })
      } else {
        const target = applicationForm.tenant_code.trim()
        await tenantApi.submitApplication({
          application_type: 'join',
          tenant_id: applicationForm.tenant_id || (/^\d+$/.test(target) ? target : undefined),
          tenant_code: applicationForm.tenant_id ? undefined : target,
          requested_role: applicationForm.requested_role,
          reason: applicationForm.reason,
        })
      }
      ElMessage.success(
        mode === 'join' ? t('tenant.join_application_submitted') : t('tenant.application_submitted')
      )
      resetApplicationForm()
      await loadApplications()
    } finally {
      applicationSubmitting.value = false
    }
  })
}

const cancelApplication = async (application: TenantApplicationInfo) => {
  applicationCancelingId.value = String(application.id)
  try {
    await tenantApi.cancelApplication(application.id)
    await loadApplications()
    ElMessage.success(t('common.operation_success'))
  } finally {
    applicationCancelingId.value = ''
  }
}

const respondInvitation = async (invitation: TenantApplicationInfo, approved: boolean) => {
  invitationRespondingId.value = String(invitation.id)
  try {
    await tenantApi.respondInvitation(invitation.id, { approved })
    await refreshAll()
    ElMessage.success(t('common.operation_success'))
  } finally {
    invitationRespondingId.value = ''
  }
}

const switchTenant = async (tenant: TenantInfo) => {
  const tenantId = String(tenant.id || '')
  if (!tenantId || tenantId === String(userStore.getTenantId || '')) {
    return
  }
  tenantSwitchingId.value = tenantId
  try {
    await userStore.switchTenant(tenantId)
    datasourceContext.clear(true)
    await datasourceContext.loadDatasources(true)
    dashboardStore.canvasDataInit()
    useEmitt().emitter.emit('datasource-context-change', null)
    ElMessage.success(t('common.switch_success'))
    router.push('/chat/index')
  } finally {
    tenantSwitchingId.value = ''
  }
}

const leaveWorkspace = async (tenant: TenantInfo) => {
  const tenantId = String(tenant.id || '')
  if (!tenantId || normalizeTenantRole(tenant.role) === 'owner') {
    return
  }
  try {
    await ElMessageBox.confirm(t('tenant.leave_workspace_confirm', { msg: tenant.name || tenant.code }), {
      confirmButtonType: 'danger',
      confirmButtonText: t('tenant.leave_workspace'),
      cancelButtonText: t('common.cancel'),
      customClass: 'confirm-no_icon',
      autofocus: false,
    })
  } catch (e) {
    return
  }
  tenantLeavingId.value = tenantId
  try {
    const remaining = await tenantApi.leave(tenantId)
    userStore.tenants = Array.isArray(remaining) ? remaining : []
    if (tenantId === String(userStore.getTenantId || '')) {
      const nextTenant = userStore.tenants[0] || null
      if (nextTenant?.id) {
        await userStore.switchTenant(nextTenant.id)
        datasourceContext.clear(true)
        await datasourceContext.loadDatasources(true)
        dashboardStore.canvasDataInit()
        useEmitt().emitter.emit('datasource-context-change', null)
      } else {
        userStore.setTenant(null)
      }
    } else {
      await userStore.loadTenants(true)
    }
    await Promise.all([loadApplications(), loadInvitations()])
    ElMessage.success(t('common.operation_success'))
  } finally {
    tenantLeavingId.value = ''
  }
}

onMounted(() => {
  refreshAll()
})
</script>

<style lang="less" scoped>
.my-workspaces {
  width: 100%;
  height: 100%;
  overflow: auto;

  .page-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 16px;
  }

  .page-title {
    font-size: 20px;
    line-height: 28px;
    font-weight: 600;
    color: #1f2329;
  }

  .page-subtitle {
    margin-top: 4px;
    font-size: 13px;
    line-height: 20px;
    color: #646a73;
  }

  .workspace-grid {
    display: grid;
    grid-template-columns: minmax(0, 1.35fr) minmax(360px, 0.65fr);
    gap: 16px;
  }

  .lower-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    margin-top: 16px;
  }

  .workspace-section {
    min-width: 0;
    border: 1px solid #dee0e3;
    border-radius: 8px;
    background: #fff;
    overflow: hidden;
  }

  .section-head {
    min-height: 48px;
    padding: 0 16px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    border-bottom: 1px solid #dee0e3;
    background: #f8f9fa;
    font-size: 15px;
    font-weight: 600;
    color: #1f2329;
  }

  .application-section {
    padding-bottom: 16px;

    .ed-form {
      padding: 16px 16px 0;
    }
  }

  .application-mode {
    margin-bottom: 16px;
  }

  .form-actions {
    display: flex;
    justify-content: flex-end;
  }

  .workspace-table {
    max-height: 360px;
    overflow-y: auto;
  }

  .workspace-name {
    font-weight: 500;
    color: #1f2329;
  }

  .muted,
  .empty-text {
    color: #8f959e;
    font-size: 12px;
    line-height: 18px;
  }

  .active-text {
    color: #24714d;
    font-size: 13px;
  }

  .workspace-actions {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .tenant-search-results {
    width: 100%;
    margin-top: 8px;
    display: grid;
    gap: 6px;
  }

  .tenant-search-result {
    width: 100%;
    min-height: 44px;
    padding: 6px 10px;
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 2px 10px;
    border: 1px solid #dee0e3;
    border-radius: 6px;
    background: #fff;
    color: #1f2329;
    text-align: left;
    cursor: pointer;

    &:hover,
    &.selected {
      border-color: var(--ed-color-primary);
      background: #eef3ff;
    }

    &:disabled {
      cursor: not-allowed;
      opacity: 0.62;
    }
  }

  .tenant-search-name {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 14px;
    line-height: 20px;
    font-weight: 500;
  }

  .tenant-search-code,
  .tenant-search-state {
    color: #8f959e;
    font-size: 12px;
    line-height: 18px;
  }

  .tenant-search-state {
    grid-column: 2;
    grid-row: 1 / span 2;
    align-self: center;
  }

  .invitation-actions {
    display: flex;
    align-items: center;
    gap: 4px;
  }
}

@media (max-width: 1200px) {
  .my-workspaces {
    .workspace-grid,
    .lower-grid {
      grid-template-columns: 1fr;
    }
  }
}
</style>
