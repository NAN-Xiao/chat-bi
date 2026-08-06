<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Download, Plus, Refresh, Search, Upload } from '@element-plus/icons-vue'
import { cloneDeep } from 'lodash-es'
import { useUserStore } from '@/stores/user'
import {
  knowledgeBaseApi,
  type KnowledgeBaseItem,
  type KnowledgeBaseScope,
  type KnowledgeBaseVersion,
  type KnowledgePublishJob,
  type KnowledgeApplicabilityState,
} from '@/api/knowledgeBase'
import { useDatasourceContextStore } from '@/stores/datasourceContext'
import KnowledgePayloadEditor from './KnowledgePayloadEditor.vue'
import { knowledgeActionState } from './knowledgeEditorState'
import KnowledgeRetrievalPreview from './KnowledgeRetrievalPreview.vue'
import KnowledgeApplicabilityTag from './KnowledgeApplicabilityTag.vue'

const userStore = useUserStore()
const datasourceContext = useDatasourceContextStore()
const items = ref<KnowledgeBaseItem[]>([])
const loading = ref(false)
const saving = ref(false)
const publishing = ref(false)
const editorVisible = ref(false)
const createVisible = ref(false)
const selected = ref<KnowledgeBaseItem | null>(null)
const versions = ref<KnowledgeBaseVersion[]>([])
const draft = ref<KnowledgeBaseVersion | null>(null)
const payload = ref<Record<string, any>>({})
const keyword = ref('')
const scopeFilter = ref<'' | KnowledgeBaseScope>('')
const createForm = ref({ name: '', description: '', visibility_scope: 'ADMIN_PUBLIC' as KnowledgeBaseScope })
const pendingFile = ref<File | null>(null)
const publishJob = ref<KnowledgePublishJob | null>(null)
const draftConflict = ref(false)
const retrievalPreviewVisible = ref(false)
const workspaceOverride = ref<{ enabled: boolean; reason?: string | null } | null>(null)
const overrideLoading = ref(false)
const applicability = ref<KnowledgeApplicabilityState | null>(null)
const applicabilityLoading = ref(false)
let publishTimer: ReturnType<typeof window.setInterval> | null = null

const isPlatformAdmin = computed(
  () => userStore.isSystemAdminUser && !userStore.isPlatformWorkspaceDelegate
)
const visibleItems = computed(() => {
  const text = keyword.value.trim().toLowerCase()
  if (!text) return items.value
  return items.value.filter((item) => `${item.name} ${item.description || ''}`.toLowerCase().includes(text))
})
const canEdit = computed(() => !!selected.value?.can_manage)
const editorTitle = computed(() => selected.value ? `编辑知识库：${selected.value.name}` : '编辑知识库')
const draftStatus = computed(() => draft.value?.status || '无草稿')
const validationErrors = computed(() => draft.value?.validation_report?.errors || [])
const validationWarnings = computed(() => draft.value?.validation_report?.warnings || [])
const actionState = computed(() => knowledgeActionState({
  status: draft.value?.status,
  canManage: canEdit.value,
  hasDraft: Boolean(draft.value),
  publishing: publishing.value,
  publishJobStatus: publishJob.value?.status,
}))
const editorBusy = computed(() => !actionState.value.save && (
  publishing.value || ['QUEUED', 'RUNNING', 'PENDING_CONFIRMATION'].includes(publishJob.value?.status || '')
))
const canToggleWorkspaceKnowledge = computed(
  () => selected.value?.visibility_scope === 'PLATFORM_PUBLIC' && userStore.isTenantAdminUser
)
const workspaceKnowledgeEnabled = computed({
  get: () => workspaceOverride.value?.enabled !== false,
  set: (value: boolean) => {
    if (workspaceOverride.value) workspaceOverride.value.enabled = value
  },
})

function knowledgeTypeText(type?: string | null) {
  if (type === 'BUSINESS') return '业务术语与 SQL'
  if (type === 'EVENT') return '事件参数'
  if (type === 'JSON_FIELD') return 'JSON 字段'
  return '普通文档'
}

function processStatusText(status?: string | null) {
  if (status === 'READY') return '已完成'
  if (status === 'PROCESSING') return '处理中'
  if (status === 'FAILED') return '处理失败'
  return '待处理'
}

function defaultPayload(type?: string | null) {
  if (type === 'BUSINESS') return { knowledge_type: 'BUSINESS', term: '', aliases: [], definition: '', formula: '', constraints: [], related_objects: [], examples: [] }
  if (type === 'EVENT') return { knowledge_type: 'EVENT', event_name: '', display_name: '', aliases: [], description: '', table_name: '', event_name_field: '', event_time_field: '', parameters: [] }
  if (type === 'JSON_FIELD') return { knowledge_type: 'JSON_FIELD', schema_name: '', table_name: '', source_field: '', json_path: '$.', field_name: '', display_name: '', data_type: 'string', expression: '', aliases: [], description: '', value_mappings: {} }
  return { knowledge_type: 'DOCUMENT', markdown: '', tags: [], datasource_neutral: false, object_references: [] }
}

async function loadItems() {
  loading.value = true
  try {
    items.value = await knowledgeBaseApi.list({
      visibility_scope: scopeFilter.value || undefined,
      keyword: keyword.value || undefined,
    })
  } catch (error) {
    console.error(error)
    items.value = []
  } finally {
    loading.value = false
  }
}

function openCreate() {
  createForm.value = {
    name: '',
    description: '',
    visibility_scope: isPlatformAdmin.value ? 'PLATFORM_PUBLIC' : 'ADMIN_PUBLIC',
  }
  createVisible.value = true
}

async function createKnowledge() {
  if (!createForm.value.name.trim()) {
    ElMessage.warning('请输入知识库名称')
    return
  }
  try {
    saving.value = true
    const item = await knowledgeBaseApi.create({ ...createForm.value, name: createForm.value.name.trim() })
    createVisible.value = false
    await loadItems()
    await openEditor(item)
  } finally {
    saving.value = false
  }
}

async function openEditor(item: KnowledgeBaseItem) {
  selected.value = await knowledgeBaseApi.detail(item.id)
  editorVisible.value = true
  pendingFile.value = null
  publishJob.value = null
  draftConflict.value = false
  workspaceOverride.value = null
  await loadVersions()
  if (canToggleWorkspaceKnowledge.value && selected.value) {
    try {
      workspaceOverride.value = await knowledgeBaseApi.workspaceEnabledState(selected.value.id)
    } catch (error) {
      console.error(error)
      workspaceOverride.value = { enabled: true, reason: null }
    }
  }
  await loadApplicability()
}

async function loadApplicability() {
  applicability.value = null
  if (!selected.value || selected.value.visibility_scope !== 'PLATFORM_PUBLIC') return
  if (!datasourceContext.initialized) await datasourceContext.loadDatasources()
  if (!datasourceContext.datasourceId) return
  applicabilityLoading.value = true
  try {
    applicability.value = await knowledgeBaseApi.applicability(
      selected.value.id,
      Number(datasourceContext.datasourceId),
    )
  } catch (error) {
    console.error(error)
    applicability.value = {
      knowledge_base_id: selected.value.id,
      version_id: selected.value.current_version_id,
      datasource_id: datasourceContext.datasourceId,
      status: 'ERROR',
      status_text: '检查失败',
      schema_hash_prefix: null,
      reference_count: 0,
      resolved_count: 0,
      warnings: ['当前数据源适用性状态读取失败，请稍后重试。'],
      checked_at: null,
    }
  } finally {
    applicabilityLoading.value = false
  }
}

async function loadVersions() {
  if (!selected.value) return
  draftConflict.value = false
  versions.value = await knowledgeBaseApi.versions(selected.value.id)
  draft.value = versions.value.find((version) =>
    ['DRAFT', 'VALIDATING', 'VALIDATION_FAILED', 'READY_TO_PUBLISH', 'PUBLISH_FAILED'].includes(version.status)
  ) || null
  if (!draft.value) {
    const current = versions.value.find((version) => version.status === 'PUBLISHED')
    if (current && canEdit.value) {
      draft.value = await knowledgeBaseApi.rollback(selected.value.id, current.id)
      versions.value = await knowledgeBaseApi.versions(selected.value.id)
    }
  }
  if (!draft.value && canEdit.value) {
    draft.value = await knowledgeBaseApi.createDraft(
      selected.value.id,
      defaultPayload(selected.value.knowledge_type)
    )
    versions.value = await knowledgeBaseApi.versions(selected.value.id)
  }
  if (draft.value) payload.value = cloneDeep(draft.value.payload)
  else payload.value = defaultPayload(selected.value.knowledge_type)
}

async function saveDraft() {
  if (!selected.value || !draft.value || !actionState.value.save) return false
  try {
    saving.value = true
    if (pendingFile.value) {
      draft.value = await knowledgeBaseApi.replaceDraftFile(selected.value.id, {
        version_id: draft.value.id,
        revision: draft.value.revision,
        file: pendingFile.value,
      })
      payload.value = cloneDeep(draft.value.payload)
      pendingFile.value = null
    }
    draft.value = await knowledgeBaseApi.saveDraft(selected.value.id, {
      version_id: draft.value.id,
      revision: draft.value.revision,
      content: payload.value,
    })
    ElMessage.success('草稿已保存')
    draftConflict.value = false
    return true
  } catch (error: any) {
    if (error?.response?.status === 409) {
      draftConflict.value = true
      ElMessage.error('草稿已被其他人更新，请刷新版本后重试。')
      return false
    }
    throw error
  } finally {
    saving.value = false
  }
}

async function validateDraft() {
  if (!selected.value || !draft.value || !actionState.value.validate) return
  try {
    saving.value = true
    if (draft.value.payload !== payload.value && !(await saveDraft())) return
    draft.value = await knowledgeBaseApi.validateDraft(selected.value.id, {
      version_id: draft.value.id,
      revision: draft.value.revision,
      content_hash: draft.value.content_hash || '',
      context: {},
    })
    if (draft.value.validation_report?.valid) ElMessage.success('校验通过，可以发布')
    else ElMessage.warning('校验未通过，请根据页面提示修正')
  } finally {
    saving.value = false
  }
}

async function publishDraft() {
  if (!selected.value || !draft.value || !actionState.value.publish) return
  try {
    publishing.value = true
    publishJob.value = await knowledgeBaseApi.publish(selected.value.id, {
      version_id: draft.value.id,
      revision: draft.value.revision,
      content_hash: draft.value.content_hash || '',
    })
    pollPublishJob()
  } finally {
    publishing.value = false
  }
}

function pollPublishJob() {
  if (publishTimer) window.clearInterval(publishTimer)
  publishTimer = window.setInterval(async () => {
    if (!selected.value) return
    publishJob.value = await knowledgeBaseApi.publishJob(selected.value.id)
    if (publishJob.value && ['SUCCEEDED', 'FAILED'].includes(publishJob.value.status)) {
      if (publishTimer) window.clearInterval(publishTimer)
      publishTimer = null
      await loadItems()
      await loadVersions()
      ElMessage[publishJob.value.status === 'SUCCEEDED' ? 'success' : 'error'](
        publishJob.value.status === 'SUCCEEDED' ? '知识库发布成功' : publishJob.value.error_message || '知识库发布失败'
      )
    }
  }, 3000)
}

async function refreshDraftAfterConflict() {
  await loadVersions()
  ElMessage.success('已刷新最新草稿，请确认内容后继续编辑。')
}

async function updateWorkspaceKnowledgeEnabled(enabled: boolean) {
  if (!selected.value || !canToggleWorkspaceKnowledge.value) return
  const previous = !enabled
  overrideLoading.value = true
  try {
    const result = await knowledgeBaseApi.workspaceEnabled(selected.value.id, enabled)
    workspaceOverride.value = result
    ElMessage.success(enabled ? '已启用当前工作空间使用' : '已停用当前工作空间使用')
  } catch (error) {
    console.error(error)
    workspaceKnowledgeEnabled.value = previous
  } finally {
    overrideLoading.value = false
  }
}

function selectFile(file: any) {
  const raw = file?.raw || file
  if (!raw) return false
  if (!/\.(md|markdown|docx)$/i.test(raw.name || '')) {
    ElMessage.warning('仅支持 Markdown 或 Word 文档')
    return false
  }
  if (raw.size > 50 * 1024 * 1024) {
    ElMessage.warning('文件不能超过 50 MB')
    return false
  }
  pendingFile.value = raw
  return false
}

async function downloadVersion(version: KnowledgeBaseVersion) {
  if (!selected.value) return
  const blob = await knowledgeBaseApi.download(selected.value.id, version.id)
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = version.file_name || `knowledge-${version.version_number}`
  anchor.click()
  URL.revokeObjectURL(url)
}

function closeEditor() {
  editorVisible.value = false
  if (publishTimer) window.clearInterval(publishTimer)
  publishTimer = null
  applicability.value = null
  loadItems()
}

onMounted(loadItems)
watch(() => datasourceContext.datasourceId, () => {
  if (editorVisible.value && selected.value?.visibility_scope === 'PLATFORM_PUBLIC') loadApplicability()
})
onBeforeUnmount(() => { if (publishTimer) window.clearInterval(publishTimer) })
</script>

<template>
  <div class="knowledge-v2-panel">
    <div class="panel-header">
      <div>
        <div class="panel-title">知识库管理</div>
        <div class="panel-subtitle">统一维护业务术语、SQL 示例、事件参数、JSON 路径和文档知识</div>
      </div>
      <div class="panel-actions">
        <el-input v-model="keyword" clearable placeholder="搜索知识库" @keyup.enter="loadItems" />
        <el-select v-model="scopeFilter" clearable placeholder="全部范围" @change="loadItems">
          <el-option label="工作空间知识" value="ADMIN_PUBLIC" />
          <el-option label="平台公共知识" value="PLATFORM_PUBLIC" />
        </el-select>
        <el-button :icon="Refresh" @click="loadItems">刷新</el-button>
        <el-button :icon="Search" @click="retrievalPreviewVisible = true">检索预览</el-button>
        <el-button type="primary" :icon="Plus" @click="openCreate">新建知识库</el-button>
      </div>
    </div>

    <el-table
      v-loading="loading"
      :data="visibleItems"
      row-key="id"
      class="knowledge-v2-table"
      @row-click="openEditor"
    >
      <el-table-column prop="name" label="名称" min-width="220" show-overflow-tooltip />
      <el-table-column label="知识类型" width="150">
        <template #default="{ row }">{{ knowledgeTypeText(row.knowledge_type) }}</template>
      </el-table-column>
      <el-table-column label="知识范围" width="150">
        <template #default="{ row }">
          <el-tag size="small" :type="row.visibility_scope === 'PLATFORM_PUBLIC' ? 'warning' : 'primary'">
            {{ row.visibility_scope === 'PLATFORM_PUBLIC' ? '平台公共知识' : '工作空间知识' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="处理状态" width="110">
        <template #default="{ row }">{{ processStatusText(row.status) }}</template>
      </el-table-column>
      <el-table-column label="发布版本" width="130">
        <template #default="{ row }">
          <el-tag v-if="row.publishing_version_id" size="small" type="warning">发布中</el-tag>
          <span v-else-if="row.current_version_id">版本 #{{ row.current_version_id }}</span>
          <span v-else class="muted-text">尚未发布</span>
        </template>
      </el-table-column>
      <el-table-column label="更新时间" width="170">
        <template #default="{ row }">{{ row.update_time || '-' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="90" fixed="right">
        <template #default="{ row }">
          <el-button text type="primary" @click.stop="openEditor(row)">编辑</el-button>
        </template>
      </el-table-column>
      <template #empty><span class="empty-state">暂无知识库</span></template>
    </el-table>

    <el-dialog v-model="createVisible" title="新建知识库" width="480px" destroy-on-close>
      <el-form label-position="top" @submit.prevent>
        <el-form-item label="名称" required><el-input v-model="createForm.name" maxlength="255" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="createForm.description" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" /></el-form-item>
        <el-form-item label="知识范围">
          <el-select v-model="createForm.visibility_scope" :disabled="!isPlatformAdmin">
            <el-option label="工作空间知识" value="ADMIN_PUBLIC" />
            <el-option v-if="isPlatformAdmin" label="平台公共知识" value="PLATFORM_PUBLIC" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="createKnowledge">创建并编辑</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="editorVisible" :title="editorTitle" size="760px" destroy-on-close :before-close="closeEditor">
      <div v-if="selected" class="editor-layout">
        <div class="editor-toolbar">
          <el-tag>{{ selected.visibility_scope === 'PLATFORM_PUBLIC' ? '平台公共知识' : '工作空间知识' }}</el-tag>
          <KnowledgeApplicabilityTag
            v-if="selected.visibility_scope === 'PLATFORM_PUBLIC'"
            :state="applicability"
            :loading="applicabilityLoading"
            :datasource-available="Boolean(datasourceContext.datasourceId)"
          />
          <span v-if="canToggleWorkspaceKnowledge" class="workspace-override">
            当前工作空间使用
            <el-switch
              v-model="workspaceKnowledgeEnabled"
              size="small"
              :loading="overrideLoading"
              @change="updateWorkspaceKnowledgeEnabled"
            />
          </span>
          <span class="version-status">草稿状态：{{ draftStatus }}</span>
          <span v-if="draft?.file_name" class="version-file">源文件：{{ draft.file_name }}</span>
        </div>
        <KnowledgePayloadEditor v-model="payload" :readonly="!canEdit || editorBusy" />
        <el-upload :disabled="!canEdit || editorBusy" :auto-upload="false" :show-file-list="false" accept=".md,.markdown,.docx" :before-upload="selectFile">
          <el-button :icon="Upload">替换源文件</el-button>
        </el-upload>
        <span v-if="pendingFile" class="pending-file">待上传：{{ pendingFile.name }}</span>
        <div v-if="validationErrors.length" class="validation-panel is-error">
          <div v-for="(issue, index) in validationErrors" :key="index">{{ issue.field_path || '内容' }}：{{ issue.message }}</div>
        </div>
        <div v-if="validationWarnings.length" class="validation-panel is-warning">
          <div v-for="(issue, index) in validationWarnings" :key="index">{{ issue.field_path || '内容' }}：{{ issue.message }}</div>
        </div>
        <div v-if="draftConflict" class="validation-panel is-conflict">
          草稿已被其他人更新，当前编辑内容已保留。刷新后将载入最新版本。
          <el-button text type="warning" @click="refreshDraftAfterConflict">刷新最新版本</el-button>
        </div>
        <div class="editor-actions">
          <el-button :icon="Download" :disabled="!draft?.file_name" @click="draft && downloadVersion(draft)">下载当前源文件</el-button>
          <el-button :loading="saving" :disabled="!actionState.save" @click="saveDraft">保存草稿</el-button>
          <el-button :loading="saving" :disabled="!actionState.validate" @click="validateDraft">校验</el-button>
          <el-button type="primary" :loading="publishing" :disabled="!actionState.publish" @click="publishDraft">发布</el-button>
        </div>
        <div class="history-title">版本历史</div>
        <div v-for="version in versions" :key="version.id" class="history-row">
          <span>版本 {{ version.version_number }} · {{ version.status }}</span>
          <el-button text @click="downloadVersion(version)" :disabled="!version.file_name">下载</el-button>
        </div>
        <div v-if="publishJob" class="publish-status">发布任务：{{ publishJob.status }}{{ publishJob.stage ? ` · ${publishJob.stage}` : '' }}</div>
      </div>
    </el-drawer>
    <KnowledgeRetrievalPreview v-model="retrievalPreviewVisible" />
  </div>
</template>

<style scoped lang="less">
.knowledge-v2-panel { height: 100%; padding: 0 0 24px; color: #1f2329; }
.panel-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; margin-bottom: 18px; }
.panel-title { font-size: 16px; font-weight: 600; line-height: 24px; }
.panel-subtitle { margin-top: 4px; color: #667085; font-size: 13px; line-height: 20px; }
.panel-actions { display: flex; align-items: center; gap: 8px; }
.panel-actions .el-input { width: 220px; }
.panel-actions .el-select { width: 150px; }
.knowledge-v2-table { min-height: 160px; }
.empty-state { display: inline-flex; min-height: 120px; align-items: center; color: #8f959e; }
.muted-text { color: #98a2b3; }
.editor-toolbar, .editor-actions, .history-row { display: flex; align-items: center; gap: 8px; }
.editor-layout { padding: 0 2px 24px; }
.editor-toolbar { margin-bottom: 16px; flex-wrap: wrap; color: #667085; font-size: 12px; }
.workspace-override { display: inline-flex; align-items: center; gap: 6px; color: #475467; }
.version-file { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pending-file { margin-left: 8px; color: #1570ef; font-size: 12px; }
.validation-panel { margin-top: 14px; padding: 10px 12px; border-radius: 6px; font-size: 12px; line-height: 20px; }
.validation-panel.is-error { color: #b42318; background: #fff1f3; }
.validation-panel.is-warning { color: #9a6700; background: #fff8e6; }
.validation-panel.is-conflict { display: flex; align-items: center; gap: 8px; color: #9a6700; background: #fff8e6; }
.editor-actions { justify-content: flex-end; margin-top: 18px; flex-wrap: wrap; }
.history-title { margin-top: 24px; padding-bottom: 8px; border-bottom: 1px solid #eaecf0; color: #344054; font-size: 13px; font-weight: 600; }
.history-row { justify-content: space-between; min-height: 36px; border-bottom: 1px solid #f2f4f7; color: #667085; font-size: 12px; }
.publish-status { margin-top: 12px; color: #1570ef; font-size: 12px; }
@media (max-width: 980px) { .panel-header { flex-direction: column; } .panel-actions { width: 100%; flex-wrap: wrap; } }
@media (max-width: 680px) { .panel-actions .el-input, .panel-actions .el-select { width: 100%; } }
</style>
