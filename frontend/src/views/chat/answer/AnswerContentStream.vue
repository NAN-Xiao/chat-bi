<script setup lang="ts">
import { computed } from 'vue'
import MdComponent from '@/views/chat/component/MdComponent.vue'

const props = defineProps<{
  content?: Record<string, string>
}>()

const entries = computed(() =>
  Object.entries(props.content || {}).filter(([, value]) => typeof value === 'string' && value.trim())
)
</script>

<template>
  <div v-if="entries.length" class="answer-content-stream" aria-live="polite">
    <div v-for="([source, value], index) in entries" :key="source" class="answer-content-item">
      <MdComponent :message="value" />
      <span v-if="index < entries.length - 1" class="answer-content-divider" aria-hidden="true" />
    </div>
  </div>
</template>

<style scoped lang="less">
.answer-content-stream {
  margin-bottom: 10px;
  padding: 2px 0 2px 10px;
  border-left: 2px solid rgba(22, 143, 112, 0.35);
  color: rgba(31, 35, 41, 0.72);
  font-size: 14px;
  line-height: 22px;
}

.answer-content-item {
  position: relative;
}

.answer-content-divider {
  display: block;
  height: 1px;
  margin: 8px 0;
  background: rgba(31, 35, 41, 0.1);
}

.answer-content-stream :deep(.markdown-body) {
  color: inherit;
  background: transparent !important;
  font-size: inherit;
  line-height: inherit;
}

.answer-content-stream :deep(.markdown-body > :first-child) {
  margin-top: 0;
}
</style>
