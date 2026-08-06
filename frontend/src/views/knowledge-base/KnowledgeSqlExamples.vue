<script setup lang="ts">
import { Delete, Plus } from '@element-plus/icons-vue'

interface SqlExample { name: string; question: string; sql: string; dialect?: string; notes?: string }
const props = withDefaults(defineProps<{ modelValue?: SqlExample[] }>(), { modelValue: () => [] })
const emit = defineEmits<{ 'update:modelValue': [value: SqlExample[]] }>()

function update(index: number, key: keyof SqlExample, value: unknown) {
  emit('update:modelValue', props.modelValue.map((item, itemIndex) => itemIndex === index ? { ...item, [key]: value } : item))
}
function add() {
  emit('update:modelValue', [...props.modelValue, { name: '', question: '', sql: '', dialect: '', notes: '' }])
}
function remove(index: number) { emit('update:modelValue', props.modelValue.filter((_, itemIndex) => itemIndex !== index)) }
</script>

<template>
  <div class="sql-examples-editor">
    <div class="editor-label">SQL 示例</div>
    <div v-for="(item, index) in modelValue" :key="index" class="example-row">
      <el-input :model-value="item.name" placeholder="示例名称" @update:model-value="update(index, 'name', $event)" />
      <el-input :model-value="item.question" placeholder="业务问题" @update:model-value="update(index, 'question', $event)" />
      <el-input :model-value="item.sql" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" placeholder="SQL" @update:model-value="update(index, 'sql', $event)" />
      <el-input :model-value="item.dialect || ''" placeholder="方言（可选）" @update:model-value="update(index, 'dialect', $event)" />
      <el-input :model-value="item.notes || ''" placeholder="说明（可选）" @update:model-value="update(index, 'notes', $event)" />
      <el-button text :icon="Delete" aria-label="删除" @click="remove(index)" />
    </div>
    <el-button text type="primary" :icon="Plus" @click="add">添加 SQL 示例</el-button>
  </div>
</template>

<style scoped lang="less">
.sql-examples-editor { width: 100%; }
.editor-label { margin-bottom: 8px; color: #475467; font-size: 13px; font-weight: 500; }
.example-row { display: grid; grid-template-columns: 1fr 1.2fr 2fr 110px 1.2fr 28px; gap: 6px; align-items: start; margin-bottom: 8px; }
@media (max-width: 900px) { .example-row { grid-template-columns: 1fr 1fr; } }
</style>
