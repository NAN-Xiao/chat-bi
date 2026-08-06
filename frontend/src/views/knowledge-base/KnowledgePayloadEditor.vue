<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { cloneDeep } from 'lodash-es'
import KnowledgeEventParameters from './KnowledgeEventParameters.vue'
import KnowledgeReferenceList from './KnowledgeReferenceList.vue'
import KnowledgeSqlExamples from './KnowledgeSqlExamples.vue'
import KnowledgeStringList from './KnowledgeStringList.vue'

type KnowledgePayload = Record<string, any>
const props = withDefaults(
  defineProps<{ modelValue: KnowledgePayload; readonly?: boolean }>(),
  { readonly: false }
)
const emit = defineEmits<{ 'update:modelValue': [value: KnowledgePayload] }>()

const local = ref<KnowledgePayload>(cloneDeep(props.modelValue))
const mappingText = ref('')
const typeOptions = [
  { label: '普通文档', value: 'DOCUMENT' },
  { label: '业务知识（术语 + SQL 示例）', value: 'BUSINESS' },
  { label: '事件与事件参数', value: 'EVENT' },
  { label: 'JSON 字段与路径', value: 'JSON_FIELD' },
]
const type = computed(() => String(local.value.knowledge_type || 'DOCUMENT'))

watch(
  () => props.modelValue,
  (value) => {
    local.value = cloneDeep(value || {})
    mappingText.value = stringifyMapping(local.value.value_mappings)
  },
  { deep: true, immediate: true }
)
watch(local, (value) => emit('update:modelValue', cloneDeep(value)), { deep: true })

function stringifyMapping(value: unknown) {
  try { return value && typeof value === 'object' ? JSON.stringify(value, null, 2) : '' } catch { return '' }
}
function updateType(value: string) {
  local.value = defaultPayload(value)
}
function parseMappings(value: string) {
  mappingText.value = value
  if (!value.trim()) { local.value.value_mappings = {}; return }
  try {
    const parsed = JSON.parse(value)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) local.value.value_mappings = parsed
  } catch {
    // Keep the editable text until the user completes valid JSON.
  }
}
function defaultPayload(knowledgeType: string): KnowledgePayload {
  if (knowledgeType === 'BUSINESS') return { knowledge_type: 'BUSINESS', term: '', aliases: [], definition: '', formula: '', constraints: [], related_objects: [], examples: [] }
  if (knowledgeType === 'EVENT') return { knowledge_type: 'EVENT', event_name: '', display_name: '', aliases: [], description: '', table_name: '', event_name_field: '', event_time_field: '', parameters: [] }
  if (knowledgeType === 'JSON_FIELD') return { knowledge_type: 'JSON_FIELD', schema_name: '', table_name: '', source_field: '', json_path: '$.', field_name: '', display_name: '', data_type: 'string', expression: '', aliases: [], description: '', value_mappings: {} }
  return { knowledge_type: 'DOCUMENT', markdown: '', tags: [], datasource_neutral: false, object_references: [] }
}

defineExpose({ defaultPayload })
</script>

<template>
  <div class="payload-editor">
    <el-form label-position="top" :disabled="readonly" @submit.prevent>
      <el-form-item label="知识类型">
        <el-select :model-value="type" @update:model-value="updateType">
          <el-option v-for="item in typeOptions" :key="item.value" v-bind="item" />
        </el-select>
      </el-form-item>

      <template v-if="type === 'DOCUMENT'">
        <el-form-item label="Markdown 内容">
          <el-input v-model="local.markdown" type="textarea" :autosize="{ minRows: 12, maxRows: 24 }" placeholder="输入可检索的知识内容" />
        </el-form-item>
        <el-form-item>
          <el-switch v-model="local.datasource_neutral" active-text="与数据源无关" inactive-text="绑定当前数据源" />
        </el-form-item>
        <KnowledgeStringList v-model="local.tags" label="标签" placeholder="输入标签" />
        <KnowledgeReferenceList v-if="!local.datasource_neutral" v-model="local.object_references" />
      </template>

      <template v-else-if="type === 'BUSINESS'">
        <el-form-item label="业务术语"><el-input v-model="local.term" placeholder="例如：付费用户" /></el-form-item>
        <KnowledgeStringList v-model="local.aliases" label="别名" placeholder="输入别名" />
        <el-form-item label="定义"><el-input v-model="local.definition" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" /></el-form-item>
        <el-form-item label="计算公式"><el-input v-model="local.formula" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" /></el-form-item>
        <KnowledgeStringList v-model="local.constraints" label="口径约束" placeholder="输入一条约束" />
        <KnowledgeReferenceList v-model="local.related_objects" label="关联表、字段或路径" />
        <KnowledgeSqlExamples v-model="local.examples" />
      </template>

      <template v-else-if="type === 'EVENT'">
        <el-form-item label="事件名称"><el-input v-model="local.event_name" /></el-form-item>
        <el-form-item label="展示名称"><el-input v-model="local.display_name" /></el-form-item>
        <KnowledgeStringList v-model="local.aliases" label="别名" />
        <el-form-item label="事件说明"><el-input v-model="local.description" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" /></el-form-item>
        <el-form-item label="物理表"><el-input v-model="local.table_name" /></el-form-item>
        <div class="two-columns">
          <el-form-item label="事件名字段"><el-input v-model="local.event_name_field" /></el-form-item>
          <el-form-item label="事件时间字段"><el-input v-model="local.event_time_field" /></el-form-item>
        </div>
        <KnowledgeEventParameters v-model="local.parameters" />
      </template>

      <template v-else>
        <div class="two-columns">
          <el-form-item label="Schema"><el-input v-model="local.schema_name" /></el-form-item>
          <el-form-item label="物理表"><el-input v-model="local.table_name" /></el-form-item>
          <el-form-item label="源字段"><el-input v-model="local.source_field" /></el-form-item>
          <el-form-item label="JSON 路径"><el-input v-model="local.json_path" placeholder="$.payload.amount" /></el-form-item>
          <el-form-item label="语义字段名"><el-input v-model="local.field_name" /></el-form-item>
          <el-form-item label="展示名称"><el-input v-model="local.display_name" /></el-form-item>
          <el-form-item label="数据类型"><el-input v-model="local.data_type" /></el-form-item>
          <el-form-item label="SQL 表达式"><el-input v-model="local.expression" /></el-form-item>
        </div>
        <KnowledgeStringList v-model="local.aliases" label="别名" />
        <el-form-item label="字段说明"><el-input v-model="local.description" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" /></el-form-item>
        <el-form-item label="值映射（JSON）">
          <el-input :model-value="mappingText" type="textarea" :autosize="{ minRows: 4, maxRows: 10 }" placeholder="{ &quot;1&quot;: &quot;成功&quot; }" @update:model-value="parseMappings" />
        </el-form-item>
      </template>
    </el-form>
  </div>
</template>

<style scoped lang="less">
.payload-editor { width: 100%; }
.payload-editor :deep(.el-select) { width: 100%; }
.two-columns { display: grid; grid-template-columns: 1fr 1fr; gap: 0 12px; }
@media (max-width: 680px) { .two-columns { grid-template-columns: 1fr; } }
</style>
