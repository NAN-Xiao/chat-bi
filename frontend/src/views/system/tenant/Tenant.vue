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

    <div class="section-title">{{ t('tenant.workspace_list') }}</div>
    <el-table :data="filteredTenants" class="tenant-table" style="width: 100%">
      <el-table-column prop="name" :label="t('tenant.name')" min-width="180" show-overflow-tooltip />
      <el-table-column prop="code" :label="t('tenant.code')" min-width="140" show-overflow-tooltip />
      <el-table-column prop="plan" :label="t('tenant.plan')" width="140">
        <template #default="scope">
          <el-tag size="small" type="info">{{ formatPlan(scope.row.plan) }}</el-tag>
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
import { tenantApi, type TenantApplicationInfo, type TenantInfo } from '@/api/tenant'
import { formatTimestamp } from '@/utils/date'
import { useUserStore } from '@/stores/user'

const { t } = useI18n()
const userStore = useUserStore()
const keyword = ref('')
const drawerVisible = ref(false)
const saving = ref(false)
const statusLoadingId = ref('')
const reviewLoadingId = ref('')
const formRef = ref()
const tenants = shallowRef<TenantInfo[]>([])
const applications = shallowRef<TenantApplicationInfo[]>([])
const defaultForm = {
  id: '',
  code: '',
  name: '',
  plan: 'default',
}
const form = reactive({ ...defaultForm })

const planOptions = computed(() => [
  { value: 'default', label: t('tenant.plan_default') },
  { value: 'basic', label: t('tenant.plan_basic') },
  { value: 'enterprise', label: t('tenant.plan_enterprise') },
])

const rules = computed(() => ({
  name: [{ required: true, message: t('tenant.name_required'), trigger: 'blur' }],
  code: [{ required: true, message: t('tenant.code_required'), trigger: 'blur' }],
  plan: [{ required: true, message: t('tenant.plan_required'), trigger: 'change' }],
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

const formatRequestedRole = (role?: string) =>
  role === 'admin' ? t('tenant.request_role_admin') : t('tenant.request_role_owner')

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

const loadTenants = async () => {
  tenants.value = await tenantApi.adminList()
}

const loadApplications = async () => {
  applications.value = await tenantApi.adminApplications()
}

const openDrawer = (tenant: TenantInfo | null) => {
  Object.assign(form, {
    ...defaultForm,
    ...(tenant || {}),
    id: tenant?.id ? String(tenant.id) : '',
    plan: tenant?.plan || 'default',
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
      if (form.id) {
        await tenantApi.edit(form.id, {
          name: form.name,
          plan: form.plan,
        })
      } else {
        await tenantApi.add({
          code: form.code,
          name: form.name,
          plan: form.plan,
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

onMounted(() => {
  loadTenants()
  loadApplications()
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
