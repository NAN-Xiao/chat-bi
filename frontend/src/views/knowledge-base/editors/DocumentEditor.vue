<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowDown, ArrowUp, CopyDocument, Delete, EditPen, Plus } from '@element-plus/icons-vue'
import { createDocumentBlock, type DocumentBlock, type DocumentPayload } from '../knowledgePayloadTypes'

const props = withDefaults(defineProps<{ modelValue: DocumentPayload; readonly?: boolean }>(), { readonly: false })
const emit = defineEmits<{ 'update:modelValue': [value: DocumentPayload] }>()
const activeBlockId = ref('')

const activeBlockIndex = computed(() => props.modelValue.blocks.findIndex((block) => block.id === activeBlockId.value))
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
  updateBlocks(props.modelValue.blocks.map((block, blockIndex) => (
    blockIndex === index ? { ...block, ...patch } : block
  )))
}

function addBlock(afterIndex = props.modelValue.blocks.length - 1) {
  const block = createDocumentBlock()
  const blocks = [...props.modelValue.blocks]
  blocks.splice(afterIndex + 1, 0, block)
  activeBlockId.value = block.id
  updateBlocks(blocks)
}

function copyBlock(index: number) {
  const source = props.modelValue.blocks[index]
  const copy = createDocumentBlock(`${source.title || '未命名知识块'} - 副本`, source.markdown)
  copy.enabled = source.enabled
  const blocks = [...props.modelValue.blocks]
  blocks.splice(index + 1, 0, copy)
  activeBlockId.value = copy.id
  updateBlocks(blocks)
}

function moveBlock(index: number, offset: number) {
  const target = index + offset
  if (target < 0 || target >= props.modelValue.blocks.length) return
  const blocks = [...props.modelValue.blocks]
  const [block] = blocks.splice(index, 1)
  blocks.splice(target, 0, block)
  updateBlocks(blocks)
}

async function renameBlock(index: number) {
  activeBlockId.value = props.modelValue.blocks[index].id
  try {
    const { value } = await ElMessageBox.prompt('请输入知识块标题', '编辑知识块标题', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputValue: props.modelValue.blocks[index].title,
      inputPlaceholder: '输入知识块标题',
      inputValidator: (title) => {
        if (!title.trim()) return '知识块标题不能为空'
        return title.trim().length <= 255 ? true : '知识块标题不能超过 255 个字符'
      },
    })
    updateBlock(index, { title: value.trim() })
  } catch {
    // Cancel keeps the current title unchanged.
  }
}

async function removeBlock(index: number) {
  if (props.modelValue.blocks.length <= 1) {
    ElMessage.warning('知识文档至少需要保留一个知识块')
    return
  }
  await ElMessageBox.confirm('删除后需保存草稿才会生效。', '删除知识块', {
    confirmButtonText: '删除',
    cancelButtonText: '取消',
    type: 'warning',
  })
  const removedBlock = props.modelValue.blocks[index]
  const blocks = props.modelValue.blocks.filter((_, blockIndex) => blockIndex !== index)
  if (removedBlock.id === activeBlockId.value) {
    activeBlockId.value = blocks[Math.min(index, blocks.length - 1)]?.id || ''
  }
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
      <el-button v-if="!readonly" type="primary" plain :icon="Plus" @click="addBlock()">新增知识块</el-button>
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
          <el-tooltip v-if="!readonly" content="编辑标题" placement="top">
            <el-button class="directory-edit" text :icon="EditPen" aria-label="编辑标题" @click="renameBlock(index)" />
          </el-tooltip>
        </div>
      </nav>
      <div class="block-detail">
        <section v-if="activeBlock && activeBlockIndex >= 0" :key="activeBlock.id" class="knowledge-block">
          <div class="block-header">
            <div class="block-title-group">
              <span class="block-index">{{ activeBlockIndex + 1 }}</span>
              <span class="block-title">{{ activeBlock.title || '未命名知识块' }}</span>
              <el-switch
                v-if="!readonly"
                :model-value="activeBlock.enabled"
                inline-prompt
                active-text="启"
                inactive-text="停"
                aria-label="检索状态"
                @update:model-value="updateBlock(activeBlockIndex, { enabled: $event })"
              />
              <el-tag v-else size="small" :type="activeBlock.enabled ? 'success' : 'info'">{{ activeBlock.enabled ? '启用' : '停用' }}</el-tag>
            </div>
            <div v-if="!readonly" class="block-actions">
              <el-tooltip content="上移" placement="top"><el-button class="block-action" text :icon="ArrowUp" :disabled="activeBlockIndex === 0" @click="moveBlock(activeBlockIndex, -1)" /></el-tooltip>
              <el-tooltip content="下移" placement="top"><el-button class="block-action" text :icon="ArrowDown" :disabled="activeBlockIndex === modelValue.blocks.length - 1" @click="moveBlock(activeBlockIndex, 1)" /></el-tooltip>
              <el-tooltip content="复制" placement="top"><el-button class="block-action" text :icon="CopyDocument" @click="copyBlock(activeBlockIndex)" /></el-tooltip>
              <el-tooltip content="删除" placement="top"><el-button class="block-action is-danger" text :icon="Delete" @click="removeBlock(activeBlockIndex)" /></el-tooltip>
            </div>
          </div>
          <div class="block-body">
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
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped lang="less">
.document-editor { width: 100%; min-width: 0; }
.block-toolbar, .block-heading, .block-header, .block-title-group, .block-actions { display: flex; align-items: center; }
.block-toolbar { justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.block-heading { gap: 8px; color: #344054; font-size: 14px; font-weight: 600; }
.block-workspace { display: grid; grid-template-columns: minmax(140px, 180px) minmax(0, 1fr); gap: 12px; margin-bottom: 18px; }
.block-directory { min-width: 0; padding-right: 12px; border-right: 1px solid #e4e7ec; }
.directory-item { display: flex; width: 100%; min-width: 0; align-items: center; border-radius: 6px; color: #475467; background: transparent; }
.directory-item:hover, .directory-item.is-active { color: #175cd3; background: #eff8ff; }
.directory-item.is-disabled { color: #98a2b3; }
.directory-select { display: flex; flex: 1 1 auto; min-width: 0; align-items: center; gap: 8px; padding: 8px; border: 0; color: inherit; background: transparent; cursor: pointer; text-align: left; }
.directory-edit, .block-action { width: 28px; height: 28px; padding: 0; border: 0; border-radius: 6px; color: #667085; }
.directory-edit { flex: 0 0 28px; margin-right: 2px; opacity: 0; }
.directory-edit:hover, .block-action:hover { color: #2f6bff; background: #eef3ff; }
.block-action.is-danger:hover { color: #f04438; background: #fff1f0; }
.directory-edit :deep(.ed-icon), .block-action :deep(.ed-icon) { font-size: 16px; }
.directory-item:hover .directory-edit, .directory-item.is-active .directory-edit, .directory-edit:focus-visible { opacity: 1; }
.directory-index, .block-index { flex: 0 0 24px; color: #667085; font-size: 12px; }
.directory-title, .block-title { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.block-detail { min-width: 0; }
.knowledge-block { min-width: 0; overflow: hidden; border: 1px solid #dfe3e8; border-radius: 8px; background: #fff; }
.block-header { min-height: 48px; justify-content: space-between; gap: 8px; padding: 7px 10px; background: #f8f9fb; }
.block-title-group { flex: 1 1 auto; min-width: 0; gap: 8px; color: #344054; }
.block-title { font-size: 13px; font-weight: 600; }
.block-actions { flex: 0 0 auto; gap: 3px; }
.block-actions :deep(.ed-button + .ed-button) { margin-left: 0; }
.block-body { padding: 14px 12px 4px; border-top: 1px solid #eaecf0; }
.markdown-editor :deep(.ed-textarea__inner) { padding: 0; border: 0; border-radius: 0; background: transparent; box-shadow: none; }
.markdown-editor :deep(.ed-textarea__inner:hover), .markdown-editor :deep(.ed-textarea__inner:focus) { box-shadow: none; }
@media (max-width: 680px) {
  .block-workspace { grid-template-columns: minmax(0, 1fr); }
  .block-directory { display: flex; max-width: 100%; overflow-x: auto; padding: 0 0 8px; border-right: 0; border-bottom: 1px solid #e4e7ec; }
  .directory-item { flex: 0 0 150px; }
  .directory-edit { opacity: 1; }
  .block-header { align-items: flex-start; flex-direction: column; }
  .block-actions { width: 100%; justify-content: flex-end; }
}
</style>
