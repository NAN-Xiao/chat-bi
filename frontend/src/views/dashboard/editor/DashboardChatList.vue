<script setup lang="ts">
import { type Chat } from '@/api/chat.ts'

withDefaults(
  defineProps<{
    currentChatId?: number
    chatList: Array<Chat>
  }>(),
  {
    currentChatId: undefined,
    chatList: () => [],
  }
)

const emits = defineEmits(['chatSelected'])

function onClickHistory(chat: Chat) {
  emits('chatSelected', chat)
}
</script>

<template>
  <el-scrollbar ref="chatListRef">
    <div class="chat-list-inner">
      <template v-for="chat in chatList" :key="chat.id">
        <div
          class="chat-list-item"
          :class="{ active: currentChatId === chat.id }"
          @click="onClickHistory(chat)"
        >
          <span class="title">{{ chat.brief ?? 'Untitled' }}</span>
        </div>
      </template>
    </div>
  </el-scrollbar>
</template>

<style scoped lang="less">
.chat-list-inner {
  --hover-color: var(--ed-color-primary-light-9);
  --active-color: var(--hover-color);

  padding-left: 14px;
  padding-right: 14px;
  width: 100%;

  display: flex;
  flex-direction: column;

  gap: 8px;

  .chat-list-item {
    width: 100%;
    height: 42px;
    cursor: pointer;
    border-radius: 6px;
    line-height: 1em;

    display: flex;
    align-items: center;
    padding: 8px;

    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;

    .title {
      flex: 1;
      width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .icon-more {
      margin-left: auto;
      display: none;

      min-width: unset;
    }

    &:hover {
      background-color: var(--hover-color);

      .icon-more {
        display: inline-flex;
      }
    }

    &.active {
      background-color: var(--active-color);
    }
  }
}
</style>
