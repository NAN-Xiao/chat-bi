<script setup lang="ts">
import { Delete, Plus } from '@element-plus/icons-vue'

interface Reference {
  object_type: string
  schema?: string | null
  table?: string | null
  field?: string | null
  json_path?: string | null
  event_name?: string | null
  event_property_key?: string | null
}

const props = withDefaults(
  defineProps<{ modelValue?: Reference[]; label?: string }>(),
  { modelValue: () => [], label: '物理对象引用' }
)
const emit = defineEmits<{ 'update:modelValue': [value: Reference[]] }>()
const types = [
  { label: '表', value: 'TABLE' },
  { label: '字段', value: 'FIELD' },
  { label: 'JSON 路径', value: 'JSON_PATH' },
  { label: '事件', value: 'EVENT' },
  { label: '事件参数', value: 'EVENT_PROPERTY' },
]

function update(index: number, key: keyof Reference, value: unknown) {
  const next = props.modelValue.map((item, itemIndex) =>
    itemIndex === index ? { ...item, [key]: value } : item
  )
  emit('update:modelValue', next)
}
function add() {
  emit('update:modelValue', [...props.modelValue, { object_type: 'TABLE', table: '' }])
}
function remove(index: number) {
  emit('update:modelValue', props.modelValue.filter((_, itemIndex) => itemIndex !== index))
}
</script>

<template>
  <div class="reference-editor">
    <div class="editor-label">{{ label }}</div>
    <div v-for="(item, index) in modelValue" :key="index" class="reference-row">
      <el-select
        :model-value="item.object_type"
        class="reference-type"
        @update:model-value="update(index, 'object_type', $event)"
      >
        <el-option v-for="type in types" :key="type.value" v-bind="type" />
      </el-select>
      <el-input
        :model-value="item.schema || ''"
        placeholder="schema"
        @update:model-value="update(index, 'schema', $event)"
      />
      <el-input
        :model-value="item.table || ''"
        placeholder="物理表"
        @update:model-value="update(index, 'table', $event)"
      />
      <el-input
        :model-value="item.field || ''"
        placeholder="字段"
        @update:model-value="update(index, 'field', $event)"
      />
      <el-input
        :model-value="item.json_path || ''"
        placeholder="JSON 路径"
        @update:model-value="update(index, 'json_path', $event)"
      />
      <el-button text :icon="Delete" aria-label="删除" @click="remove(index)" />
    </div>
    <el-button text type="primary" :icon="Plus" @click="add">添加引用</el-button>
  </div>
</template>

<style scoped lang="less">
.reference-editor {
  width: 100%;
}
.editor-label {
  margin-bottom: 8px;
  color: #475467;
  font-size: 13px;
  font-weight: 500;
}
.reference-row {
  display: grid;
  grid-template-columns: 104px 1fr 1fr 1fr 1fr 28px;
  gap: 6px;
  margin-bottom: 8px;
  align-items: center;
}
.reference-type {
  width: 104px;
}
@media (max-width: 900px) {
  .reference-row {
    grid-template-columns: 1fr 1fr;
  }
  .reference-type {
    width: 100%;
  }
}
</style>
