<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  ArrowDown,
  Delete,
  Download,
  FolderDelete,
  Plus,
  Refresh,
  RefreshLeft,
  Search,
  UploadFilled,
} from '@element-plus/icons-vue'
import type { UploadFile, UploadProps, UploadRawFile } from 'element-plus'
import { cloneDeep } from 'lodash-es'
import { useUserStore } from '@/stores/user'
import {
  knowledgeBaseApi,
  type KnowledgeBaseItem,
  type KnowledgeBaseScope,
  type KnowledgeBaseVersion,
  type KnowledgePublishJob,
  type KnowledgeApplicabilityState,
  type KnowledgeConflictDetails,
} from '@/api/knowledgeBase'
import { useDatasourceContextStore } from '@/stores/datasourceContext'
import { tenantApi, type TenantInfo } from '@/api/tenant'
import KnowledgePayloadEditor from './KnowledgePayloadEditor.vue'
import { knowledgeActionState } from './knowledgeEditorState'
import KnowledgeRetrievalPreview from './KnowledgeRetrievalPreview.vue'
import KnowledgeApplicabilityTag from './KnowledgeApplicabilityTag.vue'
import {
  downloadKnowledgeMarkdownTemplate,
  knowledgeMarkdownTemplates,
} from './knowledgeMarkdownTemplates'
import {
  KNOWLEDGE_MARKDOWN_FORMAT_ERROR,
  isKnowledgeMarkdownFileName,
  parseKnowledgeMarkdownFile,
} from './knowledgeMarkdownFormat'
import {
  defaultKnowledgePayload,
  createDocumentBlock,
  normalizeDocumentPayload,
  type DocumentBlock,
  type DocumentPayload,
  type KnowledgePayload,
} from './knowledgePayloadTypes'
import { useKnowledgeScopeNavigation } from './knowledgeScopeNavigation'
import { formatRequestErrorMessage } from '@/utils/request'

const userStore = useUserStore()
const datasourceContext = useDatasourceContextStore()
const isPlatformAdmin = computed(
  () => userStore.isSystemAdminUser && !userStore.isPlatformWorkspaceDelegate
)
const items = ref<KnowledgeBaseItem[]>([])
const loading = ref(false)
const listError = ref(false)
const saving = ref(false)
const sourceUploading = ref(false)
const publishing = ref(false)
type RowAction = 'upload' | 'download' | 'restore' | 'purge'

const rowActionBusy = ref<Record<string, RowAction>>({})
const editorVisible = ref(false)
const createVisible = ref(false)
const createSourceFile = ref<File | null>(null)
const selected = ref<KnowledgeBaseItem | null>(null)
const versions = ref<KnowledgeBaseVersion[]>([])
const draft = ref<KnowledgeBaseVersion | null>(null)
const payload = ref<KnowledgePayload>(defaultKnowledgePayload())
const keyword = ref('')
const archiveFilter = ref<'current' | 'archived'>('current')
const scopeFilter = useKnowledgeScopeNavigation()
const workspaceFilter = ref<string>(isPlatformAdmin.value ? '' : String(userStore.getTenantId || ''))
const workspaces = ref<TenantInfo[]>([])
const createForm = ref({ name: '', description: '', visibility_scope: 'ADMIN_PUBLIC' as KnowledgeBaseScope })
const publishJob = ref<KnowledgePublishJob | null>(null)
const draftConflict = ref(false)
const documentConflict = ref<{
  type: string
  localBlock?: DocumentBlock
  serverBlock?: DocumentBlock
  details: KnowledgeConflictDetails
} | null>(null)
const retrievalPreviewVisible = ref(false)
const workspaceOverride = ref<{ enabled: boolean; reason?: string | null } | null>(null)
const overrideLoading = ref(false)
const applicability = ref<KnowledgeApplicabilityState | null>(null)
const applicabilityLoading = ref(false)
let publishTimer: ReturnType<typeof window.setInterval> | null = null

const isArchivedView = computed(() => archiveFilter.value === 'archived')
const canCreateKnowledgeInScope = computed(
  () => isPlatformAdmin.value
    ? scopeFilter.value === 'PLATFORM_PUBLIC' || Boolean(workspaceFilter.value)
    : userStore.isTenantAdminUser && scopeFilter.value === 'ADMIN_PUBLIC')
const canCreateKnowledge = computed(
  () => canCreateKnowledgeInScope.value && !isArchivedView.value
)
const visibleItems = computed(() => {
  const text = keyword.value.trim().toLowerCase()
  if (!text) return items.value
  return items.value.filter((item) => `${item.name} ${item.description || ''}`.toLowerCase().includes(text))
})
const canEdit = computed(() => !!selected.value?.can_manage && !selected.value.archived)
const editorTitle = computed(() => {
  if (!selected.value) return '知识库详情'
  return `${canEdit.value ? '编辑' : '查看'}知识库：${selected.value.name}`
})
const draftStatus = computed(() => draft.value?.status || '无草稿')
const currentVersion = computed(() => versions.value.find((version) => version.status === 'PUBLISHED') || null)
const archivedPublishedVersion = computed(() => versions.value.find(
  (version) => version.status === 'ARCHIVED' && Boolean(version.publish_time)
) || null)
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
  () => !selected.value?.archived
    && selected.value?.visibility_scope === 'PLATFORM_PUBLIC'
    && userStore.isTenantAdminUser
)
const workspaceFilterVisible = computed(() => scopeFilter.value === 'ADMIN_PUBLIC')
const workspaceFilterDisabled = computed(() => !isPlatformAdmin.value)
const workspaceOptions = computed<TenantInfo[]>(() => {
  if (isPlatformAdmin.value) return workspaces.value
  if (!userStore.getTenantId) return []
  return [{
    id: userStore.getTenantId,
    name: userStore.getTenantName || userStore.getTenantId,
    role: userStore.getTenantRole || 'member',
  }]
})
const workspaceKnowledgeEnabled = computed({
  get: () => workspaceOverride.value?.enabled !== false,
  set: (value: boolean) => {
    if (workspaceOverride.value) workspaceOverride.value.enabled = value
  },
})

async function loadItems() {
  loading.value = true
  try {
    const base = { keyword: keyword.value || undefined }
    if (scopeFilter.value === 'ADMIN_PUBLIC' && !workspaceFilter.value) {
      items.value = []
    } else {
      items.value = await knowledgeBaseApi.list({
        ...base,
        visibility_scope: scopeFilter.value,
        tenant_id: scopeFilter.value === 'ADMIN_PUBLIC' ? workspaceFilter.value : undefined,
        archived: isArchivedView.value,
      })
    }
    listError.value = false
  } catch (error) {
    console.error(error)
    listError.value = true
  } finally {
    loading.value = false
  }
}

function openCreate() {
  createForm.value = {
    name: '',
    description: '',
    visibility_scope: scopeFilter.value,
  }
  createSourceFile.value = null
  createVisible.value = true
}

const handleCreateSourceChange: UploadProps['onChange'] = async (uploadFile: UploadFile) => {
  createSourceFile.value = null
  const file = uploadFile.raw
  if (!file) return
  if (!await validateSourceFile(file)) return
  createSourceFile.value = file
}

async function createKnowledge() {
  if (!createForm.value.name.trim()) {
    ElMessage.warning('请输入知识库名称')
    return
  }
  if (createForm.value.visibility_scope === 'ADMIN_PUBLIC' && !workspaceFilter.value) {
    ElMessage.warning('请选择工作空间')
    return
  }
  const sourceFile = createSourceFile.value
  try {
    saving.value = true
    const item = await knowledgeBaseApi.create({
      ...createForm.value,
      name: createForm.value.name.trim(),
      tenant_id: createForm.value.visibility_scope === 'ADMIN_PUBLIC'
        ? workspaceFilter.value
        : undefined,
    })
    createVisible.value = false
    await loadItems()
    await openEditor(item)
    if (sourceFile && selected.value) {
      if (!draft.value) {
        await knowledgeBaseApi.createDraft(selected.value.id, defaultKnowledgePayload())
        await loadVersions()
      }
      await replaceDraftSource(sourceFile)
      await loadVersions()
    }
  } finally {
    saving.value = false
  }
}

async function openEditor(item: KnowledgeBaseItem) {
  selected.value = await knowledgeBaseApi.detail(item.id)
  editorVisible.value = true
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
  if (!selected.value.archived) await loadApplicability()
}

async function loadApplicability() {
  applicability.value = null
  if (!selected.value || selected.value.visibility_scope !== 'PLATFORM_PUBLIC') return
  if (isPlatformAdmin.value) return
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
  if (draft.value) payload.value = normalizeLoadedPayload(draft.value.payload)
  else if (currentVersion.value) payload.value = normalizeLoadedPayload(currentVersion.value.payload)
  else if (archivedPublishedVersion.value) payload.value = normalizeLoadedPayload(archivedPublishedVersion.value.payload)
  else payload.value = defaultKnowledgePayload()
}

function normalizeLoadedPayload(value: Record<string, any>): KnowledgePayload {
  return normalizeDocumentPayload(value)
}

function documentBlockChanged(local: DocumentBlock, server: DocumentBlock) {
  return local.title !== server.title
    || local.markdown !== server.markdown
    || local.enabled !== server.enabled
}

function documentStructureChanged(local: DocumentPayload, server: DocumentPayload) {
  return local.blocks.map((block) => block.id).join('\u0000') !== server.blocks.map((block) => block.id).join('\u0000')
    || local.datasource_neutral !== server.datasource_neutral
    || JSON.stringify(local.tags) !== JSON.stringify(server.tags)
    || JSON.stringify(local.object_references) !== JSON.stringify(server.object_references)
}

function captureDocumentConflict(error: any, localBlock?: DocumentBlock) {
  const details = (error?.response?.data?.details || {}) as KnowledgeConflictDetails
  documentConflict.value = {
    type: details.conflict_type || 'STRUCTURE',
    localBlock: localBlock ? cloneDeep(localBlock) : undefined,
    serverBlock: details.server_block
      ? cloneDeep(details.server_block) as DocumentBlock
      : undefined,
    details,
  }
  draftConflict.value = true
}

function restoreDeletedConflictBlock() {
  if (!draft.value || !documentConflict.value?.localBlock) return
  const serverPayload = normalizeDocumentPayload(documentConflict.value.details.server_payload || draft.value.payload)
  const localBlock = documentConflict.value.localBlock
  const restored = createDocumentBlock(localBlock.title, localBlock.markdown)
  restored.enabled = localBlock.enabled
  draft.value = { ...draft.value, payload: serverPayload }
  payload.value = { ...serverPayload, blocks: [...serverPayload.blocks, restored] }
  documentConflict.value = null
  draftConflict.value = false
  ElMessage.info('本地内容已恢复为新知识块，请保存草稿。')
}

async function saveDocumentDraft(localPayload: DocumentPayload) {
  if (!selected.value || !draft.value) return false
  const serverPayload = normalizeDocumentPayload(draft.value.payload)
  const serverById = new Map(serverPayload.blocks.map((block) => [block.id, block]))
  let persisted = false
  for (const localBlock of localPayload.blocks) {
    const serverBlock = serverById.get(localBlock.id)
    if (!serverBlock || !documentBlockChanged(localBlock, serverBlock)) continue
    try {
      draft.value = await knowledgeBaseApi.saveDocumentBlock(selected.value.id, localBlock.id, {
        version_id: draft.value.id,
        block_revision: serverBlock.block_revision,
        title: localBlock.title,
        markdown: localBlock.markdown,
        enabled: localBlock.enabled,
      })
      persisted = true
    } catch (error: any) {
      if (error?.response?.status === 409) {
        captureDocumentConflict(error, localBlock)
        return false
      }
      throw error
    }
  }
  const latestServer = normalizeDocumentPayload(draft.value.payload)
  if (documentStructureChanged(localPayload, latestServer)) {
    try {
      draft.value = await knowledgeBaseApi.saveDocumentStructure(selected.value.id, {
        version_id: draft.value.id,
        structure_revision: serverPayload.structure_revision,
        content: localPayload,
      })
      persisted = true
    } catch (error: any) {
      if (error?.response?.status === 409) {
        captureDocumentConflict(error)
        return false
      }
      throw error
    }
  }
  if (!persisted) {
    draft.value = await knowledgeBaseApi.saveDraft(selected.value.id, {
      version_id: draft.value.id,
      revision: draft.value.revision,
      content: localPayload,
    })
  }
  payload.value = normalizeDocumentPayload(draft.value.payload)
  documentConflict.value = null
  return true
}

async function createEditingDraft() {
  if (!selected.value || !canEdit.value || draft.value) return
  const current = currentVersion.value
  draft.value = current
    ? await knowledgeBaseApi.rollback(selected.value.id, current.id)
    : await knowledgeBaseApi.createDraft(selected.value.id, defaultKnowledgePayload())
  await loadVersions()
  ElMessage.success('编辑草稿已创建')
}

async function rollbackVersion(version: KnowledgeBaseVersion) {
  if (!selected.value || !canEdit.value || draft.value) return
  draft.value = await knowledgeBaseApi.rollback(selected.value.id, version.id)
  await loadVersions()
  ElMessage.success(`已基于版本 ${version.version_number} 创建回滚草稿`)
}

async function archiveKnowledge(row: KnowledgeBaseItem) {
  await ElMessageBox.confirm(
    `归档后“${row.name}”将不再参与检索，但历史版本仍会保留。`,
    '归档知识库',
    { confirmButtonText: '归档', cancelButtonText: '取消', type: 'warning' }
  )
  const result = await knowledgeBaseApi.delete(row.id)
  if (selected.value?.id === row.id) editorVisible.value = false
  await loadItems()
  if (result.file_cleanup.failed > 0) {
    ElMessage.warning('未发布知识库已删除，部分源文件清理失败，请联系管理员处理')
  } else {
    ElMessage.success(result.archived ? '知识库已归档' : '未发布知识库已删除')
  }
}

async function restoreKnowledge(row: KnowledgeBaseItem) {
  if (!row.can_manage || rowBusyState(row)) return
  await ElMessageBox.confirm(
    `恢复后“${row.name}”的已发布版本将重新参与检索。`,
    '恢复知识库',
    { confirmButtonText: '恢复', cancelButtonText: '取消', type: 'warning' }
  )
  setRowBusy(row, 'restore')
  try {
    await knowledgeBaseApi.restore(row.id)
    if (selected.value?.id === row.id) editorVisible.value = false
    await loadItems()
    ElMessage.success('知识库已恢复并重新参与检索')
  } finally {
    setRowBusy(row)
  }
}

async function permanentlyDeleteKnowledge(row: KnowledgeBaseItem) {
  if (!row.archived || !row.can_manage || rowBusyState(row)) return
  await ElMessageBox.prompt(
    `此操作会永久删除“${row.name}”的全部版本、检索数据和无引用源文件，无法恢复。请输入完整知识库名称确认。`,
    '永久删除知识库',
    {
      confirmButtonText: '永久删除',
      cancelButtonText: '取消',
      type: 'error',
      inputPlaceholder: row.name,
      inputValidator: (value) => value === row.name || '知识库名称不匹配',
    }
  )
  setRowBusy(row, 'purge')
  try {
    const result = await knowledgeBaseApi.permanentDelete(row.id)
    if (selected.value?.id === row.id) editorVisible.value = false
    await loadItems()
    if (result.file_cleanup.failed > 0) {
      ElMessage.warning('知识库已永久删除，部分源文件清理失败，请联系管理员处理')
    } else {
      ElMessage.success('知识库已永久删除')
    }
  } finally {
    setRowBusy(row)
  }
}

async function saveDraft() {
  if (!selected.value || !draft.value || !actionState.value.save) return false
  try {
    saving.value = true
    const saved = await saveDocumentDraft(cloneDeep(payload.value))
    if (!saved) return false
    await loadVersions()
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

function isSupportedSourceFile(file: File) {
  return isKnowledgeMarkdownFileName(file.name)
}

async function validateSourceFile(file: File) {
  if (!isSupportedSourceFile(file)) {
    ElMessage.error(`${KNOWLEDGE_MARKDOWN_FORMAT_ERROR}仅支持 .md 或 .markdown 文件。`)
    return false
  }
  if (file.size > 50 * 1024 * 1024) {
    ElMessage.warning('源文件不能超过 50 MB')
    return false
  }
  try {
    await parseKnowledgeMarkdownFile(file)
    return true
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : KNOWLEDGE_MARKDOWN_FORMAT_ERROR)
    return false
  }
}

function rowBusyState(row: KnowledgeBaseItem) {
  return rowActionBusy.value[String(row.id)]
}

function setRowBusy(row: KnowledgeBaseItem, action?: RowAction) {
  const key = String(row.id)
  if (action) rowActionBusy.value[key] = action
  else delete rowActionBusy.value[key]
}

async function uploadRowSource(row: KnowledgeBaseItem, file: File) {
  if (!row.can_manage || rowBusyState(row)) return
  if (!await validateSourceFile(file)) return

  setRowBusy(row, 'upload')
  try {
    let rowDraft: KnowledgeBaseVersion | null = null
    if (row.draft_version_id != null) {
      rowDraft = await knowledgeBaseApi.version(row.id, row.draft_version_id)
    }
    if (!rowDraft) {
      rowDraft = row.current_version_id != null
        ? await knowledgeBaseApi.rollback(row.id, row.current_version_id)
        : await knowledgeBaseApi.createDraft(row.id, defaultKnowledgePayload())
    }
    await knowledgeBaseApi.replaceDraftFile(row.id, {
      version_id: rowDraft.id,
      revision: rowDraft.revision,
      file,
    })
    await loadItems()
    ElMessage.success('源文件已上传并保存为草稿，请编辑、校验后发布')
  } finally {
    setRowBusy(row)
  }
}

function rowSourceChangeHandler(row: KnowledgeBaseItem): NonNullable<UploadProps['onChange']> {
  return (uploadFile: UploadFile) => {
    if (uploadFile.raw) {
      void uploadRowSource(row, uploadFile.raw as UploadRawFile).catch((error) => {
        console.error(error)
      })
    }
  }
}

async function replaceDraftSource(file: File) {
  if (!selected.value || !draft.value) return
  if (!await validateSourceFile(file)) return
  sourceUploading.value = true
  try {
    draft.value = await knowledgeBaseApi.replaceDraftFile(selected.value.id, {
      version_id: draft.value.id,
      revision: draft.value.revision,
      file,
    })
    payload.value = normalizeDocumentPayload(draft.value.payload)
    draftConflict.value = false
    documentConflict.value = null
    ElMessage.success('源文件已解析并保存为知识块，请校验后发布')
  } finally {
    sourceUploading.value = false
  }
}

const handleSourceFileChange: UploadProps['onChange'] = (uploadFile: UploadFile) => {
  if (uploadFile.raw) void replaceDraftSource(uploadFile.raw as UploadRawFile)
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
  documentConflict.value = null
  ElMessage.success('已刷新最新草稿，请确认内容后继续编辑。')
}

function loadServerConflictBlock() {
  if (!documentConflict.value?.serverBlock) return
  const serverBlock = documentConflict.value.serverBlock
  payload.value = {
    ...payload.value,
    blocks: payload.value.blocks.map((block) => block.id === serverBlock.id ? cloneDeep(serverBlock) : block),
  }
  documentConflict.value = null
  draftConflict.value = false
}

async function retryLocalConflictBlock() {
  if (!selected.value || !draft.value || !documentConflict.value?.localBlock || !documentConflict.value.serverBlock) return
  const localBlock = cloneDeep(documentConflict.value.localBlock)
  const serverBlock = documentConflict.value.serverBlock
  saving.value = true
  try {
    draft.value = await knowledgeBaseApi.saveDocumentBlock(selected.value.id, localBlock.id, {
      version_id: draft.value.id,
      block_revision: serverBlock.block_revision,
      title: localBlock.title,
      markdown: localBlock.markdown,
      enabled: localBlock.enabled,
    })
    const savedBlock = normalizeDocumentPayload(draft.value.payload).blocks.find((block) => block.id === localBlock.id)
    if (savedBlock) {
      payload.value = {
        ...payload.value,
        blocks: payload.value.blocks.map((block) => block.id === savedBlock.id ? savedBlock : block),
      }
    }
    documentConflict.value = null
    draftConflict.value = false
    ElMessage.success('本地知识块已基于最新版本保存')
  } catch (error: any) {
    if (error?.response?.status === 409) captureDocumentConflict(error, localBlock)
    else throw error
  } finally {
    saving.value = false
  }
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

function downloadBlob(blob: Blob, fileName: string) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = fileName
  anchor.hidden = true
  try {
    document.body.appendChild(anchor)
    anchor.click()
  } finally {
    anchor.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 0)
  }
}

function showSourceDownloadError(error: unknown) {
  const message = formatRequestErrorMessage(error, '源文件下载失败，请稍后重试')
  ElMessage.error(
    message.includes('知识源文件不存在')
      ? '知识源文件不存在，请重新上传源文件后再发布。'
      : message
  )
}

async function downloadVersion(version: KnowledgeBaseVersion) {
  if (!selected.value) return
  try {
    const blob = await knowledgeBaseApi.download(selected.value.id, version.id)
    downloadBlob(blob, version.file_name || `knowledge-${version.version_number}`)
  } catch (error) {
    showSourceDownloadError(error)
  }
}

async function downloadRowSource(row: KnowledgeBaseItem) {
  if (rowBusyState(row)) return
  setRowBusy(row, 'download')
  try {
    let sourceVersion: KnowledgeBaseVersion | null = null
    if (row.archived) {
      const rowVersions = await knowledgeBaseApi.versions(row.id)
      sourceVersion = rowVersions.find(
        (version) => version.status === 'ARCHIVED' && Boolean(version.publish_time)
      ) || null
    } else if (row.draft_version_id != null) {
      sourceVersion = await knowledgeBaseApi.version(row.id, row.draft_version_id)
    }
    if (!sourceVersion?.file_name && row.current_version_id != null && !row.archived) {
      sourceVersion = await knowledgeBaseApi.version(row.id, row.current_version_id)
    }
    if (!sourceVersion?.file_name) {
      ElMessage.warning('该知识库暂无可下载的源文件')
      return
    }
    const blob = await knowledgeBaseApi.download(row.id, sourceVersion.id)
    downloadBlob(blob, sourceVersion.file_name)
  } catch (error) {
    showSourceDownloadError(error)
  } finally {
    setRowBusy(row)
  }
}

function downloadMarkdownTemplate(command: string | number | object) {
  const template = knowledgeMarkdownTemplates.find(({ id }) => id === command)
  if (template) downloadKnowledgeMarkdownTemplate(template)
}

function closeEditor() {
  editorVisible.value = false
  if (publishTimer) window.clearInterval(publishTimer)
  publishTimer = null
  applicability.value = null
  loadItems()
}

onMounted(async () => {
  if (isPlatformAdmin.value) {
    workspaces.value = (await tenantApi.adminList()).filter(
      (workspace) => !workspace.is_system_default && Number(workspace.status ?? 1) === 1
    )
  }
  await loadItems()
})
watch([scopeFilter, workspaceFilter, archiveFilter], () => {
  if (editorVisible.value) {
    editorVisible.value = false
    if (publishTimer) window.clearInterval(publishTimer)
    publishTimer = null
    applicability.value = null
  }
  loadItems()
})
watch(() => datasourceContext.datasourceId, () => {
  if (editorVisible.value && !selected.value?.archived && selected.value?.visibility_scope === 'PLATFORM_PUBLIC') loadApplicability()
})
onBeforeUnmount(() => { if (publishTimer) window.clearInterval(publishTimer) })
</script>

<template>
  <div class="knowledge-v2-panel">
    <div class="panel-header">
      <div class="panel-actions">
        <div class="panel-filters">
          <el-radio-group v-model="archiveFilter" class="knowledge-archive-filter">
            <el-radio-button value="current">当前知识</el-radio-button>
            <el-radio-button value="archived">已归档</el-radio-button>
          </el-radio-group>
          <el-input
            v-model="keyword"
            class="knowledge-filter-input"
            clearable
            placeholder="搜索知识库"
            @keyup.enter="loadItems"
          />
          <el-select
            v-model="scopeFilter"
            class="knowledge-filter-scope"
            placeholder="选择知识库范围"
          >
            <el-option label="平台知识库" value="PLATFORM_PUBLIC" />
            <el-option label="工作空间知识库" value="ADMIN_PUBLIC" />
          </el-select>
          <el-select
            v-if="workspaceFilterVisible"
            v-model="workspaceFilter"
            class="knowledge-filter-workspace"
            :disabled="workspaceFilterDisabled"
            placeholder="选择工作空间"
          >
            <el-option
              v-for="workspace in workspaceOptions"
              :key="workspace.id"
              :label="workspace.name"
              :value="String(workspace.id)"
            />
          </el-select>
        </div>
        <div class="panel-buttons">
          <el-button :icon="Refresh" @click="loadItems">刷新</el-button>
          <span class="panel-action-slot" :class="{ 'is-placeholder': isArchivedView }" :aria-hidden="isArchivedView ? 'true' : undefined">
            <el-button :icon="Search" :tabindex="isArchivedView ? -1 : undefined" @click="retrievalPreviewVisible = true">检索预览</el-button>
          </span>
          <el-dropdown
            class="template-download panel-action-slot"
            :class="{ 'is-placeholder': isArchivedView }"
            :aria-hidden="isArchivedView ? 'true' : undefined"
            trigger="click"
            @command="downloadMarkdownTemplate"
          >
            <el-button :icon="Download" :tabindex="isArchivedView ? -1 : undefined">
              下载 Markdown 模板
              <el-icon class="template-download-arrow"><ArrowDown /></el-icon>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item
                  v-for="template in knowledgeMarkdownTemplates"
                  :key="template.id"
                  :command="template.id"
                >
                  {{ template.label }}
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <span
            v-if="canCreateKnowledgeInScope"
            class="panel-action-slot"
            :class="{ 'is-placeholder': !canCreateKnowledge }"
            :aria-hidden="!canCreateKnowledge ? 'true' : undefined"
          >
            <el-button type="primary" :icon="Plus" :tabindex="canCreateKnowledge ? undefined : -1" @click="openCreate">新建知识库</el-button>
          </span>
        </div>
      </div>
    </div>

    <el-alert
      v-if="listError"
      class="list-error"
      type="error"
      :closable="false"
      title="知识库列表加载失败，请重试。"
    >
      <template #default>
        <el-button text type="primary" :loading="loading" @click="loadItems">重试</el-button>
      </template>
    </el-alert>
    <el-table
      v-else
      v-loading="loading"
      :data="visibleItems"
      row-key="id"
      class="knowledge-v2-table"
      @row-click="openEditor"
    >
      <el-table-column prop="name" label="名称" min-width="220" show-overflow-tooltip />
      <el-table-column label="知识范围" width="150">
        <template #default="{ row }">
          <el-tag size="small" :type="row.visibility_scope === 'PLATFORM_PUBLIC' ? 'warning' : 'primary'">
            {{ row.visibility_scope === 'PLATFORM_PUBLIC' ? '平台公共知识' : '工作空间知识' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="发布版本" width="130">
        <template #default="{ row }">
          <el-tag v-if="row.archived" size="small" type="info">已归档</el-tag>
          <el-tag v-else-if="row.publishing_version_id" size="small" type="warning">发布中</el-tag>
          <el-tag v-else-if="row.current_version_id" size="small" type="success">已发布</el-tag>
          <span v-else class="muted-text">尚未发布</span>
        </template>
      </el-table-column>
      <el-table-column label="更新时间" width="170">
        <template #default="{ row }">{{ row.update_time || '-' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="340" fixed="right">
        <template #default="{ row }">
          <div class="row-actions">
            <el-button text type="primary" :disabled="Boolean(rowBusyState(row))" @click.stop="openEditor(row)">{{ row.archived || !row.can_manage ? '查看' : '编辑' }}</el-button>
            <span
              v-if="!row.archived && row.can_manage"
              class="row-source-upload"
              @click.stop
            >
              <el-upload
                action="#"
                :auto-upload="false"
                :show-file-list="false"
                accept=".md,.markdown"
                :disabled="Boolean(rowBusyState(row))"
                :on-change="rowSourceChangeHandler(row)"
              >
                <el-button
                  text
                  type="primary"
                  :icon="UploadFilled"
                  :loading="rowBusyState(row) === 'upload'"
                  aria-label="上传源文件"
                  title="上传源文件"
                >上传</el-button>
              </el-upload>
            </span>
            <el-button
              text
              type="primary"
              :icon="Download"
              :loading="rowBusyState(row) === 'download'"
              :disabled="rowBusyState(row) === 'upload'"
              aria-label="下载源文件"
              title="下载源文件"
              @click.stop="downloadRowSource(row)"
            >下载</el-button>
            <template v-if="row.archived && row.can_manage">
              <el-button text type="primary" :icon="RefreshLeft" :loading="rowBusyState(row) === 'restore'" :disabled="Boolean(rowBusyState(row)) && rowBusyState(row) !== 'restore'" @click.stop="restoreKnowledge(row)">恢复</el-button>
              <el-button text type="danger" :icon="Delete" :loading="rowBusyState(row) === 'purge'" :disabled="Boolean(rowBusyState(row)) && rowBusyState(row) !== 'purge'" @click.stop="permanentlyDeleteKnowledge(row)">永久删除</el-button>
            </template>
            <el-button v-else-if="row.can_manage" text type="danger" :icon="FolderDelete" :disabled="Boolean(rowBusyState(row))" @click.stop="archiveKnowledge(row)">归档</el-button>
          </div>
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
        <el-form-item label="文档内容">
          <el-upload
            class="create-source-upload"
            drag
            action="#"
            :auto-upload="false"
            :show-file-list="false"
            accept=".md,.markdown"
            :on-change="handleCreateSourceChange"
          >
            <div class="source-upload-inner">
              <el-icon><UploadFilled /></el-icon>
              <span>拖拽或点击上传源文件</span>
              <small>仅支持符合内容结构要求的 Markdown（最大 50 MB）</small>
            </div>
          </el-upload>
          <div v-if="createSourceFile" class="selected-source-file">已选择：{{ createSourceFile.name }}</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="createKnowledge">创建并编辑</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="editorVisible" class="knowledge-editor-drawer" :title="editorTitle" size="760px" destroy-on-close :before-close="closeEditor">
      <div v-if="selected" class="editor-layout">
        <div class="knowledge-editor-header">
          <div class="editor-toolbar">
            <el-tag>{{ selected.visibility_scope === 'PLATFORM_PUBLIC' ? '平台公共知识' : '工作空间知识' }}</el-tag>
            <el-tag v-if="selected.archived" type="info">已归档，只读</el-tag>
            <KnowledgeApplicabilityTag
              v-if="!selected.archived && selected.visibility_scope === 'PLATFORM_PUBLIC'"
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
            <span v-if="!selected.archived" class="version-status">草稿状态：{{ draftStatus }}</span>
            <span v-if="draft?.file_name" class="version-file">源文件：{{ draft.file_name }}</span>
          </div>
          <div v-if="selected.archived && selected.can_manage" class="knowledge-lifecycle-actions">
            <el-button type="primary" :icon="RefreshLeft" :loading="rowBusyState(selected) === 'restore'" @click="restoreKnowledge(selected)">恢复知识库</el-button>
            <el-button type="danger" :icon="Delete" :loading="rowBusyState(selected) === 'purge'" @click="permanentlyDeleteKnowledge(selected)">永久删除</el-button>
          </div>
          <div v-else-if="!selected.archived" class="knowledge-lifecycle-actions">
            <el-button v-if="canEdit && !draft" type="primary" plain :icon="Plus" @click="createEditingDraft">创建草稿</el-button>
            <el-button :loading="saving" :disabled="!actionState.save" @click="saveDraft">保存草稿</el-button>
            <el-button :loading="saving" :disabled="!actionState.validate" @click="validateDraft">校验</el-button>
            <el-button type="primary" :loading="publishing" :disabled="!actionState.publish" @click="publishDraft">发布</el-button>
          </div>
        </div>
        <div v-if="canEdit && draft" class="source-upload-row">
          <el-upload
            drag
            action="#"
            :auto-upload="false"
            :show-file-list="false"
            accept=".md,.markdown"
            :disabled="sourceUploading"
            :on-change="handleSourceFileChange"
          >
            <div class="source-upload-inner">
              <el-icon><UploadFilled /></el-icon>
              <span>{{ sourceUploading ? '正在解析源文件...' : '拖拽或点击上传源文件' }}</span>
              <small>仅支持符合内容结构要求的 Markdown（.md / .markdown）</small>
            </div>
          </el-upload>
        </div>
        <KnowledgePayloadEditor v-model="payload" :readonly="!canEdit || !draft || editorBusy" />
        <div v-if="validationErrors.length" class="validation-panel is-error">
          <div v-for="(issue, index) in validationErrors" :key="index">{{ issue.field_path || '内容' }}：{{ issue.message }}</div>
        </div>
        <div v-if="validationWarnings.length" class="validation-panel is-warning">
          <div v-for="(issue, index) in validationWarnings" :key="index">{{ issue.field_path || '内容' }}：{{ issue.message }}</div>
        </div>
        <div v-if="draftConflict" class="validation-panel is-conflict">
          <template v-if="documentConflict?.type === 'BLOCK' && documentConflict.localBlock && documentConflict.serverBlock">
            <div class="conflict-title">同一知识块已被其他用户修改，本地内容仍保留在页面中。</div>
            <div class="conflict-compare">
              <div>
                <strong>本地：{{ documentConflict.localBlock.title || '未命名知识块' }}</strong>
                <p>{{ documentConflict.localBlock.markdown || '（空正文）' }}</p>
              </div>
              <div>
                <strong>服务端：{{ documentConflict.serverBlock.title || '未命名知识块' }}</strong>
                <p>{{ documentConflict.serverBlock.markdown || '（空正文）' }}</p>
              </div>
            </div>
            <div class="conflict-actions">
              <el-button @click="loadServerConflictBlock">载入服务端</el-button>
              <el-button type="warning" :loading="saving" @click="retryLocalConflictBlock">使用本地内容重试</el-button>
            </div>
          </template>
          <template v-else>
            <span>{{ documentConflict?.type === 'BLOCK_DELETED' ? '该知识块已被其他用户删除，本地内容仍保留。' : '知识块结构已被其他用户更新，本地修改仍保留。' }}</span>
            <el-button v-if="documentConflict?.type === 'BLOCK_DELETED'" type="warning" @click="restoreDeletedConflictBlock">恢复为新知识块</el-button>
            <el-button text type="warning" @click="refreshDraftAfterConflict">刷新最新结构</el-button>
          </template>
        </div>
        <div class="history-title">版本历史</div>
        <div v-for="version in versions" :key="version.id" class="history-row">
          <span>版本 {{ version.version_number }} · {{ version.status }}</span>
          <div class="history-actions">
            <el-button
              v-if="canEdit && !draft && ['PUBLISHED', 'SUPERSEDED'].includes(version.status)"
              text
              type="primary"
              @click="rollbackVersion(version)"
            >回滚为草稿</el-button>
            <el-button text :disabled="!version.file_name" @click="downloadVersion(version)">下载</el-button>
          </div>
        </div>
        <div v-if="publishJob" class="publish-status">发布任务：{{ publishJob.status }}{{ publishJob.stage ? ` · ${publishJob.stage}` : '' }}</div>
      </div>
    </el-drawer>
    <KnowledgeRetrievalPreview v-model="retrievalPreviewVisible" />
  </div>
</template>

<style scoped lang="less">
.knowledge-v2-panel { height: 100%; padding: 0 0 24px; color: #1f2329; }
.panel-header { display: flex; width: 100%; margin-bottom: 18px; }
.panel-actions { display: flex; width: 100%; min-width: 0; align-items: center; justify-content: flex-end; flex-wrap: wrap; gap: 10px 16px; padding: 8px; border: 1px solid #e4e7ed; border-radius: 8px; background: #f7f8fa; }
.panel-filters, .panel-buttons { display: flex; align-items: center; gap: 8px; }
.panel-filters { flex: 0 1 auto; min-width: 0; }
.knowledge-filter-input { width: 220px; flex: 0 0 220px; }
.knowledge-filter-scope { width: 150px; flex: 0 0 150px; }
.knowledge-filter-workspace { width: 180px; flex: 0 0 180px; }
.knowledge-archive-filter { flex: 0 0 auto; }
.panel-buttons { flex: 0 0 auto; }
.panel-buttons :deep(.ed-button + .ed-button) { margin-left: 0; }
.panel-action-slot { display: inline-flex; max-width: 100%; }
.panel-action-slot.is-placeholder { visibility: hidden; pointer-events: none; }
.template-download { max-width: 100%; }
.template-download-arrow { margin-left: 6px; }
.knowledge-v2-table { min-height: 160px; }
.row-actions { display: flex; align-items: center; gap: 2px; white-space: nowrap; }
.row-actions :deep(.ed-button + .ed-button) { margin-left: 0; }
.row-source-upload { display: inline-flex; }
.list-error { margin-bottom: 12px; }
.empty-state { display: inline-flex; min-height: 120px; align-items: center; color: #8f959e; }
.muted-text { color: #98a2b3; }
.editor-toolbar, .knowledge-lifecycle-actions, .history-row, .history-actions { display: flex; align-items: center; gap: 8px; }
.editor-layout { padding: 0 2px 24px; }
.knowledge-editor-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px 20px; margin-bottom: 16px; padding: 12px; border: 1px solid #e4e7ed; border-radius: 6px; background: #f7f8fa; }
.editor-toolbar { flex: 1 1 360px; min-width: 0; flex-wrap: wrap; color: #667085; font-size: 12px; }
.knowledge-lifecycle-actions { flex: 0 0 auto; justify-content: flex-end; flex-wrap: wrap; }
.knowledge-lifecycle-actions :deep(.ed-button + .ed-button) { margin-left: 0; }
.source-upload-row { margin-bottom: 16px; }
.source-upload-row :deep(.ed-upload), .source-upload-row :deep(.ed-upload-dragger), .create-source-upload, .create-source-upload :deep(.ed-upload), .create-source-upload :deep(.ed-upload-dragger) { width: 100%; }
.source-upload-row :deep(.ed-upload-dragger), .create-source-upload :deep(.ed-upload-dragger) { padding: 14px 16px; border-radius: 6px; }
.source-upload-inner { display: grid; grid-template-columns: 20px auto; align-items: center; justify-content: center; gap: 2px 8px; color: #344054; }
.source-upload-inner small { grid-column: 2; color: #667085; }
.selected-source-file { margin-top: 8px; color: #475467; font-size: 12px; overflow-wrap: anywhere; }
.workspace-override { display: inline-flex; align-items: center; gap: 6px; color: #475467; }
.version-file { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.validation-panel { margin-top: 14px; padding: 10px 12px; border-radius: 6px; font-size: 12px; line-height: 20px; }
.validation-panel.is-error { color: #b42318; background: #fff1f3; }
.validation-panel.is-warning { color: #9a6700; background: #fff8e6; }
.validation-panel.is-conflict { color: #9a6700; background: #fff8e6; }
.conflict-title { font-weight: 600; }
.conflict-compare { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-top: 8px; }
.conflict-compare > div { min-width: 0; padding: 8px; border: 1px solid #f5c451; border-radius: 6px; background: #fff; }
.conflict-compare p { max-height: 100px; margin: 6px 0 0; overflow: auto; color: #475467; white-space: pre-wrap; overflow-wrap: anywhere; }
.conflict-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }
.history-title { margin-top: 24px; padding-bottom: 8px; border-bottom: 1px solid #eaecf0; color: #344054; font-size: 13px; font-weight: 600; }
.history-row { justify-content: space-between; min-height: 36px; border-bottom: 1px solid #f2f4f7; color: #667085; font-size: 12px; }
.publish-status { margin-top: 12px; color: #1570ef; font-size: 12px; }
@media (max-width: 1440px) {
  .panel-actions { justify-content: space-between; }
}
@media (max-width: 680px) {
  :global(.knowledge-editor-drawer) { width: 100% !important; max-width: 100%; }
  .panel-actions, .panel-filters, .panel-buttons { width: 100%; }
  .panel-filters { flex-direction: column; }
  .knowledge-filter-input, .knowledge-filter-scope, .knowledge-filter-workspace, .knowledge-archive-filter { width: 100%; flex-basis: auto; }
  .knowledge-archive-filter :deep(.ed-radio-button) { flex: 1 1 0; }
  .knowledge-archive-filter :deep(.ed-radio-button__inner) { width: 100%; }
  .panel-buttons { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); align-items: stretch; }
  .panel-buttons :deep(.ed-button), .template-download { width: 100%; min-height: 32px; margin-left: 0; }
  .template-download :deep(.ed-button) { width: 100%; height: auto; min-height: 32px; white-space: normal; }
  .knowledge-editor-header { flex-direction: column; }
  .editor-toolbar { width: 100%; flex-basis: auto; }
  .knowledge-lifecycle-actions { display: grid; width: 100%; grid-template-columns: repeat(2, minmax(0, 1fr)); align-items: stretch; }
  .knowledge-lifecycle-actions :deep(.ed-button) { width: 100%; min-width: 0; margin-left: 0; white-space: normal; }
  .conflict-compare { grid-template-columns: minmax(0, 1fr); }
  .conflict-actions { align-items: stretch; flex-direction: column; }
  .conflict-actions :deep(.ed-button) { width: 100%; margin-left: 0; }
}
</style>
