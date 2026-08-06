<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Download, Plus, Refresh, Upload } from '@element-plus/icons-vue'
import { cloneDeep } from 'lodash-es'
import { useUserStore } from '@/stores/user'
import {
  knowledgeBaseApi,
  type KnowledgeBaseItem,
  type KnowledgeBaseScope,
  type KnowledgeBaseVersion,
  type KnowledgePublishJob,
} from '@/api/knowledgeBase'
import KnowledgePayloadEditor from './KnowledgePayloadEditor.vue'

const userStore = useUserStore()
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
  await loadVersions()
}

async function loadVersions() {
  if (!selected.value) return
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
  if (!selected.value || !draft.value || !canEdit.value) return
  try {
    saving.value = true
    if (pendingFile.value) {
      draft.value = await knowledgeBaseApi.replaceDraftFile(selected.value.id, {
        version_id: draft.value.id,
        revision: draft.value.revision,
        file: pendingFile.value,
      })
      pendingFile.value = null
    }
    draft.value = await knowledgeBaseApi.saveDraft(selected.value.id, {
      version_id: draft.value.id,
      revision: draft.value.revision,
      content: payload.value,
    })
    ElMessage.success('草稿已保存')
  } catch (error: any) {
    if (error?.response?.status === 409) ElMessage.error('草稿已被其他人更新，请刷新版本后重试。')
    throw error
  } finally {
    saving.value = false
  }
}

async function validateDraft() {
  if (!selected.value || !draft.value) return
  try {
    saving.value = true
    if (draft.value.payload !== payload.value) await saveDraft()
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
  if (!selected.value || !draft.value || draft.value.status !== 'READY_TO_PUBLISH') return
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
  loadItems()
}

onMounted(loadItems)
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
        <el-button type="primary" :icon="Plus" @click="openCreate">新建知识库</el-button>
      </div>
    </div>

    <div v-loading="loading" class="knowledge-v2-list">
      <div v-if="!visibleItems.length" class="empty-state">暂无知识库</div>
      <article v-for="item in visibleItems" :key="item.id" class="knowledge-v2-card" @click="openEditor(item)">
        <div class="card-title-row">
          <span class="card-title">{{ item.name }}</span>
          <el-tag size="small" :type="item.visibility_scope === 'PLATFORM_PUBLIC' ? 'warning' : 'primary'">
            {{ item.visibility_scope === 'PLATFORM_PUBLIC' ? '平台公共知识' : '工作空间知识' }}
          </el-tag>
        </div>
        <div class="card-description">{{ item.description || '未填写描述' }}</div>
        <div class="card-meta">
          <span>{{ item.knowledge_type || '未分类' }}</span>
          <span>{{ item.current_version_id ? `当前版本 #${item.current_version_id}` : '尚未发布' }}</span>
          <el-tag v-if="item.publishing_version_id" size="small" type="warning">发布中</el-tag>
        </div>
      </article>
    </div>

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
          <span class="version-status">草稿状态：{{ draftStatus }}</span>
          <span v-if="draft?.file_name" class="version-file">源文件：{{ draft.file_name }}</span>
        </div>
        <KnowledgePayloadEditor v-model="payload" :readonly="!canEdit" />
        <el-upload :disabled="!canEdit" :auto-upload="false" :show-file-list="false" accept=".md,.markdown,.docx" :before-upload="selectFile">
          <el-button :icon="Upload">替换源文件</el-button>
        </el-upload>
        <span v-if="pendingFile" class="pending-file">待上传：{{ pendingFile.name }}</span>
        <div v-if="validationErrors.length" class="validation-panel is-error">
          <div v-for="(issue, index) in validationErrors" :key="index">{{ issue.field_path || '内容' }}：{{ issue.message }}</div>
        </div>
        <div v-if="validationWarnings.length" class="validation-panel is-warning">
          <div v-for="(issue, index) in validationWarnings" :key="index">{{ issue.field_path || '内容' }}：{{ issue.message }}</div>
        </div>
        <div class="editor-actions">
          <el-button :icon="Download" :disabled="!draft?.file_name" @click="draft && downloadVersion(draft)">下载当前源文件</el-button>
          <el-button :loading="saving" :disabled="!canEdit || !draft" @click="saveDraft">保存草稿</el-button>
          <el-button :loading="saving" :disabled="!canEdit || !draft" @click="validateDraft">校验</el-button>
          <el-button type="primary" :loading="publishing" :disabled="draft?.status !== 'READY_TO_PUBLISH'" @click="publishDraft">发布</el-button>
        </div>
        <div class="history-title">版本历史</div>
        <div v-for="version in versions" :key="version.id" class="history-row">
          <span>版本 {{ version.version_number }} · {{ version.status }}</span>
          <el-button text @click="downloadVersion(version)" :disabled="!version.file_name">下载</el-button>
        </div>
        <div v-if="publishJob" class="publish-status">发布任务：{{ publishJob.status }}{{ publishJob.stage ? ` · ${publishJob.stage}` : '' }}</div>
      </div>
    </el-drawer>
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
.knowledge-v2-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 12px; min-height: 120px; }
.empty-state { grid-column: 1 / -1; display: grid; place-items: center; min-height: 120px; border: 1px solid #dee0e3; border-radius: 8px; color: #8f959e; }
.knowledge-v2-card { min-height: 142px; padding: 16px; border: 1px solid #dee0e3; border-radius: 8px; background: #fff; cursor: pointer; transition: border-color .15s, box-shadow .15s; }
.knowledge-v2-card:hover { border-color: #7b9ff5; box-shadow: 0 6px 16px rgba(16, 24, 40, .08); }
.card-title-row, .card-meta, .editor-toolbar, .editor-actions, .history-row { display: flex; align-items: center; gap: 8px; }
.card-title-row { justify-content: space-between; }
.card-title { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 14px; font-weight: 600; }
.card-description { min-height: 40px; margin-top: 12px; color: #475467; font-size: 13px; line-height: 20px; }
.card-meta { margin-top: 10px; color: #667085; font-size: 12px; flex-wrap: wrap; }
.editor-layout { padding: 0 2px 24px; }
.editor-toolbar { margin-bottom: 16px; flex-wrap: wrap; color: #667085; font-size: 12px; }
.version-file { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pending-file { margin-left: 8px; color: #1570ef; font-size: 12px; }
.validation-panel { margin-top: 14px; padding: 10px 12px; border-radius: 6px; font-size: 12px; line-height: 20px; }
.validation-panel.is-error { color: #b42318; background: #fff1f3; }
.validation-panel.is-warning { color: #9a6700; background: #fff8e6; }
.editor-actions { justify-content: flex-end; margin-top: 18px; flex-wrap: wrap; }
.history-title { margin-top: 24px; padding-bottom: 8px; border-bottom: 1px solid #eaecf0; color: #344054; font-size: 13px; font-weight: 600; }
.history-row { justify-content: space-between; min-height: 36px; border-bottom: 1px solid #f2f4f7; color: #667085; font-size: 12px; }
.publish-status { margin-top: 12px; color: #1570ef; font-size: 12px; }
@media (max-width: 980px) { .panel-header { flex-direction: column; } .panel-actions { width: 100%; flex-wrap: wrap; } }
@media (max-width: 680px) { .panel-actions .el-input, .panel-actions .el-select { width: 100%; } }
</style>
