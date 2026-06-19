<script lang="ts" setup>
import { computed, nextTick, reactive, ref } from 'vue'
import { modelApi } from '@/api/system'
import icon_common_openai from '@/assets/model/icon_common_openai.png'
import { useI18n } from 'vue-i18n'

withDefaults(
  defineProps<{
    activeName?: string
    editModel: boolean
  }>(),
  {
    activeName: '',
    editModel: false,
  }
)

interface RemoteModel {
  id: string
  name: string
}

const GENERIC_OPENAI_SUPPLIER_ID = 15
const { t } = useI18n()
const emits = defineEmits(['submit'])

const modelRef = ref()
const modelFetchLoading = ref(false)
const hasFetchedModels = ref(false)
const remoteModels = ref<RemoteModel[]>([])
const selectedRemoteModelIds = ref<string[]>([])

const modelForm = reactive({
  id: '',
  supplier: GENERIC_OPENAI_SUPPLIER_ID,
  name: '',
  model_type: 0,
  base_model: '',
  api_key: '',
  api_domain: '',
  config_list: [] as Array<any>,
  protocol: 1,
  default_model: false,
})

const rules = computed(() => ({
  api_domain: [
    {
      required: true,
      message: t('datasource.please_enter') + t('common.empty') + t('model.api_domain_name'),
      trigger: 'blur',
    },
  ],
  api_key: [
    {
      required: true,
      message: t('datasource.please_enter') + t('common.empty') + 'API Key',
      trigger: 'blur',
    },
  ],
  base_model: [{ required: true, message: t('model.please_select_model'), trigger: 'change' }],
}))

const selectedCountText = computed(() =>
  t('model.selected_models_count', { count: selectedRemoteModelIds.value.length })
)
const fetchStatusText = computed(() => {
  if (modelFetchLoading.value) return t('model.fetching_model_list')
  if (hasFetchedModels.value)
    return t('model.fetch_model_success', { count: remoteModels.value.length })
  return t('model.fetch_model_list_first')
})
const modelSelectPlaceholder = computed(() =>
  remoteModels.value.length ? t('model.please_select_model') : t('model.fetch_model_list_first')
)
const modelSelectEmptyText = computed(() =>
  hasFetchedModels.value ? t('model.no_remote_models') : t('model.fetch_model_list_first')
)

const resetForm = () => {
  Object.assign(modelForm, {
    id: '',
    supplier: GENERIC_OPENAI_SUPPLIER_ID,
    name: '',
    model_type: 0,
    base_model: '',
    api_key: '',
    api_domain: '',
    config_list: [],
    protocol: 1,
    default_model: false,
  })
  remoteModels.value = []
  selectedRemoteModelIds.value = []
  hasFetchedModels.value = false
  nextTick(() => {
    modelRef.value?.clearValidate()
  })
}

const initForm = (item?: any) => {
  resetForm()
  if (!item) return
  Object.assign(modelForm, {
    ...item,
    supplier: Number(item.supplier || GENERIC_OPENAI_SUPPLIER_ID),
    model_type: Number(item.model_type || 0),
    protocol: Number(item.protocol || 1),
    config_list: item.config_list || [],
  })
  if (modelForm.base_model) {
    remoteModels.value = [{ id: modelForm.base_model, name: modelForm.base_model }]
  }
}

const fetchRemoteModels = async () => {
  if (!modelForm.api_domain || !modelForm.api_key) {
    ElMessage.warning(t('model.enter_endpoint_and_key'))
    return
  }
  modelFetchLoading.value = true
  try {
    const res = await modelApi.fetchModels({
      api_domain: modelForm.api_domain,
      api_key: modelForm.api_key,
    })
    const list = (res || []).map((item: RemoteModel | string) => {
      if (typeof item === 'string') {
        return { id: item, name: item }
      }
      return { id: item.id, name: item.name || item.id }
    })
    if (
      modelForm.base_model &&
      !list.some((item: RemoteModel) => item.id === modelForm.base_model)
    ) {
      list.unshift({ id: modelForm.base_model, name: modelForm.base_model })
    }
    remoteModels.value = list
    selectedRemoteModelIds.value = []
    hasFetchedModels.value = true
    ElMessage.success(t('model.fetch_model_success', { count: list.length }))
  } finally {
    modelFetchLoading.value = false
  }
}

const buildModelPayload = (modelName: string) => ({
  ...modelForm,
  id: modelForm.id || undefined,
  supplier: modelForm.supplier || GENERIC_OPENAI_SUPPLIER_ID,
  model_type: 0,
  protocol: 1,
  name: modelName,
  base_model: modelName,
  config_list: modelForm.config_list || [],
})

const submitModel = () => {
  modelRef.value.validate((valid: boolean) => {
    if (!valid) return
    if (modelForm.id) {
      if (!modelForm.base_model) {
        ElMessage.warning(t('model.please_select_model'))
        return
      }
      emits('submit', buildModelPayload(modelForm.base_model))
      return
    }
    if (!selectedRemoteModelIds.value.length) {
      ElMessage.warning(t('model.please_select_model'))
      return
    }
    emits(
      'submit',
      selectedRemoteModelIds.value.map((id) => buildModelPayload(id))
    )
  })
}

defineExpose({
  initForm,
  submitModel,
})
</script>

<template>
  <div class="model-form">
    <el-scrollbar>
      <div class="form-content">
        <div class="model-provider">
          <img :src="icon_common_openai" width="32" height="32" />
          <div class="provider-main">
            <div class="provider-name">{{ t('supplier.generic_openai') }}</div>
            <div class="provider-desc">{{ t('model.openai_compatible_endpoint') }}</div>
          </div>
        </div>
        <el-form
          ref="modelRef"
          :rules="rules"
          label-position="top"
          :model="modelForm"
          style="width: 100%"
          @submit.prevent
        >
          <div class="drawer-section">
            <div class="section-title">{{ t('model.connection_config') }}</div>
            <el-form-item prop="api_domain" :label="t('model.api_domain_name')">
              <el-input
                v-model="modelForm.api_domain"
                clearable
                :placeholder="t('model.api_domain_placeholder')"
              />
            </el-form-item>
            <el-form-item prop="api_key" label="API Key">
              <el-input
                v-model="modelForm.api_key"
                clearable
                :placeholder="$t('datasource.please_enter') + $t('common.empty') + 'API Key'"
                type="password"
                show-password
              />
            </el-form-item>
            <div class="model-fetch-row">
              <span class="fetch-status">{{ fetchStatusText }}</span>
              <el-button type="primary" :loading="modelFetchLoading" @click="fetchRemoteModels">
                {{ t('model.fetch_model_list') }}
              </el-button>
            </div>
          </div>
          <div class="drawer-section model-select-section">
            <div class="section-title">{{ t('model.model_selection') }}</div>
            <el-form-item v-if="editModel" prop="base_model" :label="t('model.basic_model')">
              <el-select
                v-model="modelForm.base_model"
                filterable
                :no-data-text="modelSelectEmptyText"
                popper-class="model-select-popper"
                :placeholder="modelSelectPlaceholder"
                style="width: 100%"
              >
                <el-option
                  v-for="item in remoteModels"
                  :key="item.id"
                  :label="item.name"
                  :value="item.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item
              v-if="!editModel"
              class="model-select-item"
              :label="t('model.basic_model')"
            >
              <el-select
                v-model="selectedRemoteModelIds"
                multiple
                filterable
                collapse-tags
                collapse-tags-tooltip
                :max-collapse-tags="3"
                :no-data-text="modelSelectEmptyText"
                popper-class="model-select-popper"
                :placeholder="modelSelectPlaceholder"
                style="width: 100%"
              >
                <el-option
                  v-for="item in remoteModels"
                  :key="item.id"
                  :label="item.name"
                  :value="item.id"
                />
              </el-select>
              <div class="model-select-tip">{{ selectedCountText }}</div>
            </el-form-item>
          </div>
        </el-form>
      </div>
    </el-scrollbar>
  </div>
</template>

<style lang="less" scoped>
.model-form {
  height: 100%;

  & > .ed-scrollbar {
    height: 100%;

    .form-content {
      width: calc(100% - 48px);
      max-width: 680px;
      margin: 0 auto;
      padding-top: 24px;
      height: 100%;
      padding-bottom: 80px;

      .ed-form-item--default {
        margin-bottom: 16px;
      }
    }
  }
}

.model-provider {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 0 18px;
  border-bottom: 1px solid #ebeef5;
  margin-bottom: 22px;

  img {
    flex: 0 0 auto;
  }
}

.provider-main {
  min-width: 0;
}

.provider-name {
  color: #1f2329;
  font-size: 16px;
  font-weight: 600;
  line-height: 24px;
}

.provider-desc {
  color: #8f959e;
  font-size: 14px;
  line-height: 22px;
  margin-top: 2px;
}

.drawer-section {
  padding-bottom: 20px;
  margin-bottom: 22px;
  border-bottom: 1px solid #ebeef5;
}

.model-select-section {
  border-bottom: none;
}

.section-title {
  color: #1f2329;
  font-size: 15px;
  font-weight: 600;
  line-height: 24px;
  margin-bottom: 16px;
}

.model-fetch-row {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  margin: 2px 0 0;
}

.fetch-status {
  color: #8f959e;
  flex: 1;
  font-size: 14px;
  line-height: 22px;
  min-width: 0;
}

.model-select-tip {
  color: #8f959e;
  font-size: 14px;
  line-height: 22px;
  margin-top: 8px;
}

:deep(.ed-form-item__label),
:deep(.el-form-item__label) {
  font-size: 15px;
  line-height: 24px;
}

:deep(.ed-input__inner),
:deep(.el-input__inner),
:deep(.ed-select__placeholder),
:deep(.el-select__placeholder),
:deep(.ed-select__selected-item),
:deep(.el-select__selected-item) {
  font-size: 15px !important;
}

:deep(.ed-input__wrapper),
:deep(.el-input__wrapper),
:deep(.ed-select__wrapper),
:deep(.el-select__wrapper) {
  font-size: 15px !important;
}
</style>

<style lang="less">
.model-select-popper {
  .ed-select-dropdown__item,
  .el-select-dropdown__item {
    font-size: 15px;
    height: 38px;
    line-height: 38px;
  }

  .ed-select-dropdown__empty,
  .el-select-dropdown__empty {
    font-size: 15px;
    line-height: 24px;
  }
}
</style>
