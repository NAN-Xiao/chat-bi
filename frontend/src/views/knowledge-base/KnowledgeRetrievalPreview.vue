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
      </div>
      <pre v-if="result?.context" class="result-context">{{ result.context }}</pre>
      <div v-if="result?.citations?.length" class="citation-list">
        <div v-for="(item, index) in result.citations" :key="`${item.knowledge_base_id}-${index}`" class="citation-row">
          <div class="citation-title">知识库 #{{ item.knowledge_base_id || '-' }}</div>
          <div v-if="item.section_path" class="citation-path">{{ item.section_path }}</div>
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
.citation-path, .citation-score { margin-top: 4px; color: #667085; font-size: 12px; }
.preview-warnings { margin-top: 12px; color: #9a6700; font-size: 12px; line-height: 20px; }
</style>
