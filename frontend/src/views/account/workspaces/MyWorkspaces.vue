<template>
  <div class="my-workspaces professional-container">
    <div class="page-head">
      <div>
        <div class="page-title">{{ t('tenant.my_workspaces') }}</div>
        <div class="page-subtitle">{{ t('tenant.workspace_access_hint') }}</div>
      </div>
      <el-button secondary @click="refreshAll">{{ t('common.refresh') }}</el-button>
    </div>

    <div class="workspace-grid joined-grid">
      <section class="workspace-section joined-section">
        <div class="section-head">
          <span>{{ t('tenant.joined_workspaces') }}</span>
          <div v-if="currentTenantName" class="current-workspace-label">
            <el-icon size="16">
              <icon_member_outlined></icon_member_outlined>
            </el-icon>
            <span>{{ t('tenant.current_workspace') }}: {{ currentTenantName }}</span>
          </div>
        </div>
        <el-table
          :data="joinedWorkspacePageRows"
          class="workspace-table joined-workspace-table"
          style="width: 100%"
        >
          <el-table-column prop="name" :label="t('tenant.name')" min-width="180" show-overflow-tooltip>
            <template #default="scope">
              <div class="workspace-name">{{ scope.row.name || '-' }}</div>
              <div class="muted">{{ t('tenant.tenant_id') }} {{ tenantDisplayId(scope.row) }}</div>
            </template>
          </el-table-column>
          <el-table-column prop="role" :label="t('user.tenant_role')" width="140">
            <template #default="scope">
              {{ formatTenantRole(scope.row.role) }}
            </template>
          </el-table-column>
          <el-table-column prop="join_time" :label="t('tenant.join_time')" width="180">
            <template #default="scope">
              {{ formatDateTime(scope.row.join_time) }}
            </template>
          </el-table-column>
          <el-table-column fixed="right" :label="t('ds.actions')" width="120">
            <template #default="scope">
              <div class="workspace-actions">
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
            <EmptyBackground
              :description="t('tenant.no_joined_workspaces')"
              img-type="tree"
              class="joined-empty"
            >
              <el-button type="danger" class="join-workspace-empty-button" @click="openJoinDialog">
                {{ t('tenant.join_workspace') }}
              </el-button>
            </EmptyBackground>
          </template>
        </el-table>
        <div class="table-pagination">
          <el-pagination
            v-model:current-page="joinedWorkspacePage.currentPage"
            v-model:page-size="joinedWorkspacePage.pageSize"
            :page-sizes="[5, 10, 20]"
            :total="tenantList.length"
            small
            layout="total, sizes, prev, pager, next"
          />
        </div>
      </section>

    </div>

    <div class="workspace-grid request-grid">
      <section class="workspace-section request-section">
        <div class="section-head">
          <span>{{ t('tenant.my_workspace_requests') }}</span>
          <button type="button" class="join-workspace-link" @click="openJoinDialog">
            <el-icon size="15">
              <icon_add_outlined></icon_add_outlined>
            </el-icon>
            <span>{{ t('tenant.join_workspace') }}</span>
          </button>
        </div>
        <el-table
          :data="workspaceRequestPageRows"
          class="workspace-table request-table"
          style="width: 100%"
        >
          <el-table-column prop="requestType" :label="t('tenant.request_type')" width="150">
            <template #default="scope">
              <div class="request-type-cell">
                <el-icon size="16">
                  <icon_member_outlined></icon_member_outlined>
                </el-icon>
                <span>{{ scope.row.requestTypeLabel }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="tenant_name" :label="t('tenant.name')" min-width="160" show-overflow-tooltip>
            <template #default="scope">
              <div>{{ scope.row.tenant_name || '-' }}</div>
              <div class="muted">{{ scope.row.secondaryText }}</div>
            </template>
          </el-table-column>
          <el-table-column prop="requested_role" :label="t('tenant.requested_role')" width="140">
            <template #default="scope">
              {{ formatRequestedRole(scope.row.requested_role) }}
            </template>
          </el-table-column>
          <el-table-column prop="status" :label="t('tenant.application_status')" width="120">
            <template #default="scope">
              <div class="request-status" :class="requestStatusClass(scope.row.status)">
                <span class="status-icon" aria-hidden="true"></span>
                <span>{{ formatApplicationStatus(scope.row.status) }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="joinTimeStatus" :label="t('tenant.join_time')" width="190">
            <template #default="scope">
              <div class="request-time-cell">
                <div
                  class="request-time-status"
                  :class="scope.row.status === 'pending' && 'is-pending'"
                >
                  {{ formatRequestJoinStatus(scope.row) }}
                </div>
                <div class="request-time-detail">{{ formatRequestJoinTime(scope.row) }}</div>
              </div>
            </template>
          </el-table-column>
          <el-table-column fixed="right" :label="t('ds.actions')" width="170">
            <template #default="scope">
              <div v-if="scope.row.requestType === 'invitation' && scope.row.status === 'pending'" class="request-actions">
                <el-button
                  text
                  :loading="invitationRespondingId === String(scope.row.id)"
                  @click="respondInvitation(scope.row, true)"
                >
                  {{ t('tenant.approve_action') }}
                </el-button>
                <el-button
                  text
                  type="danger"
                  :disabled="invitationRespondingId === String(scope.row.id)"
                  @click="respondInvitation(scope.row, false)"
                >
                  {{ t('tenant.reject_action') }}
                </el-button>
              </div>
              <el-button
                v-else-if="scope.row.status === 'pending'"
                text
                :loading="applicationCancelingId === String(scope.row.id)"
                @click="cancelApplication(scope.row)"
              >
                {{ t('tenant.withdraw_action') }}
              </el-button>
              <span v-else class="muted">-</span>
            </template>
          </el-table-column>
          <template #empty>
            <span class="empty-text">{{ t('tenant.no_workspace_requests') }}</span>
          </template>
        </el-table>
        <div class="table-pagination">
          <el-pagination
            v-model:current-page="requestPage.currentPage"
            v-model:page-size="requestPage.pageSize"
            :page-sizes="[5, 10, 20]"
            :total="workspaceRequestRows.length"
            small
            layout="total, sizes, prev, pager, next"
          />
        </div>
      </section>
    </div>

    <el-dialog
      v-model="joinDialogVisible"
      class="workspace-light-dialog join-workspace-dialog"
      :title="t('tenant.join_workspace')"
      width="640"
      destroy-on-close
    >
      <el-form
        ref="joinFormRef"
        :model="joinForm"
        :rules="joinRules"
        label-position="top"
        class="form-content_error"
        @submit.prevent
      >
        <el-form-item prop="tenant_name" :label="t('tenant.name')">
          <el-input
            v-model="joinForm.tenant_name"
            disabled
            :placeholder="t('tenant.search_tenant_first')"
          />
        </el-form-item>
        <el-form-item prop="tenant_keyword" :label="t('tenant.workspace_search_label')">
          <el-input
            v-model="joinForm.tenant_keyword"
            maxlength="100"
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
          <div v-if="tenantSearchResults.length" class="tenant-search-results">
            <button
              v-for="tenant in tenantSearchResults"
              :key="tenant.id"
              type="button"
              class="tenant-search-result"
              :class="String(joinForm.tenant_id) === String(tenant.id) && 'selected'"
              :disabled="tenant.already_joined"
              @click="selectTenantTarget(tenant)"
            >
              <span class="tenant-search-name">{{ tenant.name }}</span>
              <span class="tenant-search-id">{{ t('tenant.tenant_id') }} {{ tenantDisplayId(tenant) }}</span>
              <span v-if="tenant.already_joined" class="tenant-search-state">
                {{ t('tenant.already_joined') }}
              </span>
            </button>
          </div>
        </el-form-item>
        <el-form-item :label="t('tenant.apply_reason')">
          <el-input
            v-model="joinForm.reason"
            type="textarea"
            maxlength="2000"
            :rows="4"
            show-word-limit
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button secondary @click="closeJoinDialog">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="joinSubmitting" @click="submitJoinApplication">
          {{ t('common.confirm') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, shallowRef, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus-secondary'
import icon_add_outlined from '@/assets/svg/icon_add_outlined.svg'
import icon_member_outlined from '@/assets/svg/icon_member_outlined.svg'
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
import { formatTimestamp } from '@/utils/date'

const { t } = useI18n()
const userStore = useUserStore()
const datasourceContext = useDatasourceContextStore()
const dashboardStore = dashboardStoreWithOut()

const tenantLeavingId = ref('')
const applicationCancelingId = ref('')
const invitationRespondingId = ref('')
const joinDialogVisible = ref(false)
const tenantSearchLoading = ref(false)
const joinSubmitting = ref(false)
const joinFormRef = ref()
const applications = shallowRef<TenantApplicationInfo[]>([])
const invitations = shallowRef<TenantApplicationInfo[]>([])
const tenantSearchResults = shallowRef<TenantSearchInfo[]>([])
const joinedWorkspacePage = reactive({
  currentPage: 1,
  pageSize: 5,
})
const requestPage = reactive({
  currentPage: 1,
  pageSize: 5,
})

const joinForm = reactive({
  tenant_id: '',
  tenant_keyword: '',
  tenant_name: '',
  reason: '',
})

const tenantList = computed(() => userStore.getTenants)
const currentTenantName = computed(() => userStore.getTenantName || '')
const tenantDisplayId = (tenant?: Partial<TenantInfo | TenantSearchInfo> | null) =>
  String(tenant?.public_id || '')
const joinedWorkspacePageRows = computed(() => {
  const start = (joinedWorkspacePage.currentPage - 1) * joinedWorkspacePage.pageSize
  return tenantList.value.slice(start, start + joinedWorkspacePage.pageSize)
})
const maxJoinedWorkspacePage = computed(() =>
  Math.max(1, Math.ceil(tenantList.value.length / joinedWorkspacePage.pageSize))
)
const workspaceRequestRows = computed(() =>
  [
    ...applications.value
      .filter((item) => item.application_type !== 'invite')
      .map((item) => ({
        ...item,
        requestType: 'application',
        requestTypeLabel: formatApplicationType(item.application_type),
        secondaryText: formatApplicationStatus(item.status),
      })),
    ...invitations.value.map((item) => ({
      ...item,
      requestType: 'invitation',
      application_type: item.application_type || 'invite',
      requestTypeLabel: t('tenant.application_type_invite'),
      secondaryText: item.inviter_name || item.inviter_account || '-',
    })),
  ]
)
const workspaceRequestPageRows = computed(() => {
  const start = (requestPage.currentPage - 1) * requestPage.pageSize
  return workspaceRequestRows.value.slice(start, start + requestPage.pageSize)
})
const maxRequestPage = computed(() =>
  Math.max(1, Math.ceil(workspaceRequestRows.value.length / requestPage.pageSize))
)
const joinRules = computed(() => ({
  tenant_keyword: [{ required: true, message: t('tenant.search_tenant_first'), trigger: 'blur' }],
}))

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

const requestStatusClass = (status?: string) => {
  if (status === 'approved') return 'status-approved'
  if (status === 'rejected') return 'status-rejected'
  if (status === 'cancelled') return 'status-cancelled'
  return 'status-pending'
}

const normalizeTimestamp = (value?: number | string | null) => {
  const timestamp = Number(value || 0)
  return Number.isFinite(timestamp) && timestamp > 0 ? timestamp : 0
}

const formatDateTime = (value?: number | string | null) => {
  const timestamp = normalizeTimestamp(value)
  return timestamp ? formatTimestamp(timestamp, 'YYYY-MM-DD HH:mm') : '-'
}

const requestResolvedTime = (row: TenantApplicationInfo) =>
  normalizeTimestamp(row.review_time) || normalizeTimestamp(row.update_time)

const requestCreatedAt = (row: TenantApplicationInfo) => formatDateTime(row.create_time)

const formatRequestJoinStatus = (row: TenantApplicationInfo & { requestType?: string }) => {
  if (row.status === 'approved') return t('tenant.joined_workspace_status')
  if (row.status === 'pending' && row.requestType === 'invitation') {
    return t('tenant.invitation_waiting_response')
  }
  return formatApplicationStatus(row.status)
}

const formatRequestJoinTime = (row: TenantApplicationInfo & { requestType?: string }) => {
  if (row.status === 'pending') {
    const label = row.requestType === 'invitation' ? t('tenant.invited_at') : t('tenant.submitted_at')
    return `${label} ${requestCreatedAt(row)}`
  }
  if (row.status === 'approved') {
    return `${t('tenant.joined_at')} ${formatDateTime(requestResolvedTime(row) || row.update_time || row.create_time)}`
  }
  return `${t('tenant.resolved_at')} ${formatDateTime(requestResolvedTime(row))}`
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

watch(
  () => [tenantList.value.length, joinedWorkspacePage.pageSize],
  () => {
    if (joinedWorkspacePage.currentPage > maxJoinedWorkspacePage.value) {
      joinedWorkspacePage.currentPage = maxJoinedWorkspacePage.value
    }
  }
)

watch(
  () => [workspaceRequestRows.value.length, requestPage.pageSize],
  () => {
    if (requestPage.currentPage > maxRequestPage.value) {
      requestPage.currentPage = maxRequestPage.value
    }
  }
)

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

const resetJoinForm = () => {
  tenantSearchResults.value = []
  Object.assign(joinForm, {
    tenant_id: '',
    tenant_keyword: '',
    tenant_name: '',
    reason: '',
  })
}

const openJoinDialog = () => {
  resetJoinForm()
  joinDialogVisible.value = true
}

const closeJoinDialog = () => {
  joinDialogVisible.value = false
}

const selectTenantTarget = (tenant: TenantSearchInfo) => {
  joinForm.tenant_id = String(tenant.id || '')
  joinForm.tenant_keyword = tenant.name || tenantDisplayId(tenant)
  joinForm.tenant_name = tenant.name || ''
}

const searchTenantTargets = async () => {
  const keyword = joinForm.tenant_keyword.trim()
  if (!keyword) return
  tenantSearchLoading.value = true
  try {
    tenantSearchResults.value = await tenantApi.search(keyword)
  } finally {
    tenantSearchLoading.value = false
  }
}

const submitJoinApplication = () => {
  joinFormRef.value?.validate(async (valid: boolean) => {
    if (!valid) return
    joinSubmitting.value = true
    try {
      await tenantApi.submitApplication({
        application_type: 'join',
        tenant_id: joinForm.tenant_id,
        reason: joinForm.reason,
      })
      ElMessage.success(t('tenant.join_application_submitted'))
      closeJoinDialog()
      resetJoinForm()
      await loadApplications()
    } finally {
      joinSubmitting.value = false
    }
  })
}

const leaveWorkspace = async (tenant: TenantInfo) => {
  const tenantId = String(tenant.id || '')
  if (!tenantId || normalizeTenantRole(tenant.role) === 'owner') {
    return
  }
  try {
    await ElMessageBox.confirm(t('tenant.leave_workspace_confirm', { msg: tenant.name || tenant.id }), {
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
        datasourceContext.clear(true)
        dashboardStore.canvasDataInit()
        useEmitt().emitter.emit('datasource-context-change', null)
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
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;

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
    min-height: 0;
    display: flex;
    flex-direction: column;
  }

  .joined-grid {
    flex: 1 1 0;
    margin-bottom: 16px;
  }

  .request-grid {
    flex: 1 1 0;
    min-height: 0;
  }

  .workspace-section {
    min-width: 0;
    min-height: 0;
    flex: 1;
    display: flex;
    flex-direction: column;
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

  .current-workspace-label {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    min-width: 0;
    color: #1f5fbf;
    font-size: 13px;
    line-height: 20px;
    font-weight: 500;

    .ed-icon {
      flex: 0 0 auto;
      color: inherit;
    }

    svg [fill] {
      fill: currentColor;
    }

    svg [stroke] {
      stroke: currentColor;
    }
  }

  .joined-section {
    min-height: 0;
  }

  .workspace-table {
    flex: 1;
    min-height: 0;

    :deep(.ed-table__inner-wrapper),
    :deep(.ed-table__body-wrapper),
    :deep(.ed-scrollbar),
    :deep(.ed-scrollbar__wrap) {
      min-height: 0;
    }
  }

  .request-section {
    min-height: 0;
  }

  .table-pagination {
    flex: 0 0 48px;
    padding: 10px 16px;
    display: flex;
    align-items: center;
    justify-content: flex-end;
    border-top: 1px solid #eff0f1;
    background: #fff;
  }

  .joined-empty {
    min-height: 220px;
    padding-top: 12px;
  }

  .join-workspace-empty-button {
    min-width: 112px;
    height: 36px;
    margin-top: 2px;
    font-weight: 500;
  }

  .join-workspace-link {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 0;
    border: none;
    background: transparent;
    color: var(--ed-color-primary);
    font-size: 13px;
    line-height: 20px;
    font-weight: 500;
    cursor: pointer;

    .ed-icon {
      color: inherit;
    }

    svg [fill] {
      fill: currentColor;
    }

    svg [stroke] {
      stroke: currentColor;
    }

    &:hover {
      color: #1d4ed8;
    }
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

  .request-type-cell,
  .request-actions {
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .request-type-cell {
    color: #1f2329;

    .ed-icon {
      color: #646a73;
    }

    svg [fill] {
      fill: currentColor;
    }

    svg [stroke] {
      stroke: currentColor;
    }
  }

  .request-status {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    line-height: 20px;
    font-weight: 500;
    color: #646a73;
  }

  .status-icon {
    position: relative;
    flex: 0 0 14px;
    width: 14px;
    height: 14px;
    border-radius: 50%;
    color: currentColor;
  }

  .status-pending {
    color: #d46b08;

    .status-icon {
      border: 1.5px solid currentColor;

      &::before {
        content: '';
        position: absolute;
        left: 5px;
        top: 2.5px;
        width: 1.5px;
        height: 5px;
        border-radius: 1px;
        background: currentColor;
      }

      &::after {
        content: '';
        position: absolute;
        left: 5px;
        top: 6.5px;
        width: 4px;
        height: 1.5px;
        border-radius: 1px;
        background: currentColor;
      }
    }
  }

  .status-approved {
    color: #24714d;

    .status-icon::before {
      content: '';
      position: absolute;
      left: 2px;
      top: 3px;
      width: 9px;
      height: 5px;
      border-left: 2px solid currentColor;
      border-bottom: 2px solid currentColor;
      transform: rotate(-45deg);
    }
  }

  .status-rejected {
    color: #c02a2a;

    .status-icon::before,
    .status-icon::after {
      content: '';
      position: absolute;
      left: 2px;
      top: 6px;
      width: 10px;
      height: 2px;
      border-radius: 1px;
      background: currentColor;
    }

    .status-icon::before {
      transform: rotate(45deg);
    }

    .status-icon::after {
      transform: rotate(-45deg);
    }
  }

  .status-cancelled {
    color: #646a73;

    .status-icon::before {
      content: '';
      position: absolute;
      left: 2px;
      top: 6px;
      width: 10px;
      height: 2px;
      border-radius: 1px;
      background: currentColor;
    }
  }

  .request-time-cell {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .request-time-status {
    font-size: 13px;
    line-height: 20px;
    font-weight: 500;
    color: #646a73;

    &.is-pending {
      color: #d46b08;
    }
  }

  .request-time-detail {
    font-size: 12px;
    line-height: 18px;
    color: #8f959e;
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

  .tenant-search-id,
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
}

@media (max-width: 1200px) {
  .my-workspaces {
  }
}
</style>
