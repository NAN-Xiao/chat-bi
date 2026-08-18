<script setup lang="ts">
import { Delete, Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, ref, watch } from 'vue'
import {
  createDocumentBlock,
  type DocumentBlock,
  type DocumentPayload,
} from '../knowledgePayloadTypes'
import KnowledgeContentFrame from './KnowledgeContentFrame.vue'

const props = withDefaults(defineProps<{ modelValue: DocumentPayload; readonly?: boolean }>(), {
  readonly: false,
})
const emit = defineEmits<{ 'update:modelValue': [value: DocumentPayload] }>()
const activeBlockId = ref('')

const activeBlockIndex = computed(() =>
  props.modelValue.blocks.findIndex((block) => block.id === activeBlockId.value)
)
const activeBlock = computed(() => props.modelValue.blocks[activeBlockIndex.value])

watch(
  () => props.modelValue.blocks.map((block) => block.id),
  (ids) => {
    if (!ids.includes(activeBlockId.value)) activeBlockId.value = ids[0] || ''
  },
  { immediate: true }
)

function updateBlocks(blocks: DocumentBlock[]) {
  emit('update:modelValue', { ...props.modelValue, blocks })
}

function updateBlock(index: number, patch: Partial<DocumentBlock>) {
  updateBlocks(
    props.modelValue.blocks.map((block, blockIndex) =>
      blockIndex === index ? { ...block, ...patch } : block
    )
  )
}

function nextBlockTitle() {
  const usedTitles = new Set(props.modelValue.blocks.map((block) => block.title.trim()))
  let suffix = props.modelValue.blocks.length + 1
  while (usedTitles.has(`新知识块 ${suffix}`)) suffix += 1
  return `新知识块 ${suffix}`
}

function addBlock() {
  if (props.readonly) return
  const block = createDocumentBlock(nextBlockTitle())
  activeBlockId.value = block.id
  updateBlocks([...props.modelValue.blocks, block])
}

async function removeActiveBlock() {
  const block = activeBlock.value
  if (props.readonly || activeBlockIndex.value < 0 || !block) return
  const removedBlockId = block.id
  if (props.modelValue.blocks.length <= 1) {
    ElMessage.warning('普通文档至少需要保留一个知识块。')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确定删除“${block.title || '未命名知识块'}”吗？删除将在保存草稿后生效。`,
      '删除知识块',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }
  const removedIndex = props.modelValue.blocks.findIndex((item) => item.id === removedBlockId)
  if (removedIndex < 0) return
  const blocks = props.modelValue.blocks.filter((_, index) => index !== removedIndex)
  activeBlockId.value = blocks[Math.min(removedIndex, blocks.length - 1)]?.id || ''
  updateBlocks(blocks)
}
</script>

<template>
  <div class="document-editor">
    <div class="block-toolbar">
      <div class="block-heading">
        <span>知识块</span>
        <el-tag size="small" type="info">{{ modelValue.blocks.length }}</el-tag>
      </div>
      <el-tooltip v-if="!readonly" content="新增知识块" placement="top">
        <el-button
          class="block-icon-action"
          :icon="Plus"
          text
          aria-label="新增知识块"
          @click="addBlock"
        />
      </el-tooltip>
    </div>
    <div class="block-workspace">
      <nav class="block-directory" aria-label="知识块目录">
        <div
          v-for="(block, index) in modelValue.blocks"
          :key="block.id"
          class="directory-item"
          :class="{ 'is-active': activeBlockId === block.id, 'is-disabled': !block.enabled }"
        >
          <button
            type="button"
            class="directory-select"
            :aria-current="activeBlockId === block.id ? 'page' : undefined"
            @click="activeBlockId = block.id"
          >
            <span class="directory-index">{{ index + 1 }}</span>
            <span class="directory-title">{{ block.title || '未命名知识块' }}</span>
          </button>
        </div>
      </nav>
      <div class="block-detail">
        <KnowledgeContentFrame
          v-if="activeBlock && activeBlockIndex >= 0"
          :key="activeBlock.id"
          :index="activeBlockIndex + 1"
          :title="activeBlock.title || '未命名知识块'"
        >
          <template v-if="!readonly" #actions>
            <el-tooltip content="删除知识块" placement="top">
              <el-button
                class="block-icon-action"
                :icon="Delete"
                text
                aria-label="删除知识块"
                @click="removeActiveBlock"
              />
            </el-tooltip>
          </template>
          <el-form label-position="top" :disabled="readonly" @submit.prevent>
            <el-form-item label="Markdown 正文" :required="activeBlock.enabled">
              <el-input
                class="markdown-editor"
                :model-value="activeBlock.markdown"
                type="textarea"
                :autosize="{ minRows: 8, maxRows: 20 }"
                placeholder="输入当前知识块的可检索内容"
                @update:model-value="updateBlock(activeBlockIndex, { markdown: $event })"
              />
            </el-form-item>
          </el-form>
        </KnowledgeContentFrame>
      </div>
    </div>
  </div>
</template>

<style scoped lang="less">
.document-editor {
  width: 100%;
  min-width: 0;
}
.block-toolbar,
.block-heading {
  display: flex;
  align-items: center;
}
.block-toolbar {
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}
.block-heading {
  gap: 8px;
  color: #344054;
  font-size: 14px;
  font-weight: 600;
}
.block-icon-action {
  width: 32px;
  height: 32px;
  padding: 0;
  border: 0;
  border-radius: 4px;
  color: #667085;
  background: transparent;
}
.block-icon-action:hover,
.block-icon-action:focus-visible {
  color: #2f6bff;
  background: #eef3ff;
}
.block-workspace {
  display: grid;
  grid-template-columns: minmax(140px, 180px) minmax(0, 1fr);
  align-items: start;
  gap: 12px;
  margin-bottom: 18px;
}
.block-directory {
  min-width: 0;
  max-height: calc(100vh - 180px);
  overflow-y: auto;
  overscroll-behavior: contain;
  padding-right: 12px;
  border-right: 1px solid #e4e7ec;
}
.directory-item {
  display: flex;
  width: 100%;
  min-width: 0;
  align-items: center;
  border-radius: 6px;
  color: #475467;
  background: transparent;
}
.directory-item:hover,
.directory-item.is-active {
  color: #175cd3;
  background: #eff8ff;
}
.directory-item.is-disabled {
  color: #98a2b3;
}
.directory-select {
  display: flex;
  flex: 1 1 auto;
  min-width: 0;
  align-items: center;
  gap: 8px;
  padding: 8px;
  border: 0;
  color: inherit;
  background: transparent;
  cursor: pointer;
  text-align: left;
}
.directory-index {
  flex: 0 0 24px;
  color: #667085;
  font-size: 12px;
}
.directory-title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.block-detail {
  min-width: 0;
}
.markdown-editor :deep(.ed-textarea__inner) {
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}
.markdown-editor :deep(.ed-textarea__inner:hover),
.markdown-editor :deep(.ed-textarea__inner:focus) {
  box-shadow: none;
}
@media (max-width: 680px) {
  .block-workspace {
    grid-template-columns: minmax(0, 1fr);
  }
  .block-directory {
    display: flex;
    max-width: 100%;
    max-height: none;
    overflow-x: auto;
    overflow-y: hidden;
    padding: 0 0 8px;
    border-right: 0;
    border-bottom: 1px solid #e4e7ec;
  }
  .directory-item {
    flex: 0 0 150px;
  }
}
</style>
