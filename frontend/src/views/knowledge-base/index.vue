<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { cloneDeep } from 'lodash-es'
import { Search } from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'
import { formatTimestamp } from '@/utils/date'
import icon_add_outlined from '@/assets/svg/icon_add_outlined.svg'
import IconOpeEdit from '@/assets/svg/icon_edit_outlined.svg'
import IconOpeDelete from '@/assets/svg/icon_delete.svg'
import icon_form_outlined from '@/assets/svg/icon_form_outlined.svg'
import icon_more_outlined from '@/assets/svg/icon_more_outlined.svg'

type KnowledgeScope = 'USER_PRIVATE' | 'ADMIN_PUBLIC' | 'PLATFORM_PUBLIC'

interface KnowledgeBaseCard {
  id: string
  name: string
  description: string
  content: string
  visibility_scope: KnowledgeScope
  active: boolean
  create_time: string
  update_time: string
}

const props = withDefaults(
  defineProps<{
    mode?: 'personal' | 'admin'
  }>(),
  {
    mode: 'personal',
  }
)

const { t } = useI18n()
const userStore = useUserStore()

const storagePrefix = 'zhishu_knowledge_base_cards'
const cardList = ref<KnowledgeBaseCard[]>([])
const keyword = ref('')
const formRef = ref()
const drawerVisible = ref(false)
const detailVisible = ref(false)
const drawerTitle = ref('')
const selectedCard = ref<KnowledgeBaseCard | null>(null)
const saving = ref(false)

const isAdminMode = computed(() => props.mode === 'admin')
const isPlatformAdmin = computed(
  () => userStore.isSystemAdminUser && !userStore.isPlatformWorkspaceDelegate
)
const defaultScope = computed<KnowledgeScope>(() => {
  if (!isAdminMode.value) return 'USER_PRIVATE'
  return isPlatformAdmin.value ? 'PLATFORM_PUBLIC' : 'ADMIN_PUBLIC'
})
const pageTitle = computed(() =>
  isAdminMode.value ? t('knowledge_base.admin_title') : t('knowledge_base.title')
)
const scopeLabel = computed(() => sourceText({ visibility_scope: defaultScope.value }))
const storageKey = computed(() => {
  if (defaultScope.value === 'PLATFORM_PUBLIC') return `${storagePrefix}:platform`
  if (defaultScope.value === 'ADMIN_PUBLIC') {
    return `${storagePrefix}:workspace:${userStore.getTenantId || 'default'}`
  }
  return `${storagePrefix}:user:${userStore.getUid || 'local'}`
})

const defaultForm = {
  id: '',
  name: '',
  description: '',
  content: '',
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
  content: [
    {
      required: true,
      message: t('knowledge_base.content_required'),
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
      item.description.toLowerCase().includes(value) ||
      item.content.toLowerCase().includes(value)
    )
  })
})

function sourceText(row: Pick<KnowledgeBaseCard, 'visibility_scope'> | null) {
  if (row?.visibility_scope === 'PLATFORM_PUBLIC') return t('knowledge_base.saas_knowledge_base')
  if (row?.visibility_scope === 'ADMIN_PUBLIC') return t('knowledge_base.workspace_knowledge_base')
  return t('knowledge_base.my_knowledge_base')
}

function sourceClass(row: Pick<KnowledgeBaseCard, 'visibility_scope'> | null) {
  if (row?.visibility_scope === 'PLATFORM_PUBLIC') return 'is-saas'
  if (row?.visibility_scope === 'ADMIN_PUBLIC') return 'is-workspace'
  return 'is-personal'
}

function statusText(row: Pick<KnowledgeBaseCard, 'active'> | null) {
  return row?.active === false ? t('knowledge_base.inactive') : t('knowledge_base.active')
}

function formatCardTime(value?: string | null) {
  const timestamp = value ? new Date(value).getTime() : 0
  return Number.isFinite(timestamp) ? formatTimestamp(timestamp, 'YYYY-MM-DD HH:mm:ss') : '-'
}

function loadCards() {
  try {
    const raw = localStorage.getItem(storageKey.value)
    const parsed = raw ? JSON.parse(raw) : []
    cardList.value = Array.isArray(parsed) ? parsed : []
  } catch {
    cardList.value = []
  }
}

function persistCards() {
  localStorage.setItem(storageKey.value, JSON.stringify(cardList.value))
}

function resetForm() {
  form.value = cloneDeep(defaultForm)
}

function openCreateCard() {
  resetForm()
  drawerTitle.value = t('knowledge_base.add_knowledge_base')
  drawerVisible.value = true
}

function openEditCard(row: KnowledgeBaseCard) {
  form.value = {
    id: row.id,
    name: row.name,
    description: row.description,
    content: row.content,
    active: row.active,
  }
  drawerTitle.value = t('knowledge_base.edit_knowledge_base')
  drawerVisible.value = true
}

function closeForm() {
  drawerVisible.value = false
  resetForm()
}

function saveCard() {
  formRef.value?.validate((valid: boolean) => {
    if (!valid || saving.value) return
    saving.value = true
    const now = new Date().toISOString()
    const existingIndex = cardList.value.findIndex((item) => item.id === form.value.id)
    const payload: KnowledgeBaseCard = {
      id: form.value.id || `${Date.now()}`,
      name: form.value.name.trim(),
      description: form.value.description.trim(),
      content: form.value.content,
      visibility_scope: defaultScope.value,
      active: form.value.active,
      create_time: existingIndex >= 0 ? cardList.value[existingIndex].create_time : now,
      update_time: now,
    }
    if (existingIndex >= 0) {
      cardList.value.splice(existingIndex, 1, payload)
    } else {
      cardList.value.unshift(payload)
    }
    persistCards()
    ElMessage.success(t('common.save_success'))
    saving.value = false
    closeForm()
  })
}

function deleteCard(row: KnowledgeBaseCard) {
  ElMessageBox.confirm(t('knowledge_base.delete_confirm', { msg: row.name }), {
    confirmButtonType: 'danger',
    confirmButtonText: t('dashboard.delete'),
    cancelButtonText: t('common.cancel'),
    customClass: 'confirm-no_icon',
    autofocus: false,
  }).then(() => {
    cardList.value = cardList.value.filter((item) => item.id !== row.id)
    persistCards()
    ElMessage.success(t('dashboard.delete_success'))
  })
}

function openDetail(row: KnowledgeBaseCard) {
  selectedCard.value = cloneDeep(row)
  detailVisible.value = true
}

watch(storageKey, loadCards, { immediate: true })
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

    <section class="knowledge-section">
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
            <div class="content-preview" :title="card.content">
              {{ card.content }}
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
        <el-form-item prop="content" :label="t('knowledge_base.document_content')">
          <el-input
            v-model="form.content"
            :placeholder="t('knowledge_base.content_placeholder')"
            :autosize="{ minRows: 12, maxRows: 24 }"
            type="textarea"
          />
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

    &.is-personal {
      --scope-color: #12a076;
      --scope-bg: #e9f8f2;
      --scope-border: #a9e7d0;
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

    &.is-personal {
      --card-source-color: #12a076;
      --card-source-bg: #e9f8f2;
      --card-source-border: #a9e7d0;
      --card-source-card-bg: #fbfffd;
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
