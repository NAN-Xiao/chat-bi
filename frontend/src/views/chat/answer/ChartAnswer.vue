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
const restoringTask = ref(false)
const POLL_INTERVAL_MS = 1000
const EMPTY_EVENT_REFRESH_ROUNDS = 3
const activeTaskStoragePrefix = 'chat.smartQa.activeTask.'

interface ActiveTaskState {
  task_id: string
  offset: number
}

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

function normalizeTaskError(error?: unknown) {
  if (typeof error === 'string' && error.trim()) {
    return error
  }
  if (error instanceof Error && error.message) {
    return error.message
  }
  if (error && typeof error === 'object') {
    const data = (error as any).response?.data || error
    const message =
      data.detail ||
      data.message ||
      data.msg ||
      data.error ||
      (typeof data.toString === 'function' && data.toString !== Object.prototype.toString
        ? data.toString()
        : '')
    if (message && String(message).trim() && message !== '[object Object]') {
      return String(message)
    }
  }
  return '问数任务异常结束，但后端未返回具体错误。请稍后重试。'
}

function failCurrentRecord(currentRecord: ChatRecord, error?: unknown) {
  const message = normalizeTaskError(error)
  currentRecord.error = message
  if (index.value >= 0 && _currentChat.value.records[index.value]) {
    _currentChat.value.records[index.value].error = message
  }
  _loading.value = false
  emits('error', currentRecord.id)
}

function hasDisplayableAnswerRecord(record?: ChatRecord) {
  return !!(
    record?.local_answer ||
    record?.chart ||
    record?.analysis ||
    record?.predict ||
    record?.predict_content
  )
}

function activeTaskStorageKey(record: ChatRecord) {
  const chatId = record.chat_id || _currentChatId.value || 'unknown'
  const recordId = record.id || record.create_time || record.question || index.value
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

function pausePolling() {
  stopFlag.value = true
  _loading.value = false
}

function rememberedActiveTask(record: ChatRecord): ActiveTaskState | undefined {
  const raw = sessionStorage.getItem(activeTaskStorageKey(record))
  if (!raw) {
    return record.task_id ? { task_id: record.task_id, offset: 0 } : undefined
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
  return record.task_id ? { task_id: record.task_id, offset: 0 } : undefined
}

async function resolveActiveTask(record: ChatRecord): Promise<ActiveTaskState | undefined> {
  const remembered = rememberedActiveTask(record)
  if (remembered) {
    return remembered
  }
  if (!record.id || record.finish || record.error || hasDisplayableAnswerRecord(record)) {
    return undefined
  }

  const recordTask = await questionApi.getRecordTask(record.id)
  if (!recordTask?.task_id || ['succeeded', 'failed'].includes(recordTask.status)) {
    return undefined
  }
  return {
    task_id: recordTask.task_id,
    offset: 0,
  }
}

async function handlePayload(
  payload: string,
  currentRecord: ChatRecord,
  state: { sql_answer: string; chart_answer: string; analysis: string; analysis_thinking: string }
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
      if (currentRecord.task_id) {
        rememberActiveTask(currentRecord, currentRecord.task_id)
      }
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
      failCurrentRecord(currentRecord, data.content)
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
    case 'analysis-result':
      state.analysis += data.content || ''
      state.analysis_thinking += data.reasoning_content || ''
      _currentChat.value.records[index.value].analysis = state.analysis
      _currentChat.value.records[index.value].analysis_thinking = state.analysis_thinking
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
      currentRecord.finish = true
      _currentChat.value.records[index.value].finish = true
      emits('finish', currentRecord.id)
      break
  }
  await nextTick()
}

async function refreshCurrentRecord(recordId?: number) {
  if (!_currentChatId.value) {
    return false
  }

  try {
    const chat = await chatApi.get(_currentChatId.value)
    const latestRecord = recordId
      ? chat?.records?.find((record) => record.id === recordId)
      : chat?.records?.[index.value]
    if (!latestRecord || index.value < 0) {
      return false
    }
    const currentTaskId = _currentChat.value.records[index.value].task_id
    _currentChat.value.records[index.value] = Object.assign(
      _currentChat.value.records[index.value],
      latestRecord,
      {
        task_id: latestRecord.task_id || currentTaskId,
      }
    )
    return true
  } catch (error) {
    console.error('Refresh chat record failed:', error)
    return false
  }
}

async function pollQuestionTask(taskId: string, currentRecord: ChatRecord, initialOffset = 0) {
  const state = {
    sql_answer: _currentChat.value.records[index.value].sql_answer || '',
    chart_answer: _currentChat.value.records[index.value].chart_answer || '',
    analysis: _currentChat.value.records[index.value].analysis || '',
    analysis_thinking: _currentChat.value.records[index.value].analysis_thinking || '',
  }
  let offset = initialOffset
  let emptyEventRounds = 0

  while (true) {
    if (stopFlag.value) {
      break
    }

    let eventPage
    try {
      eventPage = await questionApi.getTaskEvents(taskId, offset)
    } catch (error) {
      forgetActiveTask(currentRecord)
      failCurrentRecord(currentRecord, error)
      break
    }
    offset = eventPage.next_offset ?? offset
    rememberActiveTask(currentRecord, taskId, offset)
    const events = eventPage.events || []
    if (events.length > 0) {
      emptyEventRounds = 0
    } else {
      emptyEventRounds += 1
    }
    for (const eventChunk of events) {
      const parsed = parseSseChunk('', eventChunk)
      for (const payload of parsed.payloads) {
        await handlePayload(payload, currentRecord, state)
      }
    }

    if (['succeeded', 'failed'].includes(eventPage.status)) {
      forgetActiveTask(currentRecord)
      if (currentRecord.error || _currentChat.value.records[index.value]?.error) {
        failCurrentRecord(currentRecord, currentRecord.error || _currentChat.value.records[index.value]?.error)
      } else if (eventPage.status === 'failed') {
        if (!currentRecord.error) {
          failCurrentRecord(currentRecord, eventPage.error)
        } else {
          _loading.value = false
        }
      } else if (eventPage.status === 'succeeded') {
        const finishAlreadyNotified =
          currentRecord.finish || _currentChat.value.records[index.value]?.finish
        currentRecord.finish = true
        _currentChat.value.records[index.value].finish = true
        await refreshCurrentRecord(currentRecord.id)
        getChatData(currentRecord.id)
        if (!finishAlreadyNotified) {
          emits('finish', currentRecord.id)
        }
      }
      _loading.value = false
      break
    }

    if (emptyEventRounds >= EMPTY_EVENT_REFRESH_ROUNDS) {
      emptyEventRounds = 0
      const refreshed = await refreshCurrentRecord(currentRecord.id)
      const latestRecord = _currentChat.value.records[index.value]
      if (refreshed && latestRecord?.error) {
        forgetActiveTask(currentRecord)
        failCurrentRecord(currentRecord, latestRecord.error)
        break
      }
      if (refreshed && (latestRecord?.finish || hasDisplayableAnswerRecord(latestRecord))) {
        forgetActiveTask(currentRecord)
        _loading.value = false
        if (latestRecord?.id) {
          getChatData(latestRecord.id)
        }
        if (latestRecord?.finish) {
          emits('finish', latestRecord.id)
        }
        break
      }
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
    if (currentRecord.task_id) {
      rememberActiveTask(currentRecord, currentRecord.task_id)
      await pollQuestionTask(currentRecord.task_id, currentRecord)
      return
    }

    const param = {
      question: currentRecord.question,
      chat_id: _currentChatId.value,
      custom_prompt_id: currentRecord.custom_prompt_id,
      data_skill_id: currentRecord.data_skill_id,
    }
    const task = await questionApi.startTask(param)
    if (task.record_id) {
      currentRecord.id = task.record_id
      _currentChat.value.records[index.value].id = task.record_id
    }
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
  if (!recordId) {
    return
  }
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
  pausePolling()
  emits('stop')
}

onBeforeUnmount(() => {
  pausePolling()
})

async function restoreRecordTask() {
  if (restoringTask.value) {
    return
  }
  const record = props.message?.record
  if (!record || record.finish || record.error || hasDisplayableAnswerRecord(record)) {
    return
  }
  restoringTask.value = true
  try {
    const activeTask = await resolveActiveTask(record)
    if (activeTask) {
      stopFlag.value = false
      _loading.value = true
      record.task_id = activeTask.task_id
      await pollQuestionTask(activeTask.task_id, record, activeTask.offset)
      return
    }

    const refreshed = await refreshCurrentRecord(record.id)
    if (refreshed) {
      const latestRecord = _currentChat.value.records[index.value]
      if (latestRecord?.finish) {
        _loading.value = false
        getChatData(latestRecord.id)
        emits('finish', latestRecord.id)
        return
      }
      if (latestRecord?.error) {
        _loading.value = false
        emits('error', latestRecord.id)
      }
    }
  } catch (error) {
    record.error = `${record.error ? `${record.error}\n` : ''}Error:${error}`
    emits('error', record.id)
    _loading.value = false
    console.error('Restore active chat task failed:', error)
  } finally {
    restoringTask.value = false
  }
}

onMounted(() => {
  restoreRecordTask()
})

defineExpose({ sendMessage, index: () => index.value, stop, restoreRecordTask })
</script>

<template>
  <BaseAnswer
    v-if="message"
    :message="message"
    :reasoning-name="reasoningName"
    :loading="_loading"
  >
    <MdComponent v-if="message.record?.local_answer" :message="message.record.local_answer" />
    <MdComponent v-if="message.record?.analysis" :message="message.record.analysis" />
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
