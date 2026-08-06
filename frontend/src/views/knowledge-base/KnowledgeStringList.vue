<script setup lang="ts">
import { Delete, Plus } from '@element-plus/icons-vue'

const props = withDefaults(
  defineProps<{
    modelValue?: string[]
    label: string
    placeholder?: string
  }>(),
  { modelValue: () => [], placeholder: '' }
)
const emit = defineEmits<{ 'update:modelValue': [value: string[]] }>()

function update(index: number, value: string) {
  const next = [...props.modelValue]
  next[index] = value
  emit('update:modelValue', next)
}

function add() {
  emit('update:modelValue', [...props.modelValue, ''])
}

function remove(index: number) {
  emit('update:modelValue', props.modelValue.filter((_, itemIndex) => itemIndex !== index))
}
</script>

<template>
  <div class="knowledge-list-editor">
    <div class="editor-label">{{ label }}</div>
    <div v-for="(item, index) in modelValue" :key="index" class="list-row">
      <el-input
        :model-value="item"
        :placeholder="placeholder"
        @update:model-value="update(index, $event)"
      />
      <el-button text :icon="Delete" aria-label="删除" @click="remove(index)" />
    </div>
    <el-button text type="primary" :icon="Plus" @click="add">添加一条</el-button>
  </div>
</template>

<style scoped lang="less">
.knowledge-list-editor {
  width: 100%;
}
.editor-label {
  margin-bottom: 8px;
  color: #475467;
  font-size: 13px;
  font-weight: 500;
}
.list-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.list-row .el-input {
  flex: 1;
}
</style>
