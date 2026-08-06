<script setup lang="ts">
import { Delete, Plus } from '@element-plus/icons-vue'

interface EventParameter {
  name: string
  display_name?: string
  data_type: string
  required?: boolean
  description?: string
}
const props = withDefaults(defineProps<{ modelValue?: EventParameter[] }>(), { modelValue: () => [] })
const emit = defineEmits<{ 'update:modelValue': [value: EventParameter[]] }>()
const dataTypes = ['string', 'number', 'integer', 'boolean', 'json']

function update(index: number, key: keyof EventParameter, value: unknown) {
  emit(
    'update:modelValue',
    props.modelValue.map((item, itemIndex) =>
      itemIndex === index ? { ...item, [key]: value } : item
    )
  )
}
function add() {
  emit('update:modelValue', [
    ...props.modelValue,
    { name: '', display_name: '', data_type: 'string', required: false, description: '' },
  ])
}
function remove(index: number) {
  emit('update:modelValue', props.modelValue.filter((_, itemIndex) => itemIndex !== index))
}
</script>

<template>
  <div class="parameters-editor">
    <div class="editor-label">事件参数</div>
    <div v-for="(item, index) in modelValue" :key="index" class="parameter-row">
      <el-input :model-value="item.name" placeholder="参数名" @update:model-value="update(index, 'name', $event)" />
      <el-input :model-value="item.display_name || ''" placeholder="展示名" @update:model-value="update(index, 'display_name', $event)" />
      <el-select :model-value="item.data_type" @update:model-value="update(index, 'data_type', $event)">
        <el-option v-for="type in dataTypes" :key="type" :label="type" :value="type" />
      </el-select>
      <el-switch :model-value="!!item.required" inline-prompt active-text="必填" inactive-text="可选" @update:model-value="update(index, 'required', $event)" />
      <el-input :model-value="item.description || ''" placeholder="参数说明" @update:model-value="update(index, 'description', $event)" />
      <el-button text :icon="Delete" aria-label="删除" @click="remove(index)" />
    </div>
    <el-button text type="primary" :icon="Plus" @click="add">添加参数</el-button>
  </div>
</template>

<style scoped lang="less">
.parameters-editor { width: 100%; }
.editor-label { margin-bottom: 8px; color: #475467; font-size: 13px; font-weight: 500; }
.parameter-row {
  display: grid;
  grid-template-columns: 1fr 1fr 110px 72px 1.4fr 28px;
  gap: 6px;
  align-items: center;
  margin-bottom: 8px;
}
@media (max-width: 900px) { .parameter-row { grid-template-columns: 1fr 1fr; } }
</style>
