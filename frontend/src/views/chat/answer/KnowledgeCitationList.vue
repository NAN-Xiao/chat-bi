<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ snapshot?: Record<string, any> }>()
const citations = computed(() => {
  const direct = props.snapshot?.knowledge_citations
  const nested = props.snapshot?.business_context?.knowledge_citations
  return Array.isArray(direct) ? direct : Array.isArray(nested) ? nested : []
})
const warnings = computed(() => {
  const direct = props.snapshot?.retrieval_warnings
  const nested = props.snapshot?.business_context?.warnings
  return Array.isArray(direct) ? direct : Array.isArray(nested) ? nested : []
})
</script>

<template>
  <div v-if="citations.length || warnings.length" class="knowledge-citations">
    <details>
      <summary>已使用知识库（{{ citations.length }}）</summary>
      <div class="citation-list">
        <div v-for="item in citations" :key="`${item.knowledge_base_id}-${item.chunk_id}`" class="citation-item">
          <span>知识库 #{{ item.knowledge_base_id }} · 片段 #{{ item.chunk_id }}</span>
          <span v-if="item.section_path" class="section-path">{{ item.section_path }}</span>
          <span v-if="item.score !== undefined" class="score">相似度 {{ Number(item.score).toFixed(3) }}</span>
        </div>
        <div v-for="(warning, index) in warnings" :key="`warning-${index}`" class="citation-warning">
          {{ warning?.message || warning }}
        </div>
      </div>
    </details>
  </div>
</template>

<style scoped lang="less">
.knowledge-citations { margin-top: 12px; color: #667085; font-size: 12px; line-height: 20px; }
summary { cursor: pointer; color: #475467; user-select: none; }
.citation-list { margin-top: 6px; padding: 8px 10px; border: 1px solid #eaecf0; border-radius: 6px; background: #fafafa; }
.citation-item { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.section-path { color: #344054; }
.score { color: #98a2b3; }
.citation-warning { color: #b54708; }
</style>
