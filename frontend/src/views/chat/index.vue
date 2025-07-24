<template>
  <el-container class="chat-container no-padding">
    <el-aside v-if="!isAssistant && chatListSideBarShow" class="chat-container-left">
      <ChatListContainer
        v-model:chat-list="chatList"
        v-model:current-chat-id="currentChatId"
        v-model:current-chat="currentChat"
        v-model:loading="loading"
        :in-popover="!chatListSideBarShow"
        @go-empty="goEmpty"
        @on-chat-created="onChatCreated"
        @on-click-history="onClickHistory"
        @on-chat-deleted="onChatDeleted"
        @on-chat-renamed="onChatRenamed"
        @on-click-side-bar-btn="hideSideBar"
      />
    </el-aside>
    <div v-if="!isAssistant && !chatListSideBarShow" class="hidden-sidebar-btn">
      <el-popover
        :width="280"
        placement="bottom-start"
        popper-style="padding: 0;
                      height: 654px;
                      border: 1px solid rgba(222, 224, 227, 1);
                      border-radius: 6px;
                      "
      >
        <template #reference>
          <el-button link type="primary" class="icon-btn" @click="showSideBar">
            <el-icon>
              <icon_sidebar_outlined />
            </el-icon>
          </el-button>
        </template>
        <ChatListContainer
          v-model:chat-list="chatList"
          v-model:current-chat-id="currentChatId"
          v-model:current-chat="currentChat"
          v-model:loading="loading"
          :in-popover="!chatListSideBarShow"
          @go-empty="goEmpty"
          @on-chat-created="onChatCreated"
          @on-click-history="onClickHistory"
          @on-chat-deleted="onChatDeleted"
          @on-chat-renamed="onChatRenamed"
          @on-click-side-bar-btn="hideSideBar"
        />
      </el-popover>
      <el-tooltip effect="dark" :content="t('qa.new_chat')" placement="bottom">
        <el-button link type="primary" class="icon-btn" @click="createNewChatSimple">
          <el-icon>
            <icon_new_chat_outlined />
          </el-icon>
        </el-button>
      </el-tooltip>
    </div>
    <el-container :loading="loading">
      <el-main
        class="chat-record-list"
        :class="{ 'hide-sidebar': !isAssistant && !chatListSideBarShow }"
      >
        <div v-if="computedMessages.length == 0 && !loading" class="welcome-content-block">
          <div class="welcome-content">
            <div class="greeting">
              <el-icon size="32">
                <logo_fold />
              </el-icon>
              {{ t('qa.greeting') }}
            </div>
            <div class="sub">{{ t('qa.hint_description') }}</div>
            <el-button
              v-if="currentChatId === undefined"
              size="large"
              type="primary"
              class="greeting-btn"
              @click="createNewChatSimple"
            >
              <span class="inner-icon">
                <el-icon>
                  <icon_new_chat_outlined />
                </el-icon>
              </span>
              {{ t('qa.start_sqlbot') }}
            </el-button>
          </div>
        </div>
        <div v-else-if="computedMessages.length == 0 && loading" class="welcome-content-block">
          <logo />
        </div>
        <el-scrollbar v-if="computedMessages.length > 0" ref="chatListRef">
          <div class="chat-scroll" :class="{ 'no-sidebar': !isAssistant && !chatListSideBarShow }">
            <template v-for="(message, _index) in computedMessages" :key="_index">
              <ChatRow :current-chat="currentChat" :msg="message" :hide-avatar="message.first_chat">
                <RecommendQuestion
                  v-if="message.role === 'assistant' && message.first_chat"
                  ref="recommendQuestionRef"
                  :current-chat="currentChat"
                  :record-id="message.record?.id"
                  :questions="message.recommended_question"
                  :disabled="isTyping"
                  :first-chat="message.first_chat"
                  @click-question="quickAsk"
                  @stop="onChatStop"
                />
                <UserChat v-if="message.role === 'user'" :message="message" />
                <template v-if="message.role === 'assistant' && !message.first_chat">
                  <ChartAnswer
                    v-if="
                      (message?.record?.analysis_record_id === undefined ||
                        message?.record?.analysis_record_id === null) &&
                      (message?.record?.predict_record_id === undefined ||
                        message?.record?.predict_record_id === null)
                    "
                    ref="chartAnswerRef"
                    :chat-list="chatList"
                    :current-chat="currentChat"
                    :current-chat-id="currentChatId"
                    :loading="isTyping"
                    :message="message"
                    :reasoning-name="['sql_answer', 'chart_answer']"
                    @finish="onChartAnswerFinish"
                    @error="onChartAnswerError"
                    @stop="onChatStop"
                  >
                    <ChartBlock style="margin-top: 12px" :message="message" />
                    <div
                      v-if="message.record?.error && message.record?.error?.trim().length > 0"
                      class="error-container"
                    >
                      {{ message.record?.error }}
                    </div>

                    <template #tool>
                      <ChatToolBar v-if="!message.isTyping" :message="message">
                        <div class="tool-btns">
                          <el-tooltip effect="dark" :content="t('qa.ask_again')" placement="top">
                            <el-button
                              class="tool-btn"
                              text
                              :disabled="isTyping"
                              @click="askAgain(message)"
                            >
                              <el-icon size="18">
                                <icon_replace_outlined />
                              </el-icon>
                            </el-button>
                          </el-tooltip>
                          <template v-if="message.record?.chart">
                            <div class="divider"></div>
                            <div>
                              <el-button
                                class="tool-btn"
                                text
                                :disabled="isTyping"
                                @click="clickAnalysis(message.record?.id)"
                              >
                                <span class="tool-btn-inner">
                                  <el-icon size="18">
                                    <icon_screen_outlined />
                                  </el-icon>
                                  <span class="btn-text">
                                    {{ t('chat.data_analysis') }}
                                  </span>
                                </span>
                              </el-button>
                            </div>
                            <div>
                              <el-button
                                class="tool-btn"
                                text
                                :disabled="isTyping"
                                @click="clickPredict(message.record?.id)"
                              >
                                <span class="tool-btn-inner">
                                  <el-icon size="18">
                                    <icon_start_outlined />
                                  </el-icon>
                                  <span class="btn-text">
                                    {{ t('chat.data_predict') }}
                                  </span>
                                </span>
                              </el-button>
                            </div>
                          </template>
                        </div>
                      </ChatToolBar>
                    </template>
                    <template #footer>
                      <RecommendQuestion
                        ref="recommendQuestionRef"
                        :current-chat="currentChat"
                        :record-id="message.record?.id"
                        :questions="message.recommended_question"
                        :first-chat="message.first_chat"
                        :disabled="isTyping"
                        @click-question="quickAsk"
                        @stop="onChatStop"
                      />
                    </template>
                  </ChartAnswer>
                  <AnalysisAnswer
                    v-if="
                      message?.record?.analysis_record_id !== undefined &&
                      message?.record?.analysis_record_id !== null
                    "
                    ref="analysisAnswerRef"
                    :chat-list="chatList"
                    :current-chat="currentChat"
                    :current-chat-id="currentChatId"
                    :loading="isTyping"
                    :message="message"
                    @finish="onAnalysisAnswerFinish"
                    @error="onAnalysisAnswerError"
                    @stop="onChatStop"
                  >
                    <div
                      v-if="message.record?.error && message.record?.error?.trim().length > 0"
                      class="error-container"
                    >
                      {{ message.record?.error }}
                    </div>
                    <template #tool>
                      <ChatToolBar v-if="!message.isTyping" :message="message" />
                    </template>
                  </AnalysisAnswer>
                  <PredictAnswer
                    v-if="
                      message?.record?.predict_record_id !== undefined &&
                      message?.record?.predict_record_id !== null
                    "
                    ref="predictAnswerRef"
                    :chat-list="chatList"
                    :current-chat="currentChat"
                    :current-chat-id="currentChatId"
                    :loading="isTyping"
                    :message="message"
                    @finish="onPredictAnswerFinish"
                    @error="onPredictAnswerError"
                    @stop="onChatStop"
                  >
                    <ChartBlock style="margin-top: 12px" :message="message" is-predict />
                    <div
                      v-if="message.record?.error && message.record?.error?.trim().length > 0"
                      class="error-container"
                    >
                      {{ message.record?.error }}
                    </div>
                    <template #tool>
                      <ChatToolBar v-if="!message.isTyping" :message="message" />
                    </template>
                  </PredictAnswer>
                </template>
              </ChatRow>
            </template>
          </div>
        </el-scrollbar>
      </el-main>
      <el-footer
        v-if="computedMessages.length > 0 || (isAssistant && currentChatId)"
        class="chat-footer"
      >
        <div class="input-container" @click="clickInput">
          <div class="datasource">
            <template v-if="currentChat.datasource && currentChat.datasource_name">
              {{ t('qa.selected_datasource') }}：
              <span class="name">
                {{ currentChat.datasource_name }}
              </span>
            </template>
          </div>
          <div class="input-wrapper">
            <el-input
              ref="inputRef"
              v-model="inputMessage"
              :disabled="isTyping"
              class="input-area"
              type="textarea"
              :rows="1"
              :autosize="{ minRows: 1, maxRows: 8 }"
              :placeholder="t('qa.question_placeholder')"
              @keydown.enter.exact.prevent="sendMessage"
              @keydown.ctrl.enter.exact.prevent="handleCtrlEnter"
            />
          </div>
          <el-button
            circle
            type="primary"
            class="input-icon"
            :disabled="isTyping"
            @click.stop="sendMessage"
          >
            <el-icon size="16">
              <icon_send_filled />
            </el-icon>
          </el-button>
        </div>
      </el-footer>
    </el-container>

    <ChatCreator v-if="!isAssistant" ref="chatCreatorRef" @on-chat-created="onChatCreatedQuick" />
    <ChatCreator ref="hiddenChatCreatorRef" hidden @on-chat-created="onChatCreatedQuick" />
  </el-container>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { Chat, chatApi, ChatInfo, type ChatMessage, ChatRecord } from '@/api/chat'
import ChatRow from './ChatRow.vue'
import ChartAnswer from './answer/ChartAnswer.vue'
import AnalysisAnswer from './answer/AnalysisAnswer.vue'
import PredictAnswer from './answer/PredictAnswer.vue'
import UserChat from './chat-block/UserChat.vue'
import ChartBlock from './chat-block/ChartBlock.vue'
import RecommendQuestion from './RecommendQuestion.vue'
import ChatListContainer from './ChatListContainer.vue'
import ChatCreator from '@/views/chat/ChatCreator.vue'
import ChatToolBar from './ChatToolBar.vue'
import { useI18n } from 'vue-i18n'
import { find } from 'lodash-es'
import icon_new_chat_outlined from '@/assets/svg/icon_new_chat_outlined.svg'
import icon_sidebar_outlined from '@/assets/svg/icon_sidebar_outlined.svg'
import icon_replace_outlined from '@/assets/svg/icon_replace_outlined.svg'
import icon_screen_outlined from '@/assets/svg/icon_screen_outlined.svg'
import icon_start_outlined from '@/assets/svg/icon_start_outlined.svg'
import logo_fold from '@/assets/LOGO-fold.svg'
import logo from '@/assets/LOGO.svg'
import icon_send_filled from '@/assets/svg/icon_send_filled.svg'

import { useAssistantStore } from '@/stores/assistant'

const props = defineProps<{
  startChatDsId?: number
}>()

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
        record: record,
        content: record.question,
        index: i,
      })
    }
    messages.push({
      role: 'assistant',
      create_time: record.create_time,
      record: record,
      isTyping: i === currentChat.value.records.length - 1 && isTyping.value,
      first_chat: record.first_chat,
      recommended_question: record.recommended_question,
      index: i,
    })
  }

  return messages
})

const goEmpty = (func?: (...p: any[]) => void, ...param: any[]) => {
  inputMessage.value = ''
  stop(func, ...param)
}

const createNewChatSimple = async () => {
  currentChat.value = new ChatInfo()
  currentChatId.value = undefined
  await createNewChat()
}

const createNewChat = async () => {
  goEmpty()
  if (isAssistant.value) {
    const assistantChat = await assistantStore.setChat()
    if (assistantChat) {
      onChatCreatedQuick(assistantChat as any)
    }
    return
  }
  chatCreatorRef.value?.showDs()
}

function getChatList(callback?: () => void) {
  loading.value = true
  chatApi
    .list()
    .then((res) => {
      chatList.value = chatApi.toChatInfoList(res)
    })
    .finally(() => {
      loading.value = false
      if (callback && typeof callback === 'function') {
        callback()
      }
    })
}

function onClickHistory(chat: Chat) {
  scrollToBottom()
  console.debug('click history', chat)
}

function toAssistantHistory(chat: Chat) {
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
          onClickHistory(info)
        }
      })
      .finally(() => {
        loading.value = false
      })
  }
}

function onChatDeleted(id: number) {
  console.log('deleted', id)
}

function onChatRenamed(chat: Chat) {
  console.log('renamed', chat)
}

const chatListSideBarShow = ref<boolean>(true)
function hideSideBar() {
  chatListSideBarShow.value = false
}

function showSideBar() {
  chatListSideBarShow.value = true
}

function onChatCreatedQuick(chat: ChatInfo) {
  chatList.value.unshift(chat)
  currentChatId.value = chat.id
  currentChat.value = chat
  onChatCreated(chat)
}

function onChatCreated(chat: ChatInfo) {
  if (chat.records.length === 1) {
    getRecommendQuestions(chat.records[0].id)
  }
}

const recommendQuestionRef = ref()

function getRecommendQuestions(id?: number) {
  nextTick(() => {
    if (recommendQuestionRef.value) {
      if (recommendQuestionRef.value instanceof Array) {
        for (let i = 0; i < recommendQuestionRef.value.length; i++) {
          const _id = recommendQuestionRef.value[i].id()
          if (_id === id) {
            recommendQuestionRef.value[i].getRecommendQuestions()
            break
          }
        }
      } else {
        recommendQuestionRef.value.getRecommendQuestions()
      }
    }
  })
}

function quickAsk(question: string) {
  inputMessage.value = question
  nextTick(() => {
    sendMessage()
  })
}

const chartAnswerRef = ref()

async function onChartAnswerFinish(id: number) {
  loading.value = false
  isTyping.value = false
  getRecommendQuestions(id)
}

function onChartAnswerError() {
  loading.value = false
  isTyping.value = false
  console.debug('onChartAnswerError')
}

function onChatStop() {
  loading.value = false
  isTyping.value = false
  console.debug('onChatStop')
}

const sendMessage = async () => {
  if (!inputMessage.value.trim()) return

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

  nextTick(async () => {
    const index = currentChat.value.records.length - 1
    if (chartAnswerRef.value) {
      if (chartAnswerRef.value instanceof Array) {
        for (let i = 0; i < chartAnswerRef.value.length; i++) {
          const _index = chartAnswerRef.value[i].index()
          if (index === _index) {
            await chartAnswerRef.value[i].sendMessage()
            break
          }
        }
      } else {
        await chartAnswerRef.value.sendMessage()
      }
    }
  })
}

function getChatPredictData(recordId?: number) {
  chatApi.get_chart_predict_data(recordId).then((response) => {
    currentChat.value.records.forEach((record) => {
      if (record.id === recordId) {
        record.predict_data = response.data ?? []
      }
    })
  })
}

const analysisAnswerRef = ref()

async function onAnalysisAnswerFinish(id: number) {
  loading.value = false
  isTyping.value = false
  console.debug(id)
  //await getRecommendQuestions(id)
}
function onAnalysisAnswerError() {
  loading.value = false
  isTyping.value = false
}

function askAgain(message: ChatMessage) {
  inputMessage.value = message.record?.question ?? ''
  nextTick(() => {
    sendMessage()
  })
}

async function clickAnalysis(id?: number) {
  const baseRecord = find(currentChat.value.records, (value) => id === value.id)
  if (baseRecord == undefined) {
    return
  }

  loading.value = true
  isTyping.value = true

  const currentRecord = new ChatRecord()
  currentRecord.create_time = new Date()
  currentRecord.chat_id = baseRecord.chat_id
  currentRecord.question = baseRecord.question
  currentRecord.chart = baseRecord.chart
  currentRecord.data = baseRecord.data
  currentRecord.analysis_record_id = id
  currentRecord.analysis = ''

  currentChat.value.records.push(currentRecord)

  nextTick(async () => {
    const index = currentChat.value.records.length - 1
    if (analysisAnswerRef.value) {
      if (analysisAnswerRef.value instanceof Array) {
        for (let i = 0; i < analysisAnswerRef.value.length; i++) {
          const _index = analysisAnswerRef.value[i].index()
          if (index === _index) {
            await analysisAnswerRef.value[i].sendMessage()
            break
          }
        }
      } else {
        await analysisAnswerRef.value.sendMessage()
      }
    }
  })

  return
}

const predictAnswerRef = ref()

async function onPredictAnswerFinish(id: number) {
  loading.value = false
  isTyping.value = false
  getChatPredictData(id)
  //await getRecommendQuestions(id)
}
function onPredictAnswerError() {
  loading.value = false
  isTyping.value = false
}

async function clickPredict(id?: number) {
  const baseRecord = find(currentChat.value.records, (value) => id === value.id)
  if (baseRecord == undefined) {
    return
  }

  loading.value = true
  isTyping.value = true

  const currentRecord = new ChatRecord()
  currentRecord.create_time = new Date()
  currentRecord.chat_id = baseRecord.chat_id
  currentRecord.question = baseRecord.question
  currentRecord.chart = baseRecord.chart
  currentRecord.data = baseRecord.data
  currentRecord.predict_record_id = id
  currentRecord.predict = ''
  currentRecord.predict_data = ''

  currentChat.value.records.push(currentRecord)

  nextTick(async () => {
    const index = currentChat.value.records.length - 1
    if (predictAnswerRef.value) {
      if (predictAnswerRef.value instanceof Array) {
        for (let i = 0; i < predictAnswerRef.value.length; i++) {
          const _index = predictAnswerRef.value[i].index()
          if (index === _index) {
            await predictAnswerRef.value[i].sendMessage()
            break
          }
        }
      } else {
        await predictAnswerRef.value.sendMessage()
      }
    }
  })

  return
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

const inputRef = ref()

function clickInput() {
  inputRef.value?.focus()
}

function stop(func?: (...p: any[]) => void, ...param: any[]) {
  if (recommendQuestionRef.value) {
    if (recommendQuestionRef.value instanceof Array) {
      for (let i = 0; i < recommendQuestionRef.value.length; i++) {
        recommendQuestionRef.value[i].stop()
      }
    } else {
      recommendQuestionRef.value.stop()
    }
  }
  if (chartAnswerRef.value) {
    if (chartAnswerRef.value instanceof Array) {
      for (let i = 0; i < chartAnswerRef.value.length; i++) {
        chartAnswerRef.value[i].stop()
      }
    } else {
      chartAnswerRef.value.stop()
    }
  }
  if (analysisAnswerRef.value) {
    if (analysisAnswerRef.value instanceof Array) {
      for (let i = 0; i < analysisAnswerRef.value.length; i++) {
        analysisAnswerRef.value[i].stop()
      }
    } else {
      analysisAnswerRef.value.stop()
    }
  }
  if (predictAnswerRef.value) {
    if (predictAnswerRef.value instanceof Array) {
      for (let i = 0; i < predictAnswerRef.value.length; i++) {
        predictAnswerRef.value[i].stop()
      }
    } else {
      predictAnswerRef.value.stop()
    }
  }
  if (func && typeof func === 'function') {
    func(...param)
  }
}

defineExpose({
  getHistoryList,
  toAssistantHistory,
  getCurrentChatId,
  createNewChat,
})

const hiddenChatCreatorRef = ref()

function jumpCreatChat() {
  if (props.startChatDsId) {
    const _id = props.startChatDsId
    nextTick(() => {
      hiddenChatCreatorRef.value?.createChat(_id)
    })
    const newUrl = window.location.hash.replace(/\?.*$/, '')
    history.replaceState({}, '', newUrl)
  }
}

onMounted(() => {
  getChatList(jumpCreatChat)
})
</script>

<style lang="less" scoped>
.chat-container {
  height: 100%;
  position: relative;

  border-radius: 12px;

  .hidden-sidebar-btn {
    z-index: 1;
    position: absolute;
    padding: 16px;
    top: 0;
    left: 0;
  }

  .icon-btn {
    min-width: unset;
    width: 26px;
    height: 26px;
    font-size: 18px;

    --ed-button-text-color: rgba(31, 35, 41, 1);
    --ed-button-hover-text-color: var(--ed-button-text-color);
    --ed-button-active-text-color: var(--ed-button-text-color);
    --ed-button-hover-link-text-color: var(--ed-button-text-color);
    &:hover {
      background: rgba(31, 35, 41, 0.1);
    }
  }

  .chat-container-left {
    --ed-aside-width: 280px;
    border-radius: 12px 0 0 12px;

    background: rgba(245, 246, 247, 1);
  }

  .chat-record-list {
    padding: 0 0 20px 0;
    border-radius: 0 12px 12px 0;

    &.hide-sidebar {
      border-radius: 12px;
    }
  }

  .chat-scroll {
    width: 100%;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding-left: 56px;
    padding-right: 56px;

    &.no-sidebar {
      padding-left: 96px;
    }
  }

  .chat-footer {
    min-height: calc(120px + 16px);
    max-height: calc(300px + 16px);
    height: fit-content;

    padding-bottom: 16px;

    display: flex;
    flex-direction: column;
    align-items: center;

    .input-container {
      flex: 1;
      display: flex;
      flex-direction: column;
      align-items: center;
      width: 100%;
      max-width: 800px;
      border-radius: 16px;
      border: 1px solid rgba(217, 220, 223, 1);
      background: rgba(248, 249, 250, 1);
      padding: 12px;
      gap: 8px;

      position: relative;

      .input-icon {
        min-width: unset;
        position: absolute;
        bottom: 12px;
        right: 12px;

        border-color: unset;

        &.is-disabled {
          background: rgba(187, 191, 196, 1);
          border-color: unset;
        }
      }

      &:hover {
        border-color: rgba(28, 186, 144, 1);
      }
    }

    .datasource {
      width: 100%;

      line-height: 22px;
      font-size: 14px;
      font-weight: 400;
      color: rgba(100, 106, 115, 1);

      .name {
        color: rgba(31, 35, 41, 1);
      }
    }

    .input-wrapper {
      width: 100%;
      flex: 1;

      .input-area {
        height: 100%;

        :deep(.ed-textarea__inner) {
          height: 100% !important;
          background: transparent;
          box-shadow: unset;
          padding: unset;
        }
      }
    }
  }

  .send-btn {
    min-width: 0;
  }
}

.error-container {
  margin-top: 12px;
  font-weight: 400;
  font-size: 16px;
  line-height: 24px;
  color: rgba(31, 35, 41, 1);
}

.tool-btns {
  display: flex;
  flex-direction: row;
  align-items: center;
  flex-wrap: wrap;

  column-gap: 16px;
  row-gap: 8px;

  .tool-btn {
    font-size: 14px;
    font-weight: 400;
    line-height: 22px;
    color: rgba(100, 106, 115, 1);

    .tool-btn-inner {
      display: flex;
      flex-direction: row;
      align-items: center;
    }

    &:hover {
      background: rgba(31, 35, 41, 0.1);
    }
    &:active {
      background: rgba(31, 35, 41, 0.1);
    }
  }

  .btn-text {
    margin-left: 4px;
  }

  .divider {
    width: 1px;
    height: 16px;
    border-left: 1px solid rgba(31, 35, 41, 0.15);
  }
}

.welcome-content-block {
  height: 100%;
  width: 100%;

  display: flex;
  justify-content: center;
  align-items: center;

  .welcome-content {
    width: 100%;
    max-width: 800px;
    display: flex;
    gap: 16px;
    align-items: center;
    flex-direction: column;

    .greeting {
      display: flex;
      align-items: center;
      gap: 16px;
      line-height: 32px;
      font-size: 24px;
      font-weight: 600;
      color: rgba(31, 35, 41, 1);
    }

    .sub {
      color: grey;
      font-size: 16px;
      line-height: 24px;
    }

    .greeting-btn {
      width: 100%;
      height: 88px;

      border-style: dashed;

      .inner-icon {
        display: flex;
        flex-direction: row;
        align-items: center;

        margin-right: 6px;
      }

      font-size: 16px;
      line-height: 24px;
      font-weight: 500;

      --ed-button-text-color: rgba(28, 186, 144, 1);
      --ed-button-hover-text-color: rgba(28, 186, 144, 1);
      --ed-button-active-text-color: rgba(28, 186, 144, 1);
      --ed-button-bg-color: rgba(248, 249, 250, 1);
      --ed-button-hover-bg-color: rgba(28, 186, 144, 0.1);
      --ed-button-border-color: rgba(217, 220, 223, 1);
      --ed-button-hover-border-color: rgba(28, 186, 144, 1);
      --ed-button-active-bg-color: rgba(28, 186, 144, 0.2);
      --ed-button-active-border-color: rgba(28, 186, 144, 1);
    }
  }
}
</style>
