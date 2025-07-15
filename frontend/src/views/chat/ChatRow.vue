<script setup lang="ts">
// import ChatBlock from './ChatBlock.vue'
// import ChatRecordFirst from './ChatRecordFirst.vue'
import { ChatInfo, type ChatMessage } from '@/api/chat.ts'
// import { UserFilled } from '@element-plus/icons-vue'
import logo_fold from '@/assets/LOGO-fold.svg'

withDefaults(
  defineProps<{
    msg: ChatMessage
    currentChat: ChatInfo
    hideAvatar?: boolean
  }>(),
  {
    hideAvatar: false,
  }
)
</script>

<template>
  <div class="chat-row" :class="{ 'right-to-left': msg.role === 'user' }">
    <el-avatar v-if="msg.role === 'assistant'" class="ai-avatar" shape="square">
      <el-icon>
        <logo_fold v-if="!hideAvatar" />
      </el-icon>
    </el-avatar>
    <div :class="{ 'row-full': msg.role === 'assistant' }">
      <slot></slot>
    </div>
  </div>
</template>

<style scoped lang="less">
.chat-row {
  display: flex;
  flex-direction: row;
  align-items: flex-start;
  gap: 8px;

  padding: 20px 0 0;
  max-width: 800px;
  width: 100%;

  &.right-to-left {
    flex-direction: row-reverse;
  }

  .row-full {
    flex: 1;
    width: 0;
  }

  .ai-avatar {
    font-size: 28px;
    background: transparent;
    width: 28px;
  }
}
</style>
