<script setup lang="ts">
import { Search } from '@element-plus/icons-vue'
import ChatList from '@/views/chat/ChatList.vue'
import { useI18n } from 'vue-i18n'
import { computed, nextTick, ref } from 'vue'
import { Chat, chatApi, ChatInfo } from '@/api/chat.ts'
import { filter, includes } from 'lodash-es'
import ChatCreator from '@/views/chat/ChatCreator.vue'
import { useAssistantStore } from '@/stores/assistant'
import icon_sidebar_outlined from '@/assets/svg/icon_sidebar_outlined.svg'
import icon_new_chat_outlined from '@/assets/svg/icon_new_chat_outlined.svg'
import { useUserStore } from '@/stores/user'
import router from '@/router'
const userStore = useUserStore()
const props = withDefaults(
  defineProps<{
    inPopover?: boolean
    chatList?: Array<ChatInfo>
    currentChatId?: number
    currentChat?: ChatInfo
    loading?: boolean
    appName?: string
  }>(),
  {
    chatList: () => [],
    currentChatId: undefined,
    currentChat: () => new ChatInfo(),
    loading: false,
    inPopover: false,
    appName: '',
  }
)

const emits = defineEmits([
  'goEmpty',
  'onChatCreated',
  'onClickHistory',
  'onChatDeleted',
  'onChatRenamed',
  'onClickSideBarBtn',
  'update:loading',
  'update:chatList',
  'update:currentChat',
  'update:currentChatId',
])

const assistantStore = useAssistantStore()
const isCompletePage = computed(() => !assistantStore.getAssistant || assistantStore.getEmbedded)

const selectAssistantDs = computed(() => {
  return assistantStore.getAssistant && !assistantStore.getAutoDs
})

const search = ref<string>()

const _currentChatId = computed({
  get() {
    return props.currentChatId
  },
  set(v) {
    emits('update:currentChatId', v)
  },
})
const _currentChat = computed({
  get() {
    return props.currentChat
  },
  set(v) {
    emits('update:currentChat', v)
  },
})

const _chatList = computed({
  get() {
    return props.chatList
  },
  set(v) {
    emits('update:chatList', v)
  },
})

const computedChatList = computed<Array<ChatInfo>>(() => {
  if (search.value && search.value.length > 0) {
    return filter(_chatList.value, (c) =>
      includes(c.brief?.toLowerCase(), search.value?.toLowerCase())
    )
  } else {
    return _chatList.value
  }
})

const _loading = computed({
  get() {
    return props.loading
  },
  set(v) {
    emits('update:loading', v)
  },
})

const { t } = useI18n()

function onClickSideBarBtn() {
  emits('onClickSideBarBtn')
}

function onChatCreated(chat: ChatInfo) {
  _chatList.value.unshift(chat)
  _currentChatId.value = chat.id
  _currentChat.value = chat
  emits('onChatCreated', chat)
}

const chatCreatorRef = ref()

function goEmpty(func?: (...p: any[]) => void, ...params: any[]) {
  _currentChat.value = new ChatInfo()
  _currentChatId.value = undefined
  emits('goEmpty', func, ...params)
}

const createNewChat = async () => {
  try {
    await chatApi.checkLLMModel()
  } catch (error: any) {
    console.error(error)
    let errorMsg = t('model.default_miss')
    let confirm_text = t('datasource.got_it')
    if (userStore.isAdmin) {
      errorMsg = t('model.default_miss_admin')
      confirm_text = t('model.to_config')
    }
    ElMessageBox.confirm(t('qa.ask_failed'), {
      confirmButtonType: 'primary',
      tip: errorMsg,
      showCancelButton: userStore.isAdmin,
      confirmButtonText: confirm_text,
      cancelButtonText: t('common.cancel'),
      customClass: 'confirm-no_icon',
      autofocus: false,
      showClose: false,
      callback: (val: string) => {
        if (userStore.isAdmin && val === 'confirm') {
          router.push('/system/model')
        }
      },
    })
    return
  }
  goEmpty(doCreateNewChat)
}

async function doCreateNewChat() {
  if (!isCompletePage.value && !selectAssistantDs.value) {
    return
  }
  chatCreatorRef.value?.showDs()
}

function onClickHistory(chat: Chat) {
  if (chat !== undefined && chat.id !== undefined) {
    if (_currentChatId.value === chat.id) {
      return
    }
    goEmpty(goHistory, chat)
  }
}

function goHistory(chat: Chat) {
  nextTick(() => {
    if (chat !== undefined && chat.id !== undefined) {
      _currentChat.value = new ChatInfo(chat)
      _currentChatId.value = chat.id
      _loading.value = true
      chatApi
        .get(chat.id)
        .then((res) => {
          const info = chatApi.toChatInfo(res)
          if (info && info.id === _currentChatId.value) {
            _currentChat.value = info

            // scrollToBottom()
            emits('onClickHistory', info)
          }
        })
        .finally(() => {
          _loading.value = false
        })
    }
  })
}

function onChatDeleted(id: number) {
  for (let i = 0; i < _chatList.value.length; i++) {
    if (_chatList.value[i].id === id) {
      _chatList.value.splice(i, 1)
      break
    }
  }
  if (id === _currentChatId.value) {
    goEmpty()
  }
  emits('onChatDeleted', id)
}

function onChatRenamed(chat: Chat) {
  _chatList.value.forEach((c: Chat) => {
    if (c.id === chat.id) {
      c.brief = chat.brief
    }
  })
  if (_currentChat.value.id === chat.id) {
    _currentChat.value.brief = chat.brief
  }
  emits('onChatRenamed', chat)
}
</script>

<template>
  <el-container class="chat-container-right-container">
    <el-header class="chat-list-header" :class="{ 'in-popover': inPopover }">
      <div v-if="!inPopover" class="title">
        <div>{{ appName || t('qa.title') }}</div>
        <el-button link type="primary" class="icon-btn" @click="onClickSideBarBtn">
          <el-icon>
            <icon_sidebar_outlined />
          </el-icon>
        </el-button>
      </div>
      <el-button class="btn" type="primary" @click="createNewChat">
        <el-icon style="margin-right: 6px">
          <icon_new_chat_outlined />
        </el-icon>
        {{ t('qa.new_chat') }}
      </el-button>
      <el-input
        v-model="search"
        :prefix-icon="Search"
        class="search"
        name="quick-search"
        autocomplete="off"
        :placeholder="t('qa.chat_search')"
        clearable
        @click.stop
      />
    </el-header>
    <el-main class="chat-list">
      <div v-if="!computedChatList.length" class="empty-search">
        {{ !!search ? $t('datasource.relevant_content_found') : $t('dashboard.no_chat') }}
      </div>
      <ChatList
        v-else
        v-model:loading="_loading"
        :current-chat-id="_currentChatId"
        :chat-list="computedChatList"
        @chat-selected="onClickHistory"
        @chat-deleted="onChatDeleted"
        @chat-renamed="onChatRenamed"
      />
    </el-main>

    <ChatCreator
      v-if="isCompletePage || selectAssistantDs"
      ref="chatCreatorRef"
      @on-chat-created="onChatCreated"
    />
  </el-container>
</template>

<style scoped lang="less">
.chat-container-right-container {
  height: 100%;
  background: var(--workspace-panel-bg, var(--theme-panel-bg));
  color: var(--workspace-text-primary, var(--theme-text-primary));
  font-family: 'PingFang SC', 'Microsoft YaHei', 'Helvetica Neue', Arial, sans-serif;

  .icon-btn {
    min-width: unset;
    width: 28px;
    height: 28px;
    font-size: 16px;
    color: var(--workspace-text-secondary, var(--theme-text-secondary));
    border-radius: 6px;

    :deep(.ed-icon),
    :deep(svg) {
      color: inherit;
    }

    :deep(svg) {
      width: 16px;
      height: 16px;
      opacity: 0.88;
    }

    :deep(svg [stroke]) {
      stroke: currentColor;
    }

    &:hover {
      background: var(--workspace-control-hover-bg, var(--theme-hover-bg));
      color: var(--workspace-text-primary, var(--theme-text-primary));

      :deep(svg) {
        opacity: 1;
      }
    }
  }

  .chat-list-header {
    --ed-header-padding: 14px;
    --ed-header-height: calc(14px + 24px + 10px + 38px + 10px + 34px + 14px);

    &.in-popover {
      --ed-header-height: calc(14px + 38px + 10px + 34px + 14px);
    }

    display: flex;
    align-items: center;
    justify-content: center;
    flex-direction: column;
    gap: 10px;

    .title {
      height: 24px;
      width: 100%;
      display: flex;
      flex-direction: row;
      align-items: center;
      justify-content: space-between;
      font-size: 15px;
      font-weight: 600;
      line-height: 24px;
      letter-spacing: 0.1px;
      color: var(--workspace-text-primary, var(--theme-text-primary));
    }

    .btn {
      width: 100%;
      height: 38px;
      border: 0;
      border-radius: 10px;
      font-family: inherit;
      font-size: 14px;
      font-weight: 600;
      letter-spacing: 0.1px;
      background: linear-gradient(135deg, #2f6bff 0%, #1d8dff 100%);
      box-shadow: 0 8px 18px rgba(47, 107, 255, 0.18);
      transition:
        transform 0.18s ease,
        box-shadow 0.18s ease,
        filter 0.18s ease;

      --ed-button-text-color: #ffffff;
      --ed-button-bg-color: #2f6bff;
      --ed-button-border-color: transparent;
      --ed-button-hover-bg-color: #235df0;
      --ed-button-hover-text-color: #ffffff;
      --ed-button-hover-border-color: transparent;
      --ed-button-active-bg-color: #1f55de;
      --ed-button-active-border-color: transparent;

      &:hover {
        background: linear-gradient(135deg, #235df0 0%, #137fe8 100%);
        box-shadow: 0 10px 20px rgba(47, 107, 255, 0.24);
        filter: saturate(1.04);
      }

      &:active {
        transform: translateY(1px);
        box-shadow: 0 6px 14px rgba(47, 107, 255, 0.18);
      }

      :deep(.ed-icon) {
        width: 18px;
        height: 18px;
        color: inherit;
      }

      :deep(svg) {
        width: 18px;
        height: 18px;
        color: inherit;
      }

      :deep(svg path) {
        fill: currentColor !important;
      }
    }

    .search {
      height: 34px;
      width: 100%;

      :deep(.ed-input__wrapper) {
        min-height: 34px;
        padding: 0 10px;
        border-radius: 10px;
        background-color: #ffffff;
        box-shadow:
          0 0 0 1px rgba(118, 134, 166, 0.22) inset,
          0 4px 12px rgba(18, 34, 66, 0.04);
        transition:
          box-shadow 0.18s ease,
          background-color 0.18s ease;
      }

      :deep(.ed-input__wrapper:hover) {
        box-shadow:
          0 0 0 1px rgba(47, 107, 255, 0.28) inset,
          0 6px 14px rgba(18, 34, 66, 0.06);
      }

      :deep(.ed-input__wrapper.is-focus) {
        box-shadow:
          0 0 0 1px rgba(47, 107, 255, 0.52) inset,
          0 0 0 3px rgba(47, 107, 255, 0.1);
      }

      :deep(.ed-input__inner) {
        color: var(--workspace-text-primary, var(--theme-text-primary));
        font-family: inherit;
        font-size: 13px;
        font-weight: 400;
        letter-spacing: 0.1px;
      }

      :deep(.ed-input__inner::placeholder) {
        color: var(--workspace-text-tertiary, var(--theme-text-tertiary));
      }

      :deep(.ed-input__prefix),
      :deep(.ed-input__suffix) {
        color: var(--workspace-text-tertiary, var(--theme-text-tertiary));
      }

      :deep(.ed-input__prefix .ed-icon),
      :deep(.ed-input__suffix .ed-icon) {
        width: 15px;
        height: 15px;
      }
    }
  }

  .chat-list {
    padding: 0 0 20px 0;
    background: var(--workspace-panel-bg, var(--theme-panel-bg));

    .empty-search {
      width: 100%;
      text-align: center;
      margin-top: 80px;
      color: var(--workspace-text-secondary, var(--theme-text-secondary));
      font-weight: 400;
      font-size: 14px;
      line-height: 22px;
    }
  }
}
</style>
