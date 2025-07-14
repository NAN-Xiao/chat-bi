<script setup lang="ts">
import type { ChatMessage } from '@/api/chat.ts'

defineProps<{
  msg?: ChatMessage
}>()
</script>

<template>
  <div class="chat-block-outer">
    <div class="chat-block">
      <slot>
        <div class="chat-block-content">
          <!-- <div v-dompurify-html="msg?.content"></div> -->
          <div v-if="msg?.role === 'user'" v-html="msg.content"></div>
          <div v-else v-dompurify-html="msg?.content"></div>
        </div>
      </slot>
    </div>
    <div class="chat-block-footer">
      <slot name="footer"></slot>
    </div>
  </div>
</template>

<style scoped lang="less">
.chat-block-outer {
  .chat-block {
    border-radius: 2px;
    background-color: white;
    word-wrap: break-word;
    white-space: pre-wrap;

    .chat-block-content {
      padding: 12px;
    }
  }

  .chat-block-footer {
  }
}
</style>
