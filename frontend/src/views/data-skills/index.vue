<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { cloneDeep } from 'lodash-es'
import { Search } from '@element-plus/icons-vue'
import { useDatasourceContextStore } from '@/stores/datasourceContext'
import { dataSkillApi } from '@/api/dataSkill'
import { datasourceApi } from '@/api/datasource'
import icon_add_outlined from '@/assets/svg/icon_add_outlined.svg'
import IconOpeEdit from '@/assets/svg/icon_edit_outlined.svg'
import IconOpeDelete from '@/assets/svg/icon_delete.svg'
import icon_more_outlined from '@/assets/svg/icon_more_outlined.svg'
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

const skillLoading = ref(false)
const skillList = ref<any[]>([])
const skillFormRef = ref()
const skillDialogVisible = ref(false)
const skillDetailVisible = ref(false)
const skillDialogTitle = ref('')
const selectedSkill = ref<any | null>(null)
const savingSkill = ref(false)
const skillKeyword = ref('')
const datasourceOptions = ref<any[]>([])
const scopeFilter = ref('')

const isAdminMode = computed(() => props.mode === 'admin')
const isPlatformAdmin = computed(
  () => userStore.isSystemAdminUser && !userStore.isPlatformWorkspaceDelegate
)
const canCreateSkill = computed(() => !isAdminMode.value || userStore.isSystemManagerUser)

const layerOptions = computed(() => {
  const options = [
    { label: t('prompt.target_scope_all'), value: '' },
    { label: t('permission.scope_platform'), value: 'PLATFORM_PUBLIC' },
    { label: t('permission.scope_workspace'), value: 'ADMIN_PUBLIC' },
    { label: t('access.user_permission_scope'), value: 'USER_PRIVATE' },
  ]
  if (isAdminMode.value && isPlatformAdmin.value) {
    return options.filter((item) => item.value === 'PLATFORM_PUBLIC')
  }
  if (isAdminMode.value) {
    return options.filter((item) => item.value === 'ADMIN_PUBLIC')
  }
  return options
})

const defaultSkillForm = {
  id: null as number | string | null,
  type: 'DATA_SKILL',
  name: '',
  description: '',
  target_scope: 'ALL',
  active: true,
  ai_model_id: null as number | string | null,
  prompt: '',
  specific_ds: false,
  datasource_ids: [] as number[],
  visibility_scope: 'USER_PRIVATE',
}
const skillForm = ref(cloneDeep(defaultSkillForm))

const currentDatasourceId = computed(() => datasourceContext.datasourceId)
const currentDatasourceName = computed(() => datasourceContext.datasourceName)

const pageTitle = computed(() => (isAdminMode.value ? t('data_skill.admin_title') : t('data_skill.title')))

const pageSubtitle = computed(() => {
  if (isAdminMode.value) {
    return isPlatformAdmin.value
      ? t('data_skill.admin_platform_subtitle')
      : t('data_skill.admin_workspace_subtitle')
  }
  return `${t('access.current_project')}：${currentDatasourceName.value || '-'}`
})

const validateDatasource = (_: any, value: any, callback: any) => {
  if (isAdminMode.value && !isPlatformAdmin.value && skillForm.value.specific_ds && !value?.length) {
    callback(new Error(t('datasource.Please_select') + t('common.empty') + t('ds.title')))
    return
  }
  callback()
}

const skillRules = computed(() => ({
  name: [
    {
      required: true,
      message: t('datasource.please_enter') + t('common.empty') + t('data_skill.skill_name'),
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
      message: t('data_skill.content_placeholder'),
      trigger: 'blur',
    },
  ],
}))

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

const canManageSkill = (row: any) => {
  if (isAdminMode.value) return row?.can_manage === true
  return row?.visibility_scope === 'USER_PRIVATE' && row?.is_owner === true
}

const canViewSkillContent = (row: any) => {
  return row?.prompt_visible === true || (row?.visibility_scope === 'USER_PRIVATE' && row?.is_owner === true)
}

const isSkillEffective = (row: any) => row?.effective_active !== false && row?.active !== false

const activationStatusText = (row: any) =>
  isSkillEffective(row) ? t('prompt.active_enabled') : t('prompt.active_disabled')

const buildSkillQuery = () => {
  const params = new URLSearchParams()
  if (scopeFilter.value) {
    params.append('visibility_scope', scopeFilter.value)
  }
  if (isAdminMode.value && !scopeFilter.value) {
    params.append('visibility_scope', isPlatformAdmin.value ? 'PLATFORM_PUBLIC' : 'ADMIN_PUBLIC')
  }
  if (!isAdminMode.value && currentDatasourceId.value) {
    params.append('dslist', String(currentDatasourceId.value))
  }
  if (skillKeyword.value.trim()) {
    params.append('name', skillKeyword.value.trim())
  }
  const query = params.toString()
  return query ? `?${query}` : ''
}

const loadDatasourceOptions = async () => {
  if (!isAdminMode.value || isPlatformAdmin.value) {
    datasourceOptions.value = []
    return
  }
  const res: any = await datasourceApi.accessibleList().catch(() => [])
  datasourceOptions.value = Array.isArray(res) ? res : []
}

const loadSkills = async () => {
  skillLoading.value = true
  try {
    const res: any = await dataSkillApi.getList(1, 100, buildSkillQuery()).catch(() => ({ data: [] }))
    skillList.value = (res?.data || [])
      .filter(isVisibleInPersonalEntry)
      .filter((row: any) => isAdminMode.value || row?.active !== false || canManageSkill(row))
      .sort(sortBySourceAndTime)
  } finally {
    skillLoading.value = false
  }
}

const toggleSkillActivation = (skill: any, value: boolean) => {
  const previousUserEnabled = skill.user_enabled !== false
  const previousActive = skill.active !== false
  const scope = isAdminMode.value || canManageSkill(skill) ? 'global' : 'user'

  if (scope === 'global') {
    skill.active = value
    skill.effective_active = value && (skill.user_enabled !== false)
  } else {
    skill.user_enabled = value
    skill.effective_active = (skill.active !== false) && value
  }

  dataSkillApi
    .setActivation(skill.id, value, scope)
    .then((res: any) => {
      skill.active = res?.active ?? skill.active
      skill.user_enabled = res?.user_enabled ?? skill.user_enabled
      skill.effective_active = (skill.active !== false) && (skill.user_enabled !== false)
      ElMessage.success(t('common.save_success'))
      if (!isAdminMode.value && skill.active === false) {
        loadSkills()
      }
    })
    .catch(() => {
      skill.user_enabled = previousUserEnabled
      skill.active = previousActive
      skill.effective_active = previousActive && previousUserEnabled
    })
}

const resetSkillForm = () => {
  skillForm.value = {
    ...cloneDeep(defaultSkillForm),
    specific_ds: false,
    datasource_ids: [],
    visibility_scope: isAdminMode.value
      ? isPlatformAdmin.value
        ? 'PLATFORM_PUBLIC'
        : 'ADMIN_PUBLIC'
      : 'USER_PRIVATE',
  }
}

const openCreateSkill = () => {
  if (!canCreateSkill.value) return
  resetSkillForm()
  skillDialogTitle.value = t('data_skill.add_skill')
  skillDialogVisible.value = true
}

const openEditSkill = (row: any) => {
  if (!canManageSkill(row)) return
  skillForm.value = {
    ...cloneDeep(defaultSkillForm),
    ...cloneDeep(row),
    type: 'DATA_SKILL',
    specific_ds: isAdminMode.value && !isPlatformAdmin.value ? Boolean(row?.specific_ds) : false,
    datasource_ids: isAdminMode.value && !isPlatformAdmin.value ? row?.datasource_ids || [] : [],
    visibility_scope: isAdminMode.value
      ? isPlatformAdmin.value
        ? 'PLATFORM_PUBLIC'
        : 'ADMIN_PUBLIC'
      : 'USER_PRIVATE',
  }
  skillDialogTitle.value = t('data_skill.edit_skill')
  skillDialogVisible.value = true
}

const closeSkillForm = () => {
  skillDialogVisible.value = false
  resetSkillForm()
}

const saveSkill = () => {
  if (!canCreateSkill.value) return
  skillFormRef.value?.validate((valid: boolean) => {
    if (!valid || savingSkill.value) return
    const payload = cloneDeep(skillForm.value)
    payload.type = 'DATA_SKILL'
    if (isAdminMode.value) {
      payload.visibility_scope = isPlatformAdmin.value ? 'PLATFORM_PUBLIC' : 'ADMIN_PUBLIC'
      if (isPlatformAdmin.value || !payload.specific_ds) {
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
    savingSkill.value = true
    dataSkillApi
      .save(payload)
      .then(() => {
        ElMessage.success(t('common.save_success'))
        closeSkillForm()
        loadSkills()
      })
      .finally(() => {
        savingSkill.value = false
      })
  })
}

const deleteSkill = (row: any) => {
  if (!canManageSkill(row)) return
  ElMessageBox.confirm(t('data_skill.delete_confirm', { msg: row.name }), {
    confirmButtonType: 'danger',
    confirmButtonText: t('dashboard.delete'),
    cancelButtonText: t('common.cancel'),
    customClass: 'confirm-no_icon',
    autofocus: false,
  }).then(() => {
    dataSkillApi.delete([row.id]).then(() => {
      ElMessage.success(t('dashboard.delete_success'))
      loadSkills()
    })
  })
}

const openSkillDetail = (row: any) => {
  selectedSkill.value = cloneDeep(row)
  skillDetailVisible.value = true
}

const handleDatasourceChange = () => {
  skillFormRef.value?.validateField('datasource_ids')
}

onMounted(async () => {
  scopeFilter.value = isAdminMode.value
    ? isPlatformAdmin.value
      ? 'PLATFORM_PUBLIC'
      : 'ADMIN_PUBLIC'
    : ''
  if (isAdminMode.value) {
    await loadDatasourceOptions()
  } else {
    await datasourceContext.loadDatasources()
  }
  loadSkills()
})

watch(currentDatasourceId, () => {
  if (!isAdminMode.value) loadSkills()
})

watch(skillKeyword, () => {
  loadSkills()
})

watch(scopeFilter, () => {
  loadSkills()
})
</script>

<template>
  <div class="data-skills-page">
    <div class="page-header">
      <div>
        <div class="page-title">{{ pageTitle }}</div>
        <div class="page-subtitle">
          {{ pageSubtitle }}
        </div>
      </div>
      <div class="page-actions">
        <el-input
          v-model="skillKeyword"
          clearable
          class="skill-search"
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
        <el-button v-if="canCreateSkill" type="primary" @click="openCreateSkill">
          <template #icon>
            <icon_add_outlined />
          </template>
          {{ t('data_skill.add_skill') }}
        </el-button>
      </div>
    </div>

    <section class="skill-section">
      <div v-loading="skillLoading" class="skill-content">
        <div v-if="!skillList.length && !skillLoading" class="skill-empty">
          {{ t('data_skill.no_skill') }}
        </div>
        <template v-else>
          <div class="card-content">
            <article
              v-for="skill in skillList"
              :key="skill.id"
              class="skill-card"
              :class="sourceClass(skill)"
              @click="openSkillDetail(skill)"
            >
              <div class="skill-card-head">
                <div class="skill-title-area">
                  <span class="name ellipsis" :title="skill.name">{{ skill.name }}</span>
                  <div class="skill-meta-row" :title="`${sourceText(skill)} · ${targetScopeText(skill.target_scope)} · ${scopeText(skill)}`">
                    <span class="skill-source-pill">{{ sourceText(skill) }}</span>
                    <span class="skill-sub-meta ellipsis">
                      {{ targetScopeText(skill.target_scope) }} · {{ scopeText(skill) }}
                    </span>
                  </div>
                </div>
                <div class="skill-actions" @click.stop>
                  <button
                    v-if="canManageSkill(skill)"
                    type="button"
                    class="icon-action"
                    :title="t('datasource.edit')"
                    @click.stop="openEditSkill(skill)"
                  >
                    <el-icon size="14">
                      <IconOpeEdit />
                    </el-icon>
                  </button>
                  <el-popover
                    v-if="canManageSkill(skill)"
                    trigger="click"
                    :teleported="true"
                    popper-class="popover-card_skill"
                    placement="bottom-end"
                  >
                    <template #reference>
                      <button type="button" class="icon-action" :title="t('dashboard.delete')">
                        <icon_more_outlined />
                      </button>
                    </template>
                    <div class="content">
                      <div class="item" @click.stop="deleteSkill(skill)">
                        <el-icon size="16">
                          <IconOpeDelete />
                        </el-icon>
                        {{ t('dashboard.delete') }}
                      </div>
                    </div>
                  </el-popover>
                  <span class="action-divider"></span>
                  <div class="activation-switch">
                    <el-switch
                      :model-value="isSkillEffective(skill)"
                      size="small"
                      :disabled="isAdminMode && !canManageSkill(skill)"
                      @change="(value: string | number | boolean) => toggleSkillActivation(skill, Boolean(value))"
                    />
                  </div>
                </div>
              </div>

              <div class="skill-preview" :title="skill.description || t('data_skill.empty_description')">
                {{ skill.description || t('data_skill.empty_description') }}
              </div>
            </article>
          </div>
        </template>
      </div>
    </section>

    <el-drawer
      v-model="skillDialogVisible"
      :title="skillDialogTitle"
      destroy-on-close
      size="640px"
      :before-close="closeSkillForm"
      modal-class="data-skill-drawer"
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
          <div v-if="!isAdminMode" class="fixed-project">{{ t('access.user_permission_scope') }}</div>
          <div v-else-if="isPlatformAdmin" class="fixed-project">
            {{ t('training.all_data_sources') }}
          </div>
          <div v-else class="datasource-scope-editor">
            <el-radio-group v-model="skillForm.specific_ds">
              <el-radio :value="false">{{ t('training.all_data_sources') }}</el-radio>
              <el-radio :value="true">{{ t('training.partial_data_sources') }}</el-radio>
            </el-radio-group>
            <el-form-item
              v-if="skillForm.specific_ds"
              prop="datasource_ids"
              class="nested-datasource-form-item"
            >
              <el-select
                v-model="skillForm.datasource_ids"
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
          </div>
        </el-form-item>
        <el-form-item prop="prompt" :label="t('data_skill.markdown_content')">
          <el-input
            v-model="skillForm.prompt"
            :placeholder="t('data_skill.content_placeholder')"
            :autosize="{ minRows: 12, maxRows: 24 }"
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

    <el-drawer
      v-model="skillDetailVisible"
      :title="t('menu.Details')"
      destroy-on-close
      size="640px"
      modal-class="data-skill-drawer"
    >
      <el-form label-width="180px" label-position="top" class="form-content_error" @submit.prevent>
        <el-form-item :label="t('data_skill.skill_name')">
          <div class="detail-content">{{ selectedSkill?.name || '-' }}</div>
        </el-form-item>
        <el-form-item :label="t('data_skill.description')">
          <div class="detail-content">
            {{ selectedSkill?.description || t('data_skill.empty_description') }}
          </div>
        </el-form-item>
        <el-form-item :label="t('data_skill.source')">
          <div class="detail-content">{{ sourceText(selectedSkill) }}</div>
        </el-form-item>
        <el-form-item :label="t('prompt.target_scope')">
          <div class="detail-content">{{ targetScopeText(selectedSkill?.target_scope) }}</div>
        </el-form-item>
        <el-form-item :label="t('prompt.active_status')">
          <div class="detail-content">
            {{ activationStatusText(selectedSkill) }}
          </div>
        </el-form-item>
        <el-form-item :label="t('training.effective_data_sources')">
          <div class="detail-content">{{ scopeText(selectedSkill) }}</div>
        </el-form-item>
        <el-form-item
          v-if="canViewSkillContent(selectedSkill)"
          :label="t('data_skill.markdown_content')"
        >
          <div class="detail-content pre-wrap">{{ selectedSkill?.prompt }}</div>
        </el-form-item>
        <el-form-item v-else :label="t('data_skill.markdown_content')">
          <div class="detail-content muted">{{ t('data_skill.content_not_visible') }}</div>
        </el-form-item>
      </el-form>
    </el-drawer>
  </div>
</template>

<style lang="less" scoped>
.data-skills-page {
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

  .skill-section {
    min-height: 0;
  }

  .skill-empty {
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

  .skill-content {
    min-height: 96px;
  }

  .card-content {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(288px, 1fr));
    gap: 12px;
  }

  .page-actions {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 12px;
    min-width: 360px;
  }

  .skill-search {
    width: 240px;
  }

  .scope-filter {
    width: 132px;
  }

  .skill-card {
    --skill-source-color: #667085;
    --skill-source-bg: #f2f4f7;
    --skill-source-border: #d0d5dd;
    --skill-source-card-bg: #ffffff;
    width: 100%;
    min-height: 104px;
    border: 1px solid var(--skill-source-border);
    border-left: 2px solid var(--skill-source-color);
    padding: 14px 14px 12px 12px;
    border-radius: 8px;
    background: var(--skill-source-card-bg);
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
      border-color: var(--skill-source-color);
      box-shadow: 0 8px 18px rgba(16, 24, 40, 0.08);
      transform: translateY(-1px);
    }

    &.is-saas {
      --skill-source-color: #7a5af8;
      --skill-source-bg: #f3f0ff;
      --skill-source-border: #d8ccff;
      --skill-source-card-bg: #fcfbff;
    }

    &.is-workspace {
      --skill-source-color: #1570ef;
      --skill-source-bg: #eaf2ff;
      --skill-source-border: #b9d6ff;
      --skill-source-card-bg: #fbfdff;
    }

    &.is-personal {
      --skill-source-color: #12a076;
      --skill-source-bg: #e9f8f2;
      --skill-source-border: #a9e7d0;
      --skill-source-card-bg: #fbfffd;
    }

    .skill-card-head {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
      min-width: 0;
    }

    .skill-title-area {
      min-width: 0;
      flex: 1;
      padding-right: 4px;
    }

    .name {
      display: block;
      min-width: 0;
      max-width: 100%;
      color: #101828;
      font-weight: 600;
      font-size: 14px;
      line-height: 22px;
    }

    .skill-meta-row {
      display: flex;
      align-items: center;
      gap: 6px;
      margin-top: 2px;
      min-width: 0;
    }

    .skill-source-pill {
      flex: 0 0 auto;
      max-width: 88px;
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

    .skill-sub-meta {
      display: block;
      min-width: 0;
      color: #667085;
      font-size: 12px;
      line-height: 18px;
    }

    .skill-actions {
      flex: 0 0 auto;
      display: flex;
      align-items: center;
      gap: 8px;
      height: 24px;
    }

    .activation-switch {
      height: 22px;
      display: inline-flex;
      align-items: center;
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

    .skill-preview {
      display: -webkit-box;
      margin-top: 12px;
      overflow: hidden;
      color: #475467;
      font-size: 13px;
      line-height: 20px;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
    }
  }
}
</style>

<style lang="less">
.data-skill-drawer {
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

    .nested-datasource-form-item {
      margin-top: 8px;
      margin-bottom: 0;
    }
  }

  .pre-wrap {
    white-space: pre-wrap;
  }

  .muted {
    color: #8f959e;
  }
}

.popover-card_skill.popover-card_skill.popover-card_skill {
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
