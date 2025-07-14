<template>
  <el-container class="chat-container no-padding">
    <el-aside v-if="!isAssistant" class="chat-container-left">
      <el-container class="chat-container-right-container">
        <el-header class="chat-list-header">
          <div class="title">
            <div>智能问数</div>
            <el-button link type="primary" class="icon-btn">
              <el-icon>
                <icon_sidebar_outlined />
              </el-icon>
            </el-button>
          </div>
          <el-button class="btn" type="primary" @click="createNewChat">
            <el-icon>
              <Plus />
            </el-icon>
            {{ t('qa.New Conversation') }}
          </el-button>
          <el-input v-model="search" class="search" placeholder="placeholder" />
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
        <div v-if="computedMessages.length == 0" class="welcome-content-block">
          <div class="welcome-content">
            <div class="logo">SQLBot</div>
            <div>{{ t('qa.greeting') }}</div>
            <div class="sub">{{ t('qa.description') }}</div>
            <el-button
              v-if="currentChatId === undefined"
              size="large"
              type="primary"
              @click="createNewChat"
            >
              <el-icon>
                <Plus />
              </el-icon>
              {{ t('qa.New Conversation') }}
            </el-button>
          </div>
        </div>
        <el-scrollbar v-if="computedMessages.length > 0" ref="chatListRef">
          <template v-for="(message, _index) in computedMessages" :key="_index">
            <ChatRow :current-chat="currentChat" :msg="message">
              <template v-if="message.role === 'assistant'">
                <ChatAnswer
                  v-if="
                    message?.record?.analysis_record_id == undefined &&
                    message?.record?.predict_record_id == undefined
                  "
                  :message="message"
                >
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
                  </template>
                </ChatAnswer>
              </template>
              <div
                v-if="
                  message?.record?.analysis_record_id != undefined ||
                  message?.record?.predict_record_id != undefined
                "
                class="analysis-container"
              >
                <template v-if="message.record?.analysis || isAnalysisTyping">
                  <MdComponent :message="message.record?.analysis_thinking" />
                  <MdComponent :message="message.record?.analysis" />
                </template>

                <el-divider
                  v-if="
                    (message.record?.analysis || isAnalysisTyping) &&
                    (message.record?.predict || isPredictTyping)
                  "
                />
                <template v-if="message.record?.predict || isPredictTyping">
                  <MdComponent :message="message.record?.predict" />
                  <MdComponent :message="message.record?.predict_content" />
                  <!--                  <PredictChartBlock-->
                  <!--                    :id="message.record?.id + '-predict'"-->
                  <!--                    :data="message.record?.predict_data ?? '[]'"-->
                  <!--                    :message="message"-->
                  <!--                    :chart-type="data.chartType"-->
                  <!--                  />-->
                </template>
              </div>
              <template v-if="message.role === 'assistant'" #footer>
                <RecommendQuestion
                  :questions="message.recommended_question"
                  @click-question="quickAsk"
                />
              </template>
            </ChatRow>
          </template>
        </el-scrollbar>
      </el-main>
      <el-footer
        v-if="computedMessages.length > 0 || (isAssistant && currentChatId)"
        class="chat-footer"
      >
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

    <ChatCreator v-if="!isAssistant" ref="chatCreatorRef" @on-chat-created="onChatCreated" />
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
// import PredictChartBlock from './component/PredictChartBlock.vue'
import RecommendQuestion from './RecommendQuestion.vue'
import ChatCreator from './ChatCreator.vue'
import { useI18n } from 'vue-i18n'
import icon_sidebar_outlined from '@/assets/svg/icon_sidebar_outlined.svg'
import { endsWith, find, startsWith } from 'lodash-es'

import { useAssistantStore } from '@/stores/assistant'
const assistantStore = useAssistantStore()

const isAssistant = computed(() => assistantStore.getAssistant)

const { t } = useI18n()

const inputMessage = ref('')

const chatListRef = ref()
const chatCreatorRef = ref()

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
  const messages: Array<ChatMessage> = []
  if (currentChatId.value === undefined) {
    return messages
  }
  for (let i = 0; i < currentChat.value.records.length; i++) {
    const record = currentChat.value.records[i]
    if (record.question !== undefined && !record.first_chat) {
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
      first_chat: record.first_chat,
      recommended_question: record.recommended_question,
    })
  }

  return messages
})

const goEmpty = () => {
  currentChat.value = new ChatInfo()
  currentChatId.value = undefined
  inputMessage.value = ''
}

const search = ref<string>()

const createNewChat = async () => {
  goEmpty()
  if (isAssistant.value) {
    const assistantChat = await assistantStore.setChat()
    if (assistantChat) {
      onChatCreated(assistantChat as any)
    }
    return
  }
  chatCreatorRef.value?.showDs()
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
      break
    }
  }
  if (id === currentChatId.value) {
    goEmpty()
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

function onChatCreated(chat: ChatInfo) {
  chatList.value.unshift(chat)
  currentChatId.value = chat.id
  currentChat.value = chat
  if (chat.records.length === 1) {
    getRecommendQuestions(chat.records[0].id)
  }
}

async function getRecommendQuestions(record_id?: number) {
  /*chatApi.recommendQuestions(record_id).then((res) => {
    if (res && res.length > 0 && startsWith(res.trim(), '[') && endsWith(res.trim(), ']')) {
      if (currentChat.value?.records) {
        for (let record of currentChat.value.records) {
          if (record.id === record_id) {
            record.recommended_question = res
          }
        }
      }
    }
  })*/
  const response = await chatApi.recommendQuestions(record_id)
  const reader = response.body.getReader()
  const decoder = new TextDecoder()

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
        case 'recommended_question':
          if (
            data.content &&
            data.content.length > 0 &&
            startsWith(data.content.trim(), '[') &&
            endsWith(data.content.trim(), ']')
          ) {
            if (currentChat.value?.records) {
              for (let record of currentChat.value.records) {
                if (record.id === record_id) {
                  record.recommended_question = data.content
                }
              }
            }
          }
      }
    }
  }
}

onMounted(() => {
  getChatList()
})

function quickAsk(question: string) {
  inputMessage.value = question
  nextTick(() => {
    sendMessage()
  })
}

const sendMessage = async () => {
  if (!inputMessage.value.trim()) return

  loading.value = true
  isTyping.value = true

  /* const assistantChat = await assistantStore.setChat()
  if (assistantChat) {
    onChatCreated(assistantChat as any)
  } */

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

  let error: boolean = false
  if (currentChatId.value === undefined) {
    error = true
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
            currentRecord.id = data.id
            currentChat.value.records[currentChat.value.records.length - 1].id = data.id
            break
          case 'info':
            console.log(data.msg)
            break
          case 'brief':
            currentChat.value.brief = data.brief
            chatList.value.forEach((c: Chat) => {
              if (c.id === currentChat.value.id) {
                c.brief = currentChat.value.brief
              }
            })
            break
          case 'error':
            currentRecord.error = data.content
            isTyping.value = false
            break
          case 'sql-result':
            sql_answer += data.reasoning_content
            currentChat.value.records[currentChat.value.records.length - 1].sql_answer = sql_answer
            break
          case 'sql':
            currentChat.value.records[currentChat.value.records.length - 1].sql = data.content
            break
          case 'sql-data':
            //currentChat.value.records[currentChat.value.records.length - 1].data = data.content
            getChatData(currentChat.value.records[currentChat.value.records.length - 1].id)
            break
          case 'chart-result':
            chart_answer += data.reasoning_content
            currentChat.value.records[currentChat.value.records.length - 1].chart_answer =
              chart_answer
            break
          case 'chart':
            currentChat.value.records[currentChat.value.records.length - 1].chart = data.content
            break
          case 'finish':
            isTyping.value = false
            await getRecommendQuestions(currentRecord.id)
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
  } finally {
    loading.value = false
  }
}

function getChatData(recordId?: number) {
  chatApi.get_chart_data(recordId).then((response) => {
    currentChat.value.records.forEach((record) => {
      if (record.id === recordId) {
        record.data = response
      }
    })
  })
}

function getChatPredictData(recordId?: number) {
  chatApi.get_chart_predict_data(recordId).then((response) => {
    currentChat.value.records.forEach((record) => {
      if (record.id === recordId) {
        record.predict_data = response
      }
    })
  })
}

async function clickAnalysis(id?: number) {
  const baseRecord = find(currentChat.value.records, (value) => id === value.id)
  if (baseRecord == undefined) {
    return
  }

  const currentRecord = new ChatRecord()
  currentRecord.create_time = new Date()
  currentRecord.chat_id = baseRecord.chat_id
  currentRecord.question = baseRecord.question
  currentRecord.chart = baseRecord.chart
  currentRecord.data = baseRecord.data
  currentRecord.analysis_record_id = id

  currentChat.value.records.push(currentRecord)

  let _index = currentChat.value.records.length - 1

  isAnalysisTyping.value = true
  currentChat.value.records[_index].analysis = ''

  try {
    const response = await chatApi.analysis(id)
    const reader = response.body.getReader()
    const decoder = new TextDecoder()

    let analysis_answer = ''
    let analysis_answer_thinking = ''

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
            analysis_answer_thinking += data.reasoning_content
            currentChat.value.records[_index].analysis = analysis_answer
            currentChat.value.records[_index].analysis_thinking = analysis_answer_thinking
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
  const baseRecord = find(currentChat.value.records, (value) => id === value.id)
  if (baseRecord == undefined) {
    return
  }

  const currentRecord = new ChatRecord()
  currentRecord.create_time = new Date()
  currentRecord.chat_id = baseRecord.chat_id
  currentRecord.question = baseRecord.question
  currentRecord.chart = baseRecord.chart
  currentRecord.data = baseRecord.data
  currentRecord.predict_record_id = id

  currentChat.value.records.push(currentRecord)

  let _index = currentChat.value.records.length - 1

  isPredictTyping.value = true
  currentChat.value.records[_index].predict = ''
  currentChat.value.records[_index].predict_data = ''

  try {
    const response = await chatApi.predict(id)
    const reader = response.body.getReader()
    const decoder = new TextDecoder()

    let predict_answer = ''
    let predict_content = ''

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
            predict_answer += data.reasoning_content
            predict_content += data.content
            currentChat.value.records[_index].predict = predict_answer
            currentChat.value.records[_index].predict_content = predict_content
            break
          case 'predict-failed':
            break
          case 'predict-success':
            //currentChat.value.records[_index].predict_data = data.content
            getChatPredictData(currentChat.value.records[_index].id)
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

const getHistoryList = () => {
  return chatList.value
}
const getCurrentChatId = () => {
  return currentChatId.value
}
defineExpose({
  getHistoryList,
  onClickHistory,
  onChatDeleted,
  onChatRenamed,
  getCurrentChatId,
})
</script>

<style lang="less" scoped>
.chat-container {
  height: 100%;

  .icon-btn {
    min-width: unset;
    width: 26px;
    height: 26px;
    font-size: 18px;

    &:hover {
      background: rgba(31, 35, 41, 0.1);
    }
  }

  .chat-container-left {
    --ed-aside-width: 280px;
    border-radius: 12px 0 0 12px;
    //box-shadow: 0 0 3px #d7d7d7;
    //z-index: 1;

    background: rgba(245, 246, 247, 1);

    .chat-container-right-container {
      height: 100%;

      .chat-list-header {
        --ed-header-padding: 16px;
        --ed-header-height: calc(16px + 24px + 16px + 40px + 16px + 32px + 16px);

        display: flex;
        align-items: center;
        justify-content: center;
        flex-direction: column;
        gap: 16px;

        .title {
          height: 24px;
          width: 100%;
          display: flex;
          flex-direction: row;
          align-items: center;
          justify-content: space-between;
          font-weight: 500;
        }

        .btn {
          width: 100%;
          height: 40px;
        }

        .search {
          height: 32px;
          width: 100%;
        }
      }

      .chat-list {
        padding: 0 0 20px 0;
      }
    }
  }

  .chat-record-list {
    padding: 0 0 20px 0;
    background: rgba(255, 255, 255, 1);
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

.welcome-content-block {
  height: 100%;
  width: 100%;

  display: flex;
  justify-content: center;
  align-items: center;

  .welcome-content {
    padding: 12px;

    width: fit-content;
    display: flex;
    gap: 16px;
    align-items: center;
    flex-direction: column;

    .logo {
      line-height: 60px;
      font-size: 3em;
      font-weight: bold;
      color: var(--el-color-primary);
      text-align: left;
    }

    .sub {
      color: grey;
      font-size: 0.8em;
    }
  }
}
</style>
