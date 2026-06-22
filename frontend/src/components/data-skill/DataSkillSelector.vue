<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { cloneDeep } from 'lodash-es'
import { Search } from '@element-plus/icons-vue'
import { dataSkillApi } from '@/api/dataSkill'
import icon_ai from '@/assets/svg/icon_ai.svg'
import icon_add_outlined from '@/assets/svg/icon_add_outlined.svg'
import IconOpeEdit from '@/assets/svg/icon_edit_outlined.svg'

const props = withDefaults(
  defineProps<{
    modelValue?: string | number | null
    targetScope?: 'SMART_QA' | 'ANALYSIS_ASSISTANT' | 'ALL' | string
    datasourceId?: string | number | null
    datasourceName?: string
    disabled?: boolean
  }>(),
  {
    modelValue: null,
    targetScope: 'SMART_QA',
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
const skillList = ref<any[]>([])
const loading = ref(false)
const skillFormRef = ref()
const skillDialogVisible = ref(false)
const skillDialogTitle = ref('')
const savingSkill = ref(false)

const defaultSkillForm = {
  id: null as number | string | null,
  type: 'DATA_SKILL',
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
const skillForm = ref(cloneDeep(defaultSkillForm))

const skillRules = {
  name: [
    {
      required: true,
      message: t('datasource.please_enter') + t('common.empty') + t('data_skill.skill_name'),
      trigger: 'blur',
    },
  ],
  prompt: [
    {
      required: true,
      message: t('data_skill.content_placeholder'),
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

const selectedSkill = computed(() =>
  skillList.value.find((item) => String(item.id) === String(props.modelValue))
)

const selectedLabel = computed(() => selectedSkill.value?.name || t('data_skill.default_skill'))

const autoSkillDescription = computed(() => {
  if (skillList.value.length > 0) {
    return t('chat.find_data_skill_title', [skillList.value.length])
  }
  return targetScopeText(props.targetScope)
})

const targetScopeText = (scope?: string | null) => {
  if (scope === 'ANALYSIS_ASSISTANT') return t('prompt.target_scope_analysis_assistant')
  if (scope === 'ALL') return t('prompt.target_scope_all')
  return t('prompt.target_scope_smart_qa')
}

const sourceText = (row: any) => {
  if (row?.visibility_scope === 'PLATFORM_PUBLIC') return t('data_skill.saas_skill')
  if (row?.visibility_scope === 'ADMIN_PUBLIC') return t('data_skill.workspace_skill')
  if (row?.visibility_scope === 'USER_PRIVATE' && row?.is_owner) return t('data_skill.my_skill')
  return t('data_skill.workspace_skill')
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

const canManageSkill = (row: any) => {
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

const selectSkill = (value: string | number | null) => {
  emit('update:modelValue', value)
  emit('change', value)
  popoverVisible.value = false
}

const loadSkills = async () => {
  loading.value = true
  try {
    const res: any = await dataSkillApi.getList(1, 100, buildListQuery()).catch(() => ({ data: [] }))
    skillList.value = (res?.data || [])
      .filter(
        (row: any) =>
          row?.active === true &&
          row?.user_enabled !== false &&
          row?.effective_active !== false &&
          matchesTargetScope(row) &&
          isVisibleInPersonalEntry(row)
      )
      .sort(sortBySourceAndTime)

    if (
      props.modelValue &&
      !skillList.value.some((item) => String(item.id) === String(props.modelValue))
    ) {
      selectSkill(null)
    }
  } finally {
    loading.value = false
  }
}

const resetSkillForm = () => {
  skillForm.value = {
    ...cloneDeep(defaultSkillForm),
    target_scope: props.targetScope || 'SMART_QA',
    specific_ds: false,
    datasource_ids: [],
    visibility_scope: 'USER_PRIVATE',
  }
}

const openCreateSkill = () => {
  resetSkillForm()
  skillDialogTitle.value = t('data_skill.add_skill')
  skillDialogVisible.value = true
  popoverVisible.value = false
}

const openEditSkill = (row: any) => {
  if (!canManageSkill(row)) return
  skillForm.value = {
    ...cloneDeep(defaultSkillForm),
    ...cloneDeep(row),
    type: 'DATA_SKILL',
    target_scope: row.target_scope || props.targetScope || 'SMART_QA',
    specific_ds: false,
    datasource_ids: [],
    visibility_scope: 'USER_PRIVATE',
  }
  skillDialogTitle.value = t('data_skill.edit_skill')
  skillDialogVisible.value = true
  popoverVisible.value = false
}

const closeSkillForm = () => {
  skillDialogVisible.value = false
  resetSkillForm()
}

const buildSavePayload = () => {
  const payload = cloneDeep(skillForm.value)
  payload.type = 'DATA_SKILL'
  payload.target_scope = payload.target_scope || props.targetScope || 'SMART_QA'
  payload.visibility_scope = 'USER_PRIVATE'
  payload.specific_ds = false
  payload.datasource_ids = []
  return payload
}

const saveSkill = () => {
  skillFormRef.value?.validate((valid: boolean) => {
    if (!valid || savingSkill.value) return

    savingSkill.value = true
    dataSkillApi
      .save(buildSavePayload())
      .then(() => {
        ElMessage.success(t('common.save_success'))
        closeSkillForm()
        loadSkills()
        emit('saved')
      })
      .finally(() => {
        savingSkill.value = false
      })
  })
}

watch(
  () => [props.datasourceId, props.targetScope, keyword.value],
  () => {
    loadSkills()
  }
)

onMounted(() => {
  resetSkillForm()
  loadSkills()
})
</script>

<template>
  <div class="data-skill-selector" @click.stop>
    <el-popover
      v-model:visible="popoverVisible"
      :disabled="props.disabled"
      :width="380"
      placement="top-start"
      trigger="click"
      popper-class="data-skill-selector-popover"
    >
      <template #reference>
        <button class="data-skill-selector-trigger" :disabled="props.disabled" type="button">
          <el-icon class="trigger-icon" size="16">
            <icon_ai />
          </el-icon>
          <span class="trigger-label ellipsis" :title="selectedLabel">{{ selectedLabel }}</span>
        </button>
      </template>

      <div class="skill-panel">
        <div class="skill-panel-header">
          <div>
            <div class="skill-panel-title">{{ t('data_skill.title') }}</div>
            <div class="skill-panel-subtitle">
              {{ props.datasourceName || t('access.user_permission_scope') }}
            </div>
          </div>
          <el-button size="small" type="primary" class="skill-create-btn" @click.stop="openCreateSkill">
            <template #icon>
              <icon_add_outlined />
            </template>
            {{ t('data_skill.add_skill') }}
          </el-button>
        </div>

        <el-input
          v-model="keyword"
          clearable
          size="small"
          class="skill-search"
          :prefix-icon="Search"
          :placeholder="t('dashboard.search')"
          @click.stop
        />

        <div v-loading="loading" class="skill-list">
          <div
            class="skill-option is-default"
            :class="{ selected: !props.modelValue }"
            role="button"
            tabindex="0"
            @click.stop="selectSkill(null)"
          >
            <div class="skill-option-main">
              <span class="skill-option-name">{{ t('data_skill.default_skill') }}</span>
              <span class="skill-option-desc">{{ autoSkillDescription }}</span>
            </div>
          </div>

          <div v-if="!skillList.length && !loading" class="skill-empty">
            {{ t('data_skill.no_skill') }}
          </div>

          <div
            v-for="skill in skillList"
            :key="skill.id"
            class="skill-option"
            :class="[sourceClass(skill), { selected: String(skill.id) === String(props.modelValue) }]"
            role="button"
            tabindex="0"
            @click.stop="selectSkill(skill.id)"
          >
            <div class="skill-option-main">
              <div class="skill-option-title">
                <span class="skill-option-name ellipsis" :title="skill.name">{{ skill.name }}</span>
                <span class="skill-source-pill">{{ sourceText(skill) }}</span>
              </div>
              <div class="skill-option-desc ellipsis" :title="skill.description || t('data_skill.empty_description')">
                {{ skill.description || t('data_skill.empty_description') }}
              </div>
              <div class="skill-option-meta">
                <span>{{ targetScopeText(skill.target_scope) }}</span>
              </div>
            </div>
            <el-tooltip
              v-if="canManageSkill(skill)"
              :content="t('datasource.edit')"
              placement="top"
            >
              <el-button
                class="skill-edit-btn"
                link
                type="primary"
                @click.stop="openEditSkill(skill)"
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
      v-model="skillDialogVisible"
      :title="skillDialogTitle"
      destroy-on-close
      size="640px"
      :before-close="closeSkillForm"
      modal-class="data-skill-selector-drawer"
    >
      <el-form
        ref="skillFormRef"
        :model="skillForm"
        :rules="skillRules"
        label-width="180px"
        label-position="top"
        class="form-content_error"
        @submit.prevent
      >
        <el-form-item prop="name" :label="t('data_skill.skill_name')">
          <el-input
            v-model="skillForm.name"
            maxlength="50"
            clearable
            :placeholder="t('data_skill.skill_name_placeholder')"
          />
        </el-form-item>
        <el-form-item prop="description" :label="t('data_skill.description')">
          <el-input
            v-model="skillForm.description"
            :placeholder="t('data_skill.description_placeholder')"
            :autosize="{ minRows: 2, maxRows: 4 }"
            type="textarea"
          />
        </el-form-item>
        <el-form-item prop="target_scope" :label="t('prompt.target_scope')">
          <el-radio-group v-model="skillForm.target_scope">
            <el-radio :value="'SMART_QA'">{{ t('prompt.target_scope_smart_qa') }}</el-radio>
            <el-radio :value="'ANALYSIS_ASSISTANT'">
              {{ t('prompt.target_scope_analysis_assistant') }}
            </el-radio>
            <el-radio :value="'ALL'">{{ t('prompt.target_scope_all') }}</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item prop="active" :label="t('prompt.active_status')">
          <el-switch
            v-model="skillForm.active"
            :active-text="t('prompt.active_enabled')"
            :inactive-text="t('prompt.active_disabled')"
          />
        </el-form-item>
        <el-form-item :label="t('training.effective_data_sources')">
          <div class="fixed-project">{{ t('access.user_permission_scope') }}</div>
        </el-form-item>
        <el-form-item prop="prompt" :label="t('data_skill.markdown_content')">
          <el-input
            v-model="skillForm.prompt"
            :placeholder="t('data_skill.content_placeholder')"
            :autosize="{ minRows: 10, maxRows: 20 }"
            type="textarea"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <div v-loading="savingSkill" class="dialog-footer">
          <el-button secondary @click="closeSkillForm">{{ t('common.cancel') }}</el-button>
          <el-button type="primary" @click="saveSkill">{{ t('common.save') }}</el-button>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<style lang="less" scoped>
.data-skill-selector {
  width: 116px;
}

.data-skill-selector-trigger {
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
    color: #1c8f72;
  }

  .trigger-label {
    min-width: 0;
    flex: 1;
    text-align: left;
    font-size: 12px;
    line-height: 18px;
  }
}

.skill-panel {
  width: 100%;
}

.skill-panel-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.skill-panel-title {
  color: #1f2329;
  font-size: 14px;
  font-weight: 600;
  line-height: 20px;
}

.skill-panel-subtitle {
  max-width: 200px;
  margin-top: 2px;
  color: #86909c;
  font-size: 12px;
  line-height: 18px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.skill-create-btn {
  flex: 0 0 auto;
}

.skill-search {
  margin-bottom: 10px;
}

.skill-list {
  min-height: 104px;
  max-height: 320px;
  overflow-y: auto;
}

.skill-option {
  --skill-source-color: #667085;
  --skill-source-bg: #f2f4f7;
  --skill-source-border: #d0d5dd;
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
    background: var(--skill-source-bg);
  }

  &.selected {
    border-color: var(--skill-source-color);
    background: var(--skill-source-bg);
  }

  & + .skill-option {
    margin-top: 6px;
  }

  &.is-saas {
    --skill-source-color: #7a5af8;
    --skill-source-bg: #f3f0ff;
    --skill-source-border: #d8ccff;
    border-left-color: var(--skill-source-color);
  }

  &.is-workspace {
    --skill-source-color: #1570ef;
    --skill-source-bg: #eaf2ff;
    --skill-source-border: #b9d6ff;
    border-left-color: var(--skill-source-color);
  }

  &.is-personal {
    --skill-source-color: #12a076;
    --skill-source-bg: #e9f8f2;
    --skill-source-border: #a9e7d0;
    border-left-color: var(--skill-source-color);
  }
}

.skill-option-main {
  min-width: 0;
  flex: 1;
}

.skill-option-title {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.skill-source-pill {
  flex: 0 0 auto;
  max-width: 92px;
  padding: 0 5px;
  border: 1px solid var(--skill-source-border);
  border-radius: 4px;
  background: var(--skill-source-bg);
  color: var(--skill-source-color);
  font-size: 11px;
  font-weight: 500;
  line-height: 18px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.skill-option-name {
  min-width: 0;
  color: #1f2329;
  font-size: 13px;
  font-weight: 600;
  line-height: 20px;
}

.skill-option-desc {
  margin-top: 2px;
  color: #646a73;
  font-size: 12px;
  line-height: 18px;
}

.skill-option-meta {
  display: flex;
  gap: 8px;
  margin-top: 3px;
  color: #8f959e;
  font-size: 12px;
  line-height: 18px;
}

.skill-edit-btn {
  flex: 0 0 auto;
  width: 24px;
  height: 24px;
  padding: 0;
}

.skill-empty {
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
.data-skill-selector-popover.data-skill-selector-popover {
  padding: 12px;
  border-radius: 8px;
}

.data-skill-selector-drawer {
  .ed-drawer__body {
    padding: 20px 24px;
  }
}
</style>
