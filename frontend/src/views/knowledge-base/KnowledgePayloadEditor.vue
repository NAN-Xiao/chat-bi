<script setup lang="ts">
import { computed } from 'vue'
import BusinessKnowledgeEditor from './editors/BusinessKnowledgeEditor.vue'
import DocumentEditor from './editors/DocumentEditor.vue'
import EventKnowledgeEditor from './editors/EventKnowledgeEditor.vue'
import JsonFieldKnowledgeEditor from './editors/JsonFieldKnowledgeEditor.vue'
import {
  defaultKnowledgePayload,
  serializeKnowledgeDraft,
  type BusinessKnowledgePayload,
  type DocumentPayload,
  type EventKnowledgePayload,
  type JsonFieldKnowledgePayload,
  type KnowledgePayload,
} from './knowledgePayloadTypes'

const props = withDefaults(
  defineProps<{ modelValue: KnowledgePayload; readonly?: boolean }>(),
  { readonly: false }
)
const emit = defineEmits<{ 'update:modelValue': [value: KnowledgePayload] }>()
const local = computed<KnowledgePayload>({
  get: () => props.modelValue || defaultKnowledgePayload('DOCUMENT'),
  set: (value) => emit('update:modelValue', serializeKnowledgeDraft(value)),
})
const type = computed(() => local.value.knowledge_type)
const documentPayload = computed(() => local.value as DocumentPayload)
const businessPayload = computed(() => local.value as BusinessKnowledgePayload)
const eventPayload = computed(() => local.value as EventKnowledgePayload)
const jsonFieldPayload = computed(() => local.value as JsonFieldKnowledgePayload)
const typeOptions = [
  { label: '普通文档', value: 'DOCUMENT' },
  { label: '业务知识（术语 + SQL 示例）', value: 'BUSINESS' },
  { label: '事件与事件参数', value: 'EVENT' },
  { label: 'JSON 字段与路径', value: 'JSON_FIELD' },
]

function updateType(value: KnowledgePayload['knowledge_type']) {
  local.value = defaultKnowledgePayload(value)
}

function updatePayload(value: KnowledgePayload) {
  local.value = value
}
</script>

<template>
  <div class="payload-editor">
    <el-form label-position="top" :disabled="readonly" @submit.prevent>
      <el-form-item label="知识类型">
        <el-select :model-value="type" @update:model-value="updateType">
          <el-option v-for="item in typeOptions" :key="item.value" v-bind="item" />
        </el-select>
      </el-form-item>
    </el-form>

    <DocumentEditor
      v-if="type === 'DOCUMENT'"
      :model-value="documentPayload"
      :readonly="readonly"
      @update:model-value="updatePayload"
    />
    <BusinessKnowledgeEditor
      v-else-if="type === 'BUSINESS'"
      :model-value="businessPayload"
      :readonly="readonly"
      @update:model-value="updatePayload"
    />
    <EventKnowledgeEditor
      v-else-if="type === 'EVENT'"
      :model-value="eventPayload"
      :readonly="readonly"
      @update:model-value="updatePayload"
    />
    <JsonFieldKnowledgeEditor
      v-else
      :model-value="jsonFieldPayload"
      :readonly="readonly"
      @update:model-value="updatePayload"
    />
  </div>
</template>

<style scoped lang="less">
.payload-editor { width: 100%; }
.payload-editor :deep(.el-select) { width: 100%; }
</style>
