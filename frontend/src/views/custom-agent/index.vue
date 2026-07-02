<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { cloneDeep } from 'lodash-es'
import { Search } from '@element-plus/icons-vue'
import { useDatasourceContextStore } from '@/stores/datasourceContext'
import { promptApi } from '@/api/prompt'
import { datasourceApi } from '@/api/datasource'
import { modelApi } from '@/api/system'
import icon_ai from '@/assets/svg/icon_ai.svg'
import icon_add_outlined from '@/assets/svg/icon_add_outlined.svg'
import IconOpeEdit from '@/assets/svg/icon_edit_outlined.svg'
import IconOpeDelete from '@/assets/svg/icon_delete.svg'
import icon_key_outlined from '@/assets/svg/icon-key_outlined.svg'
import icon_more_outlined from '@/assets/svg/icon_more_outlined.svg'
import { formatTimestamp } from '@/utils/date'
import { useUserStore } from '@/stores/user'

const props = withDefaults(
  defineProps<{
    mode?: 'personal' | 'admin'
  }>(),
  {
    mode: 'personal',
  }
)
const { t } = useI18n()
const datasourceContext = useDatasourceContextStore()
const userStore = useUserStore()

const CUSTOM_PROMPT_TYPES = ['GENERATE_SQL', 'ANALYSIS', 'PREDICT_DATA']

const agentLoading = ref(false)
const agentList = ref<any[]>([])
const aiModelOptions = ref<any[]>([])
const agentFormRef = ref()
const agentDialogVisible = ref(false)
const agentDetailVisible = ref(false)
const agentDialogTitle = ref('')
const selectedAgent = ref<any | null>(null)
const savingAgent = ref(false)
const agentKeyword = ref('')
const datasourceOptions = ref<any[]>([])
const scopeFilter = ref('')
const datasourceFilter = ref<number | string>('')

const isAdminMode = computed(() => props.mode === 'admin')
const isPlatformAdmin = computed(
  () => userStore.isSystemAdminUser && !userStore.isPlatformWorkspaceDelegate
)
const canCreateAgent = computed(() => !isAdminMode.value || userStore.isSystemManagerUser)

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

const currentDatasourceId = computed(() => datasourceContext.datasourceId)

const pageTitle = computed(() => {
  if (!isAdminMode.value) return t('access.custom_agents')
  return isPlatformAdmin.value ? t('access.saas_agent') : t('access.workspace_agent')
})

const validateDatasource = (_: any, value: any, callback: any) => {
  if (isAdminMode.value && agentForm.value.specific_ds && !value?.length) {
    callback(new Error(t('datasource.Please_select') + t('common.empty') + t('ds.title')))
    return
  }
  callback()
}

const agentRules = {
  name: [
    {
      required: true,
      message: t('datasource.please_enter') + t('common.empty') + t('prompt.prompt_word_name'),
      trigger: 'blur',
    },
  ],
  datasource_ids: [
    {
      validator: validateDatasource,
      trigger: 'change',
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

const typeTitle = (type?: string) => {
  if (type === 'ANALYSIS') return t('prompt.data_analysis')
  if (type === 'PREDICT_DATA') return t('prompt.data_prediction')
  return t('prompt.ask_sql')
}

const targetScopeText = (scope?: string | null) => {
  if (scope === 'ANALYSIS_ASSISTANT') return t('prompt.target_scope_analysis_assistant')
  if (scope === 'ALL') return t('prompt.target_scope_all')
  return t('prompt.target_scope_smart_qa')
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

const layerOptions = computed(() => [
  ...(!isAdminMode.value || (isAdminMode.value && !isPlatformAdmin.value)
    ? [{ label: t('prompt.target_scope_all'), value: '' }]
    : []),
  ...(isAdminMode.value && isPlatformAdmin.value
    ? [{ label: t('permission.scope_platform'), value: 'PLATFORM_PUBLIC' }]
    : []),
  ...(isAdminMode.value && !isPlatformAdmin.value
    ? [
        { label: t('permission.scope_platform'), value: 'PLATFORM_PUBLIC' },
        { label: t('permission.scope_workspace'), value: 'ADMIN_PUBLIC' },
      ]
    : []),
  ...(!isAdminMode.value
    ? [
        { label: t('permission.scope_platform'), value: 'PLATFORM_PUBLIC' },
        { label: t('permission.scope_workspace'), value: 'ADMIN_PUBLIC' },
        { label: t('access.user_permission_scope'), value: 'USER_PRIVATE' },
      ]
    : []),
])

const scopeText = (row: any) => {
  if (!row) return '-'
  if (row?.visibility_scope === 'USER_PRIVATE') return t('access.user_permission_scope')
  if (row?.specific_ds) {
    return row.datasource_names?.length
      ? row.datasource_names.join('、')
      : t('training.partial_data_sources')
  }
  return t('training.all_data_sources')
}

const isVisibleInPersonalEntry = (row: any) => {
  if (isAdminMode.value) return true
  return row?.visibility_scope !== 'USER_PRIVATE' || row?.is_owner === true
}

const canManageAgent = (row: any) => {
  if (isAdminMode.value) return row?.can_manage === true
  return row?.visibility_scope === 'USER_PRIVATE' && row?.is_owner === true
}

const canViewPromptInPersonalEntry = (row: any) => {
  return (
    row?.prompt_visible === true ||
    (row?.visibility_scope === 'USER_PRIVATE' && row?.is_owner === true)
  )
}

const isAgentVisible = (row: any) => row?.visible !== false

const visibilityStatusText = (row: any) =>
  isAgentVisible(row) ? t('prompt.visible_shown') : t('prompt.visible_hidden')

const isAgentEffective = (row: any) => row?.effective_active !== false && row?.active !== false

const adminVisibilityScopes = computed(() => {
  if (!isAdminMode.value) return [scopeFilter.value || '']
  if (isPlatformAdmin.value) return [scopeFilter.value || 'PLATFORM_PUBLIC']
  return scopeFilter.value ? [scopeFilter.value] : ['PLATFORM_PUBLIC', 'ADMIN_PUBLIC']
})

const buildAgentQuery = (visibilityScope = scopeFilter.value) => {
  const params = new URLSearchParams()
  if (visibilityScope) {
    params.append('visibility_scope', visibilityScope)
  }
  const filterDatasourceId = isAdminMode.value ? datasourceFilter.value : currentDatasourceId.value
  if (filterDatasourceId) {
    params.append('dslist', String(filterDatasourceId))
  }
  if (agentKeyword.value.trim()) {
    params.append('name', agentKeyword.value.trim())
  }
  const query = params.toString()
  return query ? `?${query}` : ''
}

const dedupeAgents = (rows: any[]) => {
  const seen = new Set<string>()
  return rows.filter((row) => {
    const key = String(row?.id || '')
    if (!key || seen.has(key)) return false
    seen.add(key)
    return true
  })
}

const loadAiModels = () => {
  modelApi.listAvailable().then((res: any) => {
    aiModelOptions.value = res || []
  })
}

const loadDatasourceOptions = async () => {
  if (!isAdminMode.value) {
    datasourceOptions.value = []
    return
  }
  const request = isPlatformAdmin.value ? datasourceApi.list() : datasourceApi.accessibleList()
  const res: any = await request.catch(() => [])
  datasourceOptions.value = Array.isArray(res) ? res : []
}

const loadAgents = async () => {
  agentLoading.value = true
  try {
    const queries = isAdminMode.value
      ? adminVisibilityScopes.value.map((scope) => buildAgentQuery(scope))
      : [buildAgentQuery()]
    const responses = await Promise.all(
      queries.flatMap((query) =>
        CUSTOM_PROMPT_TYPES.map((type) =>
          promptApi.getList(1, 100, type, query).catch(() => ({ data: [] }))
        )
      )
    )
    agentList.value = dedupeAgents(responses.flatMap((res: any) => res?.data || []))
      .filter(isVisibleInPersonalEntry)
      .sort(sortBySourceAndTime)
  } finally {
    agentLoading.value = false
  }
}

const toggleAgentVisibility = (agent: any, value: boolean) => {
  if (!isAdminMode.value || !canManageAgent(agent)) return
  const previousVisible = isAgentVisible(agent)
  agent.visible = value

  promptApi
    .setVisibility(agent.id, value)
    .then((res: any) => {
      agent.visible = res?.visible ?? value
      ElMessage.success(t('common.save_success'))
    })
    .catch(() => {
      agent.visible = previousVisible
    })
}

const toggleAgentActivation = (agent: any, value: boolean) => {
  const previousUserEnabled = agent.user_enabled !== false
  const previousActive = agent.active !== false
  const scope = isAdminMode.value || canManageAgent(agent) ? 'global' : 'user'

  if (scope === 'global') {
    agent.active = value
    agent.effective_active = value && agent.user_enabled !== false
  } else {
    agent.user_enabled = value
    agent.effective_active = agent.active !== false && value
  }

  promptApi
    .setActivation(agent.id, value, scope)
    .then((res: any) => {
      agent.active = res?.active ?? agent.active
      agent.user_enabled = res?.user_enabled ?? agent.user_enabled
      agent.effective_active = agent.active !== false && agent.user_enabled !== false
      ElMessage.success(t('common.save_success'))
      if (!isAdminMode.value && agent.active === false) {
        loadAgents()
      }
    })
    .catch(() => {
      agent.user_enabled = previousUserEnabled
      agent.active = previousActive
      agent.effective_active = previousActive && previousUserEnabled
    })
}

const resetAgentForm = () => {
  agentForm.value = {
    ...cloneDeep(defaultAgentForm),
    specific_ds: false,
    datasource_ids: [],
    visibility_scope: isAdminMode.value
      ? isPlatformAdmin.value
        ? 'PLATFORM_PUBLIC'
        : 'ADMIN_PUBLIC'
      : 'USER_PRIVATE',
  }
}

const openCreateAgent = () => {
  if (!canCreateAgent.value) return
  resetAgentForm()
  agentDialogTitle.value = t('prompt.add_prompt_word')
  agentDialogVisible.value = true
}

const openEditAgent = (row: any) => {
  if (!canManageAgent(row)) return
  agentForm.value = {
    ...cloneDeep(defaultAgentForm),
    ...cloneDeep(row),
    specific_ds: isAdminMode.value ? Boolean(row?.specific_ds) : false,
    datasource_ids: isAdminMode.value ? row?.datasource_ids || [] : [],
    visibility_scope: isAdminMode.value
      ? isPlatformAdmin.value
        ? 'PLATFORM_PUBLIC'
        : 'ADMIN_PUBLIC'
      : 'USER_PRIVATE',
  }
  agentDialogTitle.value = t('prompt.edit_prompt_word')
  agentDialogVisible.value = true
}

const closeAgentForm = () => {
  agentDialogVisible.value = false
  resetAgentForm()
}

const saveAgent = () => {
  if (!canCreateAgent.value) return
  agentFormRef.value?.validate((valid: boolean) => {
    if (!valid || savingAgent.value) return
    const payload = cloneDeep(agentForm.value)
    payload.type = payload.type || 'GENERATE_SQL'
    if (isAdminMode.value) {
      payload.visibility_scope = isPlatformAdmin.value ? 'PLATFORM_PUBLIC' : 'ADMIN_PUBLIC'
      if (!payload.specific_ds) {
        payload.specific_ds = false
        payload.datasource_ids = []
      } else {
        payload.datasource_ids = (payload.datasource_ids || []).map((item: any) => Number(item))
      }
    } else {
      payload.specific_ds = false
      payload.datasource_ids = []
      payload.visibility_scope = 'USER_PRIVATE'
    }
    payload.visible = payload.visible !== false
    savingAgent.value = true
    promptApi
      .updateEmbedded(payload)
      .then(() => {
        ElMessage.success(t('common.save_success'))
        closeAgentForm()
        loadAgents()
      })
      .finally(() => {
        savingAgent.value = false
      })
  })
}

const deleteAgent = (row: any) => {
  if (!canManageAgent(row)) return
  ElMessageBox.confirm(t('prompt.prompt_word_name_de', { msg: row.name }), {
    confirmButtonType: 'danger',
    confirmButtonText: t('dashboard.delete'),
    cancelButtonText: t('common.cancel'),
    customClass: 'confirm-no_icon',
    autofocus: false,
  }).then(() => {
    promptApi.deleteEmbedded([row.id]).then(() => {
      ElMessage.success(t('dashboard.delete_success'))
      loadAgents()
    })
  })
}

const openAgentDetail = (row: any) => {
  selectedAgent.value = cloneDeep(row)
  agentDetailVisible.value = true
}

const handleDatasourceChange = () => {
  agentFormRef.value?.validateField('datasource_ids')
}

const handleDatasourceScopeModeChange = (value: string | number | boolean) => {
  if (!value) {
    agentForm.value.datasource_ids = []
  }
  handleDatasourceChange()
}

onMounted(async () => {
  scopeFilter.value = isAdminMode.value ? (isPlatformAdmin.value ? 'PLATFORM_PUBLIC' : '') : ''
  if (isAdminMode.value) {
    await loadDatasourceOptions()
  } else {
    await datasourceContext.loadDatasources()
  }
  loadAiModels()
  loadAgents()
})

watch(currentDatasourceId, () => {
  if (!isAdminMode.value) loadAgents()
})

watch(agentKeyword, () => {
  loadAgents()
})

watch(scopeFilter, () => {
  loadAgents()
})

watch(datasourceFilter, () => {
  loadAgents()
})
</script>

<template>
  <div class="custom-agent-page">
    <div class="page-header">
      <div class="page-title">{{ pageTitle }}</div>
      <div class="page-actions">
        <el-input
          v-model="agentKeyword"
          clearable
          class="agent-search"
          :prefix-icon="Search"
          :placeholder="t('dashboard.search')"
        />
        <el-select v-model="scopeFilter" class="scope-filter">
          <el-option
            v-for="item in layerOptions"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </el-select>
        <el-select
          v-if="isAdminMode"
          v-model="datasourceFilter"
          clearable
          filterable
          class="project-filter"
          :placeholder="t('prompt.project_filter_placeholder')"
        >
          <el-option
            v-for="item in datasourceOptions"
            :key="item.id"
            :label="item.name"
            :value="Number(item.id)"
          />
        </el-select>
        <el-button v-if="canCreateAgent" type="primary" @click="openCreateAgent">
          <template #icon>
            <icon_add_outlined />
          </template>
          {{ t('prompt.add_prompt_word') }}
        </el-button>
      </div>
    </div>

    <section class="agent-section">
      <div v-loading="agentLoading" class="agent-content">
        <div v-if="!agentList.length && !agentLoading" class="agent-empty">
          {{ t('prompt.no_prompt_words') }}
        </div>
        <template v-else>
          <div class="card-content">
            <article
              v-for="agent in agentList"
              :key="agent.id"
              class="agent-card"
              :class="sourceClass(agent)"
              @click="openAgentDetail(agent)"
            >
              <div class="agent-card-head">
                <div class="name-icon">
                  <el-icon class="icon-primary" size="28">
                    <icon_ai />
                  </el-icon>
                  <div class="info">
                    <div class="title-line">
                      <span class="name ellipsis" :title="agent.name">{{ agent.name }}</span>
                    </div>
                    <div class="agent-meta-row">
                      <span class="agent-source-pill">{{ sourceText(agent) }}</span>
                      <span class="sub-title ellipsis">{{ typeTitle(agent.type) }}</span>
                    </div>
                  </div>
                </div>
                <div class="agent-actions" @click.stop>
                  <el-popover
                    v-if="canManageAgent(agent)"
                    trigger="click"
                    :teleported="true"
                    popper-class="popover-card_agent"
                    placement="bottom-end"
                  >
                    <template #reference>
                      <button
                        type="button"
                        class="icon-action"
                        :title="t('dashboard.chart_more_actions')"
                      >
                        <icon_more_outlined />
                      </button>
                    </template>
                    <div class="content">
                      <div class="item" @click.stop="openEditAgent(agent)">
                        <el-icon size="16">
                          <IconOpeEdit />
                        </el-icon>
                        <span>{{ t('datasource.edit') }}</span>
                      </div>
                      <div class="item" @click.stop="deleteAgent(agent)">
                        <el-icon size="16">
                          <IconOpeDelete />
                        </el-icon>
                        <span>{{ t('dashboard.delete') }}</span>
                      </div>
                    </div>
                  </el-popover>
                  <el-tooltip
                    v-if="isAdminMode && canManageAgent(agent)"
                    :content="`${t('prompt.visible_status')}: ${visibilityStatusText(agent)}`"
                    placement="top"
                  >
                    <div class="visibility-switch">
                      <el-switch
                        :model-value="isAgentVisible(agent)"
                        size="small"
                        @change="
                          (value: string | number | boolean) =>
                            toggleAgentVisibility(agent, Boolean(value))
                        "
                      />
                    </div>
                  </el-tooltip>
                  <span class="action-divider"></span>
                  <div class="activation-switch">
                    <el-switch
                      :model-value="isAgentEffective(agent)"
                      size="small"
                      :disabled="isAdminMode && !canManageAgent(agent)"
                      @change="
                        (value: string | number | boolean) =>
                          toggleAgentActivation(agent, Boolean(value))
                      "
                    />
                  </div>
                </div>
              </div>

              <div class="detail-list">
                <div class="type-value">
                  <span class="type">{{ t('prompt.agent_description') }}</span>
                  <span
                    class="value ellipsis"
                    :title="agent.description || t('prompt.agent_empty_description')"
                  >
                    {{ agent.description || t('prompt.agent_empty_description') }}
                  </span>
                </div>
                <div class="type-value">
                  <span class="type">{{ t('prompt.ai_model') }}</span>
                  <span class="value ellipsis" :title="modelText(agent)">
                    {{ modelText(agent) }}
                  </span>
                </div>
                <div class="type-value">
                  <span class="type">{{ t('prompt.target_scope') }}</span>
                  <span class="value ellipsis" :title="targetScopeText(agent.target_scope)">
                    {{ targetScopeText(agent.target_scope) }}
                  </span>
                </div>
                <div class="type-value">
                  <span class="type">{{ t('training.effective_data_sources') }}</span>
                  <span class="value ellipsis" :title="scopeText(agent)">
                    {{ scopeText(agent) }}
                  </span>
                </div>
              </div>

              <div class="bottom-info">
                <div class="form-rate">
                  <el-icon class="form-icon" size="13">
                    <icon_key_outlined />
                  </el-icon>
                  {{ typeTitle(agent.type) }}
                </div>
                <div class="create-time">
                  {{
                    agent.create_time
                      ? formatTimestamp(agent.create_time, 'YYYY-MM-DD HH:mm:ss')
                      : '-'
                  }}
                </div>
              </div>
            </article>
          </div>
        </template>
      </div>
    </section>

    <el-drawer
      v-model="agentDialogVisible"
      :title="agentDialogTitle"
      destroy-on-close
      size="600px"
      :before-close="closeAgentForm"
      modal-class="custom-agent-drawer"
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
        <el-form-item v-if="isAdminMode" prop="visible" :label="t('prompt.visible_status')">
          <el-tooltip :content="t('prompt.visible_hint')" placement="top">
            <el-switch
              v-model="agentForm.visible"
              :active-text="t('prompt.visible_shown')"
              :inactive-text="t('prompt.visible_hidden')"
            />
          </el-tooltip>
        </el-form-item>
        <el-form-item :label="t('training.effective_data_sources')">
          <div v-if="!isAdminMode" class="fixed-project">
            {{ t('access.user_permission_scope') }}
          </div>
          <div v-else class="datasource-scope-editor">
            <el-radio-group
              v-model="agentForm.specific_ds"
              class="project-scope-mode"
              @change="handleDatasourceScopeModeChange"
            >
              <el-radio-button :value="false">{{ t('training.all_data_sources') }}</el-radio-button>
              <el-radio-button :value="true">{{ t('training.partial_data_sources') }}</el-radio-button>
            </el-radio-group>
            <el-form-item
              v-show="agentForm.specific_ds"
              prop="datasource_ids"
              class="nested-datasource-form-item"
            >
              <el-select
                v-model="agentForm.datasource_ids"
                multiple
                filterable
                :placeholder="t('datasource.Please_select') + t('common.empty') + t('ds.title')"
                style="width: 100%"
                @change="handleDatasourceChange"
              >
                <el-option
                  v-for="item in datasourceOptions"
                  :key="item.id"
                  :label="item.name"
                  :value="Number(item.id)"
                />
              </el-select>
            </el-form-item>
            <div v-if="!agentForm.specific_ds" class="scope-mode-tip">
              {{ t('prompt.all_projects_hint') }}
            </div>
          </div>
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

    <el-drawer
      v-model="agentDetailVisible"
      :title="t('menu.Details')"
      destroy-on-close
      size="600px"
      modal-class="custom-agent-drawer"
    >
      <el-form label-width="180px" label-position="top" class="form-content_error" @submit.prevent>
        <el-form-item :label="t('prompt.prompt_word_name')">
          <div class="detail-content">{{ selectedAgent?.name || '-' }}</div>
        </el-form-item>
        <el-form-item :label="t('prompt.agent_description')">
          <div class="detail-content">
            {{ selectedAgent?.description || t('prompt.agent_empty_description') }}
          </div>
        </el-form-item>
        <el-form-item :label="t('access.agent_source')">
          <div class="detail-content">{{ sourceText(selectedAgent) }}</div>
        </el-form-item>
        <el-form-item :label="t('prompt.ai_model')">
          <div class="detail-content">{{ modelText(selectedAgent) }}</div>
        </el-form-item>
        <el-form-item :label="t('prompt.target_scope')">
          <div class="detail-content">{{ targetScopeText(selectedAgent?.target_scope) }}</div>
        </el-form-item>
        <el-form-item :label="t('prompt.active_status')">
          <div class="detail-content">
            {{ selectedAgent?.active ? t('prompt.active_enabled') : t('prompt.active_disabled') }}
          </div>
        </el-form-item>
        <el-form-item
          v-if="isAdminMode && canManageAgent(selectedAgent)"
          :label="t('prompt.visible_status')"
        >
          <div class="detail-content">
            {{ visibilityStatusText(selectedAgent) }}
          </div>
        </el-form-item>
        <el-form-item :label="t('training.effective_data_sources')">
          <div class="detail-content">{{ scopeText(selectedAgent) }}</div>
        </el-form-item>
        <el-form-item
          v-if="canViewPromptInPersonalEntry(selectedAgent)"
          :label="t('prompt.prompt_word_content')"
        >
          <div class="detail-content pre-wrap">{{ selectedAgent?.prompt }}</div>
        </el-form-item>
        <el-form-item v-else :label="t('prompt.prompt_word_content')">
          <div class="detail-content muted">{{ t('access.prompt_not_visible') }}</div>
        </el-form-item>
      </el-form>
    </el-drawer>
  </div>
</template>

<style lang="less" scoped>
.custom-agent-page {
  height: 100%;
  padding: 0 0 24px;
  color: #1f2329;

  .page-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 16px;
    min-height: 34px;
  }

  .page-title {
    color: var(--workspace-text-primary, var(--theme-text-primary, #1f2329));
    font-weight: 600;
    font-size: 15px;
    line-height: 24px;
    letter-spacing: 0.1px;
    white-space: nowrap;
  }

  .agent-section {
    min-height: 0;
  }

  .agent-empty {
    min-height: 96px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #8f959e;
    font-size: 14px;
    line-height: 22px;
    border: 1px solid #dee0e3;
    border-radius: 8px;
    background: #fff;
  }

  .agent-content {
    min-height: 96px;
  }

  .card-content {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 12px;
  }

  .page-actions {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 12px;
    min-width: 360px;
  }

  .agent-search {
    width: 240px;
  }

  .scope-filter {
    width: 132px;
  }

  .project-filter {
    width: 180px;
  }

  .agent-card {
    --agent-source-color: #667085;
    --agent-source-bg: #f2f4f7;
    --agent-source-border: #d0d5dd;
    --agent-source-card-bg: #ffffff;
    width: 100%;
    height: 176px;
    border: 1px solid var(--agent-source-border);
    border-left: 2px solid var(--agent-source-color);
    padding: 12px 14px 12px 12px;
    border-radius: 8px;
    background: var(--agent-source-card-bg);
    box-shadow: none;
    cursor: pointer;
    display: flex;
    flex-direction: column;
    position: relative;
    transition:
      box-shadow 0.12s ease,
      transform 0.12s ease,
      border-color 0.12s ease;

    &:hover {
      border-color: var(--agent-source-color);
      box-shadow: 0 8px 18px rgba(16, 24, 40, 0.08);
      transform: translateY(-1px);
    }

    &.is-saas {
      --agent-source-color: #7a5af8;
      --agent-source-bg: #f3f0ff;
      --agent-source-border: #d8ccff;
      --agent-source-card-bg: #fcfbff;
    }

    &.is-workspace {
      --agent-source-color: #1570ef;
      --agent-source-bg: #eaf2ff;
      --agent-source-border: #b9d6ff;
      --agent-source-card-bg: #fbfdff;
    }

    &.is-personal {
      --agent-source-color: #12a076;
      --agent-source-bg: #e9f8f2;
      --agent-source-border: #a9e7d0;
      --agent-source-card-bg: #fbfffd;
    }

    .agent-card-head {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
      min-width: 0;
      margin-bottom: 8px;
    }

    .name-icon {
      display: flex;
      align-items: center;
      min-width: 0;
      flex: 1;

      .icon-primary {
        width: 28px;
        height: 28px;
        border-radius: 6px;
        background: #2f6de5;
        color: #ffffff;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        flex: 0 0 28px;

        :deep(svg) {
          width: 18px;
          height: 18px;
        }

        :deep(path) {
          fill: currentColor !important;
        }
      }

      .info {
        margin-left: 10px;
        min-width: 0;
        flex: 1;
      }

      .title-line {
        min-width: 0;
      }

      .agent-meta-row {
        display: flex;
        align-items: center;
        gap: 6px;
        min-width: 0;
        margin-top: 1px;
      }

      .agent-source-pill {
        flex: 0 0 auto;
        max-width: 84px;
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

      .name {
        min-width: 0;
        max-width: 100%;
        color: var(--workspace-text-primary, #1b2a41);
        font-weight: 600;
        font-size: 14px;
        line-height: 22px;
      }

      .sub-title {
        display: block;
        min-width: 0;
        color: var(--workspace-text-secondary, #66758f);
        font-weight: 400;
        font-size: 12px;
        line-height: 18px;
      }
    }

    .detail-list {
      flex: 0 0 auto;
      min-width: 0;
    }

    .agent-actions {
      flex: 0 0 auto;
      display: flex;
      align-items: center;
      gap: 8px;
      height: 24px;
    }

    .activation-switch,
    .visibility-switch {
      height: 22px;
      display: inline-flex;
      align-items: center;
      flex: 0 0 auto;
    }

    .icon-action {
      width: 22px;
      height: 22px;
      padding: 0;
      border: 0;
      background: transparent;
      color: #8a8f98;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;

      &:hover {
        color: #344054;
      }

      svg {
        width: 14px;
        height: 14px;
      }
    }

    .action-divider {
      width: 1px;
      height: 18px;
      background: #eceef3;
    }

    .type-value {
      display: flex;
      align-items: center;
      font-weight: 400;
      font-size: 12px;
      line-height: 18px;

      .type {
        color: var(--workspace-text-secondary, #66758f);
        flex: 0 0 86px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      .value {
        margin-left: 8px;
        min-width: 0;
        flex: 1;
        color: var(--workspace-text-primary, #1b2a41);
      }
    }

    .type-value + .type-value {
      margin-top: 2px;
    }

    .bottom-info {
      margin-top: auto;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      height: 20px;

      .form-rate {
        display: flex;
        align-items: center;
        min-width: 0;
        color: var(--workspace-text-secondary, #66758f);
        font-weight: 400;
        font-size: 12px;
        line-height: 18px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;

        .form-icon {
          margin-right: 6px;
          flex: 0 0 auto;
          color: var(--workspace-text-secondary, #66758f);
        }
      }

      .create-time {
        color: var(--workspace-text-secondary, #66758f);
        font-size: 12px;
        line-height: 18px;
        flex: 0 0 auto;
      }
    }
  }
}
</style>

<style lang="less">
.custom-agent-drawer {
  .fixed-project,
  .detail-content {
    width: 100%;
    color: #1f2329;
    line-height: 22px;
    word-break: break-word;
  }

  .fixed-project {
    padding: 8px 12px;
    border: 1px solid #dee0e3;
    border-radius: 6px;
    background: #f7faf9;
  }

  .datasource-scope-editor {
    width: 100%;

    .project-scope-mode {
      display: flex;
      width: 100%;
    }

    .project-scope-mode :deep(.ed-radio-button) {
      flex: 1;
    }

    .project-scope-mode :deep(.ed-radio-button__inner) {
      width: 100%;
    }

    .nested-datasource-form-item {
      margin-top: 8px;
      margin-bottom: 0;
    }

    .scope-mode-tip {
      margin-top: 8px;
      color: #646a73;
      font-size: 12px;
      line-height: 20px;
    }
  }

  .pre-wrap {
    white-space: pre-wrap;
  }

  .muted {
    color: #8f959e;
  }
}

.popover-card_agent.popover-card_agent.popover-card_agent {
  box-shadow: 0px 4px 8px 0px #1f23291a;
  border-radius: 6px;
  border: 1px solid #dee0e3;
  width: fit-content !important;
  min-width: 120px !important;
  padding: 0;

  .content {
    position: relative;

    .item {
      position: relative;
      padding: 0 12px;
      height: 40px;
      display: flex;
      align-items: center;
      cursor: pointer;

      .ed-icon {
        margin-right: 8px;
        color: #646a73;
      }

      &:hover {
        &::after {
          display: block;
        }
      }

      &::after {
        content: '';
        width: calc(100% - 8px);
        height: 32px;
        border-radius: 6px;
        position: absolute;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        background: #1f23291a;
        display: none;
      }
    }
  }
}
</style>
