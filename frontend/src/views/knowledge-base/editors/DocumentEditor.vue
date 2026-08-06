<script setup lang="ts">
import KnowledgeReferenceList from '../KnowledgeReferenceList.vue'
import KnowledgeStringList from '../KnowledgeStringList.vue'
import type { DocumentPayload } from '../knowledgePayloadTypes'

withDefaults(defineProps<{ modelValue: DocumentPayload; readonly?: boolean }>(), { readonly: false })
const emit = defineEmits<{ 'update:modelValue': [value: DocumentPayload] }>()
</script>

<template>
  <div class="document-editor">
    <el-form label-position="top" :disabled="readonly" @submit.prevent>
      <el-form-item label="Markdown 内容">
        <el-input
          :model-value="modelValue.markdown"
          type="textarea"
          :autosize="{ minRows: 12, maxRows: 24 }"
          placeholder="输入可检索的知识内容"
          @update:model-value="emit('update:modelValue', { ...modelValue, markdown: $event })"
        />
      </el-form-item>
      <el-form-item>
        <el-switch
          :model-value="modelValue.datasource_neutral"
          active-text="与数据源无关"
          inactive-text="绑定当前数据源"
          @update:model-value="emit('update:modelValue', { ...modelValue, datasource_neutral: $event })"
        />
      </el-form-item>
      <KnowledgeStringList
        :model-value="modelValue.tags"
        label="标签"
        placeholder="输入标签"
        @update:model-value="emit('update:modelValue', { ...modelValue, tags: $event })"
      />
      <KnowledgeReferenceList
        v-if="!modelValue.datasource_neutral"
        :model-value="modelValue.object_references"
        @update:model-value="emit('update:modelValue', { ...modelValue, object_references: $event })"
      />
    </el-form>
  </div>
</template>

<style scoped lang="less">
.document-editor { width: 100%; }
</style>
