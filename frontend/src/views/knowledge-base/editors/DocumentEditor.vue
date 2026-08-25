<script setup lang="ts">
import {
  ArrowDown,
  ArrowUp,
  ChatLineSquare,
  CopyDocument,
  Delete,
  Finished,
  List,
  Plus,
  RefreshLeft,
  RefreshRight,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus-secondary'
import { nextTick, ref, watch } from 'vue'
import markdown from '@/utils/markdown'
import {
  createDocumentBlock,
  type DocumentBlock,
  type DocumentPayload,
} from '../knowledgePayloadTypes'
import KnowledgeContentFrame from './KnowledgeContentFrame.vue'
import KnowledgeMarkdownEditor, { type KnowledgeBlockFormat } from './KnowledgeMarkdownEditor.vue'

const props = withDefaults(defineProps<{ modelValue: DocumentPayload; readonly?: boolean }>(), {
  readonly: false,
})
const emit = defineEmits<{ 'update:modelValue': [value: DocumentPayload] }>()

type MarkdownEditorHandle = InstanceType<typeof KnowledgeMarkdownEditor>

const activeBlockId = ref('')
const blockFormat = ref<KnowledgeBlockFormat>('paragraph')
const markdownEditor = ref<MarkdownEditorHandle | null>(null)
const blockElements = new Map<string, HTMLElement>()

function setMarkdownEditor(instance: unknown) {
  markdownEditor.value = instance as MarkdownEditorHandle | null
}

watch(
  () => props.modelValue.blocks.map((block) => block.id),
  (ids) => {
    if (!ids.includes(activeBlockId.value)) activeBlockId.value = ids[0] || ''
  },
  { immediate: true }
)

function setBlockElement(blockId: string, element: Element | null) {
  if (element instanceof HTMLElement) blockElements.set(blockId, element)
  else blockElements.delete(blockId)
}

function updateBlocks(blocks: DocumentBlock[]) {
  emit('update:modelValue', { ...props.modelValue, blocks })
}

function updateBlock(blockId: string, patch: Partial<DocumentBlock>) {
  updateBlocks(
    props.modelValue.blocks.map((block) => (block.id === blockId ? { ...block, ...patch } : block))
  )
}

function nextBlockTitle() {
  const usedTitles = new Set(props.modelValue.blocks.map((block) => block.title.trim()))
  let suffix = props.modelValue.blocks.length + 1
  while (usedTitles.has(`新知识块 ${suffix}`)) suffix += 1
  return `新知识块 ${suffix}`
}

async function activateBlock(blockId: string, scroll = false) {
  activeBlockId.value = blockId
  blockFormat.value = 'paragraph'
  if (!scroll) return
  await nextTick()
  blockElements.get(blockId)?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
}

async function addBlock() {
  if (props.readonly) return
  const block = createDocumentBlock(nextBlockTitle())
  updateBlocks([...props.modelValue.blocks, block])
  await activateBlock(block.id, true)
}

async function copyBlock(block: DocumentBlock) {
  if (props.readonly) return
  const copied = createDocumentBlock(`${block.title || '未命名知识块'} - 副本`, block.markdown)
  copied.enabled = block.enabled
  const sourceIndex = props.modelValue.blocks.findIndex((item) => item.id === block.id)
  const blocks = [...props.modelValue.blocks]
  blocks.splice(sourceIndex + 1, 0, copied)
  updateBlocks(blocks)
  await activateBlock(copied.id, true)
}

function moveBlock(blockId: string, offset: -1 | 1) {
  if (props.readonly) return
  const sourceIndex = props.modelValue.blocks.findIndex((block) => block.id === blockId)
  const targetIndex = sourceIndex + offset
  if (sourceIndex < 0 || targetIndex < 0 || targetIndex >= props.modelValue.blocks.length) return
  const blocks = [...props.modelValue.blocks]
  const [block] = blocks.splice(sourceIndex, 1)
  blocks.splice(targetIndex, 0, block)
  updateBlocks(blocks)
}

async function removeBlock(block: DocumentBlock) {
  if (props.readonly) return
  if (props.modelValue.blocks.length <= 1) {
    ElMessage.warning('普通文档至少需要保留一个知识块。')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确定删除“${block.title || '未命名知识块'}”吗？删除会自动保存。`,
      '删除知识块',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }
  const removedIndex = props.modelValue.blocks.findIndex((item) => item.id === block.id)
  if (removedIndex < 0) return
  const blocks = props.modelValue.blocks.filter((item) => item.id !== block.id)
  updateBlocks(blocks)
  await activateBlock(blocks[Math.min(removedIndex, blocks.length - 1)]?.id || '', true)
}

function renderMarkdown(value: string) {
  return markdown.render(value || '_暂无正文_')
}

function applyBlockFormat(value: KnowledgeBlockFormat) {
  blockFormat.value = value
  markdownEditor.value?.setBlockFormat(value)
}
</script>

<template>
  <div class="document-editor">
    <aside class="block-directory" aria-label="知识块目录">
      <div class="directory-heading">
        <div>
          <span class="directory-title-label">文档目录</span>
          <span class="directory-count">{{ modelValue.blocks.length }}</span>
        </div>
        <el-tooltip v-if="!readonly" content="新增知识块" placement="top">
          <el-button
            class="icon-action"
            :icon="Plus"
            text
            aria-label="新增知识块"
            @click="addBlock"
          />
        </el-tooltip>
      </div>
      <nav class="directory-list">
        <button
          v-for="(block, index) in modelValue.blocks"
          :key="block.id"
          type="button"
          class="directory-item"
          :class="{ 'is-active': activeBlockId === block.id, 'is-disabled': !block.enabled }"
          :aria-current="activeBlockId === block.id ? 'location' : undefined"
          @click="activateBlock(block.id, true)"
        >
          <span class="directory-index">{{ index + 1 }}</span>
          <span class="directory-item-title">{{ block.title || '未命名知识块' }}</span>
          <span class="directory-status" :title="block.enabled ? '已启用' : '已停用'" />
        </button>
      </nav>
    </aside>

    <main class="document-workspace">
      <div v-if="!readonly" class="format-toolbar" role="toolbar" aria-label="正文格式">
        <el-tooltip content="撤销" placement="bottom">
          <el-button
            class="toolbar-action"
            :icon="RefreshLeft"
            text
            aria-label="撤销"
            @click="markdownEditor?.undo()"
          />
        </el-tooltip>
        <el-tooltip content="重做" placement="bottom">
          <el-button
            class="toolbar-action"
            :icon="RefreshRight"
            text
            aria-label="重做"
            @click="markdownEditor?.redo()"
          />
        </el-tooltip>
        <span class="toolbar-divider" />
        <el-select
          :model-value="blockFormat"
          class="format-select"
          aria-label="段落格式"
          @update:model-value="applyBlockFormat"
        >
          <el-option label="正文" value="paragraph" />
          <el-option label="二级标题" value="heading-2" />
          <el-option label="三级标题" value="heading-3" />
        </el-select>
        <span class="toolbar-divider" />
        <el-tooltip content="无序列表" placement="bottom">
          <el-button
            class="toolbar-action"
            :icon="List"
            text
            aria-label="无序列表"
            @click="markdownEditor?.toggleBulletList()"
          />
        </el-tooltip>
        <el-tooltip content="有序列表" placement="bottom">
          <el-button
            class="toolbar-action"
            :icon="Finished"
            text
            aria-label="有序列表"
            @click="markdownEditor?.toggleOrderedList()"
          />
        </el-tooltip>
        <el-tooltip content="引用" placement="bottom">
          <el-button
            class="toolbar-action"
            :icon="ChatLineSquare"
            text
            aria-label="引用"
            @click="markdownEditor?.toggleBlockquote()"
          />
        </el-tooltip>
      </div>

      <div class="document-canvas" @contextmenu.prevent>
        <div
          v-for="(block, index) in modelValue.blocks"
          :key="block.id"
          :ref="(element) => setBlockElement(block.id, element as Element | null)"
          class="document-block"
          :class="{ 'is-active': activeBlockId === block.id, 'is-disabled': !block.enabled }"
          @click="activeBlockId !== block.id && activateBlock(block.id)"
        >
          <KnowledgeContentFrame :index="index + 1" :title="block.title || '未命名知识块'">
            <template #title>
              <el-input
                v-if="activeBlockId === block.id && !readonly"
                class="block-title-input"
                :model-value="block.title"
                maxlength="120"
                placeholder="知识块标题"
                aria-label="知识块标题"
                @update:model-value="updateBlock(block.id, { title: $event })"
              />
              <span v-else class="block-title-text">{{ block.title || '未命名知识块' }}</span>
            </template>
            <template v-if="activeBlockId === block.id && !readonly" #actions>
              <span class="enabled-label">启用</span>
              <el-switch
                :model-value="block.enabled"
                size="small"
                :aria-label="block.enabled ? '停用知识块' : '启用知识块'"
                @update:model-value="updateBlock(block.id, { enabled: $event })"
              />
              <el-tooltip content="上移" placement="top">
                <el-button
                  class="icon-action"
                  :icon="ArrowUp"
                  text
                  :disabled="index === 0"
                  aria-label="上移知识块"
                  @click.stop="moveBlock(block.id, -1)"
                />
              </el-tooltip>
              <el-tooltip content="下移" placement="top">
                <el-button
                  class="icon-action"
                  :icon="ArrowDown"
                  text
                  :disabled="index === modelValue.blocks.length - 1"
                  aria-label="下移知识块"
                  @click.stop="moveBlock(block.id, 1)"
                />
              </el-tooltip>
              <el-tooltip content="复制" placement="top">
                <el-button
                  class="icon-action"
                  :icon="CopyDocument"
                  text
                  aria-label="复制知识块"
                  @click.stop="copyBlock(block)"
                />
              </el-tooltip>
              <el-tooltip content="删除" placement="top">
                <el-button
                  class="icon-action danger"
                  :icon="Delete"
                  text
                  aria-label="删除知识块"
                  @click.stop="removeBlock(block)"
                />
              </el-tooltip>
            </template>

            <KnowledgeMarkdownEditor
              v-if="activeBlockId === block.id"
              :ref="setMarkdownEditor"
              :model-value="block.markdown"
              :readonly="readonly"
              @update:model-value="updateBlock(block.id, { markdown: $event })"
            />
            <div
              v-else
              v-dompurify-html="renderMarkdown(block.markdown)"
              class="markdown-preview"
              role="button"
              tabindex="0"
              :aria-label="`编辑${block.title || '未命名知识块'}`"
              @keydown.enter="activateBlock(block.id)"
              @keydown.space.prevent="activateBlock(block.id)"
            />
          </KnowledgeContentFrame>
        </div>
      </div>
    </main>
  </div>
</template>

<style scoped lang="less">
.document-editor {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  width: 100%;
  min-width: 0;
  align-items: start;
  background: #f5f7fa;
}

.block-directory {
  position: sticky;
  top: 0;
  min-width: 0;
  height: calc(100vh - 78px);
  overflow: hidden;
  border-right: 1px solid #e4e7ec;
  background: #fff;
}

.directory-heading {
  display: flex;
  min-height: 52px;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 0 12px 0 16px;
  border-bottom: 1px solid #eaecf0;
}

.directory-title-label {
  color: #344054;
  font-size: 13px;
  font-weight: 600;
}

.directory-count {
  margin-left: 7px;
  color: #98a2b3;
  font-size: 12px;
}

.directory-list {
  height: calc(100% - 52px);
  overflow-y: auto;
  padding: 8px;
}

.directory-item {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr) 8px;
  width: 100%;
  min-width: 0;
  align-items: center;
  gap: 6px;
  padding: 9px 8px;
  border: 0;
  border-radius: 4px;
  color: #475467;
  background: transparent;
  cursor: pointer;
  text-align: left;
}

.directory-item:hover,
.directory-item:focus-visible,
.directory-item.is-active {
  color: #175cd3;
  background: #eff8ff;
  outline: 0;
}

.directory-item.is-disabled {
  color: #98a2b3;
}

.directory-index {
  color: #98a2b3;
  font-size: 12px;
  text-align: center;
}

.directory-item-title {
  min-width: 0;
  overflow: hidden;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.directory-status {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #12b76a;
}

.directory-item.is-disabled .directory-status {
  background: #d0d5dd;
}

.document-workspace {
  min-width: 0;
}

.format-toolbar {
  position: sticky;
  z-index: 4;
  top: 0;
  display: flex;
  min-height: 52px;
  align-items: center;
  gap: 3px;
  overflow-x: auto;
  padding: 8px max(16px, calc((100% - 860px) / 2));
  border-bottom: 1px solid #e4e7ec;
  background: rgba(255, 255, 255, 0.96);
  scrollbar-width: thin;
}

.toolbar-action,
.icon-action {
  flex: 0 0 32px;
  width: 32px;
  height: 32px;
  padding: 0;
  border: 0;
  border-radius: 4px;
  color: #667085;
  background: transparent;
}

.toolbar-action:hover,
.toolbar-action:focus-visible,
.icon-action:hover,
.icon-action:focus-visible {
  color: #175cd3;
  background: #eff8ff;
}

.icon-action.danger:hover,
.icon-action.danger:focus-visible {
  color: #d92d20;
  background: #fef3f2;
}

.toolbar-divider {
  flex: 0 0 1px;
  width: 1px;
  height: 20px;
  margin: 0 5px;
  background: #e4e7ec;
}

.format-select {
  flex: 0 0 112px;
  width: 112px;
}

.format-select :deep(.ed-select__wrapper) {
  min-height: 32px;
  border-radius: 4px;
  box-shadow: none;
}

.document-canvas {
  width: min(100%, 920px);
  min-width: 0;
  margin: 0 auto;
  padding: 28px 30px 80px;
}

.document-block {
  min-width: 0;
  scroll-margin-top: 72px;
}

.document-block + .document-block {
  margin-top: 14px;
}

.document-block :deep(.knowledge-content-frame) {
  border-color: #e4e7ec;
  border-radius: 4px;
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
}

.document-block.is-active :deep(.knowledge-content-frame) {
  border-color: #84adff;
  box-shadow: 0 0 0 2px rgba(47, 107, 255, 0.08);
}

.document-block.is-disabled {
  opacity: 0.72;
}

.block-title-input {
  width: min(100%, 420px);
}

.block-title-input :deep(.ed-input__wrapper) {
  padding: 0 6px;
  background: #fff;
  box-shadow: 0 0 0 1px #d0d5dd inset;
}

.block-title-text {
  min-width: 0;
  overflow: hidden;
  color: #344054;
  font-size: 13px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.enabled-label {
  color: #667085;
  font-size: 12px;
}

.markdown-preview {
  min-height: 72px;
  color: #344054;
  font-size: 12px;
  line-height: 1.8;
  cursor: text;
  overflow-wrap: anywhere;
}

.markdown-preview:focus-visible {
  outline: 2px solid #84adff;
  outline-offset: 3px;
}

.markdown-preview :deep(> :first-child) {
  margin-top: 0;
}

.markdown-preview :deep(> :last-child) {
  margin-bottom: 0;
}

.markdown-preview :deep(table) {
  display: block;
  max-width: 100%;
  overflow-x: auto;
  border-collapse: collapse;
}

.markdown-preview :deep(th),
.markdown-preview :deep(td) {
  padding: 7px 9px;
  border: 1px solid #d0d5dd;
}

@media (max-width: 680px) {
  .document-editor {
    display: block;
  }

  .block-directory {
    position: sticky;
    z-index: 5;
    top: 0;
    height: auto;
    border-right: 0;
    border-bottom: 1px solid #e4e7ec;
  }

  .directory-heading {
    min-height: 44px;
  }

  .directory-list {
    display: flex;
    height: auto;
    overflow-x: auto;
    overflow-y: hidden;
    padding: 6px 8px;
  }

  .directory-item {
    flex: 0 0 154px;
  }

  .format-toolbar {
    top: 88px;
    min-height: 46px;
    padding: 6px 10px;
  }

  .document-canvas {
    width: 100%;
    padding: 14px 10px 64px;
  }

  .document-block {
    scroll-margin-top: 146px;
  }

  .enabled-label {
    display: none;
  }
}
</style>
