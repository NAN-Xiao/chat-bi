<template>
  <el-container class="chat-container">
    <el-aside class="chat-container-left">
      <el-container class="chat-container-right-container">
        <el-header class="chat-list-header">
          <el-button type="primary" @click="createNewChat">
            <el-icon>
              <Plus/>
            </el-icon>
            New Conversation
          </el-button>
        </el-header>
        <el-main class="chat-list">
          <el-scrollbar>
            <div v-for="chat in chatList" @click="onClickHistory(chat)"
                 :style="chat.id === currentChatId ? {border: 'solid 1px red'} : {}">
              {{ chat.create_time }}<br/>
              {{ chat.brief }}
            </div>
          </el-scrollbar>
        </el-main>
      </el-container>
    </el-aside>
    <el-container :loading="loading">
      <el-main>
        <div v-for="message in computedMessages">
          {{ message.role }}: {{ message.content }}
          <div v-if="message.isWelcome">
            <el-select v-model="currentChat.datasource" :disabled="currentChat.id!==undefined">
              <el-option v-for="item in dsList"
                         :value="item.id"
                         :key="item.id"
                         :label="item.name"/>
            </el-select>
          </div>
        </div>
      </el-main>
      <el-footer>
        <div class="chat-input">
          <div class="input-wrapper">
            <el-input
                v-model="inputMessage"
                type="textarea"
                :rows="1"
                :autosize="{ minRows: 1, maxRows: 8 }"
                placeholder="Press Enter to send, Ctrl + Enter for new line"
                @keydown.enter.exact.prevent="sendMessage"
                @keydown.ctrl.enter.exact.prevent="handleCtrlEnter"
            />
            <div class="input-actions">
              <el-button circle type="primary" class="send-btn" @click="sendMessage">
                <el-icon>
                  <Position/>
                </el-icon>
              </el-button>
            </div>
          </div>
        </div>
      </el-footer>
    </el-container>

  </el-container>
</template>

<script setup lang="ts">
import {ref, computed, nextTick, watch, onMounted} from 'vue'
import {Plus, Position} from '@element-plus/icons-vue'
import {Chat, chatApi, ChatInfo, ChatRecord, questionApi} from '@/api/chat'
import {datasourceApi} from "@/api/datasource.ts";

interface ChatMessage {
  role: 'user' | 'assistant'
  create_time?: Date | string
  content?: string | number
  isTyping?: boolean
  isWelcome?: boolean
}

const inputMessage = ref('')

const loading = ref<boolean>(false);
const chatList = ref<Array<ChatInfo>>([])
const dsList = ref<any>([])

const currentChatId = ref<number | undefined>()
const currentChat = ref<ChatInfo>(new ChatInfo())
const isTyping = ref<boolean>(false)

const computedMessages = computed<Array<ChatMessage>>(() => {
  const welcome: ChatMessage = {
    role: 'assistant',
    create_time: currentChat.value?.create_time,
    content: currentChat.value?.datasource,
    isTyping: false,
    isWelcome: true,
  }
  const messages: Array<ChatMessage> = [welcome]
  if (currentChatId.value === undefined) {
    return messages
  }
  let appendThinking = false
  for (let i = 0; i < currentChat.value.records.length; i++) {
    const record = currentChat.value.records[i]
    if (record.question !== undefined) {
      messages.push({
        role: 'user',
        create_time: record.create_time,
        content: record.question,
      })
    }
    if (record.answer !== undefined && record.answer !== '') {
      messages.push({
        role: 'assistant',
        create_time: record.create_time,
        content: record.answer,
        isTyping: i === currentChat.value.records.length - 1 && isTyping.value
      })
    } else {
      appendThinking = true
    }
  }
  if (isTyping.value && appendThinking) {
    messages.push({
      role: 'assistant',
      content: 'Thinking...',
      isTyping: true
    })
  }
  return messages
})

const createNewChat = () => {
  currentChat.value = new ChatInfo()
  currentChatId.value = undefined
  listDs()
}

function getChatList() {
  loading.value = true
  chatApi.list()
      .then((res) => {
        chatList.value = chatApi.toChatInfoList(res)
      })
      .finally(() => {
        loading.value = false
      })
}

function onClickHistory(chat: Chat) {
  currentChat.value = new ChatInfo(chat)
  if (chat !== undefined && chat.id !== undefined && !loading.value) {
    currentChatId.value = chat.id
    loading.value = true
    chatApi.get(chat.id)
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

function listDs() {
  datasourceApi.list().then((res) => {
    console.log(res)
    dsList.value = res
  })
}

onMounted(() => {
  getChatList()
  listDs()
})


const updateMessageContent = (content: string) => {
  if (currentChat.value) {
    currentChat.value.records[currentChat.value.records.length - 1].answer = content
  }
}

const sendMessage = async () => {
  if (!inputMessage.value.trim()) return
  if (computedMessages.value[0].content === undefined) return

  loading.value = true
  isTyping.value = true

  const currentRecord = new ChatRecord()
  currentRecord.create_time = new Date()
  currentRecord.chat_id = currentChatId.value
  currentRecord.question = inputMessage.value
  currentRecord.answer = ''

  currentChat.value.records.push(currentRecord)

  let error = false
  if (currentChatId.value === undefined) {
    chatApi.startChat({question: currentRecord.question.trim(), datasource: currentChat.value.datasource})
        .then((res) => {
          const chat = chatApi.toChatInfo(res)
          if (chat !== undefined) {
            chatList.value.unshift(chat)
            currentChatId.value = chat.id
            chat.records.push(currentRecord)
            currentChat.value = chat
          } else {
            error = true
          }
        })
        .catch(e => {
          isTyping.value = false
          error = true
          console.error(e)
        })
        .finally(() => {
          loading.value = false
        })
  }

  if (error) return

  try {
    const response = await questionApi.add({question: currentRecord.question, chat_id: currentChatId.value})
    const reader = response.body.getReader()
    const decoder = new TextDecoder()

    while (true) {
      const {done, value} = await reader.read()
      if (done) {
        isTyping.value = false
        break
      }

      const chunk = decoder.decode(value)
      const lines = chunk.split('\n\n')

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = JSON.parse(line.replace('data:', '').trim())
          let realContent = data.content

          switch (data.type) {
            case 'html':
              realContent = '\n' + data.content
              break

            case 'error':
              realContent = '\nError: ' + data.content
              break

            default:
              if (data.content) {
                const newContent = currentRecord.answer + realContent

                updateMessageContent(newContent)
                await nextTick()
              }
          }
        }
      }
    }
  } catch (error) {
    updateMessageContent(currentRecord.answer + '\nError: Failed to get response')
    console.error('Error:', error)
    isTyping.value = false
  }
}

watch(() => currentChat.value?.records[currentChat.value.records.length - 1]?.answer, () => {
  //scrollToBottom()
}, {deep: true})

const formatMessage = (content: string) => {
  if (!content) return ''
  return content
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/\n/g, '<br>')
      .replace(/ {2}/g, '&nbsp;&nbsp;')
}

const handleCtrlEnter = (e: KeyboardEvent) => {
  const textarea = e.target as HTMLTextAreaElement
  const start = textarea.selectionStart
  const end = textarea.selectionEnd
  const value = textarea.value

  inputMessage.value = value.substring(0, start) + '\n' + value.substring(end)

  nextTick(() => {
    textarea.selectionStart = textarea.selectionEnd = start + 1
  })
}
</script>

<style lang="less" scoped>
.chat-container {
  height: 100%;

  .chat-container-left {

    --el-aside-width: 260px;

    border-right: solid 1px rgba(0, 0, 0, 0.3);

    .chat-container-right-container {
      height: 100%;

      .chat-list-header {
        display: flex;
        align-items: center;
        justify-content: center;
      }

      .chat-list {
        padding-top: unset;
      }

    }
  }


}
</style>