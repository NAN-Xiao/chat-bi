<template>
  <div class="sqlbot-assistant-container">
    <div class="head">
      <div class="flex align-center">
        <div class="head-img-div">
          <img :src="AssistantGif" />
        </div>
        <h4>SQLBot 小助手</h4>
      </div>
    </div>
    <chat-component v-if="!loading" ref="chatRef" class="sqlbot-chat-container" />
  </div>
  <div class="sqlbot-top-btn">
    <el-icon style="cursor: pointer" @click="createChat">
      <icon_new_chat_outlined />
    </el-icon>
    <el-icon style="cursor: pointer" @click="openHistory">
      <history></history>
    </el-icon>
  </div>
  <div class="sqlbot-history-container">
    <el-drawer
      v-model="drawer"
      :append-to-body="false"
      class="sqlbot-history-drawer"
      modal-class="sqlbot-history-modal"
      title=""
      direction="ttb"
      :with-header="false"
    >
      <div class="sqlbot-history-title">
        <span>历史记录</span>
      </div>
      <div class="sqlbot-history-content">
        <div v-if="!chatList.length" class="history-empty">
          <span>暂无历史记录</span>
        </div>
        <div v-else class="sqlbot-chat-list-inner">
          <el-scrollbar max-height="350px" class="sqlbot-chat-scroller">
            <template v-for="chat in chatList" :key="chat.id">
              <div
                class="chat-list-item"
                :class="{ 'is-active-chat': currentId === chat.id }"
                @click="onClickHistory(chat)"
              >
                <span class="title">{{ chat.brief ?? 'Untitled' }}</span>
                <!-- <div class="history-operate">
                  <el-icon @click="EditPen(chat)"><IconOpeEdit /></el-icon>
                  <el-icon @click="Delete(chat)"><IconOpeDelete /></el-icon>
                </div> -->
              </div>
            </template>
          </el-scrollbar>
        </div>
      </div>
    </el-drawer>
  </div>
</template>
<script setup lang="ts">
import { onBeforeMount, onBeforeUnmount, ref } from 'vue'
import ChatComponent from '@/views/chat/index.vue'
import AssistantGif from '@/assets/img/assistant.gif'
import history from '@/assets/svg/chart/history.svg'
import icon_new_chat_outlined from '@/assets/svg/icon_new_chat_outlined.svg'
/* import IconOpeEdit from '@/assets/svg/operate/ope-edit.svg'
import IconOpeDelete from '@/assets/svg/operate/ope-delete.svg' */
import { useRoute } from 'vue-router'
import { assistantApi } from '@/api/assistant'
import { useAssistantStore } from '@/stores/assistant'

const assistantStore = useAssistantStore()
const route = useRoute()

const chatRef = ref()
const chatList = ref<Array<any>>([])
const drawer = ref(false)
const currentId = ref()

const createChat = () => {
  chatRef.value?.createNewChat()
}
const openHistory = () => {
  chatList.value = chatRef.value?.getHistoryList()
  currentId.value = chatRef.value?.getCurrentChatId()
  drawer.value = true
}
const onClickHistory = (chat: any) => {
  chatRef.value?.toAssistantHistory(chat)
}

/* const EditPen = (chat: any) => {
  chatRef.value?.onChatRenamed(chat)
}
const Delete = (chat: any) => {
  chatRef.value?.onChatDeleted(chat.id)
} */
const validator = ref({
  id: '',
  valid: false,
  id_match: false,
  token: '',
})
const loading = ref(true)
const eventName = 'sqlbot_assistant_event'
const communicationCb = async (event: any) => {
  if (event.data?.eventName === eventName) {
    if (event.data?.messageId !== route.query.id) {
      return
    }
    if (event.data?.busi == 'certificate') {
      const certificate = event.data['certificate']
      console.log(certificate)
      assistantStore.setType(1)
      assistantStore.setCertificate(certificate)
      // store certificate to pinia
    }
  }
}
onBeforeMount(async () => {
  const assistantId = route.query.id
  const online = route.query.online
  console.log(online)
  const now = Date.now()
  assistantStore.setFlag(now)
  const param = {
    id: assistantId,
    virtual: assistantStore.getFlag,
    online,
  }
  validator.value = await assistantApi.validate(param)
  assistantStore.setToken(validator.value.token)
  assistantStore.setAssistant(true)
  loading.value = false

  window.addEventListener('message', communicationCb)
  const readyData = {
    eventName: 'sqlbot_assistant_event',
    busi: 'ready',
    ready: true,
    messageId: assistantId,
  }
  window.parent.postMessage(readyData, '*')
})

onBeforeUnmount(() => {
  window.removeEventListener('message', communicationCb)
})
</script>

<style lang="less" scoped>
.sqlbot-assistant-container {
  height: 100%;
  width: 100%;
  color: rgb(31, 35, 41);
  .flex {
    display: flex;
  }
  .head {
    background: linear-gradient(90deg, #ebf1ff 24.34%, #e5fbf8 56.18%, #f2ebfe 90.18%);
    position: fixed;
    width: 100%;
    left: 0;
    top: 0;
    z-index: 100;
    height: 56px;
    line-height: 56px;
    box-sizing: border-box;
    border-bottom: 1px solid #dee0e3;
    .align-center {
      align-items: center;
      .head-img-div {
        display: flex;
        margin-left: 24px;
        img {
          width: 32px;
          height: 32px;
        }
      }
    }
  }
  .sqlbot-chat-container {
    padding-top: 56px;
    :deep(.ed-aside) {
      display: none;
    }
  }
}
.sqlbot-top-btn {
  right: 85px;
  z-index: 2009;
  position: fixed;
  top: 16px;
  display: flex;
  column-gap: 16px;
  // right: 16px;
  font-size: 22px;
  i:first-child {
    color: var(--primary-color);
  }
}
.sqlbot-history-container {
  width: 100%;
  :deep(.sqlbot-history-modal) {
    top: 56px !important;
  }
  :deep(.sqlbot-history-title) {
    border-bottom: 1px solid #dee0e3;
    padding: 16px 24px;
    font-size: 14px;
    font-weight: 500;
    color: #1f2329;
  }
  :deep(.ed-drawer__body) {
    padding: 0 !important;
  }
  :deep(.sqlbot-history-drawer) {
    height: fit-content !important;
    .sqlbot-history-content {
      padding: 16px;
      .history-empty {
        height: 60px;
        color: #8f959e !important;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 14px;
      }
      .is-active-chat {
        background-color: #ebf1ff;
        color: #3370ff;
        font-weight: 500;
      }
      .chat-list-item {
        display: flex;
        align-items: center;
        padding: 10px 8px;
        font-size: 14px;
        color: #1f2329;
        justify-content: space-between;
        .history-operate {
          display: none;
        }
        &:hover {
          cursor: pointer;
          border-radius: 4px;
          background: rgba(31, 35, 41, 0.1);
          .history-operate {
            padding-right: 16px;
            display: flex;
            column-gap: 16px;
            align-items: center;
            font-size: 18px;
            i {
              color: #8f959e;
              &:hover {
                color: #8f959e99;
              }
            }
          }
        }
      }
    }
  }
}
</style>
