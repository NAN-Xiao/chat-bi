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

const workspaceList = computed<TenantInfo[]>(() => userStore.getTenants || [])
const currentWorkspaceId = computed(() => String(userStore.getTenantId || ''))
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

const formatWorkspaceName = (workspace: TenantInfo) =>
  workspace.name || workspace.code || String(workspace.id || '')

const formatWorkspaceMeta = (workspace: TenantInfo) => {
  const parts = [
    workspace.code,
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

const currentWorkspaceLabel = computed(() => {
  if (isPlatformOnlyAdmin.value) return t('access.platform_admin_workspace_label')
  if (!userStore.getTenantId) return t('access.no_current_workspace')
  return t('access.current_workspace_named', { name: userStore.getTenantName })
})

const headerTag = computed(() => {
  if (isPlatformOnlyAdmin.value) return t('access.platform_admin')
  if (!joinedWorkspaceCount.value) return t('access.no_joined_workspace_status')
  return t('access.joined_workspace_count', { count: joinedWorkspaceCount.value })
})

const headerTagType = computed(() =>
  isPlatformOnlyAdmin.value || joinedWorkspaceCount.value ? 'success' : 'info'
)

const roleConfigs = computed(() => [
  {
    key: 'owner' as const,
    label: t('access.owner_group_title'),
    shortLabel: t('access.owner_group_short'),
    tagType: roleTagType('owner'),
    description: t('access.owner_group_description'),
    capabilities: [
      t('access.owner_capability_members'),
      t('access.owner_capability_security'),
      t('access.owner_capability_data'),
    ],
    responsibilities: [
      t('access.owner_responsibility_boundary'),
      t('access.owner_responsibility_trust'),
      t('access.owner_responsibility_risk'),
    ],
  },
  {
    key: 'admin' as const,
    label: t('access.admin_group_title'),
    shortLabel: t('access.admin_group_short'),
    tagType: roleTagType('admin'),
    description: t('access.admin_group_description'),
    capabilities: [
      t('access.admin_capability_members'),
      t('access.admin_capability_config'),
      t('access.admin_capability_support'),
    ],
    responsibilities: [
      t('access.admin_responsibility_policy'),
      t('access.admin_responsibility_support'),
      t('access.admin_responsibility_data'),
    ],
  },
  {
    key: 'member' as const,
    label: t('access.member_group_title'),
    shortLabel: t('access.member_group_short'),
    tagType: roleTagType('member'),
    description: t('access.member_group_description'),
    capabilities: [
      t('access.member_capability_analysis'),
      t('access.member_capability_assets'),
      t('access.member_capability_request'),
    ],
    responsibilities: [
      t('access.member_responsibility_scope'),
      t('access.member_responsibility_share'),
      t('access.member_responsibility_request'),
    ],
  },
])

const roleGroups = computed(() => {
  const buckets: Record<WorkspaceRoleKey, TenantInfo[]> = {
    owner: [],
    admin: [],
    member: [],
  }
  workspaceList.value.forEach((workspace) => {
    buckets[normalizeRole(workspace.role)].push(workspace)
  })
  return roleConfigs.value.map((config) => ({
    ...config,
    items: buckets[config.key],
  }))
})

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

onMounted(() => {
  refreshAccessData().catch((error) => {
    console.warn('Failed to load workspace access data', error)
  })
})
</script>

<template>
  <div class="access-page">
    <div class="access-header">
      <div>
        <div class="access-title">{{ t('access.my_permissions') }}</div>
        <div class="access-subtitle">{{ t('access.subtitle') }}</div>
      </div>
      <el-tag :type="headerTagType" effect="light" round>
        {{ headerTag }}
      </el-tag>
    </div>

    <section class="access-summary">
      <div class="summary-main">
        <div class="summary-label">{{ t('access.workspace_identity_title') }}</div>
        <div class="summary-value">{{ currentWorkspaceLabel }}</div>
        <div class="summary-description">{{ t('access.workspace_identity_description') }}</div>
      </div>
      <div class="summary-stats">
        <div v-for="group in roleGroups" :key="group.key" class="summary-stat">
          <div class="summary-stat-value">{{ group.items.length }}</div>
          <div class="summary-stat-label">{{ group.shortLabel }}</div>
        </div>
      </div>
    </section>

    <section v-if="pendingRequestCount" class="access-section invitation-section">
      <div class="section-heading">
        <div>
          <div class="section-title">{{ t('tenant.my_workspace_requests') }}</div>
          <div class="section-description">
            {{ t('access.pending_workspace_requests_description') }}
          </div>
        </div>
        <el-tag type="warning" effect="light" round>
          {{ t('access.workspace_count', { count: pendingRequestCount }) }}
        </el-tag>
      </div>

      <div class="invitation-list">
        <div v-for="application in pendingApplications" :key="`application-${application.id}`" class="invitation-row">
          <div class="invitation-main">
            <div class="workspace-title-row">
              <span class="workspace-name">
                {{ application.tenant_name || application.tenant_code }}
              </span>
              <el-tag type="info" effect="plain" round>
                {{ formatApplicationType(application.application_type) }}
              </el-tag>
              <el-tag type="warning" effect="plain" round>
                {{ t('tenant.application_status_pending') }}
              </el-tag>
            </div>
            <div class="invitation-meta">
              <span>{{ t('tenant.submitted_at') }} {{ formatDateTime(application.create_time) }}</span>
              <span>{{ t('tenant.requested_role') }}: {{ roleLabel(application.requested_role) }}</span>
            </div>
            <div v-if="application.reason" class="invitation-reason">
              {{ t('tenant.apply_reason') }}: {{ application.reason }}
            </div>
          </div>
        </div>

        <div v-for="invitation in pendingInvitations" :key="invitation.id" class="invitation-row">
          <div class="invitation-main">
            <div class="workspace-title-row">
              <span class="workspace-name">
                {{ invitation.tenant_name || invitation.tenant_code }}
              </span>
              <el-tag type="info" effect="plain" round>
                {{ t('tenant.application_type_invite') }}
              </el-tag>
              <el-tag type="warning" effect="plain" round>
                {{ t('tenant.application_status_pending') }}
              </el-tag>
            </div>
            <div class="invitation-meta">
              <span>{{ t('tenant.inviter') }}: {{ invitationInviterLabel(invitation) }}</span>
              <span>{{ t('tenant.invited_at') }} {{ formatDateTime(invitation.create_time) }}</span>
              <span>{{ t('tenant.requested_role') }}: {{ roleLabel(invitation.requested_role) }}</span>
            </div>
            <div v-if="invitation.reason" class="invitation-reason">
              {{ t('tenant.invitation_note') }}: {{ invitation.reason }}
            </div>
          </div>
          <div class="invitation-actions">
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
    </section>

    <section class="access-section">
      <div class="section-heading">
        <div>
          <div class="section-title">{{ t('access.workspace_role_groups') }}</div>
          <div class="section-description">{{ t('access.workspace_role_groups_description') }}</div>
        </div>
      </div>

      <div class="role-group-list">
        <article v-for="group in roleGroups" :key="group.key" class="role-group">
          <div class="role-group-header">
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

          <div v-if="group.items.length" class="workspace-list">
            <div v-for="workspace in group.items" :key="workspace.id" class="workspace-row">
              <div class="workspace-main">
                <div class="workspace-title-row">
                  <span class="workspace-name">{{ formatWorkspaceName(workspace) }}</span>
                  <el-tag
                    v-if="String(workspace.id) === currentWorkspaceId"
                    type="success"
                    effect="plain"
                    round
                  >
                    {{ t('access.current_workspace') }}
                  </el-tag>
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
          <div v-else class="role-empty">{{ t('access.no_workspace_in_role') }}</div>
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
  padding: 8px 0 24px;
  color: #1f2329;

  .access-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 24px;
  }

  .access-title {
    font-weight: 600;
    font-size: 22px;
    line-height: 30px;
  }

  .access-subtitle {
    margin-top: 6px;
    color: #646a73;
    font-size: 14px;
    line-height: 22px;
  }

  .access-summary,
  .access-section,
  .access-notice {
    border: 1px solid #dee0e3;
    border-radius: 8px;
    background: #fff;
  }

  .access-summary {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(280px, 420px);
    gap: 24px;
    padding: 24px;
    margin-bottom: 16px;
    background: linear-gradient(180deg, #f7faf9 0%, #fff 100%);
  }

  .summary-label {
    color: #646a73;
    font-size: 13px;
    line-height: 20px;
  }

  .summary-value {
    margin-top: 8px;
    font-weight: 600;
    font-size: 26px;
    line-height: 34px;
  }

  .summary-description {
    margin-top: 8px;
    color: #646a73;
    font-size: 14px;
    line-height: 22px;
  }

  .summary-stats {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 10px;
    align-self: stretch;
  }

  .summary-stat {
    min-width: 0;
    padding: 14px 12px;
    border: 1px solid #eff0f1;
    border-radius: 8px;
    background: rgba(255, 255, 255, 0.72);
  }

  .summary-stat-value {
    font-weight: 600;
    font-size: 24px;
    line-height: 30px;
  }

  .summary-stat-label {
    margin-top: 4px;
    color: #646a73;
    font-size: 13px;
    line-height: 20px;
  }

  .access-section {
    padding: 20px 24px 24px;
    margin-bottom: 16px;
  }

  .section-heading {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 16px;
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

  .role-group-list {
    display: grid;
    gap: 14px;
  }

  .role-group {
    min-width: 0;
    padding: 18px;
    border: 1px solid #eff0f1;
    border-radius: 8px;
    background: #fff;
  }

  .role-group-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 16px;
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
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
    margin-top: 14px;
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

  .workspace-list {
    display: grid;
    gap: 8px;
    margin-top: 14px;
  }

  .workspace-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    min-height: 58px;
    padding: 10px 12px;
    border: 1px solid #eff0f1;
    border-radius: 8px;
    background: #fff;
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

  .role-empty {
    margin-top: 14px;
    padding: 14px;
    border-radius: 8px;
    background: #f7f8fa;
    color: #86909c;
    font-size: 13px;
    line-height: 20px;
  }

  .invitation-list {
    display: grid;
    gap: 10px;
  }

  .invitation-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    min-height: 76px;
    padding: 12px 14px;
    border: 1px solid #eff0f1;
    border-radius: 8px;
    background: #fff;
  }

  .invitation-main {
    min-width: 0;
  }

  .invitation-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 14px;
    margin-top: 4px;
    color: #646a73;
    font-size: 12px;
    line-height: 18px;
  }

  .invitation-reason {
    margin-top: 6px;
    color: #86909c;
    font-size: 12px;
    line-height: 18px;
    word-break: break-word;
  }

  .invitation-actions {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-shrink: 0;
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

@media (max-width: 900px) {
  .access-page {
    .access-summary,
    .role-detail-grid {
      grid-template-columns: 1fr;
    }

    .summary-stats {
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }
  }
}

@media (max-width: 640px) {
  .access-page {
    .access-header,
    .workspace-row,
    .invitation-row {
      align-items: flex-start;
      flex-direction: column;
    }

    .summary-stats {
      grid-template-columns: 1fr;
    }

    .invitation-actions {
      width: 100%;
      justify-content: flex-start;
      flex-wrap: wrap;
    }
  }
}
</style>
