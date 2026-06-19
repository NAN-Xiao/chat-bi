<template>
  <div class="my-workspaces professional-container">
    <div class="page-head">
      <div>
        <div class="page-title">{{ pageTitle }}</div>
        <div class="page-subtitle">{{ pageHint }}</div>
      </div>
    </div>

    <div class="workspace-grid">
      <section class="workspace-section application-section">
        <div class="section-head">
          <span>{{ pageTitle }}</span>
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
            v-if="allowModeSwitch"
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
          <el-form-item
            v-if="applicationMode === 'join'"
            prop="tenant_code"
            :label="t('tenant.code')"
          >
            <el-input
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
                <span class="tenant-search-code">{{ tenant.code }}</span>
                <span v-if="tenant.already_joined" class="tenant-search-state">
                  {{ t('tenant.already_joined') }}
                </span>
              </button>
            </div>
          </el-form-item>
          <el-form-item
            v-if="applicationMode === 'join'"
            prop="requested_role"
            :label="t('tenant.requested_role')"
          >
            <el-input :model-value="t('tenant.request_role_member')" disabled style="width: 240px" />
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
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, shallowRef, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus-secondary'
import {
  tenantApi,
  type TenantSearchInfo,
} from '@/api/tenant'

const props = withDefaults(
  defineProps<{
    mode?: 'create' | 'join'
    allowSwitch?: boolean
  }>(),
  {
    mode: 'create',
    allowSwitch: false,
  }
)

const { t } = useI18n()
const applicationFormRef = ref()
const applicationMode = ref<'create' | 'join'>(props.mode)
const applicationSubmitting = ref(false)
const tenantSearchLoading = ref(false)
const tenantSearchResults = shallowRef<TenantSearchInfo[]>([])
const allowModeSwitch = computed(() => props.allowSwitch)
const pageTitle = computed(() =>
  applicationMode.value === 'join' ? t('tenant.join_workspace') : t('tenant.apply_workspace')
)
const pageHint = computed(() =>
  applicationMode.value === 'join'
    ? t('tenant.join_workspace_hint')
    : t('tenant.workspace_application_hint')
)

const applicationForm = reactive({
  tenant_id: '',
  tenant_code: '',
  tenant_name: '',
  requested_role: 'member',
  reason: '',
})

const applicationRules = computed(() => ({
  tenant_code: [
    {
      required: applicationMode.value === 'join',
      message: t('tenant.code_required'),
      trigger: 'blur',
    },
  ],
  tenant_name: [
    {
      required: applicationMode.value === 'create',
      message: t('tenant.name_required'),
      trigger: 'blur',
    },
  ],
  requested_role: [
    {
      required: applicationMode.value === 'join',
      message: t('tenant.request_role_required'),
      trigger: 'change',
    },
  ],
}))

const resetApplicationForm = () => {
  tenantSearchResults.value = []
  Object.assign(applicationForm, {
    tenant_id: '',
    tenant_code: '',
    tenant_name: '',
    requested_role: 'member',
    reason: '',
  })
}

const changeApplicationMode = () => {
  resetApplicationForm()
}

watch(
  () => props.mode,
  (mode) => {
    applicationMode.value = mode
    resetApplicationForm()
  }
)

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

const submitApplication = () => {
  applicationFormRef.value?.validate(async (valid: boolean) => {
    if (!valid) return
    applicationSubmitting.value = true
    const mode = applicationMode.value
    try {
      if (mode === 'create') {
        await tenantApi.submitApplication({
          application_type: 'create',
          tenant_name: applicationForm.tenant_name,
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
    } finally {
      applicationSubmitting.value = false
    }
  })
}
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
    grid-template-columns: minmax(420px, 760px);
    gap: 16px;
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

}

@media (max-width: 1200px) {
  .my-workspaces {
    .workspace-grid {
      grid-template-columns: 1fr;
    }
  }
}
</style>
