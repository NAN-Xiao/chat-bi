<script setup lang="ts">
import { computed, onMounted, ref, shallowRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus-secondary'
import { useUserStore } from '@/stores/user'
import { tenantApi, type TenantApplicationInfo, type TenantInfo } from '@/api/tenant'
import { formatTimestamp } from '@/utils/date'

type WorkspaceRoleKey = 'owner' | 'admin' | 'member'

const { t } = useI18n()
const userStore = useUserStore()
const pendingInvitations = shallowRef<TenantApplicationInfo[]>([])
const pendingApplications = shallowRef<TenantApplicationInfo[]>([])
const invitationRespondingId = ref('')
const applicationCancelingId = ref('')

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

const invitationInviterLabel = (invitation: TenantApplicationInfo) =>
  invitation.inviter_name || invitation.inviter_account || '-'

const formatApplicationType = (type?: string) => {
  if (type === 'join') return t('tenant.application_type_join')
  if (type === 'invite') return t('tenant.application_type_invite')
  return t('tenant.application_type_create')
}

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

const respondInvitation = async (invitation: TenantApplicationInfo, approved: boolean) => {
  invitationRespondingId.value = String(invitation.id)
  try {
    await tenantApi.respondInvitation(invitation.id, { approved })
    await refreshAccessData()
    ElMessage.success(t('common.operation_success'))
  } finally {
    invitationRespondingId.value = ''
  }
}

const cancelApplication = async (application: TenantApplicationInfo) => {
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
</script>

<template>
  <div class="access-page">
    <div class="access-header">
      <div class="access-title">{{ t('access.my_permissions') }}</div>
      <el-tag :type="headerTagType" effect="light" round>
        {{ headerTag }}
      </el-tag>
    </div>

    <div class="access-overview-grid">
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

      <section class="access-panel request-panel">
        <div class="section-heading">
          <div>
            <div class="section-title">{{ t('tenant.my_workspace_requests') }}</div>
            <div class="section-description">
              {{ t('access.pending_workspace_requests_description') }}
            </div>
          </div>
          <el-tag :type="pendingRequestCount ? 'warning' : 'info'" effect="light" round>
            {{ t('access.pending_request_count', { count: pendingRequestCount }) }}
          </el-tag>
        </div>

        <div v-if="pendingRequestCount" class="request-list">
          <div v-for="application in pendingApplications" :key="`application-${application.id}`" class="request-row">
            <div class="request-main">
              <div class="workspace-title-row">
                <span class="workspace-name">
                  {{ application.tenant_name || '-' }}
                </span>
                <el-tag type="info" effect="plain" round>
                  {{ formatApplicationType(application.application_type) }}
                </el-tag>
                <el-tag type="warning" effect="plain" round>
                  {{ t('tenant.application_status_pending') }}
                </el-tag>
              </div>
              <div class="request-meta">
                <span>{{ t('tenant.submitted_at') }} {{ formatDateTime(application.create_time) }}</span>
                <span>{{ t('tenant.requested_role') }}: {{ roleLabel(application.requested_role) }}</span>
              </div>
              <div v-if="application.reason" class="request-reason">
                {{ t('tenant.apply_reason') }}: {{ application.reason }}
              </div>
            </div>
            <div class="request-actions">
              <el-button
                text
                type="danger"
                :loading="applicationCancelingId === String(application.id)"
                @click="cancelApplication(application)"
              >
                {{ t('tenant.withdraw_action') }}
              </el-button>
            </div>
          </div>

          <div v-for="invitation in pendingInvitations" :key="invitation.id" class="request-row">
            <div class="request-main">
              <div class="workspace-title-row">
                <span class="workspace-name">
                  {{ invitation.tenant_name || '-' }}
                </span>
                <el-tag type="info" effect="plain" round>
                  {{ t('tenant.application_type_invite') }}
                </el-tag>
                <el-tag type="warning" effect="plain" round>
                  {{ t('tenant.application_status_pending') }}
                </el-tag>
              </div>
              <div class="request-meta">
                <span>{{ t('tenant.inviter') }}: {{ invitationInviterLabel(invitation) }}</span>
                <span>{{ t('tenant.invited_at') }} {{ formatDateTime(invitation.create_time) }}</span>
                <span>{{ t('tenant.requested_role') }}: {{ roleLabel(invitation.requested_role) }}</span>
              </div>
              <div v-if="invitation.reason" class="request-reason">
                {{ t('tenant.invitation_note') }}: {{ invitation.reason }}
              </div>
            </div>
            <div class="request-actions">
              <el-button
                type="primary"
                :loading="invitationRespondingId === String(invitation.id)"
                @click="respondInvitation(invitation, true)"
              >
                {{ t('tenant.accept_invitation') }}
              </el-button>
              <el-button
                text
                type="danger"
                :disabled="invitationRespondingId === String(invitation.id)"
                @click="respondInvitation(invitation, false)"
              >
                {{ t('tenant.reject_invitation') }}
              </el-button>
            </div>
          </div>
        </div>
        <div v-else class="empty-state">{{ t('tenant.no_workspace_requests') }}</div>
      </section>
    </div>

    <section class="access-panel role-reference-panel">
      <div class="section-heading">
        <div>
          <div class="section-title">{{ t('access.workspace_role_groups') }}</div>
          <div class="section-description">{{ t('access.workspace_role_groups_description') }}</div>
        </div>
      </div>

      <div class="role-reference-grid">
        <article v-for="group in visibleRoleGroups" :key="group.key" class="role-card">
          <div class="role-card-header">
            <div>
              <div class="role-group-title-row">
                <span class="role-group-title">{{ group.label }}</span>
                <el-tag :type="group.tagType" effect="light" round>
                  {{ t('access.workspace_count', { count: group.items.length }) }}
                </el-tag>
              </div>
              <div class="role-group-description">{{ group.description }}</div>
            </div>
          </div>

          <div class="role-detail-grid">
            <div class="role-detail-block">
              <div class="role-detail-title">{{ t('access.what_i_can_do') }}</div>
              <ul class="role-detail-list">
                <li v-for="item in group.capabilities" :key="item">{{ item }}</li>
              </ul>
            </div>
            <div class="role-detail-block">
              <div class="role-detail-title">{{ t('access.my_responsibilities') }}</div>
              <ul class="role-detail-list">
                <li v-for="item in group.responsibilities" :key="item">{{ item }}</li>
              </ul>
            </div>
          </div>
        </article>
      </div>
    </section>

    <section class="access-notice">
      <div class="notice-title">{{ t('access.permission_boundary_title') }}</div>
      <div class="notice-description">{{ t('access.permission_boundary_description') }}</div>
      <div class="notice-footer">{{ t('access.apply_tip') }}</div>
    </section>
  </div>
</template>

<style lang="less" scoped>
.access-page {
  height: 100%;
  padding: 0 0 24px;
  color: #1f2329;

  .access-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 16px;
    min-height: 34px;
  }

  .access-title {
    color: var(--workspace-text-primary, var(--theme-text-primary, #1f2329));
    font-weight: 600;
    font-size: 15px;
    line-height: 24px;
    letter-spacing: 0.1px;
    white-space: nowrap;
  }

  .access-overview-grid {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(360px, 460px);
    gap: 16px;
    align-items: start;
    margin-bottom: 16px;
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
  }

  .identity-panel {
    background: linear-gradient(180deg, #f7faf9 0%, #fff 100%);
  }

  .access-overview-grid .access-panel {
    margin-bottom: 0;
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

  .identity-list,
  .request-list {
    display: grid;
    gap: 8px;
    max-height: 320px;
    overflow: auto;
    padding-right: 2px;
  }

  .identity-row,
  .request-row {
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

  .request-row {
    align-items: flex-start;
    min-height: 72px;
    padding: 12px 14px;
  }

  .workspace-main,
  .request-main {
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

  .request-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 14px;
    margin-top: 4px;
    color: #646a73;
    font-size: 12px;
    line-height: 18px;
  }

  .request-reason {
    margin-top: 6px;
    color: #86909c;
    font-size: 12px;
    line-height: 18px;
    word-break: break-word;
  }

  .request-actions {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-shrink: 0;
  }

  .empty-state {
    padding: 14px;
    border-radius: 8px;
    background: #f7f8fa;
    color: #86909c;
    font-size: 13px;
    line-height: 20px;
  }

  .role-reference-panel {
    margin-bottom: 16px;
  }

  .role-reference-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 12px;
  }

  .role-card {
    min-width: 0;
    padding: 16px;
    border: 1px solid #eff0f1;
    border-radius: 8px;
    background: #fff;
  }

  .role-card-header {
    min-height: 74px;
  }

  .role-group-title-row {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
  }

  .role-group-title {
    font-weight: 600;
    font-size: 15px;
    line-height: 23px;
  }

  .role-group-description {
    margin-top: 6px;
    color: #646a73;
    font-size: 13px;
    line-height: 20px;
  }

  .role-detail-grid {
    display: grid;
    grid-template-columns: 1fr;
    gap: 10px;
    margin-top: 12px;
  }

  .role-detail-block {
    min-width: 0;
    padding: 14px;
    border-radius: 8px;
    background: #f7f8fa;
  }

  .role-detail-title {
    font-weight: 600;
    font-size: 13px;
    line-height: 20px;
  }

  .role-detail-list {
    margin: 8px 0 0;
    padding-left: 18px;
    color: #4e5969;
    font-size: 13px;
    line-height: 22px;
  }

  .access-notice {
    padding: 20px 24px;
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

@media (max-width: 1180px) {
  .access-page {
    .access-overview-grid {
      grid-template-columns: 1fr;
    }
  }
}

@media (max-width: 640px) {
  .access-page {
    .access-header,
    .identity-row,
    .request-row,
    .section-heading {
      align-items: flex-start;
      flex-direction: column;
    }

    .request-actions {
      width: 100%;
      justify-content: flex-start;
      flex-wrap: wrap;
    }
  }
}
</style>
