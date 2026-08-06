<script setup lang="ts">
import { computed } from 'vue'
import type { KnowledgeApplicabilityState } from '@/api/knowledgeBase'

const props = defineProps<{
  state?: KnowledgeApplicabilityState | null
  loading?: boolean
  datasourceAvailable?: boolean
}>()

const tagType = computed(() => {
  if (!props.datasourceAvailable) return 'info'
  if (props.loading) return 'info'
  if (props.state?.status === 'VALID') return 'success'
  if (props.state?.status === 'INVALID' || props.state?.status === 'ERROR') return 'danger'
  return 'warning'
})

const label = computed(() => {
  if (!props.datasourceAvailable) return '无当前数据源'
  if (props.loading) return '检查中'
  return props.state?.status_text || '待检查'
})

const detail = computed(() => {
  if (!props.datasourceAvailable) return '当前工作空间没有可用数据源。'
  if (props.loading) return '正在读取当前数据源的知识适用性状态。'
  if (!props.state) return '当前数据源尚未完成适用性检查。'
  const counts = `对象引用 ${props.state.resolved_count}/${props.state.reference_count} 已解析`
  const warning = props.state.warnings?.[0]
  return warning ? `${counts}；${warning}` : counts
})
</script>

<template>
  <el-tooltip :content="detail" placement="top" :show-after="250">
    <el-tag size="small" :type="tagType">{{ label }}</el-tag>
  </el-tooltip>
</template>
