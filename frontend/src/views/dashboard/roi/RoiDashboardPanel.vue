<script setup lang="ts">
defineProps<{
  dashboardId: string
}>()
</script>

<template>
  <section class="roi-dashboard-panel"></section>
</template>

<style scoped>
.roi-dashboard-panel {
  width: 100%;
  min-height: 100%;
}
</style>
