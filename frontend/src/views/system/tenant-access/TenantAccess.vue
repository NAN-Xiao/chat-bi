<template>
  <div class="tenant-members-container professional-container">
    <div class="tool-left">
      <span class="page-title">{{ t('tenant.member_access') }}</span>
      <div class="toolbar">
        <el-input
          v-model="keyword"
          class="member-search"
          :placeholder="t('tenant.member_search_placeholder')"
          clearable
          @clear="loadMembers"
          @keydown.enter.exact.prevent="handleSearch"
        >
          <template #prefix>
            <el-icon>
              <icon_searchOutline_outlined />
            </el-icon>
          </template>
        </el-input>
        <el-button secondary @click="loadMembers">{{ t('common.refresh') }}</el-button>
        <el-button secondary @click="openReviewDialog">
          {{ t('tenant.join_application_review') }}
          <span v-if="pendingReviewCount" class="button-badge">{{ pendingReviewCount }}</span>
        </el-button>
        <el-button secondary @click="openBulkInviteDialog">{{ t('tenant.bulk_invite') }}</el-button>
        <el-button type="primary" @click="openInviteDialog">
          <template #icon>
            <icon_add_outlined />
          </template>
          {{ t('tenant.send_invitation') }}
        </el-button>
      </div>
    </div>

    <div class="member-content-stack">
      <section class="member-panel">
        <el-table
          v-loading="memberLoading"
          :data="pagedMemberRows"
          class="member-table"
          style="width: 100%"
        >
        <el-table-column prop="account" :label="t('user.account')" min-width="200" show-overflow-tooltip />
        <el-table-column prop="member_remark" :label="t('tenant.member_remark')" min-width="220" show-overflow-tooltip>
          <template #default="scope">
            {{ scope.row.member_remark || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="name" :label="t('tenant.account_display_name')" min-width="160" show-overflow-tooltip>
          <template #default="scope">
            {{ scope.row.name || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="tenant_role" :label="t('user.tenant_role')" width="150">
          <template #default="scope">
            <span class="role-text" :class="tenantRoleClass(scope.row.tenant_role)">
              {{ formatTenantRole(scope.row.tenant_role) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column :label="t('tenant.project_access')" min-width="220" show-overflow-tooltip>
          <template #default="scope">
            {{ formatDatasourceAccess(scope.row) }}
          </template>
        </el-table-column>
        <el-table-column prop="create_time" :label="t('tenant.join_time')" width="180">
          <template #default="scope">
            {{ formatOptionalTimestamp(scope.row.create_time) }}
          </template>
        </el-table-column>
        <el-table-column fixed="right" :label="t('ds.actions')" width="150">
          <template #default="scope">
            <div class="table-operate">
              <el-button text :disabled="!canEditMember(scope.row)" @click="openEditDialog(scope.row)">
                {{ t('datasource.edit') }}
              </el-button>
              <el-button
                text
                type="danger"
                :disabled="!canRemoveMember(scope.row)"
                @click="removeMember(scope.row)"
              >
                {{ t('project.remove') }}
              </el-button>
            </div>
          </template>
        </el-table-column>
        <template #empty>
          <EmptyBackground :description="t('tenant.no_members')" img-type="tree" />
        </template>
        </el-table>
        <div class="table-pagination">
          <el-pagination
            v-model:current-page="memberPage.currentPage"
            v-model:page-size="memberPage.pageSize"
            :page-sizes="[5, 10, 20]"
            :total="memberRows.length"
            small
            layout="total, sizes, prev, pager, next"
          />
        </div>
      </section>

      <section class="member-panel invitation-panel">
        <div class="panel-header">
          <div class="panel-title">
            <span>{{ t('tenant.pending_invitations') }}</span>
            <span v-if="pendingInvitationCount" class="panel-count">{{ pendingInvitationCount }}</span>
          </div>
          <el-button text :loading="applicationLoading" @click="loadApplications">
            {{ t('common.refresh') }}
          </el-button>
        </div>
        <el-table
          v-loading="applicationLoading"
          :data="pagedPendingInvitations"
          class="invitation-table"
          style="width: 100%"
        >
        <el-table-column prop="applicant_account" :label="t('tenant.invited_user')" min-width="180" show-overflow-tooltip>
          <template #default="scope">
            {{ formatInvitationTarget(scope.row) }}
          </template>
        </el-table-column>
        <el-table-column prop="requested_role" :label="t('tenant.requested_role')" width="150">
          <template #default="scope">
            {{ formatTenantRole(scope.row.requested_role) }}
          </template>
        </el-table-column>
        <el-table-column prop="inviter_account" :label="t('tenant.inviter')" min-width="160" show-overflow-tooltip>
          <template #default="scope">
            {{ formatInviter(scope.row) }}
          </template>
        </el-table-column>
        <el-table-column prop="reason" :label="t('tenant.invitation_note')" min-width="180" show-overflow-tooltip>
          <template #default="scope">
            {{ scope.row.reason || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="create_time" :label="t('tenant.invited_at')" width="180">
          <template #default="scope">
            {{ formatOptionalTimestamp(scope.row.create_time) }}
          </template>
        </el-table-column>
        <el-table-column fixed="right" :label="t('ds.actions')" width="120">
          <template #default="scope">
            <el-button
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
          <EmptyBackground :description="t('tenant.no_pending_invitations')" img-type="tree" />
        </template>
        </el-table>
        <div class="table-pagination">
          <el-pagination
            v-model:current-page="invitationPage.currentPage"
            v-model:page-size="invitationPage.pageSize"
            :page-sizes="[5, 10, 20]"
            :total="pendingInvitationCount"
            small
            layout="total, sizes, prev, pager, next"
          />
        </div>
      </section>
    </div>

    <el-drawer
      v-model="memberDialogVisible"
      :title="memberDialogTitle"
      destroy-on-close
      modal-class="tenant-member-drawer"
      size="720px"
      :before-close="closeMemberDialog"
    >
      <el-form
        ref="memberFormRef"
        :model="memberForm"
        :rules="memberRules"
        label-position="top"
        class="form-content_error"
        @submit.prevent
      >
        <el-form-item prop="account" :label="t('user.account')">
          <el-input
            v-model="memberForm.account"
            :disabled="memberDialogMode === 'edit'"
            maxlength="100"
            clearable
            :placeholder="t('user.invite_account_placeholder')"
          />
        </el-form-item>
        <el-form-item v-if="memberDialogMode === 'invite'" :label="t('tenant.invitation_note')">
          <el-input
            v-model="memberForm.reason"
            type="textarea"
            :rows="3"
            maxlength="2000"
            clearable
          />
        </el-form-item>
        <el-form-item v-if="memberDialogMode === 'edit'" :label="t('tenant.member_remark')">
          <el-input
            v-model="memberForm.member_remark"
            maxlength="255"
            clearable
            :placeholder="t('tenant.member_remark_placeholder')"
          />
        </el-form-item>
        <el-form-item prop="tenant_role" :label="t('user.tenant_role')">
          <el-select v-model="memberForm.tenant_role" popper-class="tenant-light-popper" style="width: 240px">
            <el-option
              v-for="item in tenantRoleOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="memberDialogMode === 'edit'" :label="t('user.project_permission_config')">
          <div class="datasource-permission-panel">
            <div class="datasource-permission-toolbar">
              <div class="bound-datasource-title">
                <span class="bound-datasource-label">{{ t('tenant.bound_datasource') }}</span>
                <span class="bound-datasource-name">{{ boundDatasourceName }}</span>
              </div>
              <span class="datasource-permission-count">
                {{ boundDatasourceTableRows.length ? t('tenant.datasource_bound') : t('permission.no_data_source_bound') }}
              </span>
            </div>

            <el-table
              :data="boundDatasourceTableRows"
              :empty-text="t('user.no_project_permission')"
              class="datasource-permission-table"
              style="width: 100%"
            >
              <el-table-column :label="t('permission.data_source')" min-width="160">
                <template #default="scope">
                  <div class="datasource-cell">
                    <div class="datasource-name ellipsis" :title="scope.row.name">
                      {{ scope.row.name }}
                    </div>
                    <div class="datasource-type ellipsis" :title="scope.row.type_name || scope.row.type">
                      {{ scope.row.type_name || scope.row.type || '-' }}
                    </div>
                  </div>
                </template>
              </el-table-column>
              <el-table-column :label="t('user.database_scope')" min-width="150">
                <template #default="scope">
                  <span class="database-label" :title="formatDatasourceDatabase(scope.row)">
                    {{ formatDatasourceDatabase(scope.row) }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column :label="t('user.project_role')" width="132">
                <template #default="scope">
                  <el-select
                    v-model="memberForm.project_role_map[Number(scope.row.id)]"
                    popper-class="tenant-light-popper"
                    style="width: 112px"
                  >
                    <el-option
                      v-for="item in datasourceRoleOptions"
                      :key="item.value"
                      :label="item.label"
                      :value="item.value"
                    />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column :label="t('user.permission_strategy')" min-width="220">
                <template #default="scope">
                  <el-select
                    v-model="memberForm.project_permission_map[Number(scope.row.id)]"
                    multiple
                    filterable
                    collapse-tags
                    collapse-tags-tooltip
                    popper-class="tenant-light-popper"
                    style="width: 100%"
                    :placeholder="t('user.select_permission_strategy')"
                  >
                    <el-option
                      v-for="item in getPermissionStrategiesByDatasource(scope.row.id)"
                      :key="item.id"
                      :label="item.name"
                      :value="Number(item.id)"
                    >
                      <div class="permission-option">
                        <span class="permission-option-name ellipsis" :title="item.name">
                          {{ item.name }}
                        </span>
                        <span class="permission-option-summary">
                          {{ formatRuleGroupSummary(item, scope.row.id) }}
                        </span>
                      </div>
                    </el-option>
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column :label="t('user.permission_summary')" min-width="170">
                <template #default="scope">
                  <div class="permission-summary">
                    <template v-if="getSelectedStrategiesByDatasource(scope.row.id).length">
                      <div class="summary-line" :title="formatTableAccessSummary(scope.row.id)">
                        {{ formatTableAccessSummary(scope.row.id) }}
                      </div>
                      <div class="summary-line" :title="formatFieldAccessSummary(scope.row.id)">
                        {{ formatFieldAccessSummary(scope.row.id) }}
                      </div>
                      <div class="summary-line" :title="formatRowAccessSummary(scope.row.id)">
                        {{ formatRowAccessSummary(scope.row.id) }}
                      </div>
                    </template>
                    <span v-else class="muted">{{ t('user.project_access_only') }}</span>
                  </div>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button secondary @click="closeMemberDialog">{{ t('common.cancel') }}</el-button>
          <el-button type="primary" :loading="memberSubmitting" @click="saveMember">
            {{ memberDialogMode === 'invite' ? t('tenant.send_invitation') : t('common.save') }}
          </el-button>
        </div>
      </template>
    </el-drawer>

    <el-dialog
      v-model="bulkDialogVisible"
      class="workspace-light-dialog"
      :title="t('tenant.bulk_invite')"
      width="560"
      :before-close="closeBulkInviteDialog"
    >
      <el-form label-position="top" class="form-content_error" @submit.prevent>
        <el-form-item :label="t('tenant.bulk_invite_accounts')">
          <el-input v-model="bulkForm.accountsText" type="textarea" :rows="6" maxlength="4000" />
        </el-form-item>
        <el-form-item :label="t('user.tenant_role')">
          <el-select v-model="bulkForm.tenant_role" popper-class="tenant-light-popper" style="width: 240px">
            <el-option
              v-for="item in tenantRoleOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('tenant.invitation_note')">
          <el-input v-model="bulkForm.reason" type="textarea" :rows="3" maxlength="2000" />
        </el-form-item>
      </el-form>
      <el-table v-if="bulkResults.length" :data="bulkResults" class="bulk-result-table">
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
          <el-button type="primary" :loading="bulkSubmitting" @click="submitBulkInvite">
            {{ t('tenant.bulk_invite') }}
          </el-button>
        </div>
      </template>
    </el-dialog>

    <el-dialog
      v-model="reviewDialogVisible"
      class="workspace-light-dialog access-review-dialog"
      :title="t('tenant.join_application_review')"
      width="860"
    >
      <el-table v-loading="applicationLoading" :data="joinApplications" class="access-table" style="width: 100%">
        <el-table-column prop="applicant_account" :label="t('user.account')" min-width="160" show-overflow-tooltip />
        <el-table-column prop="applicant_name" :label="t('user.name')" min-width="140" show-overflow-tooltip>
          <template #default="scope">
            {{ scope.row.applicant_name || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="application_type" :label="t('tenant.access_type')" width="130">
          <template #default>
            <el-tag size="small" type="warning">
              {{ t('tenant.application_type_join') }}
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
          </template>
        </el-table-column>
        <template #empty>
          <EmptyBackground :description="t('tenant.no_join_applications')" img-type="tree" />
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
import { computed, onMounted, reactive, ref, shallowRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus-secondary'
import icon_add_outlined from '@/assets/svg/icon_add_outlined.svg'
import icon_searchOutline_outlined from '@/assets/svg/icon_search-outline_outlined.svg'
import EmptyBackground from '@/views/dashboard/common/EmptyBackground.vue'
import {
  tenantApi,
  type TenantApplicationInfo,
  type TenantBulkInviteResult,
  type TenantInfo,
  type TenantMemberInfo,
} from '@/api/tenant'
import { datasourceApi } from '@/api/datasource'
import { getList as getPermissionList, savePermissions } from '@/api/permissions'
import { decrypted } from '@/views/ds/js/aes'
import { formatTimestamp } from '@/utils/date'
import { useUserStore } from '@/stores/user'
import { idsEqual, normalizeIdString, toIdStringList, uniqueIdStrings } from '@/utils/id'

const { t } = useI18n()
const userStore = useUserStore()
const isPurePlatformAdmin = computed(
  () => userStore.isSystemAdminUser && !userStore.isPlatformWorkspaceDelegate
)
const keyword = ref('')
const memberLoading = ref(false)
const applicationLoading = ref(false)
const memberSubmitting = ref(false)
const bulkSubmitting = ref(false)
const memberDialogVisible = ref(false)
const bulkDialogVisible = ref(false)
const reviewDialogVisible = ref(false)
const memberFormRef = ref()
const memberDialogMode = ref<'invite' | 'edit'>('invite')
const editingUserId = ref<number | string>('')
const joinReviewLoadingId = ref('')
const inviteCancelingId = ref('')
const memberRows = shallowRef<TenantMemberInfo[]>([])
const joinApplications = shallowRef<TenantApplicationInfo[]>([])
const invitations = shallowRef<TenantApplicationInfo[]>([])
const datasourceOptions = shallowRef<any[]>([])
const permissionRuleGroups = shallowRef<any[]>([])
const currentTenant = shallowRef<TenantInfo | null>(null)
const bulkResults = shallowRef<TenantBulkInviteResult[]>([])
const memberPage = reactive({
  currentPage: 1,
  pageSize: 5,
})
const invitationPage = reactive({
  currentPage: 1,
  pageSize: 5,
})

const memberForm = reactive({
  account: '',
  member_remark: '',
  reason: '',
  tenant_role: 'member' as 'admin' | 'member',
  // API compatibility: project_* fields carry datasource permissions for tenant members.
  project_ids: [] as number[],
  project_role_map: {} as Record<number, string>,
  project_permission_map: {} as Record<number, number[]>,
})

const bulkForm = reactive({
  accountsText: '',
  tenant_role: 'member' as 'admin' | 'member',
  reason: '',
})

const tenantRoleOptions = computed(() => [
  { value: 'member', label: t('user.tenant_role_member') },
  { value: 'admin', label: t('user.tenant_role_admin') },
])

const datasourceRoleOptions = computed(() => [
  { value: 'viewer', label: t('datasource.datasource_role_viewer') },
  { value: 'editor', label: t('datasource.datasource_role_editor') },
])

const boundDatasourceId = computed(() => {
  const id = currentTenant.value?.bound_datasource_id || currentTenant.value?.bound_project_id
  const value = Number(id)
  return id !== undefined && id !== null && id !== '' && !Number.isNaN(value) ? value : null
})

const boundDatasourceName = computed(() =>
  currentTenant.value?.bound_datasource_name ||
  currentTenant.value?.bound_project_name ||
  t('permission.no_data_source_bound')
)

const boundDatasourceRows = computed(() => {
  const id = boundDatasourceId.value
  if (!id) return []
  const existing = datasourceOptions.value.find((item: any) => Number(item.id) === id)
  if (existing) return [existing]
  return [{ id, name: boundDatasourceName.value }]
})

const memberDialogTitle = computed(() =>
  memberDialogMode.value === 'edit' ? t('tenant.edit_member') : t('tenant.send_invitation')
)

const pendingInvitations = computed(() =>
  invitations.value.filter((item) => item.status === 'pending')
)

const pendingInvitationCount = computed(() => pendingInvitations.value.length)

const pendingReviewCount = computed(
  () => joinApplications.value.filter((item) => item.status === 'pending').length
)

const paginateRows = <T>(rows: T[], page: { currentPage: number; pageSize: number }) => {
  const currentPage = Math.max(1, Number(page.currentPage || 1))
  const pageSize = Math.max(1, Number(page.pageSize || 5))
  const start = (currentPage - 1) * pageSize
  return rows.slice(start, start + pageSize)
}

const pagedMemberRows = computed(() => paginateRows(memberRows.value, memberPage))

const pagedPendingInvitations = computed(() =>
  paginateRows(pendingInvitations.value, invitationPage)
)

const normalizePage = (page: { currentPage: number; pageSize: number }, total: number) => {
  const pageSize = Math.max(1, Number(page.pageSize || 5))
  const maxPage = Math.max(1, Math.ceil(total / pageSize))
  if (page.currentPage > maxPage) {
    page.currentPage = maxPage
  }
  if (page.currentPage < 1) {
    page.currentPage = 1
  }
}

const memberRules = {
  account: [
    {
      required: true,
      message: t('datasource.please_enter') + t('common.empty') + t('user.account'),
      trigger: 'blur',
    },
  ],
  tenant_role: [
    {
      required: true,
      message: t('tenant.request_role_required'),
      trigger: 'change',
    },
  ],
}

const toNumberList = (value: any): number[] => {
  if (!value) return []
  if (Array.isArray(value)) {
    return value.map((item: any) => Number(item)).filter((item: number) => !Number.isNaN(item))
  }
  try {
    return toNumberList(JSON.parse(value))
  } catch (e) {
    return []
  }
}

const parseJsonValue = (value: any, fallback: any) => {
  if (!value) return fallback
  if (typeof value === 'object') return value
  try {
    return JSON.parse(value)
  } catch (e) {
    return fallback
  }
}

const normalizeDatasourceRole = (role: any) => {
  const value = String(role || '').trim().toLowerCase()
  return value === 'editor' ? 'editor' : 'viewer'
}

const buildDatasourceRoleMap = (datasourceIds: number[], value: any = {}) => {
  const source = parseJsonValue(value, {})
  const result: Record<number, string> = {}
  datasourceIds.forEach((id: number) => {
    result[id] = normalizeDatasourceRole(source?.[id] || source?.[String(id)])
  })
  return result
}

const normalizeTenantRole = (role: any) => {
  const normalized = String(role || 'member').trim().toLowerCase()
  return ['owner', 'admin', 'member'].includes(normalized) ? normalized : 'member'
}

const formatTenantRole = (role: any) => {
  const normalized = normalizeTenantRole(role)
  return t(`user.tenant_role_${normalized}`)
}

const tenantRoleClass = (role: any) => {
  const normalized = normalizeTenantRole(role)
  if (normalized === 'owner') return 'is-tenant-owner'
  if (normalized === 'admin') return 'is-tenant-admin'
  return 'is-tenant-member'
}

const canEditMember = (row: TenantMemberInfo) => normalizeTenantRole(row.tenant_role) !== 'owner'

const canRemoveMember = (row: TenantMemberInfo) => {
  if (String(row.user_id) === String(userStore.getUid)) return false
  return normalizeTenantRole(row.tenant_role) !== 'owner'
}

const formatOptionalTimestamp = (value?: number | string | null) => {
  const timestamp = Number(value || 0)
  return timestamp ? formatTimestamp(timestamp, 'YYYY-MM-DD HH:mm:ss') : '-'
}

const formatInvitationTarget = (invitation: TenantApplicationInfo) =>
  invitation.applicant_name || invitation.applicant_account || '-'

const formatInviter = (invitation: TenantApplicationInfo) =>
  invitation.inviter_name || invitation.inviter_account || '-'

const formatDatasourceAccess = (row: TenantMemberInfo) => {
  const id = boundDatasourceId.value
  if (!id) return t('permission.no_data_source_bound')
  const roleMap = parseJsonValue(row.project_role_map, {})
  const role = normalizeDatasourceRole(roleMap?.[id] || roleMap?.[String(id)])
  return `${boundDatasourceName.value} / ${formatDatasourceRole(role)}`
}

const boundDatasourceTableRows = computed(() => boundDatasourceRows.value)

const getDatasourceIdsFromRule = (rule: any): number[] => {
  const ids = (rule.permissions || [])
    .map((item: any) => Number(item.ds_id))
    .filter((item: number) => !Number.isNaN(item))
  return Array.from(new Set<number>(ids))
}

const getPermissionStrategiesByDatasource = (datasourceId: any) => {
  const id = Number(datasourceId)
  return permissionRuleGroups.value.filter((rule: any) => getDatasourceIdsFromRule(rule).includes(id))
}

const getSelectedStrategiesByDatasource = (datasourceId: any) => {
  const id = Number(datasourceId)
  const selectedIds = toNumberList(memberForm.project_permission_map?.[id])
  return getPermissionStrategiesByDatasource(id).filter((rule: any) =>
    selectedIds.includes(Number(rule.id))
  )
}

const formatRuleGroupSummary = (rule: any, datasourceId?: any) => {
  const id = Number(datasourceId)
  const permissions = datasourceId
    ? (rule.permissions || []).filter((item: any) => Number(item.ds_id) === id)
    : rule.permissions || []
  const rowCount = permissions.filter((item: any) => item.type === 'row').length
  const tableCount = permissions.filter((item: any) => item.type === 'table').length
  const columnCount = permissions.filter((item: any) => item.type === 'column').length
  const parts = []
  if (tableCount) parts.push(t('user.table_rule_count', { msg: tableCount }))
  if (rowCount) parts.push(t('user.row_rule_count', { msg: rowCount }))
  if (columnCount) parts.push(t('user.column_rule_count', { msg: columnCount }))
  return parts.length ? parts.join(' / ') : t('permission.no_rule')
}

const getRuleDatasourcePermissions = (rule: any, datasourceId: any) => {
  const id = Number(datasourceId)
  return (rule.permissions || []).filter((item: any) => Number(item.ds_id) === id)
}

const formatTableAccessSummary = (datasourceId: any) => {
  const tableNames = new Set<string>()
  getSelectedStrategiesByDatasource(datasourceId).forEach((rule: any) => {
    getRuleDatasourcePermissions(rule, datasourceId).forEach((permission: any) => {
      if (permission.table_name) tableNames.add(permission.table_name)
    })
  })
  if (!tableNames.size) return t('user.all_project_tables')
  const names = Array.from(tableNames)
  return names.length > 3
    ? t('user.allowed_table_summary_more', { msg: names.slice(0, 3).join('、'), count: names.length - 3 })
    : t('user.allowed_table_summary', { msg: names.join('、') })
}

const formatFieldAccessSummary = (datasourceId: any) => {
  let restrictedCount = 0
  getSelectedStrategiesByDatasource(datasourceId).forEach((rule: any) => {
    getRuleDatasourcePermissions(rule, datasourceId).forEach((permission: any) => {
      if (permission.type !== 'column') return
      const list = Array.isArray(permission.permission_list)
        ? permission.permission_list
        : parseJsonValue(permission.permissions, [])
      restrictedCount += (list || []).filter((item: any) => item.enable === false).length
    })
  })
  return restrictedCount
    ? t('user.denied_field_summary', { msg: restrictedCount })
    : t('user.no_field_restriction')
}

const formatRowAccessSummary = (datasourceId: any) => {
  let rowCount = 0
  getSelectedStrategiesByDatasource(datasourceId).forEach((rule: any) => {
    rowCount += getRuleDatasourcePermissions(rule, datasourceId).filter((item: any) => item.type === 'row').length
  })
  return rowCount ? t('user.row_filter_summary', { msg: rowCount }) : t('user.no_row_filter')
}

const formatDatasourceDatabase = (datasource: any) => {
  if (!datasource?.configuration) return datasource?.type_name || datasource?.type || '-'
  try {
    const conf = JSON.parse(decrypted(datasource.configuration) || '{}')
    const database = conf.database || conf.dataBase || conf.filename || datasource.name
    const schema = conf.dbSchema || conf.schema
    const host = conf.host && conf.port ? `${conf.host}:${conf.port}` : conf.host
    return [database, schema, host].filter(Boolean).join(' / ') || datasource.name
  } catch (e) {
    return datasource?.name || '-'
  }
}

const formatDatasourceRole = (role: any) => {
  const normalized = normalizeDatasourceRole(role)
  return datasourceRoleOptions.value.find((item) => item.value === normalized)?.label || normalized
}

const syncBoundDatasourceSelection = () => {
  const ids = boundDatasourceId.value ? [boundDatasourceId.value] : []
  memberForm.project_ids = ids
  const nextMap: Record<number, number[]> = {}
  ids.forEach((id: number) => {
    nextMap[id] = toNumberList(memberForm.project_permission_map?.[id])
  })
  memberForm.project_permission_map = nextMap
  memberForm.project_role_map = buildDatasourceRoleMap(ids, memberForm.project_role_map)
}

const buildUserDatasourcePermissionMap = (userId: any, datasourceIds: number[]) => {
  const result: Record<number, number[]> = {}
  datasourceIds.forEach((id: number) => {
    result[id] = []
  })
  if (!userId) return result

  permissionRuleGroups.value.forEach((rule: any) => {
    const users = toIdStringList(rule.users || rule.user_list)
    if (!users.some((item) => idsEqual(item, userId))) return
    getDatasourceIdsFromRule(rule).forEach((datasourceId: number) => {
      if (!datasourceIds.includes(datasourceId)) return
      result[datasourceId] = Array.from(new Set<number>([...(result[datasourceId] || []), Number(rule.id)]))
    })
  })
  return result
}

const serializePermissionRule = (rule: any, users: string[]) => ({
  id: rule.id,
  name: rule.name,
  permissions: (rule.permissions || []).map((item: any) => ({
    ...item,
    permissions:
      item.type !== 'row'
        ? typeof item.permissions === 'object'
          ? JSON.stringify(item.permissions || [])
          : item.permissions || JSON.stringify(item.permission_list || [])
        : JSON.stringify([]),
    permission_list: [],
    expression_tree:
      item.type === 'row'
        ? typeof item.expression_tree === 'object'
          ? JSON.stringify(item.expression_tree || item.tree || {})
          : item.expression_tree || JSON.stringify(parseJsonValue(item.tree, {}))
        : JSON.stringify({}),
  })),
  users,
})

const syncUserPermissionStrategies = (userId: any): Promise<void> => {
  if (!userId || !permissionRuleGroups.value.length) return Promise.resolve()
  const userIdText = normalizeIdString(userId)
  if (!userIdText) return Promise.resolve()
  const selectedRuleIds = new Set(
    Object.values(memberForm.project_permission_map || {})
      .flatMap((item: any) => toNumberList(item))
      .map((item: number) => Number(item))
  )
  const requests: Promise<any>[] = []

  permissionRuleGroups.value.forEach((rule: any) => {
    if (!getDatasourceIdsFromRule(rule).length) return
    const currentUsers = toIdStringList(rule.users || rule.user_list)
    const currentUsersWithoutTarget = currentUsers.filter((item: string) => !idsEqual(item, userIdText))
    const shouldInclude = selectedRuleIds.has(Number(rule.id))
    const nextUsers = shouldInclude
      ? uniqueIdStrings([...currentUsersWithoutTarget, userIdText])
      : currentUsersWithoutTarget
    const changed =
      nextUsers.length !== currentUsers.length ||
      nextUsers.some((item: string, index: number) => item !== currentUsers[index])
    if (!changed) return
    rule.users = nextUsers
    requests.push(savePermissions(serializePermissionRule(rule, nextUsers)))
  })

  return Promise.all(requests).then(() => undefined)
}

const loadDatasourcePermissionContext = async () => {
  if (isPurePlatformAdmin.value) return
  const [tenant, datasources, permissions] = await Promise.all([
    tenantApi.current(),
    datasourceApi.accessibleList(),
    getPermissionList(),
  ])
  currentTenant.value = tenant || null
  datasourceOptions.value = datasources || []
  permissionRuleGroups.value = permissions || []
}

const loadMembers = async () => {
  if (isPurePlatformAdmin.value) {
    memberRows.value = []
    return
  }
  memberLoading.value = true
  try {
    const [members] = await Promise.all([tenantApi.members(keyword.value.trim()), loadDatasourcePermissionContext()])
    memberRows.value = members || []
    normalizePage(memberPage, memberRows.value.length)
  } finally {
    memberLoading.value = false
  }
}

const loadApplications = async () => {
  if (isPurePlatformAdmin.value) {
    joinApplications.value = []
    invitations.value = []
    return
  }
  applicationLoading.value = true
  try {
    const [joinRows, invitationRows] = await Promise.all([
      tenantApi.tenantApplications('pending'),
      tenantApi.invitations('pending'),
    ])
    joinApplications.value = joinRows || []
    invitations.value = invitationRows || []
    normalizePage(invitationPage, pendingInvitations.value.length)
  } finally {
    applicationLoading.value = false
  }
}

const handleSearch = ($event: any = {}) => {
  if ($event?.isComposing) return
  memberPage.currentPage = 1
  loadMembers()
}

const resetMemberForm = () => {
  Object.assign(memberForm, {
    account: '',
    member_remark: '',
    reason: '',
    tenant_role: 'member',
    project_ids: [],
    project_role_map: {},
    project_permission_map: {},
  })
  editingUserId.value = ''
}

const openInviteDialog = () => {
  memberDialogMode.value = 'invite'
  resetMemberForm()
  memberDialogVisible.value = true
}

const openEditDialog = async (row: TenantMemberInfo) => {
  if (!canEditMember(row)) {
    ElMessage.warning(t('user.only_platform_admin_manage_owner'))
    return
  }
  memberDialogMode.value = 'edit'
  await loadDatasourcePermissionContext()
  const datasourceIds = boundDatasourceId.value ? [boundDatasourceId.value] : []
  Object.assign(memberForm, {
    account: row.account,
    member_remark: row.member_remark || '',
    tenant_role: normalizeTenantRole(row.tenant_role) === 'admin' ? 'admin' : 'member',
    project_ids: datasourceIds,
    project_role_map: buildDatasourceRoleMap(datasourceIds, row.project_role_map),
    project_permission_map: buildUserDatasourcePermissionMap(row.user_id, datasourceIds),
  })
  syncBoundDatasourceSelection()
  editingUserId.value = row.user_id
  memberDialogVisible.value = true
}

const closeMemberDialog = () => {
  memberDialogVisible.value = false
}

const saveMember = () => {
  memberFormRef.value?.validate(async (valid: boolean) => {
    if (!valid) return
    memberSubmitting.value = true
    try {
      if (memberDialogMode.value === 'invite') {
        await tenantApi.invite({
          account: memberForm.account.trim(),
          requested_role: memberForm.tenant_role,
          reason: memberForm.reason.trim(),
        })
        ElMessage.success(t('tenant.invitation_sent'))
        closeMemberDialog()
        await loadApplications()
        return
      }
      const datasourceIds = boundDatasourceId.value ? [boundDatasourceId.value] : []
      const payload = {
        member_remark: memberForm.member_remark.trim(),
        tenant_role: memberForm.tenant_role,
        project_ids: datasourceIds,
        project_role_map: buildDatasourceRoleMap(datasourceIds, memberForm.project_role_map),
      }
      const saved = await tenantApi.updateMember(editingUserId.value, payload)
      await syncUserPermissionStrategies(saved?.user_id || editingUserId.value)
      ElMessage.success(t('common.save_success'))
      closeMemberDialog()
      await loadMembers()
    } finally {
      memberSubmitting.value = false
    }
  })
}

const openBulkInviteDialog = () => {
  Object.assign(bulkForm, {
    accountsText: '',
    tenant_role: 'member',
    reason: '',
  })
  bulkResults.value = []
  bulkDialogVisible.value = true
}

const closeBulkInviteDialog = () => {
  bulkDialogVisible.value = false
}

const parseBulkAccounts = () =>
  bulkForm.accountsText
    .split(/[\n,;]+/)
    .map((item) => item.trim())
    .filter(Boolean)

const submitBulkInvite = async () => {
  const accounts = Array.from(new Set(parseBulkAccounts()))
  if (!accounts.length) {
    ElMessage.warning(t('tenant.bulk_invite_accounts_required'))
    return
  }
  bulkSubmitting.value = true
  try {
    const results = await tenantApi.bulkInvite({
      accounts,
      requested_role: bulkForm.tenant_role,
      reason: bulkForm.reason.trim(),
    })
    bulkResults.value = results || []
    const created = bulkResults.value.filter((item) => item.status === 'created').length
    ElMessage.success(t('tenant.bulk_invite_finished', { created, total: bulkResults.value.length }))
    await loadApplications()
  } finally {
    bulkSubmitting.value = false
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
    await Promise.all([loadApplications(), loadMembers()])
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
    await loadApplications()
  } finally {
    inviteCancelingId.value = ''
  }
}

const removeMember = async (row: TenantMemberInfo) => {
  if (!canRemoveMember(row)) return
  await ElMessageBox.confirm(t('user.remove_member_confirm', { msg: row.name || row.account }), {
    confirmButtonType: 'danger',
    confirmButtonText: t('project.remove'),
    cancelButtonText: t('common.cancel'),
    customClass: 'confirm-no_icon',
    autofocus: false,
  })
  await tenantApi.removeMember(row.user_id)
  ElMessage.success(t('common.operation_success'))
  await loadMembers()
}

onMounted(() => {
  if (isPurePlatformAdmin.value) return
  loadMembers()
  loadApplications()
})
</script>

<style lang="less" scoped>
.tenant-members-container {
  width: 100%;
  height: 100%;
  position: relative;
  color-scheme: light;
  display: flex;
  flex-direction: column;
  min-height: 0;

  .tool-left {
    flex: 0 0 auto;
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

  .member-search {
    width: 240px;
  }

  .button-badge {
    min-width: 18px;
    height: 18px;
    padding: 0 5px;
    margin-left: 6px;
    border-radius: 999px;
    background: #f54a45;
    color: #fff;
    box-shadow: 0 6px 14px rgba(245, 74, 69, 0.24);
    font-size: 12px;
    line-height: 18px;
    font-weight: 600;
  }

  .member-content-stack {
    min-width: 0;
    min-height: 0;
    flex: 1 1 auto;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .member-panel {
    min-width: 0;
    border: 1px solid #dee0e3;
    border-radius: 8px;
    background: #fff;
    overflow: hidden;
    flex: 1 1 0;
    min-height: 0;
    display: flex;
    flex-direction: column;
  }

  .member-table {
    flex: 1 1 auto;
    min-height: 0;
  }

  .member-table,
  .invitation-table {
    :deep(.ed-table__inner-wrapper),
    :deep(.ed-table__body-wrapper),
    :deep(.ed-scrollbar),
    :deep(.ed-scrollbar__wrap) {
      min-height: 0;
    }
  }

  .invitation-panel {
    flex: 1 1 0;
  }

  .panel-header {
    min-height: 48px;
    padding: 0 16px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 1px solid #dee0e3;
    background: #f8f9fa;
  }

  .panel-title {
    display: flex;
    align-items: center;
    gap: 8px;
    color: #1f2329;
    font-size: 14px;
    font-weight: 600;
  }

  .panel-count {
    min-width: 20px;
    height: 20px;
    padding: 0 6px;
    border-radius: 999px;
    background: #f54a45;
    color: #fff;
    box-shadow: 0 6px 14px rgba(245, 74, 69, 0.24);
    font-size: 12px;
    line-height: 20px;
    text-align: center;
    font-weight: 600;
  }

  .invitation-table {
    flex: 1 1 auto;
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

  .table-operate,
  .review-actions {
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .role-text {
    font-size: 14px;
    font-weight: 500;
    line-height: 22px;

    &.is-tenant-owner {
      color: #8f3f11;
    }

    &.is-tenant-admin {
      color: #245bdb;
    }

    &.is-tenant-member {
      color: #646a73;
      font-weight: 400;
    }
  }
}

.bulk-result-table {
  margin-top: 12px;
  max-height: 240px;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: #b8c4d6 #f2f5f9;
}

.access-review-dialog {
  .access-table {
    max-height: 520px;
    overflow-y: auto;
  }
}
</style>

<style lang="less">
.tenant-member-drawer {
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
  .datasource-permission-panel {
    color: #1f2329 !important;
  }

  .datasource-permission-panel {
    width: 100%;
    border: 1px solid #dee0e3;
    border-radius: 6px;
    overflow: hidden;
    background: #fff;

    .datasource-permission-toolbar {
      min-height: 48px;
      padding: 8px 12px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      border-bottom: 1px solid #dee0e3;
      background: #f8f9fa;
    }

    .datasource-permission-count {
      color: #646a73;
      font-size: 13px;
      white-space: nowrap;
    }

    .datasource-cell {
      min-width: 0;
    }

    .datasource-name {
      font-weight: 500;
      color: #1f2329;
      line-height: 22px;
    }

    .datasource-type,
    .database-label,
    .muted {
      color: #8f959e;
      font-size: 12px;
      line-height: 20px;
    }

    .database-label {
      display: inline-block;
      max-width: 150px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .permission-summary {
      min-height: 24px;
      display: flex;
      flex-direction: column;
      align-items: flex-start;
      gap: 4px;
    }

    .summary-line {
      max-width: 100%;
      color: #646a73;
      font-size: 12px;
      line-height: 18px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
  }

  .permission-option {
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;

    .permission-option-name {
      max-width: 150px;
    }

    .permission-option-summary {
      color: #8f959e;
      font-size: 12px;
      white-space: nowrap;
    }
  }
}

.tenant-light-popper,
.tenant-light-popper.ed-popper,
.tenant-light-popper .ed-select-dropdown,
.tenant-light-popper .ed-scrollbar,
.tenant-light-popper .ed-scrollbar__wrap,
.tenant-light-popper .ed-scrollbar__view {
  color-scheme: light;
  background-color: #fff !important;
  color: #1f2329 !important;
  border-color: #dee0e3 !important;
}

.tenant-light-popper .ed-select-dropdown__item {
  background-color: #fff !important;
  color: #1f2329 !important;
}

.tenant-light-popper .ed-select-dropdown__item.hover,
.tenant-light-popper .ed-select-dropdown__item:hover {
  background-color: #f5f6f7 !important;
  color: #1f2329 !important;
}

.tenant-light-popper .ed-select-dropdown__item.selected {
  color: #336df4 !important;
  background-color: #eef3ff !important;
}

.tenant-light-popper .ed-popper__arrow::before {
  background-color: #fff !important;
  border-color: #dee0e3 !important;
}
</style>
