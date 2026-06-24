<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useEmitt } from '@/utils/useEmitt'
import { useUserStore } from '@/stores/user'
import { resolveBusinessDashboardLandingTarget } from '@/utils/dashboardLanding'

const router = useRouter()
const userStore = useUserStore()

onMounted(async () => {
  useEmitt().emitter.emit('analysis-assistant-toggle', true)
  router.replace(await resolveBusinessDashboardLandingTarget(userStore))
})
</script>

<template>
  <div />
</template>
