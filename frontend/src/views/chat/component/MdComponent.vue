<script setup lang="ts">
import md from '@/utils/markdown.ts'
import 'highlight.js/styles/github-dark-dimmed.css'
import { computed } from 'vue'

const props = defineProps<{
  message?: string
}>()

const renderMd = computed(() => {
  return md.render(props.message ?? '')
})
</script>

<template>
  <div v-dompurify-html="renderMd"></div>
</template>

<style scoped lang="less"></style>
