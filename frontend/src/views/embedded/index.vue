<template>
  <div class="sqlbot-assistant-container">
    <div class="header">
      <el-icon size="20" @click="openHistory">
        <icon_sidebar_outlined></icon_sidebar_outlined>
      </el-icon>
      <img :src="LOGO" class="logo" width="30px" height="30px" alt="" />
      <span class="tite">{{ $t('embedded.intelligent_customer_service') }}</span>

      <el-tooltip effect="dark" :content="$t('embedded.new_conversation')" placement="top">
        <el-icon class="new-chat" size="20" @click="createChat">
          <icon_new_chat_outlined></icon_new_chat_outlined>
        </el-icon>
      </el-tooltip>
    </div>
    <div class="sqlbot-chat-container">
      <chat-component v-if="!loading" ref="chatRef" />
    </div>
    <div class="drawer-assistant" @click="openHistory"></div>
  </div>
</template>
<script setup lang="ts">
import { onBeforeMount, onBeforeUnmount, ref } from 'vue'
import ChatComponent from '@/views/chat/index.vue'
import LOGO from '@/assets/embedded/LOGO.png'
import icon_sidebar_outlined from '@/assets/embedded/icon_sidebar_outlined.svg'
import icon_new_chat_outlined from '@/assets/svg/icon_new_chat_outlined.svg'
import { useRoute } from 'vue-router'
import { assistantApi } from '@/api/assistant'
import { useAssistantStore } from '@/stores/assistant'

const assistantStore = useAssistantStore()
const route = useRoute()

const chatRef = ref()

const createChat = () => {
  chatRef.value?.createNewChat()
}
const openHistory = () => {
  chatRef.value?.showFloatPopover()
}

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
      assistantStore.setType(1)
      assistantStore.setCertificate(certificate)
      assistantStore.resolveCertificate(certificate)
    }
    if (event.data?.busi == 'setOnline') {
      setFormatOnline(event.data.online)
    }
  }
}
const setFormatOnline = (text?: any) => {
  if (text === null || typeof text === 'undefined') {
    assistantStore.setOnline(false)
    return
  }
  if (typeof text === 'boolean') {
    assistantStore.setOnline(text)
    return
  }
  if (typeof text === 'string') {
    assistantStore.setOnline(text.toLowerCase() === 'true')
    return
  }
  assistantStore.setOnline(false)
}
onBeforeMount(async () => {
  const assistantId = route.query.id
  const online = route.query.online
  setFormatOnline(online)
  const now = Date.now()
  assistantStore.setFlag(now)
  assistantStore.setId(assistantId?.toString() || '')
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
  height: 100vh;
  width: 100%;
  color: rgb(31, 35, 41);
  .header {
    width: 100%;
    left: 0;
    top: 0;
    z-index: 100;
    height: 56px;
    line-height: 56px;
    background: #1cba9014;
    height: 56px;
    padding: 0 16px;
    display: flex;
    align-items: center;
    position: fixed;
    .logo {
      margin: 0 8px 0 16px;
    }

    .title {
      font-weight: 500;
      font-size: 16px;
      line-height: 24px;
    }

    .ed-icon {
      position: relative;
      cursor: pointer;

      &::after {
        content: '';
        background-color: #1f23291a;
        position: absolute;
        border-radius: 6px;
        width: 28px;
        height: 28px;
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

    .new-chat {
      position: absolute;
      right: 88px;
      top: 17px;
    }
  }
  .sqlbot-chat-container {
    padding-top: 56px;
    height: 100%;
    :deep(.ed-aside) {
      display: none;
    }
  }
  .drawer-assistant {
    height: 100%;
    position: absolute;
    left: 0;
    top: 0;
    width: 50%;
    background: #f5f6f7;
    box-shadow: 0px 6px 24px 0px #1f232914;
    padding: 16px;
    border-right: 1px solid #dee0e3;
    display: none;
  }
}
</style>

<style lang="less">
.ed-overlay-dialog,
.ed-drawer {
  margin-top: 50px;
}
</style>
