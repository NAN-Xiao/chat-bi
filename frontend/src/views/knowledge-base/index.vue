<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { cloneDeep } from 'lodash-es'
import { Search, UploadFilled } from '@element-plus/icons-vue'
import type { UploadFile, UploadProps, UploadRawFile } from 'element-plus'
import { useUserStore } from '@/stores/user'
import { knowledgeBaseApi, type KnowledgeBaseItem, type KnowledgeBaseScope } from '@/api/knowledgeBase'
import { formatTimestamp } from '@/utils/date'
import icon_add_outlined from '@/assets/svg/icon_add_outlined.svg'
import IconOpeEdit from '@/assets/svg/icon_edit_outlined.svg'
import IconOpeDelete from '@/assets/svg/icon_delete.svg'
import icon_form_outlined from '@/assets/svg/icon_form_outlined.svg'
import icon_more_outlined from '@/assets/svg/icon_more_outlined.svg'

const { t } = useI18n()
const userStore = useUserStore()

const cardList = ref<KnowledgeBaseItem[]>([])
const keyword = ref('')
const formRef = ref()
const drawerVisible = ref(false)
const detailVisible = ref(false)
const drawerTitle = ref('')
const selectedCard = ref<KnowledgeBaseItem | null>(null)
const loading = ref(false)
const saving = ref(false)
const uploadFileName = ref('')
const pendingFile = ref<File | null>(null)
let refreshTimer: ReturnType<typeof window.setTimeout> | null = null

const isPlatformAdmin = computed(
  () => userStore.isSystemAdminUser && !userStore.isPlatformWorkspaceDelegate
)
const defaultScope = computed<KnowledgeBaseScope>(() => {
  return isPlatformAdmin.value ? 'PLATFORM_PUBLIC' : 'ADMIN_PUBLIC'
})
const pageTitle = computed(() => t('knowledge_base.admin_title'))
const scopeLabel = computed(() => sourceText({ visibility_scope: defaultScope.value }))

const defaultForm = {
  id: null as number | string | null,
  name: '',
  description: '',
  active: true,
}

const form = ref(cloneDeep(defaultForm))

const rules = computed(() => ({
  name: [
    {
      required: true,
      message: t('knowledge_base.name_required'),
      trigger: 'blur',
    },
  ],
}))

const filteredCards = computed(() => {
  const value = keyword.value.trim().toLowerCase()
  if (!value) return cardList.value
  return cardList.value.filter((item) => {
    return (
      item.name.toLowerCase().includes(value) ||
      (item.description || '').toLowerCase().includes(value) ||
      (item.content || '').toLowerCase().includes(value) ||
      (item.file_name || '').toLowerCase().includes(value)
    )
  })
})

function sourceText(row: Pick<KnowledgeBaseItem, 'visibility_scope'> | null) {
  if (row?.visibility_scope === 'PLATFORM_PUBLIC') return t('knowledge_base.saas_knowledge_base')
  return t('knowledge_base.workspace_knowledge_base')
}

function sourceClass(row: Pick<KnowledgeBaseItem, 'visibility_scope'> | null) {
  if (row?.visibility_scope === 'PLATFORM_PUBLIC') return 'is-saas'
  return 'is-workspace'
}

function statusText(row: Pick<KnowledgeBaseItem, 'active'> | null) {
  return row?.active === false ? t('knowledge_base.inactive') : t('knowledge_base.active')
}

function processStatusText(row: Pick<KnowledgeBaseItem, 'status'> | null) {
  if (row?.status === 'READY') return t('knowledge_base.process_ready')
  if (row?.status === 'FAILED') return t('knowledge_base.process_failed')
  if (row?.status === 'PROCESSING') return t('knowledge_base.process_processing')
  return t('knowledge_base.process_pending')
}

function processStatusClass(row: Pick<KnowledgeBaseItem, 'status'> | null) {
  if (row?.status === 'READY') return 'is-ready'
  if (row?.status === 'FAILED') return 'is-failed'
  if (row?.status === 'PROCESSING') return 'is-processing'
  return 'is-pending'
}

function formatCardTime(value?: string | null) {
  const timestamp = value ? new Date(value).getTime() : 0
  return Number.isFinite(timestamp) ? formatTimestamp(timestamp, 'YYYY-MM-DD HH:mm:ss') : '-'
}

function clearRefreshTimer() {
  if (!refreshTimer) return
  window.clearTimeout(refreshTimer)
  refreshTimer = null
}

function scheduleStatusRefresh() {
  clearRefreshTimer()
  const hasPendingStatus = cardList.value.some((item) =>
    ['PENDING', 'PROCESSING'].includes(item.status)
  )
  if (!hasPendingStatus) return
  refreshTimer = window.setTimeout(() => {
    loadCards()
  }, 3000)
}

async function loadCards() {
  loading.value = true
  try {
    cardList.value = await knowledgeBaseApi.list({ visibility_scope: defaultScope.value })
  } catch (error) {
    console.error(error)
    cardList.value = []
  } finally {
    loading.value = false
    scheduleStatusRefresh()
  }
}

function resetForm() {
  form.value = cloneDeep(defaultForm)
  uploadFileName.value = ''
  pendingFile.value = null
  formRef.value?.clearValidate?.()
}

function openCreateCard() {
  resetForm()
  drawerTitle.value = t('knowledge_base.add_knowledge_base')
  drawerVisible.value = true
}

function openEditCard(row: KnowledgeBaseItem) {
  form.value = {
    id: row.id,
    name: row.name,
    description: row.description || '',
    active: row.active,
  }
  drawerTitle.value = t('knowledge_base.edit_knowledge_base')
  uploadFileName.value = row.file_name || ''
  pendingFile.value = null
  drawerVisible.value = true
}

function closeForm() {
  drawerVisible.value = false
  resetForm()
}

function isSupportedKnowledgeFile(file: File) {
  const name = file.name.toLowerCase()
  return name.endsWith('.md') || name.endsWith('.markdown') || name.endsWith('.docx')
}

function setNameFromFile(file: File) {
  if (form.value.name.trim()) return
  form.value.name = file.name.replace(/\.(md|markdown|docx)$/i, '')
}

const beforeKnowledgeUpload: UploadProps['beforeUpload'] = (rawFile: UploadRawFile) => {
  if (!isSupportedKnowledgeFile(rawFile)) {
    ElMessage.warning(t('knowledge_base.upload_invalid_type'))
    return false
  }
  if (rawFile.size > 50 * 1024 * 1024) {
    ElMessage.warning(t('knowledge_base.upload_too_large'))
    return false
  }

  pendingFile.value = rawFile
  uploadFileName.value = rawFile.name
  setNameFromFile(rawFile)
  ElMessage.success(t('knowledge_base.upload_selected'))
  return false
}

const handleKnowledgeFileChange: UploadProps['onChange'] = (uploadFile: UploadFile) => {
  if (uploadFile.raw) {
    beforeKnowledgeUpload(uploadFile.raw)
  }
}

function saveCard() {
  formRef.value?.validate(async (valid: boolean) => {
    if (!valid || saving.value) return
    if (!form.value.id && !pendingFile.value) {
      ElMessage.warning(t('knowledge_base.file_required'))
      return
    }
    saving.value = true
    try {
      await knowledgeBaseApi.save({
        id: form.value.id,
        name: form.value.name.trim(),
        description: form.value.description.trim(),
        active: form.value.active,
        visibility_scope: defaultScope.value,
        file: pendingFile.value,
      })
      ElMessage.success(t('common.save_success'))
      closeForm()
      await loadCards()
    } catch (error) {
      console.error(error)
    } finally {
      saving.value = false
    }
  })
}

function deleteCard(row: KnowledgeBaseItem) {
  ElMessageBox.confirm(t('knowledge_base.delete_confirm', { msg: row.name }), {
    confirmButtonType: 'danger',
    confirmButtonText: t('dashboard.delete'),
    cancelButtonText: t('common.cancel'),
    customClass: 'confirm-no_icon',
    autofocus: false,
  }).then(async () => {
    await knowledgeBaseApi.delete(row.id)
    ElMessage.success(t('dashboard.delete_success'))
    await loadCards()
  })
}

function openDetail(row: KnowledgeBaseItem) {
  selectedCard.value = cloneDeep(row)
  detailVisible.value = true
}

watch(
  defaultScope,
  () => {
    clearRefreshTimer()
    loadCards()
  },
  { immediate: true }
)

onBeforeUnmount(() => {
  clearRefreshTimer()
})
</script>

<template>
  <div class="knowledge-base-page">
    <div class="page-header">
      <div class="page-title">{{ pageTitle }}</div>
      <div class="page-actions">
        <el-input
          v-model="keyword"
          clearable
          class="knowledge-search"
          :prefix-icon="Search"
          :placeholder="t('dashboard.search')"
        />
        <div class="scope-chip" :class="sourceClass({ visibility_scope: defaultScope })">
          {{ scopeLabel }}
        </div>
        <el-button type="primary" @click="openCreateCard">
          <template #icon>
            <icon_add_outlined />
          </template>
          {{ t('knowledge_base.add_knowledge_base') }}
        </el-button>
      </div>
    </div>

    <section v-loading="loading" class="knowledge-section">
      <div class="knowledge-content">
        <div v-if="!filteredCards.length" class="knowledge-empty">
          {{ t('knowledge_base.no_knowledge_base') }}
        </div>
        <div v-else class="card-content">
          <article
            v-for="card in filteredCards"
            :key="card.id"
            class="knowledge-card"
            :class="sourceClass(card)"
            @click="openDetail(card)"
          >
            <div class="card-head">
              <div class="title-block">
                <el-icon class="card-icon" size="30">
                  <icon_form_outlined />
                </el-icon>
                <div class="title-text">
                  <div class="title-row">
                    <span class="name ellipsis" :title="card.name">{{ card.name }}</span>
                    <span class="source-pill">{{ sourceText(card) }}</span>
                  </div>
                  <div class="meta-row">
                    <span>{{ statusText(card) }}</span>
                    <span class="process-status" :class="processStatusClass(card)">
                      {{ processStatusText(card) }}
                    </span>
                    <span>{{ formatCardTime(card.update_time) }}</span>
                  </div>
                </div>
              </div>
              <div class="card-actions" @click.stop>
                <el-popover
                  trigger="click"
                  :teleported="true"
                  popper-class="popover-card_knowledge"
                  placement="bottom-end"
                >
                  <template #reference>
                    <button type="button" class="more" aria-label="more actions">
                      <icon_more_outlined />
                    </button>
                  </template>
                  <div class="content">
                    <div class="item" @click.stop="openEditCard(card)">
                      <el-icon size="16">
                        <IconOpeEdit />
                      </el-icon>
                      {{ t('datasource.edit') }}
                    </div>
                    <div class="item" @click.stop="deleteCard(card)">
                      <el-icon size="16">
                        <IconOpeDelete />
                      </el-icon>
                      {{ t('dashboard.delete') }}
                    </div>
                  </div>
                </el-popover>
              </div>
            </div>

            <div
              class="description"
              :title="card.description || t('knowledge_base.empty_description')"
            >
              {{ card.description || t('knowledge_base.empty_description') }}
            </div>
            <div class="content-preview" :title="card.file_name || card.content || ''">
              {{ card.file_name || card.content || '-' }}
            </div>
          </article>
        </div>
      </div>
    </section>

    <el-drawer
      v-model="drawerVisible"
      :title="drawerTitle"
      destroy-on-close
      size="640px"
      :before-close="closeForm"
      modal-class="knowledge-base-drawer"
    >
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="180px"
        label-position="top"
        class="form-content_error"
        @submit.prevent
      >
        <el-form-item prop="name" :label="t('knowledge_base.name')">
          <el-input
            v-model="form.name"
            maxlength="80"
            clearable
            :placeholder="t('knowledge_base.name_placeholder')"
          />
        </el-form-item>
        <el-form-item :label="t('knowledge_base.source')">
          <div class="fixed-scope">{{ scopeLabel }}</div>
        </el-form-item>
        <el-form-item prop="active" :label="t('knowledge_base.status')">
          <el-switch
            v-model="form.active"
            :active-text="t('knowledge_base.active')"
            :inactive-text="t('knowledge_base.inactive')"
          />
        </el-form-item>
        <el-form-item prop="description" :label="t('knowledge_base.description')">
          <el-input
            v-model="form.description"
            :placeholder="t('knowledge_base.description_placeholder')"
            :autosize="{ minRows: 2, maxRows: 4 }"
            type="textarea"
          />
        </el-form-item>
        <el-form-item :label="t('knowledge_base.document_content')">
          <div class="knowledge-upload-source">
            <div class="upload-source-title">{{ t('knowledge_base.upload_source') }}</div>
            <el-upload
              class="knowledge-upload"
              drag
              action="#"
              :auto-upload="false"
              :show-file-list="false"
              accept=".md,.markdown,.docx"
              :on-change="handleKnowledgeFileChange"
            >
              <div class="knowledge-upload-inner">
                <el-icon class="upload-icon" size="22">
                  <UploadFilled />
                </el-icon>
                <div class="upload-main">{{ t('knowledge_base.upload_drag_title') }}</div>
                <div class="upload-sub">{{ t('knowledge_base.upload_tip') }}</div>
              </div>
            </el-upload>
            <div v-if="uploadFileName" class="uploaded-file">
              <span class="uploaded-label">{{ t('knowledge_base.selected_file') }}</span>
              <span class="uploaded-name ellipsis" :title="uploadFileName">{{ uploadFileName }}</span>
            </div>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <div v-loading="saving" class="dialog-footer">
          <el-button secondary @click="closeForm">{{ t('common.cancel') }}</el-button>
          <el-button type="primary" @click="saveCard">{{ t('common.save') }}</el-button>
        </div>
      </template>
    </el-drawer>

    <el-drawer
      v-model="detailVisible"
      :title="t('menu.Details')"
      destroy-on-close
      size="640px"
      modal-class="knowledge-base-drawer"
    >
      <el-form label-width="180px" label-position="top" class="form-content_error" @submit.prevent>
        <el-form-item :label="t('knowledge_base.name')">
          <div class="detail-content">{{ selectedCard?.name || '-' }}</div>
        </el-form-item>
        <el-form-item :label="t('knowledge_base.source')">
          <div class="detail-content">{{ sourceText(selectedCard) }}</div>
        </el-form-item>
        <el-form-item :label="t('knowledge_base.status')">
          <div class="detail-content">{{ statusText(selectedCard) }}</div>
        </el-form-item>
        <el-form-item :label="t('knowledge_base.process_status')">
          <div class="detail-content">
            {{ processStatusText(selectedCard) }}
            <span v-if="selectedCard?.error_message" class="detail-error">
              {{ selectedCard.error_message }}
            </span>
          </div>
        </el-form-item>
        <el-form-item :label="t('knowledge_base.selected_file')">
          <div class="detail-content">{{ selectedCard?.file_name || '-' }}</div>
        </el-form-item>
        <el-form-item :label="t('knowledge_base.description')">
          <div class="detail-content">
            {{ selectedCard?.description || t('knowledge_base.empty_description') }}
          </div>
        </el-form-item>
        <el-form-item :label="t('knowledge_base.updated_at')">
          <div class="detail-content">
            {{
              formatCardTime(selectedCard?.update_time)
            }}
          </div>
        </el-form-item>
        <el-form-item :label="t('knowledge_base.document_content')">
          <div class="detail-content pre-wrap">{{ selectedCard?.content || '-' }}</div>
        </el-form-item>
      </el-form>
    </el-drawer>
  </div>
</template>

<style lang="less" scoped>
.knowledge-base-page {
  height: 100%;
  padding: 0 0 24px;
  color: var(--workspace-text-primary, #1f2329);

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

  .page-actions {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 12px;
    min-width: 360px;
  }

  .knowledge-search {
    width: 240px;
  }

  .scope-chip {
    --scope-color: #667085;
    --scope-bg: #f2f4f7;
    --scope-border: #d0d5dd;
    display: inline-flex;
    align-items: center;
    height: 32px;
    max-width: 152px;
    padding: 0 10px;
    border: 1px solid var(--scope-border);
    border-radius: 6px;
    background: var(--scope-bg);
    color: var(--scope-color);
    font-size: 13px;
    font-weight: 500;
    line-height: 20px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;

    &.is-saas {
      --scope-color: #7a5af8;
      --scope-bg: #f3f0ff;
      --scope-border: #d8ccff;
    }

    &.is-workspace {
      --scope-color: #1570ef;
      --scope-bg: #eaf2ff;
      --scope-border: #b9d6ff;
    }

  }

  .knowledge-section {
    min-height: 0;
  }

  .knowledge-content {
    min-height: 96px;
  }

  .knowledge-empty {
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

  .card-content {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 12px;
  }

  .knowledge-card {
    --card-source-color: #667085;
    --card-source-bg: #f2f4f7;
    --card-source-border: #d0d5dd;
    --card-source-card-bg: #ffffff;
    width: 100%;
    height: 174px;
    border: 1px solid var(--card-source-border);
    border-left: 2px solid var(--card-source-color);
    padding: 14px 14px 12px;
    border-radius: 8px;
    background: var(--card-source-card-bg);
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
      border-color: var(--card-source-color);
      box-shadow: 0 8px 18px rgba(16, 24, 40, 0.08);
      transform: translateY(-1px);
    }

    &.is-saas {
      --card-source-color: #7a5af8;
      --card-source-bg: #f3f0ff;
      --card-source-border: #d8ccff;
      --card-source-card-bg: #fcfbff;
    }

    &.is-workspace {
      --card-source-color: #1570ef;
      --card-source-bg: #eaf2ff;
      --card-source-border: #b9d6ff;
      --card-source-card-bg: #fbfdff;
    }

    .card-head {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
      min-width: 0;
    }

    .title-block {
      display: flex;
      align-items: center;
      min-width: 0;
      flex: 1;
    }

    .card-icon {
      width: 30px;
      height: 30px;
      flex: 0 0 30px;
      border-radius: 6px;
      background: var(--card-source-bg);
      color: var(--card-source-color);

      :deep(svg) {
        width: 18px;
        height: 18px;
      }

      :deep(path) {
        fill: currentColor !important;
      }
    }

    .title-text {
      min-width: 0;
      margin-left: 10px;
    }

    .title-row {
      display: flex;
      align-items: center;
      gap: 8px;
      min-width: 0;
    }

    .name {
      min-width: 0;
      max-width: 100%;
      color: #101828;
      font-weight: 600;
      font-size: 14px;
      line-height: 22px;
    }

    .source-pill {
      flex: 0 0 auto;
      max-width: 96px;
      padding: 0 5px;
      border: 1px solid var(--card-source-border);
      border-radius: 4px;
      background: var(--card-source-bg);
      color: var(--card-source-color);
      font-size: 11px;
      font-weight: 500;
      line-height: 18px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .meta-row {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-top: 2px;
      color: #667085;
      font-size: 12px;
      line-height: 18px;
      flex-wrap: wrap;
    }

    .process-status {
      display: inline-flex;
      align-items: center;
      height: 18px;
      padding: 0 5px;
      border-radius: 4px;
      background: #f2f4f7;
      color: #667085;
      font-size: 11px;
      font-weight: 500;
      line-height: 18px;

      &.is-ready {
        background: #e9f8f2;
        color: #12a076;
      }

      &.is-processing,
      &.is-pending {
        background: #eaf2ff;
        color: #1570ef;
      }

      &.is-failed {
        background: #fff1f3;
        color: #d92d20;
      }
    }

    .card-actions {
      flex: 0 0 auto;
      height: 28px;
    }

    .more {
      border: 0;
      padding: 0;
      color: #667085;
      background: transparent;
      appearance: none;
      line-height: 1;
      cursor: pointer;
      width: 28px;
      height: 28px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border-radius: 8px;

      &:hover {
        color: #1f2329;
        background: #edf3ff;
      }
    }

    .description,
    .content-preview {
      display: -webkit-box;
      overflow: hidden;
      -webkit-box-orient: vertical;
      word-break: break-word;
    }

    .description {
      margin-top: 12px;
      color: #475467;
      font-size: 13px;
      line-height: 20px;
      -webkit-line-clamp: 2;
    }

    .content-preview {
      margin-top: 8px;
      color: #667085;
      font-size: 12px;
      line-height: 18px;
      -webkit-line-clamp: 2;
    }
  }
}
</style>

<style lang="less">
.knowledge-base-drawer {
  .fixed-scope,
  .detail-content {
    width: 100%;
    color: #1f2329;
    line-height: 22px;
    word-break: break-word;
  }

  .fixed-scope {
    padding: 8px 12px;
    border: 1px solid #dee0e3;
    border-radius: 6px;
    background: #f7faf9;
  }

  .pre-wrap {
    white-space: pre-wrap;
  }

  .detail-error {
    display: block;
    margin-top: 6px;
    color: #d92d20;
    font-size: 12px;
    line-height: 18px;
  }

  .knowledge-upload-source {
    width: 100%;
  }

  .upload-source-title {
    margin-bottom: 10px;
    color: #1f2329;
    font-size: 14px;
    line-height: 22px;
    font-weight: 500;
  }

  .knowledge-upload {
    width: 100%;

    .ed-upload {
      display: block;
      width: 100%;
    }

    .ed-upload-dragger {
      width: 100%;
      height: 112px;
      padding: 0;
      border: 1px dashed #d8dde8;
      border-radius: 12px;
      background: #fff;

      &:hover {
        border-color: #4f7df3;
        background: #f8fbff;
      }
    }
  }

  .knowledge-upload-inner {
    display: flex;
    height: 100%;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    color: #4b5565;
    text-align: center;
  }

  .upload-icon {
    margin-bottom: 8px;
    color: #1f2329;
  }

  .upload-main {
    color: #1f2329;
    font-size: 13px;
    font-weight: 600;
    line-height: 20px;
  }

  .upload-sub {
    margin-top: 3px;
    color: #6b7280;
    font-size: 13px;
    line-height: 20px;
  }

  .uploaded-file {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
    margin-top: 10px;
    color: #475467;
    font-size: 13px;
    line-height: 20px;
  }

  .uploaded-label {
    flex: 0 0 auto;
    color: #667085;
  }

  .uploaded-name {
    min-width: 0;
    color: #1f2329;
    font-weight: 500;
  }

}

.popover-card_knowledge.popover-card_knowledge.popover-card_knowledge {
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
