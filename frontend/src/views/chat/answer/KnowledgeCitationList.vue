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
const failureType = computed(() =>
  props.snapshot?.retrieval_failure_type
  || props.snapshot?.business_context?.retrieval_failure_type
  || props.snapshot?.business_context?.business_semantic_context?.retrieval_failure_type
  || null
)

function failureText(value: unknown) {
  if (value === 'NO_ELIGIBLE_KNOWLEDGE') return '当前数据源没有适用知识'
  if (value === 'PERMISSION_CONTEXT_MISMATCH') return '知识库权限或数据源上下文不匹配'
  if (value === 'EMPTY_QUERY') return '检索内容为空'
  if (value) return '知识检索暂时不可用'
  return ''
}

function contentPreview(value: unknown) {
  const text = typeof value === 'string' ? value.trim() : ''
  return text.length > 180 ? `${text.slice(0, 180)}...` : text
}
</script>

<template>
  <div v-if="citations.length || warnings.length || failureType" class="knowledge-citations">
    <details>
      <summary>已使用知识库（{{ citations.length }}）</summary>
      <div class="citation-list">
        <div v-for="(item, index) in citations" :key="`${item.knowledge_base_id}-${item.version_id}-${index}`" class="citation-item">
          <div class="citation-source">
            <span>{{ item.knowledge_base_name || '知识库' }}</span>
            <span v-if="item.version_number != null"> · 版本 {{ item.version_number }}</span>
            <span v-if="item.source_file_name"> · {{ item.source_file_name }}</span>
          </div>
          <span v-if="item.section_path" class="section-path">{{ item.section_path }}</span>
          <span v-if="item.score !== undefined" class="score">相似度 {{ Number(item.score).toFixed(3) }}</span>
          <div v-if="contentPreview(item.content)" class="citation-excerpt">{{ contentPreview(item.content) }}</div>
        </div>
        <div v-if="failureType" class="citation-failure">{{ failureText(failureType) }}</div>
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
.citation-source { color: #344054; font-weight: 600; }
.section-path { color: #344054; }
.score { color: #98a2b3; }
.citation-excerpt { flex-basis: 100%; color: #667085; white-space: pre-wrap; }
.citation-failure { color: #b42318; }
.citation-warning { color: #b54708; }
</style>
