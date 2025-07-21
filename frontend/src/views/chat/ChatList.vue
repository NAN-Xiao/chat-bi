<script setup lang="ts">
import { Delete, EditPen, MoreFilled } from '@element-plus/icons-vue'
import { type Chat, chatApi } from '@/api/chat.ts'
import { computed } from 'vue'
import dayjs from 'dayjs'
import { getDate } from '@/utils/utils.ts'
import { groupBy } from 'lodash-es'
import { useI18n } from 'vue-i18n'

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

const { t } = useI18n()

function groupByDate(chat: Chat) {
  const todayStart = dayjs(dayjs().format('YYYY-MM-DD') + ' 00:00:00').toDate()
  const todayEnd = dayjs(dayjs().format('YYYY-MM-DD') + ' 23:59:59').toDate()
  const weekStart = dayjs(dayjs().subtract(7, 'day').format('YYYY-MM-DD') + ' 00:00:00').toDate()

  const time = getDate(chat.create_time)

  if (time) {
    if (time >= todayStart && time <= todayEnd) {
      return t('qa.today')
    }
    if (time < todayStart && time >= weekStart) {
      return t('qa.week')
    }
    if (time < weekStart) {
      return t('qa.earlier')
    }
  }

  return t('qa.no_time')
}

const computedChatGroup = computed(() => {
  return groupBy(props.chatList, groupByDate)
})

const computedChatList = computed(() => {
  const _list = []
  if (computedChatGroup.value[t('qa.today')]) {
    _list.push({
      key: t('qa.today'),
      list: computedChatGroup.value[t('qa.today')],
    })
  }
  if (computedChatGroup.value[t('qa.week')]) {
    _list.push({
      key: t('qa.week'),
      list: computedChatGroup.value[t('qa.week')],
    })
  }
  if (computedChatGroup.value[t('qa.earlier')]) {
    _list.push({
      key: t('qa.earlier'),
      list: computedChatGroup.value[t('qa.earlier')],
    })
  }
  if (computedChatGroup.value[t('qa.no_time')]) {
    _list.push({
      key: t('qa.no_time'),
      list: computedChatGroup.value[t('qa.no_time')],
    })
  }

  return _list
})

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
      <div v-for="group in computedChatList" :key="group.key" class="group">
        <div class="group-title">{{ group.key }}</div>
        <template v-for="chat in group.list" :key="chat.id">
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
    </div>
  </el-scrollbar>
</template>

<style scoped lang="less">
.chat-list-inner {
  --hover-color: var(--ed-color-primary-light-9);
  --active-color: var(--hover-color);

  padding-left: 16px;
  padding-right: 16px;
  width: 100%;

  display: flex;
  flex-direction: column;

  gap: 16px;

  .group {
    display: flex;
    flex-direction: column;

    .group-title {
      padding: 0 8px;
      color: rgba(100, 106, 115, 1);
      line-height: 20px;
      font-weight: 500;
      font-size: 12px;

      margin-bottom: 4px;
    }
  }

  .chat-list-item {
    width: 100%;
    height: 40px;
    cursor: pointer;
    border-radius: 6px;
    line-height: 22px;
    font-size: 14px;
    font-weight: 400;

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
      background-color: rgba(31, 35, 41, 0.1);

      .icon-more {
        display: inline-flex;
        color: rgba(100, 106, 115, 1);

        &:hover {
          background-color: rgba(31, 35, 41, 0.1);
        }
      }
    }

    &.active {
      background-color: rgba(255, 255, 255, 1);
      font-weight: 500;
    }
  }
}
</style>
