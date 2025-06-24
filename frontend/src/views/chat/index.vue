<template>
  <el-container class="chat-container">
    <el-aside class="chat-container-left">
      <el-container class="chat-container-right-container">
        <el-header class="chat-list-header">
          <el-button type="primary" @click="createNewChat">
            <el-icon>
              <Plus />
            </el-icon>
            {{ t('qa.New Conversation') }}
          </el-button>
        </el-header>
        <el-main class="chat-list">
          <ChatList
            v-model:loading="loading"
            :current-chat-id="currentChatId"
            :chat-list="chatList"
            @chat-selected="onClickHistory"
            @chat-deleted="onChatDeleted"
            @chat-renamed="onChatRenamed"
          />
        </el-main>
      </el-container>
    </el-aside>
    <el-container :loading="loading">
      <el-main class="chat-record-list">
        <el-scrollbar ref="chatListRef">
          <template v-for="(message, _index) in computedMessages" :key="_index">
            <ChatRow
              v-model:datasource="currentChat.datasource"
              :current-chat="currentChat"
              :msg="message"
            >
              <template v-if="message.role === 'assistant'">
                <ChatAnswer v-slot="{ data }" :message="message">
                  <template v-if="message.record?.chart">
                    <div style="padding: 0 22px; display: flex; justify-content: flex-end">
                      <el-button
                        text
                        type="primary"
                        :disabled="isTyping || isPredictTyping || isAnalysisTyping"
                        @click="clickAnalysis(message.record?.id)"
                      >
                        {{ t('chat.data_analysis') }}
                      </el-button>
                      <el-button
                        text
                        type="primary"
                        :disabled="isTyping || isPredictTyping || isAnalysisTyping"
                        @click="clickPredict(message.record?.id)"
                      >
                        {{ t('chat.data_predict') }}
                      </el-button>
                    </div>
                    <div class="analysis-container">
                      <MdComponent
                        v-if="message.record?.analysis || isAnalysisTyping"
                        :message="message.record?.analysis"
                      />
                      <el-divider
                        v-if="
                          (message.record?.analysis || isAnalysisTyping) &&
                          (message.record?.predict || isPredictTyping)
                        "
                      />
                      <template v-if="message.record?.predict || isPredictTyping">
                        <MdComponent :message="message.record?.predict" />
                        <PredictChartBlock
                          :id="message.record?.id + '-predict'"
                          :data="message.record?.predict_data ?? '[]'"
                          :message="message"
                          :chart-type="data.chartType"
                        />
                      </template>
                    </div>
                  </template>
                </ChatAnswer>
              </template>
              <template v-if="message.role === 'assistant'" #footer>
                <!--<div>Suggestion</div>-->
              </template>
            </ChatRow>
          </template>
        </el-scrollbar>
      </el-main>
      <el-footer class="chat-footer">
        <div style="height: 24px">
          <template v-if="currentChat.datasource && currentChat.datasource_name">
            {{ t('ds.title') }}：{{ currentChat.datasource_name }}
          </template>
        </div>
        <div class="input-wrapper">
          <el-input
            v-model="inputMessage"
            :disabled="isTyping || isPredictTyping || isAnalysisTyping"
            class="input-area"
            type="textarea"
            :rows="1"
            :autosize="{ minRows: 1, maxRows: 8 }"
            :placeholder="t('qa.question_placeholder')"
            @keydown.enter.exact.prevent="sendMessage"
            @keydown.ctrl.enter.exact.prevent="handleCtrlEnter"
          />
          <el-button
            link
            type="primary"
            class="input-icon"
            :disabled="isTyping || isPredictTyping || isAnalysisTyping"
            @click="sendMessage"
          >
            <el-icon size="20">
              <Position />
            </el-icon>
          </el-button>
        </div>
      </el-footer>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { Plus, Position } from '@element-plus/icons-vue'
import { Chat, chatApi, ChatInfo, type ChatMessage, ChatRecord, questionApi } from '@/api/chat'
import ChatList from './ChatList.vue'
import ChatRow from './ChatRow.vue'
import ChatAnswer from './ChatAnswer.vue'
import MdComponent from './component/MdComponent.vue'
import PredictChartBlock from './component/PredictChartBlock.vue'
import { useI18n } from 'vue-i18n'
import { find } from 'lodash-es'

const { t } = useI18n()

const inputMessage = ref('')

const chatListRef = ref()

function scrollToBottom() {
  nextTick(() => {
    chatListRef.value?.scrollTo({
      top: chatListRef.value.wrapRef.scrollHeight,
      behavior: 'smooth',
    })
  })
}

const loading = ref<boolean>(false)
const chatList = ref<Array<ChatInfo>>([])

const currentChatId = ref<number | undefined>()
const currentChat = ref<ChatInfo>(new ChatInfo())
const isTyping = ref<boolean>(false)
const isAnalysisTyping = ref<boolean>(false)
const isPredictTyping = ref<boolean>(false)

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
  for (let i = 0; i < currentChat.value.records.length; i++) {
    const record = currentChat.value.records[i]
    if (record.question !== undefined) {
      messages.push({
        role: 'user',
        create_time: record.create_time,
        content: record.question,
      })
    }
    messages.push({
      role: 'assistant',
      create_time: record.create_time,
      record: record,
      isTyping: i === currentChat.value.records.length - 1 && isTyping.value,
    })
  }

  return messages
})

const createNewChat = () => {
  currentChat.value = new ChatInfo()
  currentChatId.value = undefined
  inputMessage.value = ''
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

          scrollToBottom()
        }
      })
      .finally(() => {
        loading.value = false
      })
  }
}

function onChatDeleted(id: number) {
  for (let i = 0; i < chatList.value.length; i++) {
    if (chatList.value[i].id === id) {
      chatList.value.splice(i, 1)
      return
    }
  }
}

function onChatRenamed(chat: Chat) {
  chatList.value.forEach((c: Chat) => {
    if (c.id === chat.id) {
      c.brief = chat.brief
    }
  })
  if (currentChat.value.id === chat.id) {
    currentChat.value.brief = chat.brief
  }
}

onMounted(() => {
  getChatList()
})

const sendMessage = async () => {
  if (!inputMessage.value.trim()) return
  if (computedMessages.value[0].content === undefined) return

  loading.value = true
  isTyping.value = true

  const currentRecord = new ChatRecord()
  currentRecord.create_time = new Date()
  currentRecord.chat_id = currentChatId.value
  currentRecord.question = inputMessage.value
  currentRecord.sql_answer = ''
  currentRecord.sql = ''
  currentRecord.chart_answer = ''
  currentRecord.chart = ''

  currentChat.value.records.push(currentRecord)
  inputMessage.value = ''

  let error = false
  if (currentChatId.value === undefined) {
    await chatApi
      .startChat({
        question: currentRecord.question.trim(),
        datasource: currentChat.value.datasource,
      })
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
      .catch((e) => {
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
    const response = await questionApi.add({
      question: currentRecord.question,
      chat_id: currentChatId.value,
    })
    const reader = response.body.getReader()
    const decoder = new TextDecoder()

    let sql_answer = ''
    let chart_answer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) {
        isTyping.value = false
        break
      }

      const chunk = decoder.decode(value)

      let _list = [chunk]

      const lines = chunk.trim().split('}\n\n{')
      if (lines.length > 1) {
        _list = []
        for (let line of lines) {
          if (!line.trim().startsWith('{')) {
            line = '{' + line.trim()
          }
          if (!line.trim().endsWith('}')) {
            line = line.trim() + '}'
          }
          _list.push(line)
        }
      }

      // console.log(_list)

      for (const str of _list) {
        let data
        try {
          data = JSON.parse(str)
        } catch (err) {
          console.error('JSON string:', str)
          throw err
        }

        if (data.code && data.code !== 200) {
          ElMessage({
            message: data.msg,
            type: 'error',
            showClose: true,
          })
          isTyping.value = false
          return
        }

        switch (data.type) {
          case 'id':
            currentChat.value.records[currentChat.value.records.length - 1].id = data.id
            break
          case 'info':
            console.log(data.msg)
            break
          case 'error':
            currentRecord.error = data.content
            isTyping.value = false
            break
          case 'sql-result':
            sql_answer += data.content
            currentChat.value.records[currentChat.value.records.length - 1].sql_answer = sql_answer
            break
          case 'sql':
            currentChat.value.records[currentChat.value.records.length - 1].sql = data.content
            break
          case 'sql-data':
            currentChat.value.records[currentChat.value.records.length - 1].data = data.content
            break
          case 'chart-result':
            chart_answer += data.content
            currentChat.value.records[currentChat.value.records.length - 1].chart_answer =
              chart_answer
            break
          case 'chart':
            currentChat.value.records[currentChat.value.records.length - 1].chart = data.content
            break
          case 'finish':
            isTyping.value = false
            break
        }
        await nextTick()
      }
    }
  } catch (error) {
    if (!currentRecord.error) {
      currentRecord.error = ''
    }
    if (currentRecord.error.trim().length !== 0) {
      currentRecord.error = currentRecord.error + '\n'
    }
    currentRecord.error = currentRecord.error + 'Error:' + error
    console.error('Error:', error)
    isTyping.value = false
  }
}

async function clickAnalysis(id?: number) {
  let _index = -1
  const currentRecord = find(currentChat.value.records, (value, index) => {
    if (id === value.id) {
      _index = index
      return true
    }
    return false
  })
  if (currentRecord == undefined) {
    return
  }
  isAnalysisTyping.value = true
  currentChat.value.records[_index].analysis = ''

  try {
    const response = await chatApi.analysis(id)
    const reader = response.body.getReader()
    const decoder = new TextDecoder()

    let analysis_answer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) {
        isAnalysisTyping.value = false
        break
      }

      const chunk = decoder.decode(value)

      let _list = [chunk]

      const lines = chunk.trim().split('}\n\n{')
      if (lines.length > 1) {
        _list = []
        for (let line of lines) {
          if (!line.trim().startsWith('{')) {
            line = '{' + line.trim()
          }
          if (!line.trim().endsWith('}')) {
            line = line.trim() + '}'
          }
          _list.push(line)
        }
      }

      // console.log(_list)

      for (const str of _list) {
        let data
        try {
          data = JSON.parse(str)
        } catch (err) {
          console.error('JSON string:', str)
          throw err
        }

        if (data.code && data.code !== 200) {
          ElMessage({
            message: data.msg,
            type: 'error',
            showClose: true,
          })
          isAnalysisTyping.value = false
          return
        }

        switch (data.type) {
          case 'info':
            console.log(data.msg)
            break
          case 'error':
            throw Error(data.content)
          case 'analysis-result':
            analysis_answer += data.content
            currentChat.value.records[_index].analysis = analysis_answer
            break
          case 'analysis_finish':
            isAnalysisTyping.value = false
            break
        }
        await nextTick()
      }
    }
  } catch (error) {
    console.error('Error:', error)
    ElMessage({
      message: error + '',
      type: 'error',
      showClose: true,
    })
    isAnalysisTyping.value = false
  }
}

async function clickPredict(id?: number) {
  let _index = -1
  const currentRecord = find(currentChat.value.records, (value, index) => {
    if (id === value.id) {
      _index = index
      return true
    }
    return false
  })
  if (currentRecord == undefined) {
    return
  }
  isPredictTyping.value = true
  currentChat.value.records[_index].predict = ''
  currentChat.value.records[_index].predict_data = ''

  try {
    const response = await chatApi.predict(id)
    const reader = response.body.getReader()
    const decoder = new TextDecoder()

    let predict_answer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) {
        isPredictTyping.value = false
        break
      }

      const chunk = decoder.decode(value)

      let _list = [chunk]

      const lines = chunk.trim().split('}\n\n{')
      if (lines.length > 1) {
        _list = []
        for (let line of lines) {
          if (!line.trim().startsWith('{')) {
            line = '{' + line.trim()
          }
          if (!line.trim().endsWith('}')) {
            line = line.trim() + '}'
          }
          _list.push(line)
        }
      }

      // console.log(_list)

      for (const str of _list) {
        let data
        try {
          data = JSON.parse(str)
        } catch (err) {
          console.error('JSON string:', str)
          throw err
        }

        if (data.code && data.code !== 200) {
          ElMessage({
            message: data.msg,
            type: 'error',
            showClose: true,
          })
          return
        }

        switch (data.type) {
          case 'info':
            console.log(data.msg)
            break
          case 'error':
            throw Error(data.content)
          case 'predict-result':
            predict_answer += data.content
            currentChat.value.records[_index].predict = predict_answer
            break
          case 'predict':
            currentChat.value.records[_index].predict_data = data.content
            break
          case 'predict_finish':
            isPredictTyping.value = false
            break
        }
        await nextTick()
      }
    }
  } catch (error) {
    console.error('Error:', error)
    ElMessage({
      message: error + '',
      type: 'error',
      showClose: true,
    })
    isPredictTyping.value = false
  }
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

.analysis-container {
  color: var(--ed-text-color-primary);
  font-size: 12px;
  line-height: 1.7692307692;
  padding: 16px 22px;
}
</style>
