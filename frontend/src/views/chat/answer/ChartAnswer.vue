<script setup lang="ts">
import BaseAnswer from './BaseAnswer.vue'
import { Chat, chatApi, ChatInfo, type ChatMessage, ChatRecord, questionApi } from '@/api/chat.ts'
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import ChartBlock from '@/views/chat/chat-block/ChartBlock.vue'
import MdComponent from '@/views/chat/component/MdComponent.vue'
import JSONBig from 'json-bigint'
import { parseSseChunk } from '@/utils/sse'

const props = withDefaults(
  defineProps<{
    recordId?: number
    chatList?: Array<ChatInfo>
    currentChatId?: number
    currentChat?: ChatInfo
    message?: ChatMessage
    loading?: boolean
    reasoningName: 'sql_answer' | 'chart_answer' | Array<'sql_answer' | 'chart_answer'>
  }>(),
  {
    recordId: undefined,
    chatList: () => [],
    currentChatId: undefined,
    currentChat: () => new ChatInfo(),
    message: undefined,
    loading: false,
  }
)

const emits = defineEmits([
  'finish',
  'error',
  'stop',
  'scrollBottom',
  'update:loading',
  'update:chatList',
  'update:currentChat',
  'update:currentChatId',
])

const index = computed(() => {
  if (props.message?.index) {
    return props.message.index
  }
  if (props.message?.index === 0) {
    return 0
  }
  return -1
})

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

const _loading = computed({
  get() {
    return props.loading
  },
  set(v) {
    emits('update:loading', v)
  },
})

const stopFlag = ref(false)
const POLL_INTERVAL_MS = 1000
const activeTaskStoragePrefix = 'chat.smartQa.activeTask.'

interface ActiveTaskState {
  task_id: string
  offset: number
}

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

function activeTaskStorageKey(record: ChatRecord) {
  const chatId = record.chat_id || _currentChatId.value || 'unknown'
  const recordId = record.create_time || record.question || index.value
  return `${activeTaskStoragePrefix}${chatId}.${recordId}`
}

function rememberActiveTask(record: ChatRecord, taskId: string, offset = 0) {
  sessionStorage.setItem(
    activeTaskStorageKey(record),
    JSON.stringify({
      task_id: taskId,
      offset,
    })
  )
}

function forgetActiveTask(record: ChatRecord) {
  sessionStorage.removeItem(activeTaskStorageKey(record))
}

function rememberedActiveTask(record: ChatRecord): ActiveTaskState | undefined {
  if (record.task_id) {
    return { task_id: record.task_id, offset: 0 }
  }
  const raw = sessionStorage.getItem(activeTaskStorageKey(record))
  if (!raw) {
    return undefined
  }
  try {
    const parsed = JSON.parse(raw)
    if (parsed?.task_id) {
      return {
        task_id: parsed.task_id,
        offset: Number(parsed.offset || 0),
      }
    }
  } catch {
    return { task_id: raw, offset: 0 }
  }
  return undefined
}

async function handlePayload(
  payload: string,
  currentRecord: ChatRecord,
  state: { sql_answer: string; chart_answer: string }
) {
  let data
  try {
    data = JSONBig.parse(payload)
  } catch (err) {
    console.error('JSON string:', payload)
    throw err
  }

  if (data.code && data.code !== 200) {
    ElMessage({
      message: data.msg,
      type: 'error',
      showClose: true,
    })
    _loading.value = false
    return
  }

  switch (data.type) {
    case 'id':
      currentRecord.id = data.id
      _currentChat.value.records[index.value].id = data.id
      break
    case 'regenerate_record_id':
      currentRecord.regenerate_record_id = data.regenerate_record_id
      _currentChat.value.records[index.value].regenerate_record_id = data.regenerate_record_id
      break
    case 'question':
      currentRecord.question = data.question
      _currentChat.value.records[index.value].question = data.question
      break
    case 'info':
      console.info(data.msg)
      break
    case 'brief':
      _currentChat.value.brief = data.brief
      _chatList.value.forEach((c: Chat) => {
        if (c.id === _currentChat.value.id) {
          c.brief = _currentChat.value.brief
        }
      })
      break
    case 'error':
      currentRecord.error = data.content
      emits('error', currentRecord.id)
      break
    case 'sql-result':
      state.sql_answer += data.reasoning_content || ''
      _currentChat.value.records[index.value].sql_answer = state.sql_answer
      break
    case 'sql':
      _currentChat.value.records[index.value].sql = data.content
      break
    case 'sql-data':
      getChatData(_currentChat.value.records[index.value].id)
      break
    case 'chart-result':
      state.chart_answer += data.reasoning_content || ''
      _currentChat.value.records[index.value].chart_answer = state.chart_answer
      break
    case 'chart':
      _currentChat.value.records[index.value].chart = data.content
      break
    case 'datasource':
      if (!_currentChat.value.datasource) {
        _currentChat.value.datasource = data.id
      }
      break
    case 'finish':
      emits('finish', currentRecord.id)
      break
  }
  await nextTick()
}

async function pollQuestionTask(taskId: string, currentRecord: ChatRecord, initialOffset = 0) {
  const state = {
    sql_answer: _currentChat.value.records[index.value].sql_answer || '',
    chart_answer: _currentChat.value.records[index.value].chart_answer || '',
  }
  let offset = initialOffset

  while (true) {
    if (stopFlag.value) {
      break
    }

    const eventPage = await questionApi.getTaskEvents(taskId, offset)
    offset = eventPage.next_offset ?? offset
    rememberActiveTask(currentRecord, taskId, offset)
    for (const eventChunk of eventPage.events || []) {
      const parsed = parseSseChunk('', eventChunk)
      for (const payload of parsed.payloads) {
        await handlePayload(payload, currentRecord, state)
      }
    }

    if (['succeeded', 'failed'].includes(eventPage.status)) {
      forgetActiveTask(currentRecord)
      if (eventPage.status === 'failed' && eventPage.error && !currentRecord.error) {
        currentRecord.error = eventPage.error
        emits('error', currentRecord.id)
      }
      _loading.value = false
      break
    }

    await sleep(POLL_INTERVAL_MS)
  }
}

const sendMessage = async () => {
  stopFlag.value = false
  _loading.value = true

  if (index.value < 0) {
    _loading.value = false
    return
  }

  const currentRecord: ChatRecord = _currentChat.value.records[index.value]
  if (currentRecord.local_answer) {
    _loading.value = false
    return
  }

  let error: boolean = false
  if (_currentChatId.value === undefined) {
    error = true
  }
  if (error) return

  try {
    const param = {
      question: currentRecord.question,
      chat_id: _currentChatId.value,
      custom_prompt_id: currentRecord.custom_prompt_id,
      data_skill_id: currentRecord.data_skill_id,
    }
    const task = await questionApi.startTask(param)
    currentRecord.task_id = task.task_id
    _currentChat.value.records[index.value].task_id = task.task_id
    rememberActiveTask(currentRecord, task.task_id)
    await pollQuestionTask(task.task_id, currentRecord)
  } catch (error) {
    if (!currentRecord.error) {
      currentRecord.error = ''
    }
    if (currentRecord.error.trim().length !== 0) {
      currentRecord.error = currentRecord.error + '\n'
    }
    currentRecord.error = currentRecord.error + 'Error:' + error
    console.error('Error:', error)
    emits('error')
  } finally {
    _loading.value = false
  }
}

const loadingData = ref(false)

function hasRecordData(record?: ChatRecord) {
  if (!record?.data) {
    return false
  }
  if (typeof record.data === 'string') {
    return record.data.trim().length > 0
  }
  return Array.isArray(record.data?.data) ? record.data.data.length > 0 : !!record.data
}

function getChatData(recordId?: number) {
  const currentRecord = _currentChat.value.records.find((record) => record.id === recordId)
  if (hasRecordData(currentRecord)) {
    return
  }

  loadingData.value = true
  chatApi
    .get_chart_data(recordId)
    .then((response) => {
      _currentChat.value.records.forEach((record) => {
        if (record.id === recordId) {
          record.data = response
        }
      })
    })
    .finally(() => {
      loadingData.value = false
      emits('scrollBottom')
    })
}

function stop() {
  stopFlag.value = true
  _loading.value = false
  emits('stop')
}

onBeforeUnmount(() => {
  stop()
})

onMounted(() => {
  if (props.message?.record?.id && props.message?.record?.finish) {
    getChatData(props.message.record.id)
    return
  }
  const record = props.message?.record
  if (!record || record.local_answer || record.finish) {
    return
  }
  const activeTask = rememberedActiveTask(record)
  if (activeTask) {
    stopFlag.value = false
    _loading.value = true
    record.task_id = activeTask.task_id
    pollQuestionTask(activeTask.task_id, record, activeTask.offset).catch((error) => {
      record.error = `${record.error ? `${record.error}\n` : ''}Error:${error}`
      emits('error', record.id)
      _loading.value = false
    })
  }
})

defineExpose({ sendMessage, index: () => index.value, stop })
</script>

<template>
  <BaseAnswer v-if="message" :message="message" :reasoning-name="reasoningName" :loading="_loading">
    <MdComponent v-if="message.record?.local_answer" :message="message.record.local_answer" />
    <ChartBlock
      style="margin-top: 6px"
      :message="message"
      :record-id="recordId"
      :loading-data="loadingData"
    />
    <slot></slot>
    <template #tool>
      <slot name="tool"></slot>
    </template>
    <template #footer>
      <slot name="footer"></slot>
    </template>
  </BaseAnswer>
</template>

<style scoped lang="less"></style>
