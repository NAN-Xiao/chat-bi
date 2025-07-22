<script setup lang="ts">
import BaseAnswer from './BaseAnswer.vue'
import { Chat, chatApi, ChatInfo, type ChatMessage, ChatRecord, questionApi } from '@/api/chat.ts'
import { useAssistantStore } from '@/stores/assistant'
import { computed, nextTick, ref } from 'vue'
const assistantStore = useAssistantStore()
const props = withDefaults(
  defineProps<{
    chatList?: Array<ChatInfo>
    currentChatId?: number
    currentChat?: ChatInfo
    message?: ChatMessage
    loading?: boolean
    reasoningName: 'sql_answer' | 'chart_answer' | Array<'sql_answer' | 'chart_answer'>
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

const sendMessage = async () => {
  stopFlag.value = false
  _loading.value = true

  if (index.value < 0) {
    _loading.value = false
    return
  }

  const currentRecord: ChatRecord = _currentChat.value.records[index.value]

  let error: boolean = false
  if (_currentChatId.value === undefined) {
    error = true
  }
  if (error) return

  try {
    const controller: AbortController = new AbortController()
    const param = {
      question: currentRecord.question,
      chat_id: _currentChatId.value,
      assistant_certificate: assistantStore.getCertificate,
      controller,
    }
    console.log(assistantStore.getCertificate)
    console.log(param)
    const response = await questionApi.add(param)
    const reader = response.body.getReader()
    const decoder = new TextDecoder()

    let sql_answer = ''
    let chart_answer = ''

    while (true) {
      if (stopFlag.value) {
        controller.abort()
        break
      }

      const { done, value } = await reader.read()
      if (done) {
        _loading.value = false
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
          _loading.value = false
          return
        }

        switch (data.type) {
          case 'id':
            currentRecord.id = data.id
            _currentChat.value.records[index.value].id = data.id
            break
          case 'info':
            console.log(data.msg)
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
            emits('error')
            break
          case 'sql-result':
            sql_answer += data.reasoning_content
            _currentChat.value.records[index.value].sql_answer = sql_answer
            break
          case 'sql':
            _currentChat.value.records[index.value].sql = data.content
            break
          case 'sql-data':
            getChatData(_currentChat.value.records[index.value].id)
            break
          case 'chart-result':
            chart_answer += data.reasoning_content
            _currentChat.value.records[index.value].chart_answer = chart_answer
            break
          case 'chart':
            _currentChat.value.records[index.value].chart = data.content
            break
          case 'finish':
            emits('finish', currentRecord.id)
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
    emits('error')
  } finally {
    _loading.value = false
  }
}

function getChatData(recordId?: number) {
  chatApi.get_chart_data(recordId).then((response) => {
    _currentChat.value.records.forEach((record) => {
      if (record.id === recordId) {
        record.data = response
      }
    })
  })
}
function stop() {
  stopFlag.value = true
  _loading.value = false
}
defineExpose({ sendMessage, index: () => index.value, stop })
</script>

<template>
  <BaseAnswer v-if="message" :message="message" :reasoning-name="reasoningName" :loading="_loading">
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
