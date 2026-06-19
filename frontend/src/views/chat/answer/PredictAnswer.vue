<script setup lang="ts">
import BaseAnswer from './BaseAnswer.vue'
import { chatApi, ChatInfo, type ChatMessage, ChatRecord } from '@/api/chat.ts'
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import MdComponent from '@/views/chat/component/MdComponent.vue'
import ChartBlock from '@/views/chat/chat-block/ChartBlock.vue'
import { parseSseChunk } from '@/utils/sse'

const props = withDefaults(
  defineProps<{
    recordId?: number
    chatList?: Array<ChatInfo>
    currentChatId?: number
    currentChat?: ChatInfo
    message?: ChatMessage
    loading?: boolean
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
  'scrollBottom',
  'stop',
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
  const currentRecord: ChatRecord = targetChat.records[recordIndex]

  let error: boolean = false
  if (_currentChatId.value === undefined || currentRecord.predict_record_id === undefined) {
    error = true
  }
  if (error) return

  let controller: AbortController | undefined
  try {
    controller = new AbortController()
    controllerRef.value = controller
    const response = await chatApi.predict(currentRecord.predict_record_id, controller)
    const reader = response.body.getReader()
    const decoder = new TextDecoder('utf-8')

    let predict_answer = ''
    let predict_content = ''

    let tempResult = ''

    while (true) {
      if (stopFlag.value) {
        controller.abort()
        setLoading(false)
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
          data = JSON.parse(payload)
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
          case 'info':
            console.info(data.msg)
            break
          case 'error':
            currentRecord.error = data.content
            emitIfMounted('error', currentRecord.id)
            break
          case 'predict-result':
            predict_answer += data.reasoning_content || ''
            predict_content += data.content || ''
            targetChat.records[recordIndex].predict = predict_answer
            targetChat.records[recordIndex].predict_content = predict_content
            break
          case 'predict-failed':
            emitIfMounted('error', currentRecord.id)
            break
          case 'predict-success':
            getChatPredictData(targetChat.records[recordIndex].id, targetChat)
            emitIfMounted('finish', currentRecord.id)
            break
          case 'predict_finish':
            setLoading(false)
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

const chartBlockRef = ref()

const loadingData = ref(false)

function getChatPredictData(recordId?: number, targetChat: ChatInfo = _currentChat.value) {
  if (!recordId) {
    return
  }
  if (!unmounted.value) {
    loadingData.value = true
  }
  chatApi
    .get_chart_predict_data(recordId)
    .then((response) => {
      let has = false
      targetChat.records.forEach((record) => {
        if (record.id === recordId) {
          has = true
          record.predict_data = response ?? []

          if (record.predict_data.length > 1) {
            getChatData(recordId, targetChat)
          } else {
            if (!unmounted.value) {
              loadingData.value = false
            }
          }
        }
      })
      if (!has && !unmounted.value) {
        setLoading(false)
      }
    })
    .catch((e) => {
      if (!unmounted.value) {
        loadingData.value = false
      }
      console.error(e)
    })
}

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
  controllerRef.value?.abort()
  setLoading(false)
  emitIfMounted('stop')
}

onBeforeUnmount(() => {
  unmounted.value = true
})

onMounted(() => {
  if (props.message?.record?.id && props.message?.record?.finish) {
    getChatPredictData(props.message.record.id)
  }
})

defineExpose({ sendMessage, index: () => index.value, chatList: () => _chatList, stop })
</script>

<template>
  <BaseAnswer v-if="message" :message="message" :reasoning-name="['predict']" :loading="_loading">
    <MdComponent :message="message.record?.predict_content" style="margin-top: 12px" />
    <ChartBlock
      v-if="message.record?.predict_data?.length > 0 && message.record?.data"
      ref="chartBlockRef"
      style="margin-top: 12px"
      :record-id="recordId"
      :message="message"
      :loading-data="loadingData"
      is-predict
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
