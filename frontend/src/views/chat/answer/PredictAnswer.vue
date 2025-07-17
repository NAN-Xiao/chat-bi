<script setup lang="ts">
import BaseAnswer from './BaseAnswer.vue'
import { chatApi, ChatInfo, type ChatMessage, ChatRecord } from '@/api/chat.ts'
import { computed, nextTick } from 'vue'
import MdComponent from '@/views/chat/component/MdComponent.vue'
const props = withDefaults(
  defineProps<{
    chatList: Array<ChatInfo>
    currentChatId?: number
    currentChat: ChatInfo
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

const sendMessage = async () => {
  _loading.value = true

  if (index.value < 0) {
    _loading.value = false
    return
  }

  const currentRecord: ChatRecord = _currentChat.value.records[index.value]

  let error: boolean = false
  if (_currentChatId.value === undefined || currentRecord.predict_record_id === undefined) {
    error = true
  }
  if (error) return

  try {
    const response = await chatApi.predict(currentRecord.predict_record_id)
    const reader = response.body.getReader()
    const decoder = new TextDecoder()

    let predict_answer = ''
    let predict_content = ''

    while (true) {
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
          return
        }

        switch (data.type) {
          case 'info':
            console.log(data.msg)
            break
          case 'error':
            currentRecord.error = data.content
            emits('error')
            break
          case 'predict-result':
            predict_answer += data.reasoning_content
            predict_content += data.content
            _currentChat.value.records[index.value].predict = predict_answer
            _currentChat.value.records[index.value].predict_content = predict_content
            break
          case 'predict-failed':
            emits('error')
            break
          case 'predict-success':
            //currentChat.value.records[_index].predict_data = data.content
            emits('finish', currentRecord.id)
            break
          case 'predict_finish':
            _loading.value = false
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

defineExpose({ sendMessage, index: index.value, chatList: _chatList })
</script>

<template>
  <BaseAnswer v-if="message" :message="message" :reasoning-name="['predict']" :loading="_loading">
    <MdComponent :message="message.record?.predict_content" style="margin-top: 12px" />
    <slot></slot>
    <slot name="footer"></slot>
  </BaseAnswer>
</template>

<style scoped lang="less"></style>
