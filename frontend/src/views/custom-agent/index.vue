<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { cloneDeep } from 'lodash-es'
import { Search } from '@element-plus/icons-vue'
import { useDatasourceContextStore } from '@/stores/datasourceContext'
import { promptApi } from '@/api/prompt'
import { modelApi } from '@/api/system'
import icon_ai from '@/assets/svg/icon_ai.svg'
import icon_add_outlined from '@/assets/svg/icon_add_outlined.svg'
import IconOpeEdit from '@/assets/svg/icon_edit_outlined.svg'
import IconOpeDelete from '@/assets/svg/icon_delete.svg'
import icon_key_outlined from '@/assets/svg/icon-key_outlined.svg'
import icon_more_outlined from '@/assets/svg/icon_more_outlined.svg'
import { formatTimestamp } from '@/utils/date'

const { t } = useI18n()
const datasourceContext = useDatasourceContextStore()

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

const defaultAgentForm = {
  id: null as number | string | null,
  type: 'GENERATE_SQL',
  name: '',
  description: '',
  target_scope: 'SMART_QA',
  active: true,
  ai_model_id: null as number | string | null,
  prompt: '',
  specific_ds: false,
  datasource_ids: [] as number[],
  visibility_scope: 'USER_PRIVATE',
}
const agentForm = ref(cloneDeep(defaultAgentForm))

const currentDatasourceId = computed(() => datasourceContext.datasourceId)
const currentDatasourceName = computed(() => datasourceContext.datasourceName)

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
  if (row?.visibility_scope === 'USER_PRIVATE' && row?.is_owner) return t('access.my_agent')
  return t('access.admin_agent')
}

const scopeText = (row: any) => {
  if (row?.visibility_scope === 'USER_PRIVATE') return t('access.user_permission_scope')
  if (row?.specific_ds) {
    return row.datasource_names?.length
      ? row.datasource_names.join('、')
      : t('training.partial_data_sources')
  }
  return t('training.all_data_sources')
}

const isVisibleInPersonalEntry = (row: any) => {
  return row?.visibility_scope !== 'USER_PRIVATE' || row?.is_owner === true
}

const canManageAgent = (row: any) => {
  return row?.visibility_scope === 'USER_PRIVATE' && row?.is_owner === true
}

const canViewPromptInPersonalEntry = (row: any) => {
  return row?.prompt_visible === true || (row?.visibility_scope === 'USER_PRIVATE' && row?.is_owner === true)
}

const buildAgentQuery = () => {
  const params = new URLSearchParams()
  if (currentDatasourceId.value) {
    params.append('dslist', String(currentDatasourceId.value))
  }
  if (agentKeyword.value.trim()) {
    params.append('name', agentKeyword.value.trim())
  }
  const query = params.toString()
  return query ? `?${query}` : ''
}

const loadAiModels = () => {
  modelApi.listAvailable().then((res: any) => {
    aiModelOptions.value = res || []
  })
}

const loadAgents = async () => {
  agentLoading.value = true
  try {
    const query = buildAgentQuery()
    const responses = await Promise.all(
      CUSTOM_PROMPT_TYPES.map((type) =>
        promptApi.getList(1, 100, type, query).catch(() => ({ data: [] }))
      )
    )
    agentList.value = responses
      .flatMap((res: any) => res?.data || [])
      .filter(isVisibleInPersonalEntry)
      .sort((a: any, b: any) => {
        const left = a.create_time ? new Date(a.create_time).getTime() : 0
        const right = b.create_time ? new Date(b.create_time).getTime() : 0
        return right - left
      })
  } finally {
    agentLoading.value = false
  }
}

const resetAgentForm = () => {
  agentForm.value = {
    ...cloneDeep(defaultAgentForm),
    specific_ds: false,
    datasource_ids: [],
    visibility_scope: 'USER_PRIVATE',
  }
}

const openCreateAgent = () => {
  resetAgentForm()
  agentDialogTitle.value = t('prompt.add_prompt_word')
  agentDialogVisible.value = true
}

const openEditAgent = (row: any) => {
  if (!canManageAgent(row)) return
  agentForm.value = {
    ...cloneDeep(defaultAgentForm),
    ...cloneDeep(row),
    specific_ds: false,
    datasource_ids: [],
    visibility_scope: 'USER_PRIVATE',
  }
  agentDialogTitle.value = t('prompt.edit_prompt_word')
  agentDialogVisible.value = true
}

const closeAgentForm = () => {
  agentDialogVisible.value = false
  resetAgentForm()
}

const saveAgent = () => {
  agentFormRef.value?.validate((valid: boolean) => {
    if (!valid || savingAgent.value) return
    const payload = cloneDeep(agentForm.value)
    payload.type = payload.type || 'GENERATE_SQL'
    payload.specific_ds = false
    payload.datasource_ids = []
    payload.visibility_scope = 'USER_PRIVATE'
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

onMounted(async () => {
  await datasourceContext.loadDatasources()
  loadAiModels()
  loadAgents()
})

watch(currentDatasourceId, () => {
  loadAgents()
})

watch(agentKeyword, () => {
  loadAgents()
})
</script>

<template>
  <div class="custom-agent-page">
    <div class="page-header">
      <div>
        <div class="page-title">{{ t('access.custom_agents') }}</div>
        <div class="page-subtitle">
          {{ t('access.current_project') }}：{{ currentDatasourceName || '-' }}
        </div>
      </div>
      <div class="page-actions">
        <el-input
          v-model="agentKeyword"
          clearable
          class="agent-search"
          :prefix-icon="Search"
          :placeholder="t('dashboard.search')"
        />
        <el-button type="primary" @click="openCreateAgent">
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
            <el-row :gutter="16" class="w-full">
              <el-col
                v-for="agent in agentList"
                :key="agent.id"
                :xs="24"
                :sm="12"
                :md="12"
                :lg="8"
                :xl="6"
                class="mb-16"
              >
                <article class="agent-card" @click="openAgentDetail(agent)">
                  <div class="name-icon">
                    <el-icon class="icon-primary" size="32">
                      <icon_ai />
                    </el-icon>
                    <div class="info">
                      <div class="title-line">
                        <span class="name ellipsis" :title="agent.name">{{ agent.name }}</span>
                        <el-tag size="small" effect="plain" round>
                          {{ sourceText(agent) }}
                        </el-tag>
                      </div>
                      <div class="sub-title">{{ typeTitle(agent.type) }}</div>
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
                      <span class="type">{{ t('prompt.active_status') }}</span>
                      <span
                        class="value"
                        :class="agent.active ? 'is-active-status' : 'is-inactive-status'"
                      >
                        {{ agent.active ? t('prompt.active_enabled') : t('prompt.active_disabled') }}
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
                      <el-icon class="form-icon" size="14">
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
                    <div v-if="canManageAgent(agent)" class="methods" @click.stop>
                      <el-popover
                        trigger="click"
                        :teleported="true"
                        popper-class="popover-card_agent"
                        placement="bottom-end"
                      >
                        <template #reference>
                          <button type="button" class="more" aria-label="more actions">
                            <icon_more_outlined />
                          </button>
                        </template>
                        <div class="content">
                          <div class="item" @click.stop="openEditAgent(agent)">
                            <el-icon size="16">
                              <IconOpeEdit />
                            </el-icon>
                            {{ t('datasource.edit') }}
                          </div>
                          <div class="item" @click.stop="deleteAgent(agent)">
                            <el-icon size="16">
                              <IconOpeDelete />
                            </el-icon>
                            {{ t('dashboard.delete') }}
                          </div>
                        </div>
                      </el-popover>
                    </div>
                  </div>
                </article>
              </el-col>
            </el-row>
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
  padding: 8px 0 24px;
  color: #1f2329;

  .page-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 16px;
  }

  .page-title {
    font-weight: 600;
    font-size: 22px;
    line-height: 30px;
  }

  .page-subtitle {
    margin-top: 6px;
    color: #646a73;
    font-size: 14px;
    line-height: 22px;
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
    .w-full {
      width: 100%;
    }

    .mb-16 {
      margin-bottom: 16px;
    }
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

  .agent-card {
    width: 100%;
    height: 246px;
    border: 1px solid var(--workspace-border, #e2eaf4);
    padding: 16px 54px 20px 16px;
    border-radius: 8px;
    background: #ffffff;
    box-shadow: 0 12px 28px rgba(24, 46, 86, 0.07);
    cursor: pointer;
    display: flex;
    flex-direction: column;
    position: relative;
    transition:
      box-shadow 0.12s ease,
      transform 0.12s ease,
      border-color 0.12s ease;

    &:hover {
      border-color: var(--workspace-border, #e2eaf4);
      box-shadow: 0 16px 36px rgba(24, 46, 86, 0.11);
      transform: translateY(-2px) scale(1.012);
    }

    .name-icon {
      display: flex;
      align-items: center;
      margin-bottom: 12px;

      .icon-primary {
        width: 32px;
        height: 32px;
        border-radius: 6px;
        background: #2f6de5;
        color: #ffffff;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        flex: 0 0 32px;

        :deep(svg) {
          width: 20px;
          height: 20px;
        }

        :deep(path) {
          fill: currentColor !important;
        }
      }

      .info {
        margin-left: 12px;
        max-width: calc(100% - 50px);
        min-width: 0;
      }

      .title-line {
        display: flex;
        align-items: center;
        gap: 8px;
        min-width: 0;
      }

      .name {
        min-width: 0;
        max-width: 100%;
        color: var(--workspace-text-primary, #1b2a41);
        font-weight: 500;
        font-size: 16px;
        line-height: 24px;
      }

      .sub-title {
        color: var(--workspace-text-secondary, #66758f);
        font-weight: 400;
        font-size: 12px;
        line-height: 20px;
      }
    }

    .detail-list {
      flex: 0 0 auto;
      min-width: 0;
    }

    .type-value {
      display: flex;
      align-items: center;
      font-weight: 400;
      font-size: 14px;
      line-height: 22px;

      .type {
        color: var(--workspace-text-secondary, #66758f);
        flex: 0 0 86px;
        white-space: nowrap;
      }

      .value {
        margin-left: 16px;
        min-width: 0;
        flex: 1;
        color: var(--workspace-text-primary, #1b2a41);

        &.is-active-status {
          color: var(--ed-color-primary, #1cba90);
        }

        &.is-inactive-status {
          color: var(--workspace-text-tertiary, #8a97aa);
        }
      }
    }

    .type-value + .type-value {
      margin-top: 6px;
    }

    .bottom-info {
      margin-top: auto;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      height: 22px;

      .form-rate {
        display: flex;
        align-items: center;
        min-width: 0;
        color: var(--workspace-text-secondary, #66758f);
        font-weight: 400;
        font-size: 14px;
        line-height: 22px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;

        .form-icon {
          margin-right: 10px;
          flex: 0 0 auto;
          color: var(--workspace-text-secondary, #66758f);
        }
      }

      .create-time {
        color: var(--workspace-text-secondary, #66758f);
        font-size: 12px;
        line-height: 20px;
        flex: 0 0 auto;
      }

      .methods {
        position: absolute;
        right: 16px;
        top: 16px;
        align-items: center;
        display: flex;

        .more {
          border: 0;
          padding: 0;
          color: var(--workspace-text-secondary, #66758f);
          background: transparent;
          appearance: none;
          line-height: 1;
          position: relative;
          cursor: pointer;
          width: 28px;
          height: 28px;
          flex: 0 0 28px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          transition:
            color 0.16s ease,
            transform 0.16s ease;

          svg {
            position: relative;
            z-index: 10;
          }

          &::after {
            content: '';
            position: absolute;
            border-radius: 8px;
            width: 28px;
            height: 28px;
            transform: translate(-50%, -50%);
            top: 50%;
            left: 50%;
            background: var(--workspace-control-bg, #f7faff);
            border: 1px solid var(--workspace-border-soft, #eff4fa);
            box-shadow: 0 1px 2px rgba(24, 46, 86, 0.05);
            transition:
              background-color 0.16s ease,
              border-color 0.16s ease,
              box-shadow 0.16s ease;
          }

          &:hover {
            color: var(--workspace-text-primary, #1b2a41);
            transform: translateY(-1px);

            &::after {
              background-color: var(--workspace-control-hover-bg, #edf3ff);
              border-color: var(--workspace-border, #e2eaf4);
              box-shadow: 0 4px 10px rgba(24, 46, 86, 0.08);
            }
          }

          &:focus-visible {
            outline: none;
          }
        }
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
