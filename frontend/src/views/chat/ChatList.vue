<script setup lang="ts">
import { Delete, EditPen, MoreFilled } from '@element-plus/icons-vue'
import { type Chat, chatApi } from '@/api/chat.ts'
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    currentChatId?: number
    chatList: Array<Chat>
    loading?: boolean
  }>(),
  {
    currentChatId: undefined,
    chatList: () => [],
    loading: false,
  }
)

const emits = defineEmits(['chatSelected', 'chatRenamed', 'chatDeleted', 'update:loading'])

const _loading = computed({
  get() {
    return props.loading
  },
  set(v) {
    emits('update:loading', v)
  },
})

function onClickHistory(chat: Chat) {
  emits('chatSelected', chat)
}

function handleCommand(command: string | number | object, chat: Chat) {
  if (chat && chat.id !== undefined) {
    switch (command) {
      case 'rename':
        ElMessageBox.prompt('Please enter new brief', 'Rename', {
          confirmButtonText: 'OK',
          cancelButtonText: 'Cancel',
          customStyle: { 'padding-left': 'unset', padding: 'var(--ed-messagebox-padding-primary)' },
          inputValue: chat.brief,
          inputValidator: (value: string) => {
            if (!value) return false
            if (value.trim().length == 0) return false
            return true
          },
        }).then(({ value }) => {
          _loading.value = true
          chatApi
            .renameChat(chat.id, value)
            .then((res) => {
              ElMessage({
                type: 'success',
                message: 'Successfully renamed chat',
              })
              emits('chatRenamed', { id: chat.id, brief: res })
            })
            .catch((err) => {
              ElMessage({
                type: 'error',
                message: err.message,
              })
              console.error(err)
            })
            .finally(() => {
              _loading.value = false
            })
        })

        break
      case 'delete':
        ElMessageBox.confirm('This action will permanently delete the chat. Continue?', 'Warning', {
          confirmButtonText: 'OK',
          cancelButtonText: 'Cancel',
          type: 'warning',
        }).then(() => {
          _loading.value = true
          chatApi
            .deleteChat(chat.id)
            .then((res) => {
              ElMessage({
                type: 'success',
                message: res,
              })
              emits('chatDeleted', chat.id)
            })
            .catch((err) => {
              ElMessage({
                type: 'error',
                message: err.message,
              })
              console.error(err)
            })
            .finally(() => {
              _loading.value = false
            })
        })

        break
    }
  }
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
          <el-button class="icon-more" link type="primary" @click.stop>
            <el-dropdown trigger="click" @command="(cmd: any) => handleCommand(cmd, chat)">
              <el-icon>
                <MoreFilled />
              </el-icon>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item :icon="EditPen" command="rename">Rename</el-dropdown-item>
                  <el-dropdown-item :icon="Delete" command="delete">Delete</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </el-button>
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
