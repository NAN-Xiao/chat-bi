<script setup lang="ts">
import { computed } from 'vue'
import DocumentEditor from './editors/DocumentEditor.vue'
import {
  defaultKnowledgePayload,
  serializeKnowledgeDraft,
  type KnowledgePayload,
} from './knowledgePayloadTypes'

const props = withDefaults(
  defineProps<{ modelValue: KnowledgePayload; readonly?: boolean }>(),
  { readonly: false }
)
const emit = defineEmits<{ 'update:modelValue': [value: KnowledgePayload] }>()
const local = computed<KnowledgePayload>({
  get: () => props.modelValue || defaultKnowledgePayload(),
  set: (value) => emit('update:modelValue', serializeKnowledgeDraft(value)),
})

function updatePayload(value: KnowledgePayload) {
  local.value = value
}
</script>

<template>
  <div class="payload-editor">
    <DocumentEditor
      :model-value="local"
      :readonly="readonly"
      @update:model-value="updatePayload"
    />
  </div>
</template>

<style scoped lang="less">
.payload-editor { width: 100%; }
</style>
