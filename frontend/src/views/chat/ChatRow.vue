<script setup lang="ts">
import ChatBlock from './ChatBlock.vue'
import ChatRecordFirst from './ChatRecordFirst.vue'
import { ChatInfo, type ChatMessage } from '@/api/chat.ts'
import { UserFilled } from '@element-plus/icons-vue'

withDefaults(
  defineProps<{
    msg: ChatMessage
    currentChat: ChatInfo
  }>(),
  {}
)
</script>

<template>
  <div class="chat-row" :class="{ 'right-to-left': msg.role === 'user' }">
    <el-avatar v-if="msg.role === 'assistant'" class="ai-avatar" shape="square">SQLBot</el-avatar>
    <el-avatar v-if="msg.role === 'user'" class="user-avatar" shape="square">
      <el-icon>
        <UserFilled />
      </el-icon>
    </el-avatar>
    <ChatBlock v-if="!msg.first_chat" :msg="msg" :class="{ 'row-full': msg.role === 'assistant' }">
      <slot></slot>
      <template #footer>
        <slot name="footer"></slot>
      </template>
    </ChatBlock>
    <ChatRecordFirst v-else :current-chat="currentChat" :msg="msg" />
  </div>
</template>

<style scoped lang="less">
.chat-row {
  display: flex;
  flex-direction: row;
  align-items: flex-start;
  gap: 8px;

  padding: 20px 20px 0;

  &.right-to-left {
    flex-direction: row-reverse;
  }

  .row-full {
    flex: 1;
    width: 0;
  }
}

.ai-avatar {
  background: var(--el-color-primary);
}

.user-avatar {
  background: var(--ed-color-primary);
}
</style>
