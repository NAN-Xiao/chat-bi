<script lang="ts" setup>
import { computed, onMounted, reactive, ref } from 'vue'
import icon_export_outlined from '@/assets/svg/icon_export_outlined.svg'
import { promptApi } from '@/api/prompt'
import { formatTimestamp } from '@/utils/date'
import { datasourceApi } from '@/api/datasource'
import { modelApi } from '@/api/system'
import icon_add_outlined from '@/assets/svg/icon_add_outlined.svg'
import IconOpeEdit from '@/assets/svg/icon_edit_outlined.svg'
import icon_copy_outlined from '@/assets/embedded/icon_copy_outlined.svg'
import IconOpeDelete from '@/assets/svg/icon_delete.svg'
import icon_key_outlined from '@/assets/svg/icon-key_outlined.svg'
import icon_more_outlined from '@/assets/svg/icon_more_outlined.svg'
import icon_searchOutline_outlined from '@/assets/svg/icon_search-outline_outlined.svg'
import icon_ai from '@/assets/svg/icon_ai.svg'
import EmptyBackground from '@/views/dashboard/common/EmptyBackground.vue'
import { useClipboard } from '@vueuse/core'
import { useI18n } from 'vue-i18n'
import { cloneDeep } from 'lodash-es'
import { convertFilterText } from '@/components/filter-text'
import { DrawerMain } from '@/components/drawer-main'
import iconFilter from '@/assets/svg/icon-filter_outlined.svg'
import Uploader from '@/views/system/excel-upload/Uploader.vue'
import { useUserStore } from '@/stores/user'

interface AgentForm {
  id?: string | number | null
  type: string | null
  prompt: string | null
  description: string | null
  target_scope: string
  active: boolean
  ai_model_id: string | number | null
  ai_model_name: string | null
  can_manage?: boolean
  visibility_scope?: string
  specific_ds: boolean
  datasource_ids: number[]
  datasource_names: string[]
  name: string | null
}

const drawerMainRef = ref()
const { t } = useI18n()
const { copy } = useClipboard({ legacy: true })
const userStore = useUserStore()
const isPlatformAdmin = computed(() => userStore.isSystemAdminUser)

const keywords = ref('')
const oldKeywords = ref('')
const searchLoading = ref(false)
const currentType = ref('GENERATE_SQL')
const options = ref<any[]>([])
const aiModelOptions = ref<any[]>([])
const fieldList = ref<any[]>([])
const dialogFormVisible = ref(false)
const rowInfoDialog = ref(false)
const termFormRef = ref()
const updateLoading = ref(false)
const dialogTitle = ref('')

const pageInfo = reactive({
  currentPage: 1,
  pageSize: 10,
  total: 0,
})

const state = reactive<any>({
  conditions: [],
  filterTexts: [],
})

const defaultForm: AgentForm = {
  id: null,
  type: null,
  prompt: null,
  description: null,
  target_scope: 'SMART_QA',
  active: false,
  ai_model_id: null,
  ai_model_name: null,
  datasource_ids: [],
  datasource_names: [],
  name: null,
  specific_ds: false,
}
const pageForm = ref<AgentForm>(cloneDeep(defaultForm))

const filterOption = ref<any[]>([
  {
    type: 'select',
    option: [],
    field: 'dslist',
    title: t('ds.title'),
    operate: 'in',
    property: { placeholder: t('common.empty') + t('ds.title') },
  },
])

const typeTitle = (type = currentType.value) => {
  if (type === 'GENERATE_SQL') return t('prompt.ask_sql')
  if (type === 'ANALYSIS') return t('prompt.data_analysis')
  if (type === 'PREDICT_DATA') return t('prompt.data_prediction')
  return ''
}

const loadDatasources = () => {
  if (isPlatformAdmin.value) {
    options.value = []
    filterOption.value[0].option = []
    return
  }
  datasourceApi.accessibleList().then((res: any) => {
    options.value = res || []
    filterOption.value[0].option = [...(res || [])]
  })
}

const loadAiModels = () => {
  modelApi.listAvailable().then((res: any) => {
    aiModelOptions.value = res || []
  })
}

onMounted(() => {
  loadDatasources()
  loadAiModels()
  search()
})

const getFileName = () => `${typeTitle()}.xlsx`

const configParams = () => {
  const params = new URLSearchParams()
  params.set('visibility_scope', isPlatformAdmin.value ? 'PLATFORM_PUBLIC' : 'ADMIN_PUBLIC')
  if (keywords.value) {
    params.set('name', keywords.value)
  }

  state.conditions.forEach((ele: any) => {
    ele.value.forEach((itx: any) => {
      params.append(ele.field, String(itx))
    })
  })

  const query = params.toString()
  return query ? `?${query}` : ''
}

const search = ($event: any = {}) => {
  if ($event?.isComposing) {
    return
  }
  searchLoading.value = true
  oldKeywords.value = keywords.value
  promptApi
    .getList(pageInfo.currentPage, pageInfo.pageSize, currentType.value, configParams())
    .then((res: any) => {
      fieldList.value = res.data
      pageInfo.total = res.total_count
    })
    .finally(() => {
      searchLoading.value = false
    })
}

const exportExcel = () => {
  const title = typeTitle()
  ElMessageBox.confirm(t('prompt.export_hint', { msg: pageInfo.total, type: title }), {
    confirmButtonType: 'primary',
    confirmButtonText: t('professional.export'),
    cancelButtonText: t('common.cancel'),
    customClass: 'confirm-no_icon',
    autofocus: false,
  }).then(() => {
    searchLoading.value = true
    const params: Record<string, string> = {}
    params.visibility_scope = isPlatformAdmin.value ? 'PLATFORM_PUBLIC' : 'ADMIN_PUBLIC'
    if (keywords.value) {
      params.name = keywords.value
    }
    promptApi
      .export2Excel(currentType.value, params)
      .then((res) => {
        const blob = new Blob([res], {
          type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        const link = document.createElement('a')
        link.href = URL.createObjectURL(blob)
        link.download = `${title}.xlsx`
        document.body.appendChild(link)
        link.click()
        document.body.removeChild(link)
      })
      .catch(async (error) => {
        if (error.response) {
          try {
            let text = await error.response.data.text()
            try {
              text = JSON.parse(text)
            } finally {
              ElMessage({
                message: text,
                type: 'error',
                showClose: true,
              })
            }
          } catch (e) {
            console.error('Error processing error response:', e)
          }
        } else {
          ElMessage({
            message: error,
            type: 'error',
            showClose: true,
          })
        }
      })
      .finally(() => {
        searchLoading.value = false
      })
  })
}

const deleteHandler = (row: any) => {
  ElMessageBox.confirm(t('prompt.prompt_word_name_de', { msg: row.name }), {
    confirmButtonType: 'danger',
    confirmButtonText: t('dashboard.delete'),
    cancelButtonText: t('common.cancel'),
    customClass: 'confirm-no_icon',
    autofocus: false,
  }).then(() => {
    promptApi.deleteEmbedded([row.id]).then(() => {
      ElMessage({
        type: 'success',
        message: t('dashboard.delete_success'),
      })
      search()
    })
  })
}

const validateDatasource = (_: any, value: any, callback: any) => {
  if (pageForm.value.specific_ds && !value.length) {
    callback(new Error(t('datasource.Please_select') + t('common.empty') + t('ds.title')))
  } else {
    callback()
  }
}

const rules = {
  name: [
    {
      required: true,
      message: t('datasource.please_enter') + t('common.empty') + t('prompt.prompt_word_name'),
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
    },
  ],
}

const saveHandler = () => {
  termFormRef.value.validate((res: any) => {
    if (res) {
      const obj = cloneDeep(pageForm.value)
      if (isPlatformAdmin.value) {
        obj.visibility_scope = 'PLATFORM_PUBLIC'
        obj.specific_ds = false
        obj.datasource_ids = []
      }
      if (!obj.id) {
        delete obj.id
      }
      updateLoading.value = true
      promptApi
        .updateEmbedded(obj)
        .then(() => {
          ElMessage({
            type: 'success',
            message: t('common.save_success'),
          })
          search()
          onFormClose()
        })
        .finally(() => {
          updateLoading.value = false
        })
    }
  })
}

const editHandler = (row: any) => {
  pageForm.value = cloneDeep(defaultForm)
  pageForm.value.type = currentType.value
  if (row) {
    pageForm.value = cloneDeep({
      description: null,
      target_scope: 'SMART_QA',
      active: false,
      ai_model_id: null,
      ai_model_name: null,
      ...row,
    })
  }
  loadDatasources()
  loadAiModels()
  dialogTitle.value = row?.id ? t('prompt.edit_prompt_word') : t('prompt.add_prompt_word')
  dialogFormVisible.value = true
}

const onFormClose = () => {
  pageForm.value = cloneDeep(defaultForm)
  dialogFormVisible.value = false
}

const handleSizeChange = (val: number) => {
  pageInfo.currentPage = 1
  pageInfo.pageSize = val
  search()
}

const handleCurrentChange = (val: number) => {
  pageInfo.currentPage = val
  search()
}

const handleRowClick = (row: any) => {
  pageForm.value = cloneDeep({
    description: null,
    target_scope: 'SMART_QA',
    active: false,
    ai_model_id: null,
    ai_model_name: null,
    ...row,
  })
  rowInfoDialog.value = true
}

const onRowFormClose = () => {
  pageForm.value = cloneDeep(defaultForm)
  rowInfoDialog.value = false
}

const handleDatasourceChange = () => {
  termFormRef.value.validateField('datasource_ids')
}

const typeChange = (val: string) => {
  currentType.value = val
  pageInfo.currentPage = 1
  search()
}

const fillFilterText = () => {
  const textArray = state.conditions?.length
    ? convertFilterText(state.conditions, filterOption.value)
    : []
  state.filterTexts = [...textArray]
  Object.assign(state.filterTexts, textArray)
}

const searchCondition = (conditions: any) => {
  state.conditions = conditions
  fillFilterText()
  pageInfo.currentPage = 1
  search()
  drawerMainClose()
}

const clearFilter = (params?: number) => {
  const index = params ? params : 0
  if (isNaN(index)) {
    state.filterTexts = []
  } else {
    state.filterTexts.splice(index, 1)
  }
  drawerMainRef.value.clearFilter(index)
}

const drawerMainOpen = async () => {
  drawerMainRef.value.init()
}

const drawerMainClose = () => {
  drawerMainRef.value.close()
}

const scopeText = (row: any) => {
  if (row.specific_ds) {
    return row.datasource_names?.length
      ? row.datasource_names.join(', ')
      : t('training.partial_data_sources')
  }
  return t('training.all_data_sources')
}

const modelText = (row: any) => {
  return row.ai_model_name || t('prompt.default_ai_model')
}

const targetScopeText = (scope?: string | null) => {
  if (scope === 'ANALYSIS_ASSISTANT') return t('prompt.target_scope_analysis_assistant')
  if (scope === 'ALL') return t('prompt.target_scope_all')
  return t('prompt.target_scope_smart_qa')
}

const canManageAgent = (row: any) => {
  return row.can_manage === true
}

const copyCode = () => {
  copy(pageForm.value.prompt || '')
    .then(() => {
      ElMessage.success(t('embedded.copy_successful'))
    })
    .catch(() => {
      ElMessage.error(t('embedded.copy_failed'))
    })
}
</script>

<template>
  <div class="prompt">
    <div class="tool-left">
      <div class="btn-select">
        <el-button
          :class="[currentType === 'GENERATE_SQL' && 'is-active']"
          text
          @click="typeChange('GENERATE_SQL')"
        >
          {{ $t('prompt.ask_sql') }}
        </el-button>
        <el-button
          :class="[currentType === 'ANALYSIS' && 'is-active']"
          text
          @click="typeChange('ANALYSIS')"
        >
          {{ $t('prompt.data_analysis') }}
        </el-button>
        <el-button
          :class="[currentType === 'PREDICT_DATA' && 'is-active']"
          text
          @click="typeChange('PREDICT_DATA')"
        >
          {{ $t('prompt.data_prediction') }}
        </el-button>
      </div>
      <div class="tool-row">
        <el-input
          v-model="keywords"
          style="width: 240px"
          :placeholder="$t('dashboard.search')"
          clearable
          @keydown.enter.exact.prevent="search"
        >
          <template #prefix>
            <el-icon>
              <icon_searchOutline_outlined />
            </el-icon>
          </template>
        </el-input>
        <el-button secondary @click="exportExcel">
          <template #icon>
            <icon_export_outlined />
          </template>
          {{ $t('professional.export_all') }}
        </el-button>
        <Uploader
          :upload-path="`/system/custom_prompt/${currentType}/uploadExcel`"
          :template-path="`/system/custom_prompt/template`"
          :template-name="getFileName()"
          @upload-finished="search"
        />
        <el-button v-if="!isPlatformAdmin" class="no-margin" secondary @click="drawerMainOpen">
          <template #icon>
            <iconFilter></iconFilter>
          </template>
          {{ $t('user.filter') }}
        </el-button>
        <el-button class="no-margin" type="primary" @click="editHandler(null)">
          <template #icon>
            <icon_add_outlined></icon_add_outlined>
          </template>
          {{ $t('prompt.add_prompt_word') }}
        </el-button>
      </div>
    </div>

    <div v-loading="searchLoading" class="agent-content">
      <filter-text
        :total="pageInfo.total"
        :filter-texts="state.filterTexts"
        @clear-filter="clearFilter"
      />

      <div v-if="fieldList.length" class="card-content">
        <el-row :gutter="16" class="w-full">
          <el-col
            v-for="item in fieldList"
            :key="item.id"
            :xs="24"
            :sm="12"
            :md="12"
            :lg="8"
            :xl="6"
            class="mb-16"
          >
            <article class="agent-card" @click="handleRowClick(item)">
              <div class="name-icon">
                <el-icon class="icon-primary" size="32">
                  <icon_ai></icon_ai>
                </el-icon>
                <div class="info">
                  <div class="name ellipsis" :title="item.name">{{ item.name }}</div>
                  <div class="sub-title">{{ typeTitle(item.type) }}</div>
                </div>
              </div>

              <div class="detail-list">
                <div class="type-value">
                  <span class="type">{{ $t('prompt.agent_description') }}</span>
                  <span class="value ellipsis" :title="item.description || $t('prompt.agent_empty_description')">
                    {{ item.description || $t('prompt.agent_empty_description') }}
                  </span>
                </div>
                <div class="type-value">
                  <span class="type">{{ $t('prompt.ai_model') }}</span>
                  <span class="value ellipsis" :title="modelText(item)">{{ modelText(item) }}</span>
                </div>
                <div class="type-value">
                  <span class="type">{{ $t('prompt.target_scope') }}</span>
                  <span class="value ellipsis" :title="targetScopeText(item.target_scope)">
                    {{ targetScopeText(item.target_scope) }}
                  </span>
                </div>
                <div class="type-value">
                  <span class="type">{{ $t('prompt.active_status') }}</span>
                  <span class="value" :class="item.active ? 'is-active-status' : 'is-inactive-status'">
                    {{ item.active ? $t('prompt.active_enabled') : $t('prompt.active_disabled') }}
                  </span>
                </div>
                <div class="type-value">
                  <span class="type">{{ $t('training.effective_data_sources') }}</span>
                  <span class="value ellipsis" :title="scopeText(item)">{{ scopeText(item) }}</span>
                </div>
              </div>

              <div class="bottom-info">
                <div class="form-rate">
                  <el-icon class="form-icon" size="14">
                    <icon_key_outlined></icon_key_outlined>
                  </el-icon>
                  {{ typeTitle(item.type) }}
                </div>
                <div class="create-time">
                  {{ formatTimestamp(item.create_time, 'YYYY-MM-DD HH:mm:ss') }}
                </div>
                <div v-if="canManageAgent(item)" class="methods" @click.stop>
                  <el-popover
                    trigger="click"
                    :teleported="true"
                    popper-class="popover-card_agent"
                    placement="bottom-end"
                  >
                    <template #reference>
                      <button type="button" class="more" aria-label="more actions">
                        <icon_more_outlined></icon_more_outlined>
                      </button>
                    </template>
                    <div class="content">
                      <div class="item" @click.stop="editHandler(item)">
                        <el-icon size="16">
                          <IconOpeEdit></IconOpeEdit>
                        </el-icon>
                        {{ $t('datasource.edit') }}
                      </div>
                      <div class="item" @click.stop="deleteHandler(item)">
                        <el-icon size="16">
                          <IconOpeDelete></IconOpeDelete>
                        </el-icon>
                        {{ $t('dashboard.delete') }}
                      </div>
                    </div>
                  </el-popover>
                </div>
              </div>
            </article>
          </el-col>
        </el-row>
      </div>

      <template v-else-if="!searchLoading">
        <EmptyBackground
          v-if="!!oldKeywords"
          :description="$t('datasource.relevant_content_found')"
          img-type="tree"
        />
        <template v-else>
          <EmptyBackground
            class="datasource-yet"
            :description="$t('prompt.no_prompt_words')"
            img-type="noneWhite"
          />
        </template>
      </template>
    </div>

    <div v-if="fieldList.length" class="pagination-container">
      <el-pagination
        v-model:current-page="pageInfo.currentPage"
        v-model:page-size="pageInfo.pageSize"
        :page-sizes="[10, 20, 30]"
        :background="true"
        layout="total, sizes, prev, pager, next, jumper"
        :total="pageInfo.total"
        @size-change="handleSizeChange"
        @current-change="handleCurrentChange"
      />
    </div>
  </div>

  <el-drawer
    v-model="dialogFormVisible"
    :title="dialogTitle"
    destroy-on-close
    size="600px"
    :before-close="onFormClose"
    modal-class="prompt-add_drawer"
  >
    <el-form
      ref="termFormRef"
      :model="pageForm"
      label-width="180px"
      label-position="top"
      :rules="rules"
      class="form-content_error"
      @submit.prevent
    >
      <el-form-item prop="name" :label="t('prompt.prompt_word_name')">
        <el-input
          v-model="pageForm.name"
          :placeholder="
            $t('datasource.please_enter') + $t('common.empty') + $t('prompt.prompt_word_name')
          "
          autocomplete="off"
          maxlength="50"
          clearable
        />
      </el-form-item>

      <el-form-item prop="description" :label="t('prompt.agent_description')">
        <el-input
          v-model="pageForm.description"
          :placeholder="$t('prompt.agent_description_placeholder')"
          :autosize="{ minRows: 2, maxRows: 4 }"
          type="textarea"
        />
      </el-form-item>

      <el-form-item prop="ai_model_id" :label="t('prompt.ai_model')">
        <el-select
          v-model="pageForm.ai_model_id"
          clearable
          filterable
          :placeholder="$t('prompt.select_ai_model_placeholder')"
          style="width: 100%"
        >
          <el-option :label="$t('prompt.default_ai_model')" :value="null" />
          <el-option
            v-for="item in aiModelOptions"
            :key="item.id"
            :label="item.default_model ? `${item.name}（${$t('prompt.default_ai_model')}）` : item.name"
            :value="item.id"
          />
        </el-select>
      </el-form-item>

      <el-form-item prop="target_scope" :label="t('prompt.target_scope')">
        <el-radio-group v-model="pageForm.target_scope">
          <el-radio :value="'SMART_QA'">{{ $t('prompt.target_scope_smart_qa') }}</el-radio>
          <el-radio :value="'ANALYSIS_ASSISTANT'">
            {{ $t('prompt.target_scope_analysis_assistant') }}
          </el-radio>
          <el-radio :value="'ALL'">{{ $t('prompt.target_scope_all') }}</el-radio>
        </el-radio-group>
      </el-form-item>

      <el-form-item prop="active" :label="t('prompt.active_status')">
        <el-switch
          v-model="pageForm.active"
          :active-text="$t('prompt.active_enabled')"
          :inactive-text="$t('prompt.active_disabled')"
        />
        <div class="tips">
          {{ t('prompt.active_hint') }}
        </div>
      </el-form-item>

      <el-form-item prop="prompt" :label="t('prompt.prompt_word_content')">
        <el-input
          v-model="pageForm.prompt"
          :placeholder="$t('prompt.replaced_with')"
          :autosize="{ minRows: 6, maxRows: 14 }"
          type="textarea"
        />
        <div class="tips">
          {{ t('prompt.loss_exercise_caution') }}
        </div>
      </el-form-item>

      <el-form-item v-if="isPlatformAdmin" :label="t('training.effective_data_sources')">
        <div class="content">{{ t('training.all_data_sources') }}</div>
      </el-form-item>

      <el-form-item
        v-else
        class="is-required"
        :class="!pageForm.specific_ds && 'no-error'"
        prop="datasource_ids"
        :label="t('training.effective_data_sources')"
      >
        <el-radio-group v-model="pageForm.specific_ds">
          <el-radio :value="false">{{ $t('training.all_data_sources') }}</el-radio>
          <el-radio :value="true">{{ $t('training.partial_data_sources') }}</el-radio>
        </el-radio-group>
        <el-select
          v-if="pageForm.specific_ds"
          v-model="pageForm.datasource_ids"
          multiple
          filterable
          :placeholder="$t('datasource.Please_select') + $t('common.empty') + $t('ds.title')"
          style="width: 100%; margin-top: 8px"
          @change="handleDatasourceChange"
        >
          <el-option v-for="item in options" :key="item.id" :label="item.name" :value="item.id" />
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <div v-loading="updateLoading" class="dialog-footer">
        <el-button secondary @click="onFormClose">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" @click="saveHandler">
          {{ $t('common.save') }}
        </el-button>
      </div>
    </template>
  </el-drawer>

  <el-drawer
    v-model="rowInfoDialog"
    :title="$t('menu.Details')"
    destroy-on-close
    size="600px"
    :before-close="onRowFormClose"
    modal-class="prompt-term_drawer"
  >
    <el-form label-width="180px" label-position="top" class="form-content_error" @submit.prevent>
      <el-form-item :label="t('prompt.prompt_word_name')">
        <div class="content">
          {{ pageForm.name }}
        </div>
      </el-form-item>
      <el-form-item :label="t('prompt.agent_description')">
        <div class="content">
          {{ pageForm.description || t('prompt.agent_empty_description') }}
        </div>
      </el-form-item>
      <el-form-item :label="t('prompt.ai_model')">
        <div class="content">
          {{ modelText(pageForm) }}
        </div>
      </el-form-item>
      <el-form-item :label="t('prompt.target_scope')">
        <div class="content">
          {{ targetScopeText(pageForm.target_scope) }}
        </div>
      </el-form-item>
      <el-form-item :label="t('prompt.active_status')">
        <div class="content">
          {{ pageForm.active ? t('prompt.active_enabled') : t('prompt.active_disabled') }}
        </div>
      </el-form-item>
      <el-form-item :label="t('prompt.prompt_word_content')">
        <div style="white-space: pre-wrap" class="content">
          {{ pageForm.prompt }}
        </div>
        <div class="copy-icon">
          <el-tooltip :offset="12" effect="dark" :content="t('datasource.copy')" placement="top">
            <el-icon class="hover-icon_with_bg" style="cursor: pointer" size="16" @click="copyCode">
              <icon_copy_outlined></icon_copy_outlined>
            </el-icon>
          </el-tooltip>
        </div>
      </el-form-item>
      <el-form-item :label="t('ds.title')">
        <div class="content">
          {{
            pageForm.datasource_names.length && pageForm.specific_ds
              ? pageForm.datasource_names.join(', ')
              : t('training.all_data_sources')
          }}
        </div>
      </el-form-item>
    </el-form>
  </el-drawer>

  <drawer-main
    ref="drawerMainRef"
    :filter-options="filterOption"
    @trigger-filter="searchCondition"
  />
</template>

<style lang="less" scoped>
.no-margin {
  margin: 0;
}

.prompt {
  height: 100%;
  position: relative;
  display: flex;
  flex-direction: column;
  min-height: 0;

  .datasource-yet {
    padding-bottom: 0;
    height: auto;
    padding-top: 160px;
  }

  .tool-left {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 16px;

    .btn-select {
      height: 32px;
      display: inline-flex;
      padding: 0 4px;
      align-items: center;
      justify-content: center;
      background: #ffffff;
      border: 1px solid var(--ed-border-color);
      border-radius: 6px;
      flex: none;

      .is-active {
        background: var(--ed-color-primary-1a, #1cba901a);
        font-weight: 500;
      }

      .ed-button:not(.is-active) {
        color: #1f2329;
      }

      .ed-button.is-text {
        height: 24px;
        padding: 0 8px;
        line-height: 22px;
      }

      .ed-button + .ed-button {
        margin-left: 4px;
      }
    }
  }

  .tool-row {
    display: flex;
    align-items: center;
    flex-direction: row;
    gap: 8px;
    flex-wrap: wrap;
    justify-content: flex-end;
  }

  .agent-content {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding-bottom: 2px;
  }

  .card-content {
    padding-top: 12px;

    .w-full {
      width: 100%;
    }

    .mb-16 {
      margin-bottom: 16px;
    }
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

      .name {
        font-weight: 500;
        font-size: 16px;
        line-height: 24px;
        max-width: 100%;
        color: var(--workspace-text-primary, #1b2a41);
      }

      .sub-title {
        font-weight: 400;
        font-size: 12px;
        line-height: 20px;
        color: var(--workspace-text-secondary, #66758f);
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

  .pagination-container {
    display: flex;
    justify-content: end;
    align-items: center;
    margin-top: 16px;
  }
}
</style>

<style lang="less">
.prompt-term_drawer {
  .ed-form-item--label-top .ed-form-item__label {
    margin-bottom: 4px;
  }

  .ed-form-item__label {
    color: #646a73;
  }

  .content {
    width: 100%;
    line-height: 22px;
    word-break: break-all;
  }

  .copy-icon {
    position: absolute;
    right: 0;
    top: -27px;
  }
}

.prompt-add_drawer {
  .tips {
    font-weight: 400;
    font-size: 14px;
    line-height: 22px;
    color: #ff8800;
  }

  .no-error.no-error {
    .ed-form-item__error {
      display: none;
    }
    margin-bottom: 16px;
  }

  .ed-textarea__inner {
    line-height: 22px;
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
