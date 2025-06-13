<template>
  <el-drawer
    v-model="dialogShow"
    direction="btt"
    size="90%"
    trigger="click"
    :title="t('dashboard.add_chart')"
    modal-class="custom-drawer"
    @closed="handleClose()"
  >
    <el-container class="chat-container">
      <el-aside class="chat-container-left">
        <el-container class="chat-container-right-container">
          <el-main class="chat-list">
            <DashboardChatList
              v-model:loading="loading"
              :current-chat-id="currentChatId"
              :chat-list="chatList"
              @chat-selected="onClickHistory"
            />
          </el-main>
        </el-container>
      </el-aside>
      <el-container :loading="loading">
        <el-main class="chat-record-list">
          <el-scrollbar ref="chatListRef"> </el-scrollbar>
        </el-main>
      </el-container>
    </el-container>

    <template #footer>
      <el-row class="multiplexing-footer">
        <el-col class="adapt-count">
          <span>{{ t('dashboard.chart_selected', [selectComponentCount]) }} </span>
        </el-col>
        <el-button class="close-button" @click="dialogShow = false">{{
          t('common.cancel')
        }}</el-button>
        <el-button
          type="primary"
          :disabled="!selectComponentCount"
          class="confirm-button"
          @click="saveMultiplexing"
          >{{ t('common.save') }}</el-button
        >
      </el-row>
    </template>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Chat, chatApi, ChatInfo } from '@/api/chat.ts'
import DashboardChatList from '@/views/dashboard/editor/DashboardChatList.vue'
const dialogShow = ref(false)
const { t } = useI18n()
const selectComponentCount = computed(() => Object.keys(state.curMultiplexingComponents).length)
const state = reactive({
  curMultiplexingComponents: {},
})

const loading = ref<boolean>(false)
const chatList = ref<Array<ChatInfo>>([])

const currentChatId = ref<number | undefined>()
const currentChat = ref<ChatInfo>(new ChatInfo())

onMounted(() => {
  getChatList()
})

function onClickHistory(chat: Chat) {
  currentChat.value = new ChatInfo(chat)
  if (chat !== undefined && chat.id !== undefined && !loading.value) {
    currentChatId.value = chat.id
    loading.value = true
    chatApi
      .get(chat.id)
      .then((res) => {
        const info = chatApi.toChatInfo(res)
        if (info) {
          currentChat.value = info
        }
      })
      .finally(() => {
        loading.value = false
      })
  }
}

function getChatList() {
  loading.value = true
  chatApi
    .list()
    .then((res) => {
      chatList.value = chatApi.toChatInfoList(res)
    })
    .finally(() => {
      loading.value = false
    })
}

const dialogInit = () => {
  dialogShow.value = true
  state.curMultiplexingComponents = {}
}

const saveMultiplexing = () => {
  dialogShow.value = false
}
const handleClose = () => {}
defineExpose({
  dialogInit,
})
</script>

<style lang="less" scoped>
.close-button {
  position: absolute;
  top: 18px;
  right: 120px;
}
.confirm-button {
  position: absolute;
  top: 18px;
  right: 20px;
}
.multiplexing-area {
  width: 100%;
  height: 100%;
}
.multiplexing-footer {
  position: relative;
}

.adapt-count {
  position: absolute;
  top: 18px;
  left: 20px;
  color: #646a73;
  font-size: 14px;
  font-weight: 400;
  line-height: 22px;
}

.adapt-select {
  position: absolute;
  top: 18px;
  right: 220px;
}
.adapt-text {
  font-size: 14px;
  font-weight: 400;
  color: #1f2329;
  line-height: 22px;
}
</style>

<style lang="less">
.custom-drawer {
  .ed-drawer__footer {
    height: 64px !important;
    padding: 0 !important;
    box-shadow: 0 -1px 0px #d7d7d7 !important;
  }

  .ed-drawer__body {
    padding: 0 0 64px 0 !important;
  }
}

.chat-container {
  height: 100%;

  .chat-container-left {
    padding-top: 20px;
    --ed-aside-width: 260px;

    box-shadow: 0 0 3px #d7d7d7;
    z-index: 1;

    background: var(--ed-fill-color-blank);

    .chat-container-right-container {
      height: 100%;

      .chat-list-header {
        display: flex;
        align-items: center;
        justify-content: center;
      }

      .chat-list {
        padding: 0 0 20px 0;
      }
    }
  }

  .chat-record-list {
    padding: 0 0 20px 0;
  }

  .chat-footer {
    --ed-footer-height: 120px;

    display: flex;
    flex-direction: column;

    .input-wrapper {
      flex: 1;

      position: relative;

      .input-area {
        height: 100%;
        padding-bottom: 8px;

        :deep(.ed-textarea__inner) {
          height: 100% !important;
        }
      }

      .input-icon {
        min-width: unset;
        position: absolute;
        bottom: 14px;
        right: 8px;
      }
    }
  }

  .send-btn {
    min-width: 0;
  }
}
</style>
