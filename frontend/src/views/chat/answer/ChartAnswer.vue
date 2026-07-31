<script setup lang="ts">
import BaseAnswer from './BaseAnswer.vue'
import { chatApi, ChatInfo, type ChatMessage, ChatRecord, questionApi } from '@/api/chat.ts'
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
import {
  partitionTerminalRecordUpdate,
  shouldShowFinalAnswer,
  shouldShowTerminalResult,
} from './answerVisibility'
import {
  applyBriefToTaskOwner,
  isTaskOwnerChatVisible,
  resolveTaskOwnerChatId,
} from './chatTaskContext'

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
const finalAnswerReady = ref(
  !!(props.message?.record?.finish || props.message?.record?.finish_time)
)
const POLL_INTERVAL_MS = 1000
const activeTaskStoragePrefix = 'chat.smartQa.activeTask.'
const notifiedFinishRecordIds = new Set<number>()
const recordOwnerChatIds = new WeakMap<ChatRecord, number>()

function taskOwnerChatId(record = props.message?.record) {
  if (!record) {
    return resolveTaskOwnerChatId(undefined, props.currentChatId)
  }
  const rememberedChatId = recordOwnerChatIds.get(record)
  if (rememberedChatId) {
    return rememberedChatId
  }
  const ownerChatId = resolveTaskOwnerChatId(record.chat_id, props.currentChatId)
  if (ownerChatId) {
    recordOwnerChatIds.set(record, ownerChatId)
  }
  return ownerChatId
}

function taskOwnerChatVisible(record = props.message?.record) {
  return isTaskOwnerChatVisible(
    taskOwnerChatId(record),
    _currentChatId.value,
    _currentChat.value.id
  )
}

function findVisibleRecord(record: ChatRecord) {
  if (!taskOwnerChatVisible(record)) {
    return undefined
  }
  return _currentChat.value.records.find(
    (candidate) => candidate === record || (!!record.id && candidate.id === record.id)
  )
}

function updateOwnedRecord(record: ChatRecord, values: Partial<ChatRecord>) {
  Object.assign(record, values)
  const visibleRecord = findVisibleRecord(record)
  if (visibleRecord && visibleRecord !== record) {
    Object.assign(visibleRecord, values)
  }
  return visibleRecord || record
}

const showFinalAnswer = computed(() =>
  shouldShowFinalAnswer({
    record: props.message?.record,
    isTyping: props.message?.isTyping,
    finalAnswerReady: finalAnswerReady.value,
  })
)
const showTerminalResult = computed(() =>
  shouldShowTerminalResult({
    record: props.message?.record,
    isTyping: props.message?.isTyping,
    finalAnswerReady: finalAnswerReady.value,
  })
)

interface ActiveTaskState {
  task_id: string
  offset: number
}

function tenantTaskScope(record?: ChatRecord) {
  return (
    (record as any)?.tenant_id ||
    (taskOwnerChatVisible(record) ? (_currentChat.value as any)?.tenant_id : undefined) ||
    'default'
  )
}

function taskKey(record: ChatRecord) {
  return buildSmartQaTaskKey({
    tenantId: tenantTaskScope(record),
    chatId: taskOwnerChatId(record),
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
  updateOwnedRecord(currentRecord, { error: message })
  clearCurrentTask(currentRecord)
  _loading.value = false
  emits('error', currentRecord.id)
}

function activeTaskStorageKey(record: ChatRecord) {
  const chatId = taskOwnerChatId(record) || 'unknown'
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
  updateOwnedRecord(record, { task_id: undefined })
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
      updateOwnedRecord(currentRecord, { id: data.id })
      if (currentRecord.task_id) {
        rememberActiveTask(currentRecord, currentRecord.task_id)
      }
      break
    case 'regenerate_record_id':
      updateOwnedRecord(currentRecord, { regenerate_record_id: data.regenerate_record_id })
      break
    case 'question':
      updateOwnedRecord(currentRecord, { question: data.question })
      break
    case 'info':
      console.info(data.msg)
      break
    case 'brief':
      applyBriefToTaskOwner({
        chatList: _chatList.value,
        currentChat: _currentChat.value,
        currentChatId: _currentChatId.value,
        ownerChatId: taskOwnerChatId(currentRecord),
        brief: data.brief,
      })
      break
    case 'error':
      failCurrentRecord(currentRecord, data.content)
      break
    case 'sql-result':
      state.sql_answer += data.reasoning_content || ''
      updateOwnedRecord(currentRecord, { sql_answer: state.sql_answer })
      break
    case 'sql':
      updateOwnedRecord(currentRecord, { sql: data.content })
      break
    case 'sql-data':
      getChatData(currentRecord.id, currentRecord)
      break
    case 'chart-result':
      state.chart_answer += data.reasoning_content || ''
      updateOwnedRecord(currentRecord, { chart_answer: state.chart_answer })
      break
    case 'analysis-result':
      state.analysis += data.content || ''
      state.analysis_thinking += data.reasoning_content || ''
      updateOwnedRecord(currentRecord, {
        analysis: state.analysis,
        analysis_thinking: state.analysis_thinking,
      })
      if (data.notice) {
        updateOwnedRecord(currentRecord, { analysis_notice: data.notice })
      }
      break
    case 'chart':
      updateOwnedRecord(currentRecord, { chart: data.content })
      break
    case 'datasource':
      if (taskOwnerChatVisible(currentRecord) && !_currentChat.value.datasource) {
        _currentChat.value.datasource = data.id
      }
      break
    case 'finish':
      break
  }
  await nextTick()
}

async function fetchCurrentRecord(
  recordId?: number,
  targetRecord: ChatRecord | undefined = props.message?.record
): Promise<ChatRecord | undefined> {
  const ownerChatId = taskOwnerChatId(targetRecord)
  if (!ownerChatId || !targetRecord || !recordId) {
    return undefined
  }

  try {
    const chat = await chatApi.get(ownerChatId, { includeRecordData: false })
    const latestRecord = chat?.records?.find((record) => record.id === recordId)
    if (!latestRecord) {
      return undefined
    }
    return latestRecord
  } catch (error) {
    console.error('Refresh chat record failed:', error)
    return undefined
  }
}

const sendMessage = async () => {
  stopFlag.value = false
  finalAnswerReady.value = false
  _loading.value = true

  const currentRecord = props.message?.record
  if (!currentRecord) {
    _loading.value = false
    return
  }

  if (currentRecord.local_answer) {
    _loading.value = false
    return
  }

  const ownerChatId = taskOwnerChatId(currentRecord)
  if (!ownerChatId) return

  try {
    if (currentRecord.task_id) {
      finalAnswerReady.value = false
      rememberActiveTask(currentRecord, currentRecord.task_id)
      attachGlobalTask(currentRecord, currentRecord.task_id)
      return
    }

    const param = {
      question: currentRecord.question,
      chat_id: ownerChatId,
      custom_prompt_id: currentRecord.custom_prompt_id,
      data_skill_id: currentRecord.data_skill_id,
    }
    const task = await questionApi.startTask(param)
    if (task.record_id) {
      updateOwnedRecord(currentRecord, { id: task.record_id })
    }
    updateOwnedRecord(currentRecord, { task_id: task.task_id })
    finalAnswerReady.value = false
    rememberActiveTask(currentRecord, task.task_id)
    attachGlobalTask(currentRecord, task.task_id)
  } catch (error) {
    const previousError = currentRecord.error?.trim() ? `${currentRecord.error}\n` : ''
    updateOwnedRecord(currentRecord, { error: `${previousError}Error:${error}` })
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

function loadChartData(
  recordId?: number,
  isStale?: () => boolean,
  targetRecord: ChatRecord | undefined = props.message?.record
) {
  if (!recordId) {
    return Promise.resolve()
  }
  if (isStale?.()) {
    return Promise.resolve()
  }
  const currentRecord =
    targetRecord?.id === recordId
      ? targetRecord
      : taskOwnerChatVisible(targetRecord)
        ? _currentChat.value.records.find((record) => record.id === recordId)
        : undefined
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
      if (!currentRecord) {
        return
      }
      applyChartDataResponseToRecord(currentRecord, response)
      const visibleRecord = findVisibleRecord(currentRecord)
      if (visibleRecord && visibleRecord !== currentRecord) {
        applyChartDataResponseToRecord(visibleRecord, response)
      }
    })
    .finally(() => {
      loadingData.value = false
      emits('scrollBottom')
    })
}

function getChatData(recordId?: number, targetRecord?: ChatRecord) {
  void loadChartData(recordId, undefined, targetRecord)
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
  let pendingTerminalUpdate:
    | ReturnType<typeof partitionTerminalRecordUpdate<ChatRecord>>
    | undefined
  const entry = smartQaTaskStore.ensureTask({
    tenantId: tenantTaskScope(currentRecord),
    chatId: taskOwnerChatId(currentRecord),
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
        const latestRecord = await fetchCurrentRecord(
          Number(record.id || currentRecord.id),
          currentRecord
        )
        if (!latestRecord || !(latestRecord.finish || latestRecord.finish_time)) {
          return false
        }
        pendingTerminalUpdate = partitionTerminalRecordUpdate(latestRecord, currentRecord.task_id)
        return true
      },
      loadRecordData: async ({ record }) => {
        if (pendingTerminalUpdate) {
          updateOwnedRecord(currentRecord, pendingTerminalUpdate.content as Partial<ChatRecord>)
        }
        const recordId = Number(record.id || currentRecord.id)
        if (recordId) {
          await loadChartData(recordId, undefined, currentRecord)
        }
        if (pendingTerminalUpdate) {
          updateOwnedRecord(currentRecord, pendingTerminalUpdate.afterData as Partial<ChatRecord>)
        }
      },
      onFinish: async ({ record }) => {
        await markFinalAnswerReady()
        if (pendingTerminalUpdate) {
          updateOwnedRecord(currentRecord, pendingTerminalUpdate.terminal as Partial<ChatRecord>)
        }
        clearCurrentTask(currentRecord)
        _loading.value = false
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
      getChatData(record.id, record)
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
      updateOwnedRecord(record, { task_id: activeTask.task_id })
      attachGlobalTask(record, activeTask.task_id, activeTask.offset)
      return
    }

    if (!shouldRefreshRecordAfterNoActiveTask(record)) {
      return
    }

    const latestRecord = await fetchCurrentRecord(record.id, record)
    if (latestRecord) {
      if (latestRecord?.finish || latestRecord?.finish_time) {
        const pendingTerminalUpdate = partitionTerminalRecordUpdate(latestRecord, record.task_id)
        updateOwnedRecord(record, pendingTerminalUpdate.content as Partial<ChatRecord>)
        await loadChartData(latestRecord.id, undefined, record)
        updateOwnedRecord(record, pendingTerminalUpdate.afterData as Partial<ChatRecord>)
        await markFinalAnswerReady()
        updateOwnedRecord(record, pendingTerminalUpdate.terminal as Partial<ChatRecord>)
        clearCurrentTask(record)
        _loading.value = false
        emits('finish', latestRecord.id)
        return
      }
      updateOwnedRecord(record, {
        ...latestRecord,
        task_id: latestRecord.task_id || record.task_id,
      })
      if (latestRecord?.error) {
        _loading.value = false
        emits('error', latestRecord.id)
      }
    }
  } catch (error) {
    updateOwnedRecord(record, {
      error: `${record.error ? `${record.error}\n` : ''}Error:${error}`,
    })
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
    if (previousRecord && previousRecord !== record) {
      smartQaTaskStore.detachTaskCallbacks(taskKey(previousRecord))
    }
    if (shouldRestoreWhenAnswerRecordChanges(previousRecord, record)) {
      void restoreRecordTask()
    }
  },
  { flush: 'post' }
)

defineExpose({ sendMessage, index: () => index.value, stop, restoreRecordTask, loadChartData })
</script>

<template>
  <BaseAnswer v-if="message" :message="message" :reasoning-name="reasoningName" :loading="_loading">
    <template v-if="showFinalAnswer">
      <MdComponent v-if="message.record?.local_answer" :message="message.record.local_answer" />
      <BusinessNotice
        v-if="message.record?.analysis_notice"
        :notice="message.record.analysis_notice"
        :message="message.record?.analysis"
      />
      <MdComponent v-else-if="message.record?.analysis" :message="message.record.analysis" />
      <ChartBlock
        v-if="showTerminalResult && !message.record?.error"
        style="margin-top: 6px"
        :message="message"
        :record-id="recordId"
        :loading-data="loadingData"
      />
      <slot></slot>
    </template>
    <template #tool>
      <slot
        v-if="showFinalAnswer && (!message.record?.analysis_notice || showTerminalResult)"
        name="tool"
      ></slot>
    </template>
    <template #footer>
      <slot
        v-if="showFinalAnswer && (!message.record?.analysis_notice || showTerminalResult)"
        name="footer"
      ></slot>
    </template>
  </BaseAnswer>
</template>

<style scoped lang="less"></style>
