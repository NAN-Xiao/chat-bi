<script setup lang="ts">
import KnowledgeEventParameters from '../KnowledgeEventParameters.vue'
import KnowledgeStringList from '../KnowledgeStringList.vue'
import type { EventKnowledgePayload } from '../knowledgePayloadTypes'

withDefaults(defineProps<{ modelValue: EventKnowledgePayload; readonly?: boolean }>(), { readonly: false })
const emit = defineEmits<{ 'update:modelValue': [value: EventKnowledgePayload] }>()
</script>

<template>
  <el-form label-position="top" :disabled="readonly" @submit.prevent>
    <el-form-item label="事件名称"><el-input :model-value="modelValue.event_name" @update:model-value="emit('update:modelValue', { ...modelValue, event_name: $event })" /></el-form-item>
    <el-form-item label="展示名称"><el-input :model-value="modelValue.display_name" @update:model-value="emit('update:modelValue', { ...modelValue, display_name: $event })" /></el-form-item>
    <KnowledgeStringList :model-value="modelValue.aliases" label="别名" @update:model-value="emit('update:modelValue', { ...modelValue, aliases: $event })" />
    <el-form-item label="事件说明"><el-input :model-value="modelValue.description" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" @update:model-value="emit('update:modelValue', { ...modelValue, description: $event })" /></el-form-item>
    <el-form-item label="物理表"><el-input :model-value="modelValue.table_name" @update:model-value="emit('update:modelValue', { ...modelValue, table_name: $event })" /></el-form-item>
    <div class="two-columns">
      <el-form-item label="事件名字段"><el-input :model-value="modelValue.event_name_field" @update:model-value="emit('update:modelValue', { ...modelValue, event_name_field: $event })" /></el-form-item>
      <el-form-item label="事件时间字段"><el-input :model-value="modelValue.event_time_field" @update:model-value="emit('update:modelValue', { ...modelValue, event_time_field: $event })" /></el-form-item>
    </div>
    <KnowledgeEventParameters :model-value="modelValue.parameters" @update:model-value="emit('update:modelValue', { ...modelValue, parameters: $event })" />
  </el-form>
</template>

<style scoped lang="less">
.two-columns { display: grid; grid-template-columns: 1fr 1fr; gap: 0 12px; }
@media (max-width: 680px) { .two-columns { grid-template-columns: 1fr; } }
</style>
