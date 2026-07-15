<script setup lang="ts">
import BaseAnswer from './BaseAnswer.vue'
import { Chat, chatApi, ChatInfo, type ChatMessage, ChatRecord, questionApi } from '@/api/chat.ts'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import ChartBlock from '@/views/chat/chat-block/ChartBlock.vue'
import MdComponent from '@/views/chat/component/MdComponent.vue'
import BusinessNotice from '@/views/chat/BusinessNotice.vue'
import JSONBig from 'json-bigint'
import { parseSseChunk } from '@/utils/sse'
import {
  hasStoredFinalAnswer,
  shouldLookupRecordTask,
  shouldRefreshRecordAfterNoActiveTask,
  shouldRestoreWhenAnswerRecordChanges,
  shouldUseRememberedTask,
} from './taskRestore'
import { buildSmartQaTaskKey, smartQaTaskStore } from './smartQaTaskStore'
import { applyChartDataResponseToRecord } from './chartDataResponse'

const props = withDefaults(
  defineProps<{
    recordId?: number
    chatList?: Array<ChatInfo>
    currentChatId?: number
    currentChat?: ChatInfo
    message?: ChatMessage
    loading?: boolean
    deferDataLoading?: boolean
    reasoningName: 'sql_answer' | 'chart_answer' | Array<'sql_answer' | 'chart_answer'>
  }>(),
  {
    recordId: undefined,
    chatList: () => [],
    currentChatId: undefined,
    currentChat: () => new ChatInfo(),
    message: undefined,
    loading: false,
    deferDataLoading: false,
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
const finalAnswerReady = ref(!!(props.message?.record?.finish || props.message?.record?.finish_time))
const POLL_INTERVAL_MS = 1000
const activeTaskStoragePrefix = 'chat.smartQa.activeTask.'
const notifiedFinishRecordIds = new Set<number>()

const showFinalAnswer = computed(() => {
  const record = props.message?.record
  if (!record || props.message?.isTyping) {
    return false
  }
  if (record.error || record.stopped) {
    return true
  }
  if (record.finish || record.finish_time) {
    return finalAnswerReady.value
  }
  return !record.task_id
})

interface ActiveTaskState {
  task_id: string
  offset: number
}

function tenantTaskScope(record?: ChatRecord) {
  return (
    (record as any)?.tenant_id ||
    (_currentChat.value as any)?.tenant_id ||
    'default'
  )
}

function taskKey(record: ChatRecord) {
  return buildSmartQaTaskKey({
    tenantId: tenantTaskScope(record),
    chatId: _currentChatId.value || record.chat_id,
    recordId: record.id,
  })
}

function emitFinishOnce(recordId?: number) {
  if (!recordId || notifiedFinishRecordIds.has(recordId)) {
    return
  }
  notifiedFinishRecordIds.add(recordId)
  emits('finish', recordId)
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
  clearCurrentTask(currentRecord)
  _loading.value = false
  emits('error', currentRecord.id)
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

function clearCurrentTask(record: ChatRecord) {
  record.task_id = undefined
  if (index.value >= 0 && _currentChat.value.records[index.value]) {
    _currentChat.value.records[index.value].task_id = undefined
  }
}

function pausePolling() {
  stopFlag.value = true
  _loading.value = false
}

async function markFinalAnswerReady() {
  await nextTick()
  await nextTick()
  finalAnswerReady.value = true
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
  if (!shouldUseRememberedTask(record)) {
    return undefined
  }
  const remembered = rememberedActiveTask(record)
  if (remembered) {
    return remembered
  }
  const recordId = record.id
  if (!shouldLookupRecordTask(record) || recordId === undefined) {
    return undefined
  }

  const recordTask = await questionApi.getRecordTask(recordId)
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
      if (data.notice) {
        _currentChat.value.records[index.value].analysis_notice = data.notice
      }
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
      await markFinalAnswerReady()
      clearCurrentTask(currentRecord)
      break
  }
  await nextTick()
}

async function refreshCurrentRecord(recordId?: number) {
  if (!_currentChatId.value) {
    return false
  }

  try {
    const chat = await chatApi.get(_currentChatId.value, { includeRecordData: false })
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

const sendMessage = async () => {
  stopFlag.value = false
  finalAnswerReady.value = false
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
      finalAnswerReady.value = false
      rememberActiveTask(currentRecord, currentRecord.task_id)
      attachGlobalTask(currentRecord, currentRecord.task_id)
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
    finalAnswerReady.value = false
    rememberActiveTask(currentRecord, task.task_id)
    attachGlobalTask(currentRecord, task.task_id)
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
    const text = record.data.trim()
    if (!text) {
      return false
    }
    try {
      const data = JSONBig.parse(text)
      return (
        data?.status === 'failed' ||
        data?.status === 'business_notice' ||
        (Array.isArray(data?.data) && data.data.length > 0)
      )
    } catch {
      return true
    }
  }
  if (record.data?.status === 'failed') {
    return true
  }
  if (record.data?.status === 'business_notice') {
    return true
  }
  return Array.isArray(record.data?.data) && record.data.data.length > 0
}

function loadChartData(recordId?: number, isStale?: () => boolean) {
  if (!recordId) {
    return Promise.resolve()
  }
  if (isStale?.()) {
    return Promise.resolve()
  }
  const currentRecord = _currentChat.value.records.find((record) => record.id === recordId)
  if (hasRecordData(currentRecord)) {
    return Promise.resolve()
  }

  loadingData.value = true
  return chatApi
    .get_chart_data(recordId)
    .then((response) => {
      if (isStale?.()) {
        return
      }
      _currentChat.value.records.forEach((record) => {
        if (record.id === recordId) {
          applyChartDataResponseToRecord(record, response)
        }
      })
    })
    .finally(() => {
      loadingData.value = false
      emits('scrollBottom')
    })
}

function getChatData(recordId?: number) {
  void loadChartData(recordId)
}

function attachGlobalTask(currentRecord: ChatRecord, taskId: string, initialOffset = 0) {
  smartQaTaskStore.configure({
    pollIntervalMs: POLL_INTERVAL_MS,
    getTaskEvents: questionApi.getTaskEvents,
  })
  const taskState = {
    sql_answer: currentRecord.sql_answer || '',
    chart_answer: currentRecord.chart_answer || '',
    analysis: currentRecord.analysis || '',
    analysis_thinking: currentRecord.analysis_thinking || '',
  }
  const entry = smartQaTaskStore.ensureTask({
    tenantId: tenantTaskScope(currentRecord),
    chatId: _currentChatId.value || currentRecord.chat_id,
    record: currentRecord,
    taskId,
    offset: initialOffset,
    callbacks: {
      onEvents: async ({ events }) => {
        for (const eventChunk of events) {
          const parsed = parseSseChunk('', eventChunk)
          for (const payload of parsed.payloads) {
            await handlePayload(payload, currentRecord, taskState)
          }
        }
      },
      refreshRecord: async ({ record }) => {
        await refreshCurrentRecord(Number(record.id || currentRecord.id))
        const latestRecord = _currentChat.value.records[index.value]
        if (latestRecord?.finish || latestRecord?.finish_time) {
          await markFinalAnswerReady()
        }
        if (latestRecord) {
          clearCurrentTask(latestRecord)
        }
      },
      loadRecordData: async ({ record }) => {
        const recordId = Number(record.id || currentRecord.id)
        if (recordId) {
          await loadChartData(recordId)
        }
      },
      onFinish: async ({ record }) => {
        _loading.value = false
        await markFinalAnswerReady()
        emitFinishOnce(Number(record.id || currentRecord.id))
      },
      onError: ({ error }) => {
        _loading.value = false
        failCurrentRecord(currentRecord, error)
      },
    },
  })
  if (entry) {
    _loading.value = true
    if (currentRecord.id) {
      void refreshCurrentRecord(currentRecord.id).then(async (refreshed) => {
        const latestRecord = _currentChat.value.records[index.value]
        if (refreshed && latestRecord && hasStoredFinalAnswer(latestRecord)) {
          if (latestRecord.finish || latestRecord.finish_time) {
            await markFinalAnswerReady()
          }
          clearCurrentTask(latestRecord)
          _loading.value = false
          if (latestRecord.id && latestRecord.chart && !hasRecordData(latestRecord)) {
            getChatData(latestRecord.id)
          }
        }
      })
    }
  }
  return entry
}

function stop() {
  const record = props.message?.record
  if (record) {
    smartQaTaskStore.pauseTask(taskKey(record))
  }
  pausePolling()
  emits('stop')
}

onBeforeUnmount(() => {
  const record = props.message?.record
  if (record) {
    smartQaTaskStore.detachTaskCallbacks(taskKey(record))
  }
})

async function restoreRecordTask() {
  if (restoringTask.value) {
    return
  }
  const record = props.message?.record
  if (!record) {
    return
  }
  if (hasStoredFinalAnswer(record)) {
    if (!props.deferDataLoading && record.id && record.chart && !hasRecordData(record)) {
      getChatData(record.id)
    }
    return
  }
  restoringTask.value = true
  try {
    const activeTask = await resolveActiveTask(record)
    if (activeTask) {
      stopFlag.value = false
      finalAnswerReady.value = false
      _loading.value = true
      record.task_id = activeTask.task_id
      attachGlobalTask(record, activeTask.task_id, activeTask.offset)
      return
    }

    if (!shouldRefreshRecordAfterNoActiveTask(record)) {
      return
    }

    const refreshed = await refreshCurrentRecord(record.id)
    if (refreshed) {
      const latestRecord = _currentChat.value.records[index.value]
      if (latestRecord?.finish) {
        await markFinalAnswerReady()
        clearCurrentTask(latestRecord)
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
    clearCurrentTask(record)
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

watch(
  () => props.message?.record,
  (record, previousRecord) => {
    if (shouldRestoreWhenAnswerRecordChanges(previousRecord, record)) {
      void restoreRecordTask()
    }
  },
  { flush: 'post' }
)

defineExpose({ sendMessage, index: () => index.value, stop, restoreRecordTask, loadChartData })
</script>

<template>
  <BaseAnswer
    v-if="message"
    :message="message"
    :reasoning-name="reasoningName"
    :loading="_loading"
  >
    <template v-if="showFinalAnswer">
      <MdComponent v-if="message.record?.local_answer" :message="message.record.local_answer" />
      <BusinessNotice
        v-if="message.record?.analysis_notice"
        :notice="message.record.analysis_notice"
        :message="message.record?.analysis"
      />
      <MdComponent v-else-if="message.record?.analysis" :message="message.record.analysis" />
      <ChartBlock
        style="margin-top: 6px"
        :message="message"
        :record-id="recordId"
        :loading-data="loadingData"
      />
      <slot></slot>
    </template>
    <template #tool>
      <slot v-if="showFinalAnswer" name="tool"></slot>
    </template>
    <template #footer>
      <slot v-if="showFinalAnswer" name="footer"></slot>
    </template>
  </BaseAnswer>
</template>

<style scoped lang="less"></style>
