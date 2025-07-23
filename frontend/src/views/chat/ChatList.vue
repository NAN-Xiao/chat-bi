<script setup lang="ts">
import icon_more_outlined from '@/assets/svg/icon_more_outlined.svg'
import icon_expand_down_filled from '@/assets/embedded/icon_expand-down_filled.svg'
import rename from '@/assets/svg/icon_rename_outlined.svg'
import delIcon from '@/assets/svg/icon_delete.svg'
import { type Chat, chatApi } from '@/api/chat.ts'
import { computed, ref } from 'vue'
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

const expandMap = ref({
  [t('qa.today')]: true,
  [t('qa.week')]: true,
  [t('qa.earlier')]: true,
  [t('qa.no_time')]: true,
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
        <div
          class="group-title"
          style="cursor: pointer"
          @click="expandMap[group.key] = !expandMap[group.key]"
        >
          <el-icon :class="!expandMap[group.key] && 'expand'" style="margin-right: 8px" size="10">
            <icon_expand_down_filled></icon_expand_down_filled>
          </el-icon>
          {{ group.key }}
        </div>
        <template v-for="chat in group.list" :key="chat.id">
          <div
            class="chat-list-item"
            :class="{ active: currentChatId === chat.id, hide: !expandMap[group.key] }"
            @click="onClickHistory(chat)"
          >
            <span class="title">{{ chat.brief ?? 'Untitled' }}</span>
            <el-popover :teleported="false" popper-class="popover-card" placement="bottom">
              <template #reference>
                <el-icon class="more" size="16" style="margin-left: auto" @click.stop>
                  <icon_more_outlined></icon_more_outlined>
                </el-icon>
              </template>
              <div class="content">
                <div class="item" @click.stop="handleCommand('rename', chat)">
                  <el-icon size="16">
                    <rename></rename>
                  </el-icon>
                  {{ $t('dashboard.rename') }}
                </div>
                <div class="item" @click.stop="handleCommand('delete', chat)">
                  <el-icon size="16">
                    <delIcon></delIcon>
                  </el-icon>
                  {{ $t('dashboard.delete') }}
                </div>
              </div>
            </el-popover>
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

      .expand {
        transform: rotate(-90deg);
      }
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

    .more {
      display: none;
      &.ed-icon {
        position: relative;
        cursor: pointer;
        margin-top: 4px;

        &::after {
          content: '';
          background-color: #1f23291a;
          position: absolute;
          border-radius: 6px;
          width: 24px;
          height: 24px;
          transform: translate(-50%, -50%);
          top: 50%;
          left: 50%;
          display: none;
        }

        &:hover {
          &::after {
            display: block;
          }
        }
      }
    }

    &:hover {
      background-color: rgba(31, 35, 41, 0.1);

      .more {
        display: block;
      }
    }

    &.active {
      background-color: rgba(255, 255, 255, 1);
      font-weight: 500;
    }

    &.hide {
      display: none;
    }
  }
}
</style>

<style lang="less">
.popover-card.popover-card.popover-card {
  box-shadow: 0px 4px 8px 0px #1f23291a;
  border-radius: 4px;
  border: 1px solid #dee0e3;
  width: 120px !important;
  min-width: 120px !important;
  padding: 0;
  .content {
    position: relative;
    &::after {
      position: absolute;
      content: '';
      top: 40px;
      left: 0;
      width: 100%;
      height: 1px;
      background: #dee0e3;
    }
    .item {
      position: relative;
      padding-left: 12px;
      height: 40px;
      display: flex;
      align-items: center;
      cursor: pointer;
      .ed-icon {
        margin-right: 8px;
        color: #646a73;
      }
      &:hover {
        &::after {
          display: block;
        }
      }

      &::after {
        content: '';
        width: 112px;
        height: 32px;
        border-radius: 4px;
        position: absolute;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        background: #1f23291a;
        display: none;
      }
    }
  }
}
</style>
