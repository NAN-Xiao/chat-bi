<script setup lang="ts">
import KnowledgeReferenceList from '../KnowledgeReferenceList.vue'
import KnowledgeSqlExamples from '../KnowledgeSqlExamples.vue'
import KnowledgeStringList from '../KnowledgeStringList.vue'
import type { BusinessKnowledgePayload } from '../knowledgePayloadTypes'
import KnowledgeContentFrame from './KnowledgeContentFrame.vue'

withDefaults(defineProps<{ modelValue: BusinessKnowledgePayload; readonly?: boolean }>(), {
  readonly: false,
})
const emit = defineEmits<{ 'update:modelValue': [value: BusinessKnowledgePayload] }>()
</script>

<template>
  <KnowledgeContentFrame :index="1" title="业务术语与 SQL">
    <el-form label-position="top" :disabled="readonly" @submit.prevent>
      <el-form-item label="业务术语"
        ><el-input
          :model-value="modelValue.term"
          placeholder="例如：付费用户"
          @update:model-value="emit('update:modelValue', { ...modelValue, term: $event })"
      /></el-form-item>
      <KnowledgeStringList
        :model-value="modelValue.aliases"
        label="别名"
        placeholder="输入别名"
        @update:model-value="emit('update:modelValue', { ...modelValue, aliases: $event })"
      />
      <el-form-item label="定义"
        ><el-input
          :model-value="modelValue.definition"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          @update:model-value="emit('update:modelValue', { ...modelValue, definition: $event })"
      /></el-form-item>
      <el-form-item label="计算公式"
        ><el-input
          :model-value="modelValue.formula"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 5 }"
          @update:model-value="emit('update:modelValue', { ...modelValue, formula: $event })"
      /></el-form-item>
      <KnowledgeStringList
        :model-value="modelValue.constraints"
        label="口径约束"
        placeholder="输入一条约束"
        @update:model-value="emit('update:modelValue', { ...modelValue, constraints: $event })"
      />
      <KnowledgeReferenceList
        :model-value="modelValue.related_objects"
        label="关联表、字段或路径"
        @update:model-value="emit('update:modelValue', { ...modelValue, related_objects: $event })"
      />
      <KnowledgeSqlExamples
        :model-value="modelValue.examples"
        @update:model-value="emit('update:modelValue', { ...modelValue, examples: $event })"
      />
    </el-form>
  </KnowledgeContentFrame>
</template>
