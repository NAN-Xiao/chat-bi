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

function updatePayload(value: KnowledgePayload) {
  local.value = value
}
</script>

<template>
  <div class="payload-editor">
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
</style>
