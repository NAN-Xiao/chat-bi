<script setup lang="ts">

import type {ChatMessage} from "@/api/chat.ts";

defineProps<{
  msg?: ChatMessage
}>()

</script>

<template>
  <div class="chat-block">
    <slot>
      <div v-html="msg?.content"></div>
    </slot>
  </div>
</template>

<style scoped lang="less">
.chat-block {
  border-radius: 2px;
  background-color: white;
  padding: 12px;
  word-wrap: break-word;
  white-space: pre-wrap;
}
</style>