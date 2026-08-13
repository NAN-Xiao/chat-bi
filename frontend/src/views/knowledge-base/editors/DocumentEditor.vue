<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { DocumentBlock, DocumentPayload } from '../knowledgePayloadTypes'

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
</script>

<template>
  <div class="document-editor">
    <div class="block-toolbar">
      <div class="block-heading">
        <span>知识块</span>
        <el-tag size="small" type="info">{{ modelValue.blocks.length }}</el-tag>
      </div>
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
        <section v-if="activeBlock && activeBlockIndex >= 0" :key="activeBlock.id" class="knowledge-block">
          <div class="block-header">
            <span class="block-index">{{ activeBlockIndex + 1 }}</span>
            <span class="block-title">{{ activeBlock.title || '未命名知识块' }}</span>
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
.block-toolbar, .block-heading, .block-header { display: flex; align-items: center; }
.block-toolbar { margin-bottom: 12px; }
.block-heading { gap: 8px; color: #344054; font-size: 14px; font-weight: 600; }
.block-workspace { display: grid; grid-template-columns: minmax(140px, 180px) minmax(0, 1fr); align-items: start; gap: 12px; margin-bottom: 18px; }
.block-directory { min-width: 0; max-height: calc(100vh - 180px); overflow-y: auto; overscroll-behavior: contain; padding-right: 12px; border-right: 1px solid #e4e7ec; }
.directory-item { display: flex; width: 100%; min-width: 0; align-items: center; border-radius: 6px; color: #475467; background: transparent; }
.directory-item:hover, .directory-item.is-active { color: #175cd3; background: #eff8ff; }
.directory-item.is-disabled { color: #98a2b3; }
.directory-select { display: flex; flex: 1 1 auto; min-width: 0; align-items: center; gap: 8px; padding: 8px; border: 0; color: inherit; background: transparent; cursor: pointer; text-align: left; }
.directory-index, .block-index { flex: 0 0 24px; color: #667085; font-size: 12px; }
.directory-title, .block-title { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.block-detail { min-width: 0; }
.knowledge-block { min-width: 0; overflow: hidden; border: 1px solid #dfe3e8; border-radius: 8px; background: #fff; }
.block-header { min-height: 48px; gap: 8px; padding: 7px 10px; background: #f8f9fb; }
.block-title { color: #344054; font-size: 13px; font-weight: 600; }
.block-body { padding: 14px 12px 4px; border-top: 1px solid #eaecf0; }
.markdown-editor :deep(.ed-textarea__inner) { padding: 0; border: 0; border-radius: 0; background: transparent; box-shadow: none; }
.markdown-editor :deep(.ed-textarea__inner:hover), .markdown-editor :deep(.ed-textarea__inner:focus) { box-shadow: none; }
@media (max-width: 680px) {
  .block-workspace { grid-template-columns: minmax(0, 1fr); }
  .block-directory { display: flex; max-width: 100%; max-height: none; overflow-x: auto; overflow-y: hidden; padding: 0 0 8px; border-right: 0; border-bottom: 1px solid #e4e7ec; }
  .directory-item { flex: 0 0 150px; }
}
</style>
