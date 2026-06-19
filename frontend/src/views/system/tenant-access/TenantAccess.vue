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
        <el-button secondary @click="openBulkAddDialog">{{ t('tenant.bulk_add_members') }}</el-button>
        <el-button type="primary" @click="openAddDialog">
          <template #icon>
            <icon_add_outlined />
          </template>
          {{ t('tenant.add_user') }}
        </el-button>
      </div>
    </div>

    <section class="member-panel">
      <el-table
        v-loading="memberLoading"
        :data="memberRows"
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
            {{ formatProjectAccess(scope.row) }}
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
    </section>

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
        <el-form-item :label="t('tenant.member_remark')">
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
        <el-form-item :label="t('user.project_permission_config')">
          <div class="project-permission-panel">
            <div class="project-permission-toolbar">
              <el-select
                v-model="memberForm.project_ids"
                multiple
                filterable
                collapse-tags
                collapse-tags-tooltip
                popper-class="tenant-light-popper"
                style="width: 420px"
                :placeholder="t('user.select_accessible_projects')"
                @change="handleProjectIdsChange"
              >
                <el-option
                  v-for="item in projectOptions"
                  :key="item.id"
                  :label="item.name"
                  :value="Number(item.id)"
                />
              </el-select>
              <span class="project-permission-count">
                {{ t('user.selected_project_count', { msg: selectedProjectRows.length }) }}
              </span>
            </div>

            <el-table
              :data="selectedProjectRows"
              :empty-text="t('user.no_project_permission')"
              class="project-permission-table"
              style="width: 100%"
            >
              <el-table-column :label="t('permission.data_source')" min-width="160">
                <template #default="scope">
                  <div class="project-cell">
                    <div class="project-name ellipsis" :title="scope.row.name">
                      {{ scope.row.name }}
                    </div>
                    <div class="project-type ellipsis" :title="scope.row.type_name || scope.row.type">
                      {{ scope.row.type_name || scope.row.type || '-' }}
                    </div>
                  </div>
                </template>
              </el-table-column>
              <el-table-column :label="t('user.database_scope')" min-width="150">
                <template #default="scope">
                  <span class="database-label" :title="formatProjectDatabase(scope.row)">
                    {{ formatProjectDatabase(scope.row) }}
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
                      v-for="item in projectRoleOptions"
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
                      v-for="item in getPermissionStrategiesByProject(scope.row.id)"
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
                    <template v-if="getSelectedStrategiesByProject(scope.row.id).length">
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
              <el-table-column :label="t('ds.actions')" width="76" fixed="right">
                <template #default="scope">
                  <el-button text @click="removeProjectAccess(scope.row.id)">
                    {{ t('project.remove') }}
                  </el-button>
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
            {{ t('common.save') }}
          </el-button>
        </div>
      </template>
    </el-drawer>

    <el-dialog
      v-model="bulkDialogVisible"
      class="workspace-light-dialog"
      :title="t('tenant.bulk_add_members')"
      width="560"
      :before-close="closeBulkAddDialog"
    >
      <el-form label-position="top" class="form-content_error" @submit.prevent>
        <el-form-item :label="t('tenant.bulk_member_accounts')">
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
      </el-form>
      <el-table v-if="bulkResults.length" :data="bulkResults" class="bulk-result-table">
        <el-table-column prop="account" :label="t('user.account')" min-width="160" show-overflow-tooltip />
        <el-table-column prop="status" :label="t('tenant.status')" width="110">
          <template #default="scope">
            <el-tag size="small" :type="scope.row.status === 'created' ? 'success' : 'danger'">
              {{ scope.row.status === 'created' ? t('tenant.member_added') : t('tenant.member_add_failed') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="message" :label="t('tenant.review_comment')" min-width="180" show-overflow-tooltip />
      </el-table>
      <template #footer>
        <div class="dialog-footer">
          <el-button secondary @click="closeBulkAddDialog">{{ t('common.cancel') }}</el-button>
          <el-button type="primary" :loading="bulkSubmitting" @click="submitBulkAdd">
            {{ t('tenant.add_members') }}
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
import { computed, onMounted, reactive, ref, shallowRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus-secondary'
import icon_add_outlined from '@/assets/svg/icon_add_outlined.svg'
import icon_searchOutline_outlined from '@/assets/svg/icon_search-outline_outlined.svg'
import EmptyBackground from '@/views/dashboard/common/EmptyBackground.vue'
import {
  tenantApi,
  type TenantApplicationInfo,
  type TenantBulkMemberResult,
  type TenantMemberInfo,
} from '@/api/tenant'
import { datasourceApi } from '@/api/datasource'
import { getList as getPermissionList, savePermissions } from '@/api/permissions'
import { decrypted } from '@/views/ds/js/aes'
import { formatTimestamp } from '@/utils/date'
import { useUserStore } from '@/stores/user'

const { t } = useI18n()
const userStore = useUserStore()
const keyword = ref('')
const memberLoading = ref(false)
const applicationLoading = ref(false)
const memberSubmitting = ref(false)
const bulkSubmitting = ref(false)
const memberDialogVisible = ref(false)
const bulkDialogVisible = ref(false)
const reviewDialogVisible = ref(false)
const memberFormRef = ref()
const memberDialogMode = ref<'add' | 'edit'>('add')
const editingUserId = ref<number | string>('')
const joinReviewLoadingId = ref('')
const inviteCancelingId = ref('')
const memberRows = shallowRef<TenantMemberInfo[]>([])
const joinApplications = shallowRef<TenantApplicationInfo[]>([])
const invitations = shallowRef<TenantApplicationInfo[]>([])
const projectOptions = shallowRef<any[]>([])
const permissionRuleGroups = shallowRef<any[]>([])
const bulkResults = shallowRef<TenantBulkMemberResult[]>([])

const memberForm = reactive({
  account: '',
  member_remark: '',
  tenant_role: 'member' as 'admin' | 'member',
  project_ids: [] as number[],
  project_role_map: {} as Record<number, string>,
  project_permission_map: {} as Record<number, number[]>,
})

const bulkForm = reactive({
  accountsText: '',
  tenant_role: 'member' as 'admin' | 'member',
})

const tenantRoleOptions = computed(() => [
  { value: 'member', label: t('user.tenant_role_member') },
  { value: 'admin', label: t('user.tenant_role_admin') },
])

const projectRoleOptions = computed(() => [
  { value: 'viewer', label: t('datasource.project_role_viewer') },
  { value: 'editor', label: t('datasource.project_role_editor') },
])

const memberDialogTitle = computed(() =>
  memberDialogMode.value === 'edit' ? t('tenant.edit_member') : t('tenant.add_user')
)

const accessRequests = computed(() =>
  [...joinApplications.value, ...invitations.value].sort(
    (a, b) => Number(b.create_time || 0) - Number(a.create_time || 0)
  )
)

const pendingReviewCount = computed(() => accessRequests.value.filter((item) => item.status === 'pending').length)

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

const normalizeProjectRole = (role: any) => {
  const value = String(role || '').trim().toLowerCase()
  return value === 'editor' ? 'editor' : 'viewer'
}

const buildProjectRoleMap = (projectIds: number[], value: any = {}) => {
  const source = parseJsonValue(value, {})
  const result: Record<number, string> = {}
  projectIds.forEach((id: number) => {
    result[id] = normalizeProjectRole(source?.[id] || source?.[String(id)])
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

const formatApplicationType = (type?: string) => {
  if (type === 'invite') return t('tenant.application_type_invite')
  return t('tenant.application_type_join')
}

const formatProjectAccess = (row: TenantMemberInfo) => {
  const ids = toNumberList(row.project_ids)
  if (!ids.length) return t('tenant.no_project_access_short')
  const names = projectOptions.value
    .filter((item: any) => ids.includes(Number(item.id)))
    .map((item: any) => item.name)
  if (!names.length) return t('tenant.project_count', { msg: ids.length })
  return names.length > 3
    ? t('tenant.project_access_summary_more', { msg: names.slice(0, 3).join('、'), count: names.length - 3 })
    : names.join('、')
}

const selectedProjectRows = computed(() => {
  const ids = toNumberList(memberForm.project_ids)
  return projectOptions.value.filter((item: any) => ids.includes(Number(item.id)))
})

const getProjectIdsFromRule = (rule: any): number[] => {
  const ids = (rule.permissions || [])
    .map((item: any) => Number(item.ds_id))
    .filter((item: number) => !Number.isNaN(item))
  return Array.from(new Set<number>(ids))
}

const getPermissionStrategiesByProject = (projectId: any) => {
  const id = Number(projectId)
  return permissionRuleGroups.value.filter((rule: any) => getProjectIdsFromRule(rule).includes(id))
}

const getSelectedStrategiesByProject = (projectId: any) => {
  const id = Number(projectId)
  const selectedIds = toNumberList(memberForm.project_permission_map?.[id])
  return getPermissionStrategiesByProject(id).filter((rule: any) =>
    selectedIds.includes(Number(rule.id))
  )
}

const formatRuleGroupSummary = (rule: any, projectId?: any) => {
  const id = Number(projectId)
  const permissions = projectId
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

const getRuleProjectPermissions = (rule: any, projectId: any) => {
  const id = Number(projectId)
  return (rule.permissions || []).filter((item: any) => Number(item.ds_id) === id)
}

const formatTableAccessSummary = (projectId: any) => {
  const tableNames = new Set<string>()
  getSelectedStrategiesByProject(projectId).forEach((rule: any) => {
    getRuleProjectPermissions(rule, projectId).forEach((permission: any) => {
      if (permission.table_name) tableNames.add(permission.table_name)
    })
  })
  if (!tableNames.size) return t('user.all_project_tables')
  const names = Array.from(tableNames)
  return names.length > 3
    ? t('user.allowed_table_summary_more', { msg: names.slice(0, 3).join('、'), count: names.length - 3 })
    : t('user.allowed_table_summary', { msg: names.join('、') })
}

const formatFieldAccessSummary = (projectId: any) => {
  let restrictedCount = 0
  getSelectedStrategiesByProject(projectId).forEach((rule: any) => {
    getRuleProjectPermissions(rule, projectId).forEach((permission: any) => {
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

const formatRowAccessSummary = (projectId: any) => {
  let rowCount = 0
  getSelectedStrategiesByProject(projectId).forEach((rule: any) => {
    rowCount += getRuleProjectPermissions(rule, projectId).filter((item: any) => item.type === 'row').length
  })
  return rowCount ? t('user.row_filter_summary', { msg: rowCount }) : t('user.no_row_filter')
}

const formatProjectDatabase = (project: any) => {
  if (!project?.configuration) return project?.type_name || project?.type || '-'
  try {
    const conf = JSON.parse(decrypted(project.configuration) || '{}')
    const database = conf.database || conf.dataBase || conf.filename || project.name
    const schema = conf.dbSchema || conf.schema
    const host = conf.host && conf.port ? `${conf.host}:${conf.port}` : conf.host
    return [database, schema, host].filter(Boolean).join(' / ') || project.name
  } catch (e) {
    return project?.name || '-'
  }
}

const handleProjectIdsChange = (value: any[]) => {
  const ids = toNumberList(value)
  memberForm.project_ids = ids
  const nextMap: Record<number, number[]> = {}
  ids.forEach((id: number) => {
    nextMap[id] = toNumberList(memberForm.project_permission_map?.[id])
  })
  memberForm.project_permission_map = nextMap
  memberForm.project_role_map = buildProjectRoleMap(ids, memberForm.project_role_map)
}

const removeProjectAccess = (projectId: any) => {
  const id = Number(projectId)
  memberForm.project_ids = toNumberList(memberForm.project_ids).filter((item: number) => item !== id)
  const nextMap = { ...(memberForm.project_permission_map || {}) }
  delete nextMap[id]
  memberForm.project_permission_map = nextMap
  const nextRoleMap = { ...(memberForm.project_role_map || {}) }
  delete nextRoleMap[id]
  memberForm.project_role_map = nextRoleMap
}

const buildUserProjectPermissionMap = (userId: any, projectIds: number[]) => {
  const result: Record<number, number[]> = {}
  projectIds.forEach((id: number) => {
    result[id] = []
  })
  if (!userId) return result

  permissionRuleGroups.value.forEach((rule: any) => {
    const users = toNumberList(rule.users || rule.user_list)
    if (!users.includes(Number(userId))) return
    getProjectIdsFromRule(rule).forEach((projectId: number) => {
      if (!projectIds.includes(projectId)) return
      result[projectId] = Array.from(new Set<number>([...(result[projectId] || []), Number(rule.id)]))
    })
  })
  return result
}

const serializePermissionRule = (rule: any, users: number[]) => ({
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
  const selectedRuleIds = new Set(
    Object.values(memberForm.project_permission_map || {})
      .flatMap((item: any) => toNumberList(item))
      .map((item: number) => Number(item))
  )
  const requests: Promise<any>[] = []

  permissionRuleGroups.value.forEach((rule: any) => {
    if (!getProjectIdsFromRule(rule).length) return
    const currentUsers = toNumberList(rule.users || rule.user_list)
    const shouldInclude = selectedRuleIds.has(Number(rule.id))
    const nextUsers = shouldInclude
      ? Array.from(new Set<number>([...currentUsers, Number(userId)]))
      : currentUsers.filter((item: number) => item !== Number(userId))
    const changed =
      nextUsers.length !== currentUsers.length ||
      nextUsers.some((item: number) => !currentUsers.includes(item))
    if (!changed) return
    rule.users = nextUsers
    requests.push(savePermissions(serializePermissionRule(rule, nextUsers)))
  })

  return Promise.all(requests).then(() => undefined)
}

const loadProjectOptions = async () => {
  const [projects, permissions] = await Promise.all([datasourceApi.accessibleList(), getPermissionList()])
  projectOptions.value = projects || []
  permissionRuleGroups.value = permissions || []
}

const loadMembers = async () => {
  memberLoading.value = true
  try {
    const [members] = await Promise.all([tenantApi.members(keyword.value.trim()), loadProjectOptions()])
    memberRows.value = members || []
  } finally {
    memberLoading.value = false
  }
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

const handleSearch = ($event: any = {}) => {
  if ($event?.isComposing) return
  loadMembers()
}

const resetMemberForm = () => {
  Object.assign(memberForm, {
    account: '',
    member_remark: '',
    tenant_role: 'member',
    project_ids: [],
    project_role_map: {},
    project_permission_map: {},
  })
  editingUserId.value = ''
}

const openAddDialog = async () => {
  memberDialogMode.value = 'add'
  resetMemberForm()
  await loadProjectOptions()
  memberDialogVisible.value = true
}

const openEditDialog = async (row: TenantMemberInfo) => {
  if (!canEditMember(row)) {
    ElMessage.warning(t('user.only_platform_admin_manage_owner'))
    return
  }
  memberDialogMode.value = 'edit'
  await loadProjectOptions()
  const projectIds = toNumberList(row.project_ids)
  Object.assign(memberForm, {
    account: row.account,
    member_remark: row.member_remark || '',
    tenant_role: normalizeTenantRole(row.tenant_role) === 'admin' ? 'admin' : 'member',
    project_ids: projectIds,
    project_role_map: buildProjectRoleMap(projectIds, row.project_role_map),
    project_permission_map: buildUserProjectPermissionMap(row.user_id, projectIds),
  })
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
      const projectIds = toNumberList(memberForm.project_ids)
      const payload = {
        member_remark: memberForm.member_remark.trim(),
        tenant_role: memberForm.tenant_role,
        project_ids: projectIds,
        project_role_map: buildProjectRoleMap(projectIds, memberForm.project_role_map),
      }
      const saved =
        memberDialogMode.value === 'edit'
          ? await tenantApi.updateMember(editingUserId.value, payload)
          : await tenantApi.addMember({ account: memberForm.account.trim(), ...payload })
      await syncUserPermissionStrategies(saved.user_id)
      ElMessage.success(t('common.save_success'))
      closeMemberDialog()
      await loadMembers()
    } finally {
      memberSubmitting.value = false
    }
  })
}

const openBulkAddDialog = () => {
  Object.assign(bulkForm, {
    accountsText: '',
    tenant_role: 'member',
  })
  bulkResults.value = []
  bulkDialogVisible.value = true
}

const closeBulkAddDialog = () => {
  bulkDialogVisible.value = false
}

const parseBulkAccounts = () =>
  bulkForm.accountsText
    .split(/[\n,;]+/)
    .map((item) => item.trim())
    .filter(Boolean)

const submitBulkAdd = async () => {
  const accounts = Array.from(new Set(parseBulkAccounts()))
  if (!accounts.length) {
    ElMessage.warning(t('tenant.bulk_member_accounts_required'))
    return
  }
  bulkSubmitting.value = true
  try {
    const results = await tenantApi.bulkAddMembers({
      accounts,
      tenant_role: bulkForm.tenant_role,
    })
    bulkResults.value = results || []
    const created = bulkResults.value.filter((item) => item.status === 'created').length
    ElMessage.success(t('tenant.bulk_add_finished', { created, total: bulkResults.value.length }))
    await loadMembers()
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
    font-size: 12px;
    line-height: 18px;
  }

  .member-panel {
    min-width: 0;
    border: 1px solid #dee0e3;
    border-radius: 8px;
    background: #fff;
    overflow: hidden;
  }

  .member-table {
    max-height: calc(100vh - 150px);
    overflow-y: auto;
    scrollbar-width: thin;
    scrollbar-color: #b8c4d6 #f2f5f9;
  }

  .member-table::-webkit-scrollbar {
    width: 10px;
    height: 10px;
  }

  .member-table::-webkit-scrollbar-track {
    background: #f2f5f9;
    border-radius: 999px;
  }

  .member-table::-webkit-scrollbar-thumb {
    background: #b8c4d6;
    border-radius: 999px;
    border: 2px solid #f2f5f9;
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

  .project-permission-panel {
    width: 100%;
    border: 1px solid #dee0e3;
    border-radius: 6px;
    overflow: hidden;
    background: #fff;
    color: #1f2329;

    .project-permission-toolbar {
      min-height: 48px;
      padding: 8px 12px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      border-bottom: 1px solid #dee0e3;
      background: #f8f9fa;
    }

    .project-permission-count {
      color: #646a73;
      font-size: 13px;
      white-space: nowrap;
    }

    .project-permission-table {
      .ed-table__cell {
        vertical-align: top;
      }
    }

    .project-cell {
      min-width: 0;
    }

    .project-name {
      font-weight: 500;
      color: #1f2329;
      line-height: 22px;
    }

    .project-type,
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
