<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { cloneDeep } from 'lodash-es'
import { Search } from '@element-plus/icons-vue'
import { promptApi } from '@/api/prompt'
import { modelApi } from '@/api/system'
import icon_ai from '@/assets/svg/icon_ai.svg'
import icon_add_outlined from '@/assets/svg/icon_add_outlined.svg'
import IconOpeEdit from '@/assets/svg/icon_edit_outlined.svg'

const CUSTOM_PROMPT_TYPES = ['GENERATE_SQL', 'ANALYSIS', 'PREDICT_DATA']

const props = withDefaults(
  defineProps<{
    modelValue?: string | number | null
    targetScope?: 'SMART_QA' | 'ANALYSIS_ASSISTANT' | 'ALL' | string
    customPromptTypes?: string[]
    createType?: string
    datasourceId?: string | number | null
    datasourceName?: string
    disabled?: boolean
  }>(),
  {
    modelValue: null,
    targetScope: 'SMART_QA',
    customPromptTypes: () => ['GENERATE_SQL'],
    createType: 'GENERATE_SQL',
    datasourceId: null,
    datasourceName: '',
    disabled: false,
  }
)

const emit = defineEmits<{
  'update:modelValue': [value: string | number | null]
  change: [value: string | number | null]
  saved: []
}>()

const { t } = useI18n()

const popoverVisible = ref(false)
const keyword = ref('')
const agentList = ref<any[]>([])
const loading = ref(false)
const aiModelOptions = ref<any[]>([])
const agentFormRef = ref()
const agentDialogVisible = ref(false)
const agentDialogTitle = ref('')
const savingAgent = ref(false)

const defaultAgentForm = {
  id: null as number | string | null,
  type: 'GENERATE_SQL',
  name: '',
  description: '',
  target_scope: 'SMART_QA',
  active: true,
  visible: true,
  ai_model_id: null as number | string | null,
  prompt: '',
  specific_ds: false,
  datasource_ids: [] as number[],
  visibility_scope: 'USER_PRIVATE',
}
const agentForm = ref(cloneDeep(defaultAgentForm))

const agentRules = {
  name: [
    {
      required: true,
      message: t('datasource.please_enter') + t('common.empty') + t('prompt.prompt_word_name'),
      trigger: 'blur',
    },
  ],
  prompt: [
    {
      required: true,
      message: t('prompt.replaced_with'),
      trigger: 'blur',
    },
  ],
}

const datasourceIdValue = computed(() => {
  if (props.datasourceId === null || props.datasourceId === undefined || props.datasourceId === '') {
    return null
  }
  const value = Number(props.datasourceId)
  return Number.isFinite(value) ? value : null
})

const usablePromptTypes = computed(() => {
  const types = props.customPromptTypes?.length ? props.customPromptTypes : CUSTOM_PROMPT_TYPES
  return types.filter((item) => CUSTOM_PROMPT_TYPES.includes(item))
})

const canCreateAgent = computed(() => true)

const selectedAgent = computed(() =>
  agentList.value.find((item) => String(item.id) === String(props.modelValue))
)

const selectedLabel = computed(() => selectedAgent.value?.name || t('prompt.default_agent'))

const targetScopeText = (scope?: string | null) => {
  if (scope === 'ANALYSIS_ASSISTANT') return t('prompt.target_scope_analysis_assistant')
  if (scope === 'ALL') return t('prompt.target_scope_all')
  return t('prompt.target_scope_smart_qa')
}

const typeTitle = (type?: string) => {
  if (type === 'ANALYSIS') return t('prompt.data_analysis')
  if (type === 'PREDICT_DATA') return t('prompt.data_prediction')
  return t('prompt.ask_sql')
}

const modelText = (row: any) => row?.ai_model_name || t('prompt.default_ai_model')

const sourceText = (row: any) => {
  if (row?.visibility_scope === 'PLATFORM_PUBLIC') return t('access.saas_agent')
  if (row?.visibility_scope === 'ADMIN_PUBLIC') return t('access.workspace_agent')
  if (row?.visibility_scope === 'USER_PRIVATE' && row?.is_owner) return t('access.my_agent')
  return t('access.workspace_agent')
}

const sourceClass = (row: any) => {
  if (row?.visibility_scope === 'PLATFORM_PUBLIC') return 'is-saas'
  if (row?.visibility_scope === 'USER_PRIVATE') return 'is-personal'
  return 'is-workspace'
}

const sourceRank = (row: any) => {
  if (row?.visibility_scope === 'PLATFORM_PUBLIC') return 0
  if (row?.visibility_scope === 'USER_PRIVATE') return 2
  return 1
}

const createTimeValue = (row: any) => {
  const value = row?.create_time ? new Date(row.create_time).getTime() : 0
  return Number.isFinite(value) ? value : 0
}

const sortBySourceAndTime = (a: any, b: any) => {
  const sourceDiff = sourceRank(a) - sourceRank(b)
  if (sourceDiff !== 0) return sourceDiff
  return createTimeValue(b) - createTimeValue(a)
}

const matchesTargetScope = (row: any) => {
  const rowScope = row?.target_scope || 'SMART_QA'
  return (
    rowScope === props.targetScope ||
    rowScope === 'ALL' ||
    (props.targetScope === 'SMART_QA' && !row?.target_scope)
  )
}

const isVisibleInPersonalEntry = (row: any) => {
  return row?.visibility_scope !== 'USER_PRIVATE' || row?.is_owner === true
}

const canManageAgent = (row: any) => {
  return row?.visibility_scope === 'USER_PRIVATE' && row?.is_owner === true
}

const buildListQuery = () => {
  const params = new URLSearchParams()
  if (datasourceIdValue.value) {
    params.append('dslist', String(datasourceIdValue.value))
  }
  params.append('effective_only', 'true')
  if (keyword.value.trim()) {
    params.append('name', keyword.value.trim())
  }
  const query = params.toString()
  return query ? `?${query}` : ''
}

const selectAgent = (value: string | number | null) => {
  emit('update:modelValue', value)
  emit('change', value)
  popoverVisible.value = false
}

const loadAiModels = () => {
  modelApi.listAvailable().then((res: any) => {
    aiModelOptions.value = res || []
  })
}

const loadAgents = async () => {
  loading.value = true
  try {
    const query = buildListQuery()
    const responses = await Promise.all(
      usablePromptTypes.value.map((type) =>
        promptApi.getList(1, 100, type, query).catch(() => ({ data: [] }))
      )
    )
    agentList.value = responses
      .flatMap((res: any) => res?.data || [])
      .filter((row: any) => row?.active === true && matchesTargetScope(row) && isVisibleInPersonalEntry(row))
      .sort(sortBySourceAndTime)

    if (
      props.modelValue &&
      !agentList.value.some((item) => String(item.id) === String(props.modelValue))
    ) {
      selectAgent(null)
    }
  } finally {
    loading.value = false
  }
}

const resetAgentForm = () => {
  agentForm.value = {
    ...cloneDeep(defaultAgentForm),
    type: props.createType || usablePromptTypes.value[0] || 'GENERATE_SQL',
    target_scope: props.targetScope || 'SMART_QA',
    specific_ds: false,
    datasource_ids: [],
    visibility_scope: 'USER_PRIVATE',
  }
}

const openCreateAgent = () => {
  resetAgentForm()
  agentDialogTitle.value = t('prompt.add_prompt_word')
  agentDialogVisible.value = true
  popoverVisible.value = false
}

const openEditAgent = (row: any) => {
  if (!canManageAgent(row)) return
  agentForm.value = {
    ...cloneDeep(defaultAgentForm),
    ...cloneDeep(row),
    target_scope: row.target_scope || props.targetScope || 'SMART_QA',
    specific_ds: false,
    datasource_ids: [],
    visibility_scope: 'USER_PRIVATE',
  }
  agentDialogTitle.value = t('prompt.edit_prompt_word')
  agentDialogVisible.value = true
  popoverVisible.value = false
}

const closeAgentForm = () => {
  agentDialogVisible.value = false
  resetAgentForm()
}

const buildSavePayload = () => {
  const payload = cloneDeep(agentForm.value)
  payload.type = payload.type || props.createType || usablePromptTypes.value[0] || 'GENERATE_SQL'
  payload.target_scope = payload.target_scope || props.targetScope || 'SMART_QA'

  payload.visibility_scope = 'USER_PRIVATE'
  payload.specific_ds = false
  payload.datasource_ids = []
  return payload
}

const saveAgent = () => {
  agentFormRef.value?.validate((valid: boolean) => {
    if (!valid || savingAgent.value) return

    savingAgent.value = true
    promptApi
      .updateEmbedded(buildSavePayload())
      .then(() => {
        ElMessage.success(t('common.save_success'))
        closeAgentForm()
        loadAgents()
        emit('saved')
      })
      .finally(() => {
        savingAgent.value = false
      })
  })
}

watch(
  () => [
    props.datasourceId,
    props.targetScope,
    (props.customPromptTypes || []).join(','),
    keyword.value,
  ],
  () => {
    loadAgents()
  }
)

onMounted(() => {
  loadAiModels()
  resetAgentForm()
  loadAgents()
})
</script>

<template>
  <div class="agent-selector" @click.stop>
    <el-popover
      v-model:visible="popoverVisible"
      :disabled="props.disabled"
      :width="360"
      placement="top-start"
      trigger="click"
      popper-class="agent-selector-popover"
    >
      <template #reference>
        <button class="agent-selector-trigger" :disabled="props.disabled" type="button">
          <el-icon class="trigger-icon" size="16">
            <icon_ai />
          </el-icon>
          <span class="trigger-label ellipsis" :title="selectedLabel">{{ selectedLabel }}</span>
        </button>
      </template>

      <div class="agent-panel">
        <div class="agent-panel-header">
          <div>
            <div class="agent-panel-title">{{ t('access.custom_agents') }}</div>
            <div class="agent-panel-subtitle">
              {{ props.datasourceName || t('access.user_permission_scope') }}
            </div>
          </div>
          <el-button
            size="small"
            type="primary"
            class="agent-create-btn"
            :disabled="!canCreateAgent"
            @click.stop="openCreateAgent"
          >
            <template #icon>
              <icon_add_outlined />
            </template>
            {{ t('prompt.add_prompt_word') }}
          </el-button>
        </div>

        <el-input
          v-model="keyword"
          clearable
          size="small"
          class="agent-search"
          :prefix-icon="Search"
          :placeholder="t('dashboard.search')"
          @click.stop
        />

        <div v-loading="loading" class="agent-list">
          <div
            class="agent-option is-default"
            :class="{ selected: !props.modelValue }"
            role="button"
            tabindex="0"
            @click.stop="selectAgent(null)"
          >
            <div class="agent-option-main">
              <span class="agent-option-name">{{ t('prompt.default_agent') }}</span>
              <span class="agent-option-desc">{{ targetScopeText(props.targetScope) }}</span>
            </div>
          </div>

          <div v-if="!agentList.length && !loading" class="agent-empty">
            {{ t('prompt.no_prompt_words') }}
          </div>

          <div
            v-for="agent in agentList"
            :key="agent.id"
            class="agent-option"
            :class="[sourceClass(agent), { selected: String(agent.id) === String(props.modelValue) }]"
            role="button"
            tabindex="0"
            @click.stop="selectAgent(agent.id)"
          >
            <div class="agent-option-main">
              <div class="agent-option-title">
                <span class="agent-option-name ellipsis" :title="agent.name">{{ agent.name }}</span>
                <span class="agent-source-pill">{{ sourceText(agent) }}</span>
              </div>
              <div class="agent-option-desc ellipsis" :title="agent.description || typeTitle(agent.type)">
                {{ agent.description || typeTitle(agent.type) }}
              </div>
              <div class="agent-option-meta">
                <span>{{ typeTitle(agent.type) }}</span>
                <span>{{ modelText(agent) }}</span>
              </div>
            </div>
            <el-tooltip
              v-if="canManageAgent(agent)"
              :content="t('datasource.edit')"
              placement="top"
            >
              <el-button
                class="agent-edit-btn"
                link
                type="primary"
                @click.stop="openEditAgent(agent)"
              >
                <el-icon size="15">
                  <IconOpeEdit />
                </el-icon>
              </el-button>
            </el-tooltip>
          </div>
        </div>
      </div>
    </el-popover>

    <el-drawer
      v-model="agentDialogVisible"
      :title="agentDialogTitle"
      destroy-on-close
      size="600px"
      :before-close="closeAgentForm"
      modal-class="agent-selector-drawer"
    >
      <el-form
        ref="agentFormRef"
        :model="agentForm"
        :rules="agentRules"
        label-width="180px"
        label-position="top"
        class="form-content_error"
        @submit.prevent
      >
        <el-form-item prop="name" :label="t('prompt.prompt_word_name')">
          <el-input
            v-model="agentForm.name"
            maxlength="50"
            clearable
            :placeholder="t('datasource.please_enter') + t('common.empty') + t('prompt.prompt_word_name')"
          />
        </el-form-item>
        <el-form-item prop="description" :label="t('prompt.agent_description')">
          <el-input
            v-model="agentForm.description"
            :placeholder="t('prompt.agent_description_placeholder')"
            :autosize="{ minRows: 2, maxRows: 4 }"
            type="textarea"
          />
        </el-form-item>
        <el-form-item prop="ai_model_id" :label="t('prompt.ai_model')">
          <el-select
            v-model="agentForm.ai_model_id"
            clearable
            filterable
            :placeholder="t('prompt.select_ai_model_placeholder')"
            style="width: 100%"
          >
            <el-option :label="t('prompt.default_ai_model')" :value="null" />
            <el-option
              v-for="model in aiModelOptions"
              :key="model.id"
              :label="model.default_model ? `${model.name}（${t('prompt.default_ai_model')}）` : model.name"
              :value="model.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item prop="target_scope" :label="t('prompt.target_scope')">
          <el-radio-group v-model="agentForm.target_scope">
            <el-radio :value="'SMART_QA'">{{ t('prompt.target_scope_smart_qa') }}</el-radio>
            <el-radio :value="'ANALYSIS_ASSISTANT'">
              {{ t('prompt.target_scope_analysis_assistant') }}
            </el-radio>
            <el-radio :value="'ALL'">{{ t('prompt.target_scope_all') }}</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item prop="active" :label="t('prompt.active_status')">
          <el-switch
            v-model="agentForm.active"
            :active-text="t('prompt.active_enabled')"
            :inactive-text="t('prompt.active_disabled')"
          />
        </el-form-item>
        <el-form-item :label="t('training.effective_data_sources')">
          <div class="fixed-project">{{ t('access.user_permission_scope') }}</div>
        </el-form-item>
        <el-form-item prop="prompt" :label="t('prompt.prompt_word_content')">
          <el-input
            v-model="agentForm.prompt"
            :placeholder="t('prompt.replaced_with')"
            :autosize="{ minRows: 6, maxRows: 14 }"
            type="textarea"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <div v-loading="savingAgent" class="dialog-footer">
          <el-button secondary @click="closeAgentForm">{{ t('common.cancel') }}</el-button>
          <el-button type="primary" @click="saveAgent">{{ t('common.save') }}</el-button>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<style lang="less" scoped>
.agent-selector {
  width: 116px;
}

.agent-selector-trigger {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  height: 28px;
  padding: 0 9px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: var(--workspace-control-bg, #f7faff);
  color: var(--workspace-text-secondary, #4e5969);
  box-shadow: 0 0 0 1px var(--workspace-border, #dbe5f2) inset;
  cursor: pointer;

  &:disabled {
    cursor: not-allowed;
    opacity: 0.55;
  }

  .trigger-icon {
    flex: 0 0 auto;
    color: #3370ff;
  }

  .trigger-label {
    min-width: 0;
    flex: 1;
    text-align: left;
    font-size: 12px;
    line-height: 18px;
  }
}

.agent-panel {
  width: 100%;
}

.agent-panel-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.agent-panel-title {
  color: #1f2329;
  font-size: 14px;
  font-weight: 600;
  line-height: 20px;
}

.agent-panel-subtitle {
  max-width: 190px;
  margin-top: 2px;
  color: #86909c;
  font-size: 12px;
  line-height: 18px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-create-btn {
  flex: 0 0 auto;
}

.agent-search {
  margin-bottom: 10px;
}

.agent-list {
  min-height: 104px;
  max-height: 320px;
  overflow-y: auto;
}

.agent-option {
  --agent-source-color: #667085;
  --agent-source-bg: #f2f4f7;
  --agent-source-border: #d0d5dd;
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 64px;
  padding: 9px 10px;
  border: 1px solid transparent;
  border-left: 2px solid transparent;
  border-radius: 6px;
  cursor: pointer;

  &:hover {
    background: var(--agent-source-bg);
  }

  &.selected {
    border-color: var(--agent-source-color);
    background: var(--agent-source-bg);
  }

  & + .agent-option {
    margin-top: 6px;
  }

  &.is-saas {
    --agent-source-color: #7a5af8;
    --agent-source-bg: #f3f0ff;
    --agent-source-border: #d8ccff;
    border-left-color: var(--agent-source-color);
  }

  &.is-workspace {
    --agent-source-color: #1570ef;
    --agent-source-bg: #eaf2ff;
    --agent-source-border: #b9d6ff;
    border-left-color: var(--agent-source-color);
  }

  &.is-personal {
    --agent-source-color: #12a076;
    --agent-source-bg: #e9f8f2;
    --agent-source-border: #a9e7d0;
    border-left-color: var(--agent-source-color);
  }
}

.agent-option-main {
  min-width: 0;
  flex: 1;
}

.agent-option-title {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.agent-source-pill {
  flex: 0 0 auto;
  max-width: 92px;
  padding: 0 5px;
  border: 1px solid var(--agent-source-border);
  border-radius: 4px;
  background: var(--agent-source-bg);
  color: var(--agent-source-color);
  font-size: 11px;
  font-weight: 500;
  line-height: 18px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-option-name {
  min-width: 0;
  color: #1f2329;
  font-size: 13px;
  font-weight: 600;
  line-height: 20px;
}

.agent-option-desc {
  margin-top: 2px;
  color: #646a73;
  font-size: 12px;
  line-height: 18px;
}

.agent-option-meta {
  display: flex;
  gap: 8px;
  margin-top: 3px;
  color: #8f959e;
  font-size: 12px;
  line-height: 18px;
}

.agent-edit-btn {
  flex: 0 0 auto;
  width: 24px;
  height: 24px;
  padding: 0;
}

.agent-empty {
  padding: 24px 0;
  color: #8f959e;
  text-align: center;
  font-size: 13px;
}

.fixed-project {
  width: 100%;
  min-height: 32px;
  padding: 6px 10px;
  border-radius: 6px;
  background: #f5f7fa;
  color: #4e5969;
  line-height: 20px;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}
</style>

<style lang="less">
.agent-selector-popover.agent-selector-popover {
  padding: 12px;
  border-radius: 8px;
}

.agent-selector-drawer {
  .ed-drawer__body {
    padding: 20px 24px;
  }
}
</style>
