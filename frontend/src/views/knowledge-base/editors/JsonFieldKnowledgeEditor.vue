<script setup lang="ts">
import { ref, watch } from 'vue'
import KnowledgeStringList from '../KnowledgeStringList.vue'
import type { JsonFieldKnowledgePayload } from '../knowledgePayloadTypes'
import KnowledgeContentFrame from './KnowledgeContentFrame.vue'

const props = withDefaults(
  defineProps<{ modelValue: JsonFieldKnowledgePayload; readonly?: boolean }>(),
  { readonly: false }
)
const emit = defineEmits<{ 'update:modelValue': [value: JsonFieldKnowledgePayload] }>()
const mappingText = ref('')

function stringifyMapping(value: unknown) {
  try {
    return value && typeof value === 'object' ? JSON.stringify(value, null, 2) : ''
  } catch {
    return ''
  }
}
function parseMappings(value: string) {
  mappingText.value = value
  if (!value.trim()) {
    emit('update:modelValue', { ...props.modelValue, value_mappings: {} })
    return
  }
  try {
    const parsed = JSON.parse(value)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      emit('update:modelValue', { ...props.modelValue, value_mappings: parsed })
    }
  } catch {
    // Keep editable text until JSON is complete.
  }
}
watch(
  () => props.modelValue.value_mappings,
  (value) => {
    mappingText.value = stringifyMapping(value)
  },
  { deep: true, immediate: true }
)
</script>

<template>
  <KnowledgeContentFrame :index="1" title="JSON 字段">
    <el-form label-position="top" :disabled="readonly" @submit.prevent>
      <div class="two-columns">
        <el-form-item label="Schema"
          ><el-input
            :model-value="modelValue.schema_name"
            @update:model-value="emit('update:modelValue', { ...modelValue, schema_name: $event })"
        /></el-form-item>
        <el-form-item label="物理表"
          ><el-input
            :model-value="modelValue.table_name"
            @update:model-value="emit('update:modelValue', { ...modelValue, table_name: $event })"
        /></el-form-item>
        <el-form-item label="源字段"
          ><el-input
            :model-value="modelValue.source_field"
            @update:model-value="
              emit('update:modelValue', { ...modelValue, source_field: $event })
            "
        /></el-form-item>
        <el-form-item label="JSON 路径"
          ><el-input
            :model-value="modelValue.json_path"
            placeholder="$.payload.amount"
            @update:model-value="emit('update:modelValue', { ...modelValue, json_path: $event })"
        /></el-form-item>
        <el-form-item label="语义字段名"
          ><el-input
            :model-value="modelValue.field_name"
            @update:model-value="emit('update:modelValue', { ...modelValue, field_name: $event })"
        /></el-form-item>
        <el-form-item label="展示名称"
          ><el-input
            :model-value="modelValue.display_name"
            @update:model-value="
              emit('update:modelValue', { ...modelValue, display_name: $event })
            "
        /></el-form-item>
        <el-form-item label="数据类型"
          ><el-input
            :model-value="modelValue.data_type"
            @update:model-value="emit('update:modelValue', { ...modelValue, data_type: $event })"
        /></el-form-item>
        <el-form-item label="SQL 表达式"
          ><el-input
            :model-value="modelValue.expression"
            @update:model-value="emit('update:modelValue', { ...modelValue, expression: $event })"
        /></el-form-item>
      </div>
      <KnowledgeStringList
        :model-value="modelValue.aliases"
        label="别名"
        @update:model-value="emit('update:modelValue', { ...modelValue, aliases: $event })"
      />
      <el-form-item label="字段说明"
        ><el-input
          :model-value="modelValue.description"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          @update:model-value="emit('update:modelValue', { ...modelValue, description: $event })"
      /></el-form-item>
      <el-form-item label="值映射（JSON）">
        <el-input
          :model-value="mappingText"
          type="textarea"
          :autosize="{ minRows: 4, maxRows: 10 }"
          placeholder='{ "1": "成功" }'
          @update:model-value="parseMappings"
        />
      </el-form-item>
    </el-form>
  </KnowledgeContentFrame>
</template>

<style scoped lang="less">
.two-columns {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 12px;
}
@media (max-width: 680px) {
  .two-columns {
    grid-template-columns: 1fr;
  }
}
</style>
