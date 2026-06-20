<script setup lang="ts">
import BaseAnswer from './BaseAnswer.vue'
import { Chat, chatApi, ChatInfo, type ChatMessage, ChatRecord, questionApi } from '@/api/chat.ts'
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import ChartBlock from '@/views/chat/chat-block/ChartBlock.vue'
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
const controllerRef = ref<AbortController>()
const unmounted = ref(false)

function setLoading(value: boolean) {
  if (!unmounted.value) {
    _loading.value = value
  }
}

function emitIfMounted(event: Parameters<typeof emits>[0], ...args: any[]) {
  if (!unmounted.value) {
    emits(event, ...args)
  }
}

const sendMessage = async () => {
  stopFlag.value = false
  setLoading(true)

  const recordIndex = index.value
  if (recordIndex < 0) {
    setLoading(false)
    return
  }

  const targetChat = _currentChat.value
  const targetChatList = _chatList.value
  const currentRecord: ChatRecord = targetChat.records[recordIndex]

  let error: boolean = false
  if (_currentChatId.value === undefined) {
    error = true
  }
  if (error) return

  let controller: AbortController | undefined
  try {
    controller = new AbortController()
    controllerRef.value = controller
    const param = {
      question: currentRecord.question,
      chat_id: _currentChatId.value,
      custom_prompt_id: currentRecord.custom_prompt_id,
      datasource_id: currentRecord.datasource || targetChat.datasource,
    }
    const response = await questionApi.add(param, controller)
    const reader = response.body.getReader()
    const decoder = new TextDecoder('utf-8')

    let sql_answer = ''
    let chart_answer = ''

    let tempResult = ''

    while (true) {
      if (stopFlag.value) {
        controller.abort()
        break
      }

      const { done, value } = await reader.read()
      if (done) {
        setLoading(false)
        break
      }

      const parsed = parseSseChunk(tempResult, decoder.decode(value, { stream: true }))
      tempResult = parsed.buffer
      if (!parsed.payloads.length) {
        continue
      }

      for (const payload of parsed.payloads) {
        let data
        try {
          data = JSONBig.parse(payload)
        } catch (err) {
          console.error('JSON string:', payload)
          throw err
        }

        if (data.code && data.code !== 200) {
          if (!unmounted.value) {
            ElMessage({
              message: data.msg,
              type: 'error',
              showClose: true,
            })
          }
          setLoading(false)
          return
        }

        if (unmounted.value) {
          continue
        }

        switch (data.type) {
          case 'id':
            currentRecord.id = data.id
            targetChat.records[recordIndex].id = data.id
            break
          case 'regenerate_record_id':
            currentRecord.regenerate_record_id = data.regenerate_record_id
            targetChat.records[recordIndex].regenerate_record_id = data.regenerate_record_id
            break
          case 'question':
            currentRecord.question = data.question
            targetChat.records[recordIndex].question = data.question
            break
          case 'info':
            console.info(data.msg)
            break
          case 'brief':
            targetChat.brief = data.brief
            targetChatList.forEach((c: Chat) => {
              if (c.id === targetChat.id) {
                c.brief = targetChat.brief
              }
            })
            break
          case 'error':
            currentRecord.error = data.content
            emitIfMounted('error', currentRecord.id)
            break
          case 'sql-result':
            sql_answer += data.reasoning_content || ''
            targetChat.records[recordIndex].sql_answer = sql_answer
            break
          case 'sql':
            targetChat.records[recordIndex].sql = data.content
            break
          case 'sql-data':
            getChatData(targetChat.records[recordIndex].id, targetChat)
            break
          case 'chart-result':
            chart_answer += data.reasoning_content || ''
            targetChat.records[recordIndex].chart_answer = chart_answer
            break
          case 'chart':
            targetChat.records[recordIndex].chart = data.content
            break
          case 'datasource':
            if (!targetChat.datasource) {
              targetChat.datasource = data.id
            }
            break
          case 'finish':
            emitIfMounted('finish', currentRecord.id)
            break
        }
        if (!unmounted.value) {
          await nextTick()
        }
      }
    }
  } catch (error: any) {
    if (stopFlag.value || error?.name === 'AbortError') {
      return
    }
    if (unmounted.value) {
      console.error('Error:', error)
      return
    }
    if (!currentRecord.error) {
      currentRecord.error = ''
    }
    if (currentRecord.error.trim().length !== 0) {
      currentRecord.error = currentRecord.error + '\n'
    }
    currentRecord.error = currentRecord.error + 'Error:' + error
    console.error('Error:', error)
    emitIfMounted('error')
  } finally {
    if (controller && controllerRef.value === controller) {
      controllerRef.value = undefined
    }
    setLoading(false)
  }
}

const loadingData = ref(false)

function getChatData(recordId?: number, targetChat: ChatInfo = _currentChat.value) {
  if (!recordId) {
    return
  }
  if (!unmounted.value) {
    loadingData.value = true
  }
  chatApi
    .get_chart_data(recordId)
    .then((response) => {
      targetChat.records.forEach((record) => {
        if (record.id === recordId) {
          record.data = response
        }
      })
    })
    .finally(() => {
      if (!unmounted.value) {
        loadingData.value = false
        emits('scrollBottom')
      }
    })
}

function stop() {
  stopFlag.value = true
  const recordId = props.message?.record?.id || props.recordId
  void chatApi.stopGeneration(recordId).catch((error) => {
    console.error('Stop generation failed:', error)
  })
  controllerRef.value?.abort()
  setLoading(false)
  emitIfMounted('stop')
}

onBeforeUnmount(() => {
  unmounted.value = true
})

onMounted(() => {
  if (props.message?.record?.id && props.message?.record?.finish) {
    getChatData(props.message.record.id)
  }
})

defineExpose({ sendMessage, index: () => index.value, stop })
</script>

<template>
  <BaseAnswer v-if="message" :message="message" :reasoning-name="reasoningName" :loading="_loading">
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
