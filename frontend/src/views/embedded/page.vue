<template>
  <div class="sqlbot--embedded-page">
    <chat-component ref="chatRef" />
  </div>
</template>
<script setup lang="ts">
import ChatComponent from '@/views/chat/index.vue'
import { ref } from 'vue'

const chatRef = ref()
</script>

<style lang="less" scoped>
.sqlbot--embedded-page {
  width: 100%;
  height: 100%;
  position: relative;
  background: #f7f8fa;
}
</style>
