<script setup lang="ts">
import BaseAnswer from './BaseAnswer.vue'
import { chatApi, ChatInfo, type ChatMessage, ChatRecord } from '@/api/chat.ts'
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'
import MdComponent from '@/views/chat/component/MdComponent.vue'
import { parseSseChunk } from '@/utils/sse'
const props = withDefaults(
  defineProps<{
    chatList?: Array<ChatInfo>
    currentChatId?: number
    currentChat?: ChatInfo
    message?: ChatMessage
    loading?: boolean
  }>(),
  {
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
  if (_currentChatId.value === undefined || currentRecord.analysis_record_id === undefined) {
    error = true
  }
  if (error) return

  let controller: AbortController | undefined
  try {
    controller = new AbortController()
    controllerRef.value = controller
    const response = await chatApi.analysis(currentRecord.analysis_record_id, controller)
    const reader = response.body.getReader()
    const decoder = new TextDecoder('utf-8')

    let analysis_answer = ''
    let analysis_answer_thinking = ''

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
          case 'info':
            console.info(data.msg)
            break
          case 'error':
            currentRecord.error = data.content
            emitIfMounted('error', currentRecord.id)
            break
          case 'analysis-result':
            analysis_answer += data.content || ''
            analysis_answer_thinking += data.reasoning_content || ''
            targetChat.records[recordIndex].analysis = analysis_answer
            targetChat.records[recordIndex].analysis_thinking = analysis_answer_thinking
            break
          case 'analysis_finish':
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
function stop() {
  stopFlag.value = true
  controllerRef.value?.abort()
  setLoading(false)
  emitIfMounted('stop')
}

onBeforeUnmount(() => {
  unmounted.value = true
})
defineExpose({ sendMessage, index: () => index.value, chatList: () => _chatList.value, stop })
</script>

<template>
  <BaseAnswer
    v-if="message"
    :message="message"
    :reasoning-name="['analysis_thinking']"
    :loading="_loading"
  >
    <MdComponent :message="message.record?.analysis" style="margin-top: 12px" />
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
