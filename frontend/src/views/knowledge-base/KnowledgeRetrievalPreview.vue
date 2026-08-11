<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Search } from '@element-plus/icons-vue'
import { knowledgeBaseApi, type KnowledgeRetrievalPreviewResult } from '@/api/knowledgeBase'
import { useDatasourceContextStore } from '@/stores/datasourceContext'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ (event: 'update:modelValue', value: boolean): void }>()

const datasourceContext = useDatasourceContextStore()
const query = ref('')
const loading = ref(false)
const errorMessage = ref('')
const result = ref<KnowledgeRetrievalPreviewResult | null>(null)

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})
const datasourceName = computed(() => datasourceContext.datasourceName || '当前数据源')

function failureText(value?: string | null) {
  if (value === 'NO_ELIGIBLE_KNOWLEDGE') return '当前数据源没有适用知识'
  if (value === 'PERMISSION_CONTEXT_MISMATCH') return '知识库权限或数据源上下文不匹配'
  if (value === 'EMPTY_QUERY') return '检索内容为空'
  return value ? '知识检索暂时不可用' : ''
}

function contentPreview(value?: string | null) {
  const text = value?.trim() || ''
  return text.length > 240 ? `${text.slice(0, 240)}...` : text
}

watch(
  () => props.modelValue,
  async (value) => {
    if (value && !datasourceContext.initialized) await datasourceContext.loadDatasources()
  }
)

async function searchKnowledge() {
  const text = query.value.trim()
  if (!text) {
    ElMessage.warning('请输入检索内容')
    return
  }
  if (!datasourceContext.datasourceId) {
    ElMessage.warning('当前工作空间没有可用数据源')
    return
  }
  loading.value = true
  errorMessage.value = ''
  try {
    result.value = await knowledgeBaseApi.retrievalPreview({
      datasource_id: Number(datasourceContext.datasourceId),
      query: text,
      surface: 'KNOWLEDGE_MANAGEMENT_PREVIEW',
    })
  } catch (error) {
    console.error(error)
    result.value = null
    errorMessage.value = '检索预览失败，请稍后重试。'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <el-drawer v-model="visible" title="检索预览" size="620px" destroy-on-close>
    <div class="preview-toolbar">
      <span class="datasource-label">数据源：{{ datasourceName }}</span>
      <el-input
        v-model="query"
        clearable
        maxlength="4000"
        placeholder="输入问题或业务术语"
        @keyup.enter="searchKnowledge"
      >
        <template #append>
          <el-button :icon="Search" :loading="loading" @click="searchKnowledge">检索</el-button>
        </template>
      </el-input>
    </div>
    <el-alert v-if="errorMessage" type="error" :closable="false" :title="errorMessage" />
    <el-empty v-else-if="!result && !loading" description="输入内容后查看当前数据源可用的知识" />
    <div v-else v-loading="loading" class="preview-result">
      <div class="result-meta">
        <span>命中 {{ result?.citations?.length || 0 }} 条</span>
        <span v-if="result?.latency_ms != null">耗时 {{ result.latency_ms }} ms</span>
        <span v-if="result?.failure_type" class="result-failure">{{ failureText(result.failure_type) }}</span>
      </div>
      <pre v-if="result?.context" class="result-context">{{ result.context }}</pre>
      <div v-if="result?.citations?.length" class="citation-list">
        <div v-for="(item, index) in result.citations" :key="`${item.knowledge_base_id}-${index}`" class="citation-row">
          <div class="citation-title">{{ item.knowledge_base_name || '知识库' }}</div>
          <div v-if="item.version_number != null || item.source_file_name" class="citation-source">
            <span v-if="item.version_number != null">版本 {{ item.version_number }}</span>
            <span v-if="item.source_file_name">{{ item.source_file_name }}</span>
          </div>
          <div v-if="item.section_path" class="citation-path">{{ item.section_path }}</div>
          <div v-if="contentPreview(item.content)" class="citation-content">{{ contentPreview(item.content) }}</div>
          <div v-if="item.score != null" class="citation-score">相似度 {{ Number(item.score).toFixed(3) }}</div>
        </div>
      </div>
      <div v-if="result?.warnings?.length" class="preview-warnings">
        <div v-for="(warning, index) in result.warnings" :key="index">
          {{ typeof warning === 'string' ? warning : warning.message || '部分知识未参与检索' }}
        </div>
      </div>
    </div>
  </el-drawer>
</template>

<style scoped lang="less">
.preview-toolbar { display: grid; gap: 10px; margin-bottom: 16px; }
.datasource-label { color: #667085; font-size: 12px; }
.preview-result { min-height: 180px; }
.result-meta { display: flex; gap: 12px; color: #667085; font-size: 12px; }
.result-context { max-height: 260px; margin: 12px 0; padding: 10px 12px; overflow: auto; border: 1px solid #eaecf0; border-radius: 6px; background: #fafafa; color: #344054; font: inherit; font-size: 12px; line-height: 18px; white-space: pre-wrap; }
.citation-list { display: grid; gap: 8px; }
.citation-row { padding: 10px 12px; border: 1px solid #eaecf0; border-radius: 6px; }
.citation-title { color: #344054; font-size: 13px; font-weight: 600; }
.citation-source, .citation-path, .citation-score { margin-top: 4px; color: #667085; font-size: 12px; }
.citation-source { display: flex; gap: 10px; }
.citation-content { margin-top: 8px; color: #475467; font-size: 12px; line-height: 18px; white-space: pre-wrap; }
.result-failure { color: #b42318; }
.preview-warnings { margin-top: 12px; color: #9a6700; font-size: 12px; line-height: 20px; }
</style>
