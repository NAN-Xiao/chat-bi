<template>
  <div class="tenant-access-container professional-container">
    <div class="tool-left">
      <span class="page-title">{{ t('tenant.member_access') }}</span>
      <div class="toolbar">
        <el-button secondary @click="loadAccessRequests">{{ t('common.refresh') }}</el-button>
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
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, shallowRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus-secondary'
import icon_add_outlined from '@/assets/svg/icon_add_outlined.svg'
import EmptyBackground from '@/views/dashboard/common/EmptyBackground.vue'
import { tenantApi, type TenantApplicationInfo } from '@/api/tenant'

const { t } = useI18n()
const inviteDialogVisible = ref(false)
const inviteFormRef = ref()
const inviteSubmitting = ref(false)
const joinReviewLoadingId = ref('')
const inviteCancelingId = ref('')
const joinApplications = shallowRef<TenantApplicationInfo[]>([])
const invitations = shallowRef<TenantApplicationInfo[]>([])

const inviteForm = reactive({
  account: '',
  requested_role: 'member' as 'admin' | 'member',
  reason: '',
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

const formatRequestedRole = (role?: string) => {
  if (role === 'owner') return t('tenant.request_role_owner')
  if (role === 'admin') return t('tenant.request_role_admin')
  return t('tenant.request_role_member')
}

const loadAccessRequests = async () => {
  const [joinRows, invitationRows] = await Promise.all([
    tenantApi.tenantApplications('pending'),
    tenantApi.invitations('pending'),
  ])
  joinApplications.value = joinRows || []
  invitations.value = invitationRows || []
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
  }
}
</style>
