<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useEmitt } from '@/utils/useEmitt'

const router = useRouter()

onMounted(() => {
  useEmitt().emitter.emit('analysis-assistant-toggle', true)
  router.replace('/chat/index')
})
</script>

<template>
  <div />
</template>
