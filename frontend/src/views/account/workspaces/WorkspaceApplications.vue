<template>
  <div class="my-workspaces professional-container">
    <div class="workspace-application-panel">
      <div v-if="allowModeSwitch" class="workspace-mode-bar">
        <el-radio-group
          v-model="applicationMode"
          class="application-mode"
          @change="changeApplicationMode"
        >
          <el-radio-button label="create">{{ t('tenant.application_type_create') }}</el-radio-button>
          <el-radio-button label="join">{{ t('tenant.application_type_join') }}</el-radio-button>
        </el-radio-group>
      </div>

      <div class="workspace-grid">
        <section class="workspace-section application-section">
          <el-form
            ref="applicationFormRef"
            :model="applicationForm"
            :rules="applicationRules"
            label-position="top"
            class="form-content_error"
            @submit.prevent
          >
            <el-form-item
              v-if="applicationMode === 'create'"
              prop="tenant_name"
              :label="t('tenant.name')"
            >
              <el-input
                v-model="applicationForm.tenant_name"
                maxlength="255"
                clearable
              />
            </el-form-item>
            <el-form-item
              v-if="applicationMode === 'join'"
              prop="tenant_code"
              :label="t('tenant.workspace_search_label')"
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
                    {{ t('tenant.search_workspace') }}
                  </el-button>
                </template>
              </el-input>
              <div
                v-if="applicationMode === 'join' && tenantSearchResults.length"
                class="tenant-search-results"
              >
                <div
                  v-for="tenant in tenantSearchResults"
                  :key="tenant.id"
                  class="tenant-search-result"
                >
                  <div class="tenant-search-main">
                    <span class="tenant-search-name">{{ tenant.name }}</span>
                    <span class="tenant-search-code">{{ tenant.code }}</span>
                  </div>
                  <el-button
                    v-if="!tenant.already_joined"
                    type="primary"
                    @click="openJoinReasonDialog(tenant)"
                  >
                    {{ t('tenant.apply_join_workspace') }}
                  </el-button>
                  <span v-else class="tenant-search-state">{{ t('tenant.already_joined') }}</span>
                </div>
              </div>
              <div
                v-else-if="applicationMode === 'join' && hasSearched && !tenantSearchLoading"
                class="tenant-search-empty"
              >
                {{ t('tenant.no_search_workspace_results') }}
              </div>
            </el-form-item>
            <el-form-item v-if="applicationMode === 'create'" :label="t('tenant.apply_reason')">
              <el-input
                v-model="applicationForm.reason"
                type="textarea"
                maxlength="2000"
                :rows="4"
                show-word-limit
              />
            </el-form-item>
            <div v-if="applicationMode === 'create'" class="form-actions">
              <el-button type="primary" :loading="applicationSubmitting" @click="submitApplication">
                {{ t('common.confirm') }}
              </el-button>
            </div>
          </el-form>
        </section>
      </div>
    </div>

    <el-dialog
      v-model="joinReasonDialogVisible"
      class="workspace-light-dialog join-reason-dialog"
      :title="t('tenant.apply_join_workspace')"
      width="520"
      destroy-on-close
    >
      <div v-if="selectedTenantTarget" class="join-target-summary">
        <div class="join-target-name">{{ selectedTenantTarget.name }}</div>
        <div class="join-target-code">{{ selectedTenantTarget.code }}</div>
      </div>
      <el-form label-position="top" class="form-content_error" @submit.prevent>
        <el-form-item :label="t('tenant.apply_reason')">
          <el-input
            v-model="joinReason"
            type="textarea"
            maxlength="2000"
            :rows="4"
            show-word-limit
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button secondary @click="closeJoinReasonDialog">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="applicationSubmitting" @click="submitJoinApplication">
          {{ t('common.confirm') }}
        </el-button>
      </template>
    </el-dialog>
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
const hasSearched = ref(false)
const joinReasonDialogVisible = ref(false)
const joinReason = ref('')
const selectedTenantTarget = shallowRef<TenantSearchInfo | null>(null)
const tenantSearchResults = shallowRef<TenantSearchInfo[]>([])
const allowModeSwitch = computed(() => props.allowSwitch)

const applicationForm = reactive({
  tenant_id: '',
  tenant_code: '',
  tenant_name: '',
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
}))

const resetApplicationForm = () => {
  tenantSearchResults.value = []
  hasSearched.value = false
  closeJoinReasonDialog()
  Object.assign(applicationForm, {
    tenant_id: '',
    tenant_code: '',
    tenant_name: '',
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

const openJoinReasonDialog = (tenant: TenantSearchInfo) => {
  applicationForm.tenant_id = String(tenant.id || '')
  applicationForm.tenant_code = tenant.code || String(tenant.id || '')
  applicationForm.tenant_name = tenant.name || tenant.code || ''
  selectedTenantTarget.value = tenant
  joinReason.value = ''
  joinReasonDialogVisible.value = true
}

const closeJoinReasonDialog = () => {
  joinReasonDialogVisible.value = false
  selectedTenantTarget.value = null
  joinReason.value = ''
}

const searchTenantTargets = async () => {
  const keyword = applicationForm.tenant_code.trim()
  if (!keyword) return
  tenantSearchLoading.value = true
  hasSearched.value = true
  applicationForm.tenant_id = ''
  applicationForm.tenant_name = ''
  try {
    tenantSearchResults.value = await tenantApi.search(keyword)
  } finally {
    tenantSearchLoading.value = false
  }
}

const submitJoinApplication = async () => {
  if (!selectedTenantTarget.value || !applicationForm.tenant_id) {
    ElMessage.warning(t('tenant.search_tenant_first'))
    return
  }
  applicationSubmitting.value = true
  try {
    await tenantApi.submitApplication({
      application_type: 'join',
      tenant_id: applicationForm.tenant_id,
      reason: joinReason.value,
    })
    ElMessage.success(t('tenant.join_application_submitted'))
    closeJoinReasonDialog()
    resetApplicationForm()
    applicationMode.value = 'join'
  } finally {
    applicationSubmitting.value = false
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
      }
      ElMessage.success(t('tenant.application_submitted'))
      resetApplicationForm()
      applicationMode.value = mode
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

  .workspace-application-panel {
    width: min(100%, 860px);
  }

  .workspace-mode-bar {
    display: flex;
    align-items: center;
    margin-bottom: 10px;
  }

  .workspace-grid {
    display: grid;
    grid-template-columns: minmax(0, 860px);
  }

  .workspace-section {
    min-width: 0;
    border: 1px solid #dee0e3;
    border-radius: 8px;
    background: #fff;
  }

  .application-section {
    padding: 16px;

    .ed-form {
      width: 100%;
    }
  }

  .application-mode {
    flex-shrink: 0;
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
    padding: 10px 12px;
    display: flex;
    align-items: center;
    gap: 12px;
    border: 1px solid #dee0e3;
    border-radius: 6px;
    background: #fff;
    color: #1f2329;
    text-align: left;
  }

  .tenant-search-result:hover {
    border-color: var(--ed-color-primary);
    background: #eef3ff;
  }

  .tenant-search-main {
    flex: 1;
    min-width: 0;
    display: grid;
    gap: 2px;
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
    flex-shrink: 0;
  }

  .tenant-search-empty {
    margin-top: 8px;
    padding: 10px 12px;
    border-radius: 6px;
    background: #f7f8fa;
    color: #86909c;
    font-size: 13px;
    line-height: 20px;
  }

  .join-target-summary {
    margin-bottom: 16px;
    padding: 10px 12px;
    border: 1px solid #dee0e3;
    border-radius: 6px;
    background: #f7f8fa;
  }

  .join-target-name {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: #1f2329;
    font-size: 14px;
    line-height: 20px;
    font-weight: 500;
  }

  .join-target-code {
    margin-top: 2px;
    color: #8f959e;
    font-size: 12px;
    line-height: 18px;
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
