<script setup lang="ts">
import { computed, onMounted, reactive, ref, shallowRef, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus-secondary'
import { useUserStore } from '@/stores/user'
import { tenantApi, type TenantApplicationInfo, type TenantInfo } from '@/api/tenant'
import { formatTimestamp } from '@/utils/date'
import UserAvatar from '@/components/user-avatar/UserAvatar.vue'
import icon_admin_outlined from '@/assets/svg/icon_admin_outlined.svg'
import icon_logs_outlined from '@/assets/svg/icon_logs_outlined.svg'
import icon_user from '@/assets/svg/icon_user.svg'

type WorkspaceRoleKey = 'owner' | 'admin' | 'member'
type AccessPanelKey = 'account' | 'requests' | 'permissions'
type WorkspaceRequestRow = {
  id: number | string
  application_type?: string
  tenant_name?: string
  status?: string
  reason?: string
  create_time?: number | string | null
  inviter_name?: string
  inviter_account?: string
  requestType: 'application' | 'invitation'
  requestTypeLabel: string
  requestTimeLabel: string
  requestTime?: number | string | null
  descriptionText: string
}

const { t } = useI18n()
const userStore = useUserStore()
const pendingInvitations = shallowRef<TenantApplicationInfo[]>([])
const pendingApplications = shallowRef<TenantApplicationInfo[]>([])
const invitationRespondingId = ref('')
const applicationCancelingId = ref('')
const activePanel = ref<AccessPanelKey>('account')
const requestPage = reactive({
  currentPage: 1,
  pageSize: 10,
})

const workspaceList = computed<TenantInfo[]>(() => userStore.getTenants || [])
const joinedWorkspaceCount = computed(() => workspaceList.value.length)
const pendingInvitationCount = computed(() => pendingInvitations.value.length)
const pendingApplicationCount = computed(() => pendingApplications.value.length)
const pendingRequestCount = computed(() => pendingInvitationCount.value + pendingApplicationCount.value)
const isPlatformOnlyAdmin = computed(
  () => userStore.isSystemAdminUser && !userStore.isPlatformWorkspaceDelegate
)

const normalizeRole = (role?: string): WorkspaceRoleKey => {
  const normalized = String(role || '').trim().toLowerCase()
  if (normalized === 'owner') return 'owner'
  if (normalized === 'admin') return 'admin'
  return 'member'
}

const roleTagType = (role: WorkspaceRoleKey) => {
  if (role === 'owner') return 'success'
  if (role === 'admin') return 'warning'
  return 'info'
}

const roleLabel = (role?: string) => {
  const normalized = String(role || '').trim().toLowerCase()
  if (normalized === 'owner') return t('access.role_owner_label')
  if (normalized === 'admin') return t('access.role_admin_label')
  if (normalized === 'viewer') return t('access.role_viewer_label')
  return t('access.role_member_label')
}

const currentWorkspaceLabel = computed(() => {
  if (isPlatformOnlyAdmin.value) return t('access.platform_admin_workspace_label')
  return userStore.getTenantName || t('access.no_current_workspace')
})

const currentRoleLabel = computed(() => {
  if (isPlatformOnlyAdmin.value) return t('access.platform_admin')
  if (!userStore.getTenantId) return t('access.no_joined_workspace_status')
  return roleLabel(userStore.getTenantRole)
})

const accountDetailRows = computed(() => [
  { label: t('user.name'), value: userStore.getName || '-' },
  { label: t('user.account'), value: userStore.getAccount || '-' },
  { label: t('access.account_id'), value: userStore.getUid || '-' },
  { label: t('access.current_workspace'), value: currentWorkspaceLabel.value },
  { label: t('user.tenant_role'), value: currentRoleLabel.value },
])

const accessNavItems = computed(() => [
  { key: 'account' as const, label: t('access.account_details'), icon: icon_user },
  { key: 'requests' as const, label: t('access.my_requests'), icon: icon_logs_outlined },
  { key: 'permissions' as const, label: t('access.permission_details'), icon: icon_admin_outlined },
])

const formatWorkspaceName = (workspace: TenantInfo) => workspace.name || String(workspace.id || '')
const tenantDisplayId = (workspace?: Partial<TenantInfo> | null) =>
  String(workspace?.public_id || '')

const formatWorkspaceMeta = (workspace: TenantInfo) => {
  const parts = [
    tenantDisplayId(workspace) ? `${t('tenant.tenant_id')} ${tenantDisplayId(workspace)}` : '',
    workspace.owner_name ? t('access.workspace_owner_meta', { owner: workspace.owner_name }) : '',
  ].filter(Boolean)
  return parts.join(' · ')
}

const normalizeTimestamp = (value?: number | string | null) => {
  const timestamp = Number(value || 0)
  return Number.isFinite(timestamp) && timestamp > 0 ? timestamp : 0
}

const formatDateTime = (value?: number | string | null) => {
  const timestamp = normalizeTimestamp(value)
  return timestamp ? formatTimestamp(timestamp, 'YYYY-MM-DD HH:mm') : '-'
}

const invitationInviterLabel = (invitation: Pick<TenantApplicationInfo, 'inviter_name' | 'inviter_account'>) =>
  invitation.inviter_name || invitation.inviter_account || '-'

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

const requestRows = computed<WorkspaceRequestRow[]>(() =>
  [
    ...pendingApplications.value.map((item) => ({
      id: item.id,
      application_type: item.application_type,
      tenant_name: item.tenant_name,
      status: item.status,
      reason: item.reason,
      create_time: item.create_time,
      requestType: 'application' as const,
      requestTypeLabel: formatApplicationType(item.application_type),
      requestTimeLabel: t('tenant.submitted_at'),
      requestTime: item.create_time,
      descriptionText: item.reason || '-',
    })),
    ...pendingInvitations.value.map((item) => ({
      id: item.id,
      application_type: item.application_type || 'invite',
      tenant_name: item.tenant_name,
      status: item.status,
      reason: item.reason,
      create_time: item.create_time,
      inviter_name: item.inviter_name,
      inviter_account: item.inviter_account,
      requestType: 'invitation' as const,
      requestTypeLabel: t('tenant.application_type_invite'),
      requestTimeLabel: t('tenant.invited_at'),
      requestTime: item.create_time,
      descriptionText: item.reason || invitationInviterLabel(item),
    })),
  ]
)

const requestPageRows = computed(() => {
  const start = (requestPage.currentPage - 1) * requestPage.pageSize
  return requestRows.value.slice(start, start + requestPage.pageSize)
})

const maxRequestPage = computed(() =>
  Math.max(1, Math.ceil(requestRows.value.length / requestPage.pageSize))
)

const headerTag = computed(() => {
  if (isPlatformOnlyAdmin.value) return t('access.platform_admin')
  if (!joinedWorkspaceCount.value) return t('access.no_joined_workspace_status')
  return t('access.joined_workspace_count', { count: joinedWorkspaceCount.value })
})

const headerTagType = computed(() =>
  isPlatformOnlyAdmin.value || joinedWorkspaceCount.value ? 'success' : 'info'
)

const loadPendingInvitations = async () => {
  if (isPlatformOnlyAdmin.value) {
    pendingInvitations.value = []
    return
  }
  const rows = await tenantApi.myInvitations('pending')
  pendingInvitations.value = rows.filter((item) => item.status === 'pending')
}

const loadPendingApplications = async () => {
  if (isPlatformOnlyAdmin.value) {
    pendingApplications.value = []
    return
  }
  const rows = await tenantApi.myApplications('pending')
  pendingApplications.value = rows.filter(
    (item) => item.status === 'pending' && item.application_type !== 'invite'
  )
}

const refreshAccessData = async () => {
  await Promise.all([userStore.loadTenants(true), loadPendingApplications(), loadPendingInvitations()])
}

const respondInvitation = async (invitation: Pick<TenantApplicationInfo, 'id'>, approved: boolean) => {
  invitationRespondingId.value = String(invitation.id)
  try {
    await tenantApi.respondInvitation(invitation.id, { approved })
    await refreshAccessData()
    ElMessage.success(t('common.operation_success'))
  } finally {
    invitationRespondingId.value = ''
  }
}

const cancelApplication = async (application: Pick<TenantApplicationInfo, 'id'>) => {
  applicationCancelingId.value = String(application.id)
  try {
    await tenantApi.cancelApplication(application.id)
    await refreshAccessData()
    ElMessage.success(t('common.operation_success'))
  } finally {
    applicationCancelingId.value = ''
  }
}

onMounted(() => {
  refreshAccessData().catch((error) => {
    console.warn('Failed to load workspace access data', error)
  })
})

watch(
  () => [requestRows.value.length, requestPage.pageSize],
  () => {
    if (requestPage.currentPage > maxRequestPage.value) {
      requestPage.currentPage = maxRequestPage.value
    }
  }
)
</script>

<template>
  <div class="access-page dv-preview dv-teleport-query no-padding">
    <aside class="resource-area access-sidebar">
      <div class="access-sidebar-title">{{ t('access.my_permissions') }}</div>
      <nav class="access-nav" :aria-label="t('access.my_permissions')">
        <button
          v-for="item in accessNavItems"
          :key="item.key"
          type="button"
          class="access-nav-item"
          :class="activePanel === item.key && 'is-active'"
          @click="activePanel = item.key"
        >
          <el-icon size="16">
            <component :is="item.icon"></component>
          </el-icon>
          <span class="access-nav-label">{{ item.label }}</span>
          <span v-if="item.key === 'requests' && pendingRequestCount" class="access-nav-badge">
            {{ pendingRequestCount }}
          </span>
        </button>
      </nav>
    </aside>

    <main class="preview-area access-main">
      <div class="preview-stage access-stage">
        <template v-if="activePanel === 'account'">
          <div class="access-header">
            <div class="access-title">{{ t('access.account_details') }}</div>
            <el-tag :type="headerTagType" effect="light" round>
              {{ headerTag }}
            </el-tag>
          </div>

          <section class="access-panel account-panel">
            <div class="account-summary">
              <UserAvatar
                :name="userStore.getName"
                :account="userStore.getAccount"
                :uid="userStore.getUid"
                :size="62"
              />
              <div class="account-summary-main">
                <div class="account-name">{{ userStore.getName || userStore.getAccount || '-' }}</div>
                <div class="account-text">{{ userStore.getAccount || '-' }}</div>
              </div>
            </div>

            <div class="account-detail-list">
              <div v-for="row in accountDetailRows" :key="row.label" class="account-detail-row">
                <div class="account-detail-label">{{ row.label }}</div>
                <div class="account-detail-value">{{ row.value }}</div>
              </div>
            </div>
          </section>
        </template>

        <template v-else-if="activePanel === 'requests'">
          <div class="access-header">
            <div class="access-title">{{ t('access.my_requests') }}</div>
            <el-tag :type="pendingRequestCount ? 'warning' : 'info'" effect="light" round>
              {{ t('access.pending_request_count', { count: pendingRequestCount }) }}
            </el-tag>
          </div>

          <section class="access-panel request-panel">
            <div class="section-heading">
              <div>
                <div class="section-title">{{ t('tenant.my_workspace_requests') }}</div>
                <div class="section-description">
                  {{ t('access.pending_workspace_requests_description') }}
                </div>
              </div>
            </div>

            <div v-if="pendingRequestCount" class="request-table-shell">
              <el-table :data="requestPageRows" class="request-table" style="width: 100%">
                <el-table-column prop="requestTypeLabel" :label="t('tenant.request_type')" width="150">
                  <template #default="scope">
                    <el-tag effect="plain" round>
                      {{ scope.row.requestTypeLabel }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="tenant_name" :label="t('tenant.name')" min-width="180" show-overflow-tooltip>
                  <template #default="scope">
                    <div class="workspace-name">{{ scope.row.tenant_name || '-' }}</div>
                    <div v-if="scope.row.requestType === 'invitation'" class="workspace-meta">
                      {{ t('tenant.inviter') }}: {{ invitationInviterLabel(scope.row) }}
                    </div>
                  </template>
                </el-table-column>
                <el-table-column prop="status" :label="t('tenant.application_status')" width="130">
                  <template #default="scope">
                    <div class="request-status" :class="requestStatusClass(scope.row.status)">
                      <span class="status-icon" aria-hidden="true"></span>
                      <span>{{ formatApplicationStatus(scope.row.status) }}</span>
                    </div>
                  </template>
                </el-table-column>
                <el-table-column prop="requestTime" :label="t('tenant.apply_time')" width="210">
                  <template #default="scope">
                    <div class="request-time-cell">
                      <div class="request-time-status">{{ scope.row.requestTimeLabel }}</div>
                      <div class="request-time-detail">{{ formatDateTime(scope.row.requestTime) }}</div>
                    </div>
                  </template>
                </el-table-column>
                <el-table-column prop="descriptionText" :label="t('tenant.apply_reason')" min-width="180" show-overflow-tooltip>
                  <template #default="scope">
                    <span class="request-description-cell">{{ scope.row.descriptionText || '-' }}</span>
                  </template>
                </el-table-column>
                <el-table-column fixed="right" :label="t('ds.actions')" width="170">
                  <template #default="scope">
                    <div v-if="scope.row.requestType === 'invitation'" class="request-actions">
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
                      v-else
                      text
                      type="danger"
                      :loading="applicationCancelingId === String(scope.row.id)"
                      @click="cancelApplication(scope.row)"
                    >
                      {{ t('tenant.withdraw_action') }}
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
              <div class="table-pagination">
                <el-pagination
                  v-model:current-page="requestPage.currentPage"
                  v-model:page-size="requestPage.pageSize"
                  :page-sizes="[5, 10, 20]"
                  :total="requestRows.length"
                  small
                  layout="total, sizes, prev, pager, next"
                />
              </div>
            </div>
            <div v-else class="empty-state">{{ t('tenant.no_workspace_requests') }}</div>
          </section>
        </template>

        <template v-else>
          <div class="access-header">
            <div class="access-title">{{ t('access.permission_details') }}</div>
            <el-tag :type="headerTagType" effect="light" round>
              {{ headerTag }}
            </el-tag>
          </div>

          <section class="access-notice">
            <div class="notice-title">{{ t('access.permission_boundary_title') }}</div>
            <div class="notice-description">{{ t('access.permission_boundary_description') }}</div>
            <div class="notice-footer">{{ t('access.apply_tip') }}</div>
          </section>

          <section class="access-panel identity-panel">
            <div class="section-heading">
              <div>
                <div class="section-title">{{ t('access.workspace_identity_title') }}</div>
                <div class="section-description">{{ t('access.workspace_identity_description') }}</div>
              </div>
            </div>

            <div v-if="workspaceList.length" class="identity-list">
              <div v-for="workspace in workspaceList" :key="workspace.id" class="identity-row">
                <div class="workspace-main">
                  <div class="workspace-title-row">
                    <span class="workspace-name">{{ formatWorkspaceName(workspace) }}</span>
                  </div>
                  <div v-if="formatWorkspaceMeta(workspace)" class="workspace-meta">
                    {{ formatWorkspaceMeta(workspace) }}
                  </div>
                </div>
                <el-tag :type="roleTagType(normalizeRole(workspace.role))" effect="plain" round>
                  {{ roleLabel(workspace.role) }}
                </el-tag>
              </div>
            </div>
            <div v-else class="empty-state">{{ t('access.no_joined_workspace_status') }}</div>
          </section>
        </template>
      </div>
    </main>
  </div>
</template>

<style lang="less" scoped>
.access-page {
  --dashboard-preview-card-bg: #ffffff;
  --dashboard-preview-canvas-bg: #fbfbff;
  --dashboard-preview-sidebar-bg: #f3f7fc;

  width: 100%;
  height: 100%;
  min-height: 0;
  padding: 0;
  display: flex;
  overflow: hidden;
  background: var(--dashboard-preview-sidebar-bg);
  color: #1f2329;
  font-family: 'PingFang SC', 'Microsoft YaHei', 'Helvetica Neue', Arial, sans-serif;

  .access-sidebar {
    --ed-aside-width: 280px;

    position: relative;
    flex: 0 0 280px;
    width: 280px;
    height: 100%;
    min-width: 0;
    padding: 8px 0 0;
    border: 0;
    border-right: 1px solid var(--workspace-border, var(--theme-shell-border));
    border-radius: 0;
    background: var(--dashboard-preview-sidebar-bg);
    color: var(--workspace-text-primary, #1f2329);
    overflow: hidden;
  }

  .access-sidebar-title {
    height: 24px;
    margin: 0 8px 10px;
    color: var(--workspace-text-primary, var(--TextPrimary, #1f2329));
    font-weight: 600;
    font-size: 15px;
    line-height: 24px;
    white-space: nowrap;
  }

  .access-nav {
    display: grid;
    gap: 1px;
    padding: 0 8px;
  }

  .access-nav-item {
    width: 100%;
    height: 32px;
    padding: 0 8px;
    display: flex;
    align-items: center;
    gap: 6px;
    border: 0;
    border-radius: 6px;
    background: transparent;
    color: var(--workspace-text-primary, #1f2329);
    font-size: 13px;
    line-height: 20px;
    font-weight: 400;
    text-align: left;
    cursor: pointer;
    transition:
      background-color 0.18s ease,
      color 0.18s ease;

    &:hover {
      background: var(--workspace-control-hover-bg, #eef2f8);
    }

    &.is-active {
      background: #e8f0ff;
      color: var(--workspace-text-primary, var(--theme-text-primary));
      font-weight: 500;

      .ed-icon {
        color: var(--ed-color-primary, #2f6bff);
        transform: scale(1.08);
      }
    }

    .ed-icon {
      flex: 0 0 auto;
      color: var(--workspace-text-secondary, #667085);
      transition:
        color 0.18s ease,
        transform 0.18s ease;
    }

    svg [fill] {
      fill: currentColor;
    }

    svg [stroke] {
      stroke: currentColor;
    }
  }

  .access-nav-label {
    min-width: 0;
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .access-nav-badge {
    min-width: 18px;
    height: 18px;
    padding: 0 5px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: 999px;
    background: #fff7e6;
    color: #d46b08;
    font-size: 12px;
    line-height: 18px;
    font-weight: 500;
  }

  .access-main {
    flex: 1;
    display: flex;
    min-width: 0;
    min-height: 0;
    overflow-x: hidden;
    overflow-y: auto;
    position: relative;
    background: var(--dashboard-preview-canvas-bg);
  }

  .access-stage {
    display: flex;
    flex: 1;
    min-width: 0;
    min-height: 0;
    flex-direction: column;
    padding: 24px 26px;
    background: var(--dashboard-preview-canvas-bg);
  }

  .access-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 16px;
    min-height: 34px;
    flex: 0 0 auto;
  }

  .access-title {
    color: var(--workspace-text-primary, var(--theme-text-primary, #1f2329));
    font-weight: 600;
    font-size: 15px;
    line-height: 24px;
    letter-spacing: 0.1px;
    white-space: nowrap;
  }

  .access-panel,
  .access-notice {
    border: 1px solid #dee0e3;
    border-radius: 8px;
    background: #fff;
  }

  .access-panel {
    min-width: 0;
    padding: 20px 24px 24px;
    margin-bottom: 16px;
    flex: 0 0 auto;
  }

  .account-panel {
    padding: 24px;
  }

  .account-summary {
    display: flex;
    align-items: center;
    gap: 14px;
    padding-bottom: 20px;
    border-bottom: 1px solid #eff0f1;
  }

  .account-summary-main {
    min-width: 0;
  }

  .account-name {
    color: #1f2329;
    font-size: 18px;
    line-height: 26px;
    font-weight: 600;
    word-break: break-word;
  }

  .account-text {
    margin-top: 2px;
    color: #86909c;
    font-size: 13px;
    line-height: 20px;
    word-break: break-word;
  }

  .account-detail-list {
    margin-top: 20px;
    border: 1px solid #eff0f1;
    border-radius: 8px;
    overflow: hidden;
  }

  .account-detail-row {
    min-height: 50px;
    padding: 0 14px;
    display: grid;
    grid-template-columns: 160px minmax(0, 1fr);
    align-items: center;
    gap: 16px;
    border-bottom: 1px solid #eff0f1;

    &:last-child {
      border-bottom: 0;
    }
  }

  .account-detail-label {
    color: #646a73;
    font-size: 13px;
    line-height: 20px;
  }

  .account-detail-value {
    min-width: 0;
    color: #1f2329;
    font-size: 14px;
    line-height: 22px;
    word-break: break-word;
  }

  .identity-panel {
    background: linear-gradient(180deg, #f7faf9 0%, #fff 100%);
  }

  .section-heading {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 16px;
  }

  .section-heading > .ed-tag {
    flex-shrink: 0;
  }

  .section-title {
    font-weight: 600;
    font-size: 16px;
    line-height: 24px;
  }

  .section-description {
    margin-top: 4px;
    color: #646a73;
    font-size: 13px;
    line-height: 20px;
  }

  .identity-list {
    display: grid;
    gap: 8px;
    max-height: 320px;
    overflow: auto;
    padding-right: 2px;
  }

  .identity-row {
    display: flex;
    justify-content: space-between;
    gap: 16px;
    border: 1px solid #eff0f1;
    border-radius: 8px;
    background: #fff;
  }

  .identity-row {
    align-items: center;
    min-height: 58px;
    padding: 10px 12px;
    background: rgba(255, 255, 255, 0.84);
  }

  .workspace-main {
    min-width: 0;
  }

  .workspace-title-row {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
  }

  .workspace-name {
    min-width: 0;
    font-weight: 500;
    font-size: 14px;
    line-height: 22px;
    word-break: break-word;
  }

  .workspace-meta {
    margin-top: 2px;
    color: #86909c;
    font-size: 12px;
    line-height: 18px;
    word-break: break-word;
  }

  .request-table-shell {
    border: 1px solid #eff0f1;
    border-radius: 8px;
    overflow: hidden;
    background: #fff;
  }

  .request-table {
    :deep(.ed-table__inner-wrapper),
    :deep(.ed-table__body-wrapper),
    :deep(.ed-scrollbar),
    :deep(.ed-scrollbar__wrap) {
      min-height: 0;
    }

    :deep(.ed-table__header-wrapper th.ed-table__cell) {
      background: #f7f8fa;
      color: #646a73;
      font-weight: 600;
    }

    :deep(.ed-table__cell) {
      border-color: #eff0f1;
    }

    :deep(.ed-table__body tr:hover > td.ed-table__cell) {
      background: #f8fbff;
    }
  }

  .request-actions {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-shrink: 0;
  }

  .request-status {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    color: #646a73;
    font-size: 13px;
    line-height: 20px;
    font-weight: 500;
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
    color: #646a73;
    font-size: 13px;
    line-height: 20px;
    font-weight: 500;
  }

  .request-time-detail,
  .request-description-cell {
    color: #86909c;
    font-size: 12px;
    line-height: 18px;
  }

  .table-pagination {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    min-height: 48px;
    padding: 10px 16px;
    border-top: 1px solid #eff0f1;
    background: #fff;
  }

  .empty-state {
    padding: 14px;
    border-radius: 8px;
    background: #f7f8fa;
    color: #86909c;
    font-size: 13px;
    line-height: 20px;
  }

  .access-notice {
    padding: 20px 24px;
    margin-bottom: 16px;
    background: #f7faf9;
  }

  .notice-title {
    font-weight: 600;
    font-size: 15px;
    line-height: 23px;
  }

  .notice-description,
  .notice-footer {
    margin-top: 8px;
    color: #646a73;
    font-size: 14px;
    line-height: 22px;
  }

  .notice-footer {
    color: #1f2329;
    font-weight: 500;
  }
}

@media (max-width: 640px) {
  .access-page {
    flex-direction: column;
    overflow: auto;

    .access-sidebar {
      flex: 0 0 auto;
      width: 100%;
      height: auto;
      padding-bottom: 8px;
      border-right: 0;
      border-bottom: 1px solid var(--workspace-border, var(--theme-shell-border));
    }

    .access-main {
      overflow: visible;
    }

    .access-stage {
      padding: 16px;
    }

    .access-nav {
      grid-template-columns: repeat(auto-fit, minmax(112px, 1fr));
    }

    .access-header,
    .identity-row,
    .section-heading {
      align-items: flex-start;
      flex-direction: column;
    }

    .account-detail-row {
      grid-template-columns: 1fr;
      gap: 4px;
      padding: 10px 14px;
      align-items: flex-start;
    }
  }
}
</style>
