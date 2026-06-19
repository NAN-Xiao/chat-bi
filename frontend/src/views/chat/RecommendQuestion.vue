<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'
import { endsWith, startsWith } from 'lodash-es'
import { useI18n } from 'vue-i18n'
import { chatApi, ChatInfo } from '@/api/chat.ts'
import { parseSseChunk } from '@/utils/sse'

const props = withDefaults(
  defineProps<{
    recordId?: number
    currentChat?: ChatInfo
    questions?: string
    firstChat?: boolean
    disabled?: boolean
    position?: string
  }>(),
  {
    recordId: undefined,
    currentChat: () => new ChatInfo(),
    questions: '[]',
    firstChat: false,
    disabled: false,
    position: 'chat',
  }
)

const emits = defineEmits(['clickQuestion', 'update:currentChat', 'stop', 'loadingOver'])

const loading = ref(false)
const RECOMMEND_QUESTION_TIMEOUT_MS = 15000

const _currentChat = computed({
  get() {
    return props.currentChat
  },
  set(v) {
    emits('update:currentChat', v)
  },
})

const computedQuestions = computed<string[]>(() => {
  if (
    props.questions &&
    props.questions.length > 0 &&
    startsWith(props.questions.trim(), '[') &&
    endsWith(props.questions.trim(), ']')
  ) {
    try {
      const parsedQuestions = JSON.parse(props.questions)
      if (Array.isArray(parsedQuestions)) {
        return parsedQuestions.length > 4 ? parsedQuestions.slice(0, 4) : parsedQuestions
      }
      return []
    } catch (error) {
      console.error('Failed to parse questions:', error)
      return []
    }
  }
  return []
})

const { t } = useI18n()

function clickQuestion(question: string): void {
  if (!props.disabled) {
    emits('clickQuestion', question)
  }
}

const stopFlag = ref(false)
const controllerRef = ref<AbortController>()
const unmounted = ref(false)

function setLoading(value: boolean) {
  if (!unmounted.value) {
    loading.value = value
  }
}

function emitIfMounted(event: Parameters<typeof emits>[0], ...args: any[]) {
  if (!unmounted.value) {
    emits(event, ...args)
  }
}

async function getRecommendQuestions(articles_number: number) {
  stopFlag.value = false
  setLoading(true)
  let controller: AbortController | undefined
  let timeoutId: ReturnType<typeof setTimeout> | undefined
  try {
    controller = new AbortController()
    controllerRef.value = controller
    timeoutId = setTimeout(() => {
      stopFlag.value = true
      controller?.abort()
    }, RECOMMEND_QUESTION_TIMEOUT_MS)
    const params = articles_number ? '?articles_number=' + articles_number : ''
    const response = await chatApi.recommendQuestions(props.recordId, controller, params)
    const streamReader: ReadableStreamDefaultReader<Uint8Array> = response.body.getReader()
    const decoder = new TextDecoder('utf-8')

    let tempResult = ''
    let shouldCloseStream = false

    while (true) {
      if (stopFlag.value) {
        controller.abort()
        setLoading(false)
        break
      }

      const { done, value } = await streamReader.read()
      if (done) {
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
          case 'recommended_question':
            if (
              data.content &&
              data.content.length > 0 &&
              startsWith(data.content.trim(), '[') &&
              endsWith(data.content.trim(), ']')
            ) {
              if (_currentChat.value?.records) {
                for (let record of _currentChat.value.records) {
                  if (record.id === props.recordId) {
                    record.recommended_question = data.content

                    await nextTick()
                  }
                }
              }
              shouldCloseStream = true
            }
            break
          case 'recommended_question_finish':
          case 'error':
            shouldCloseStream = true
            break
        }

        if (shouldCloseStream) {
          break
        }
      }

      if (shouldCloseStream) {
        await streamReader.cancel().catch(() => undefined)
        controller.abort()
        break
      }
    }
  } catch (error: any) {
    if (!stopFlag.value && error?.name !== 'AbortError') {
      console.error('Recommend questions failed:', error)
    }
  } finally {
    if (timeoutId) {
      clearTimeout(timeoutId)
    }
    if (controller && controllerRef.value === controller) {
      controllerRef.value = undefined
    }
    setLoading(false)
    emitIfMounted('loadingOver')
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

defineExpose({ getRecommendQuestions, id: () => props.recordId, stop })
</script>

<template>
  <div v-if="computedQuestions.length > 0 || loading" class="recommend-questions">
    <template v-if="position === 'chat'">
      <div v-if="firstChat" style="margin-bottom: 8px">{{ t('qa.guess_u_ask') }}</div>
      <div v-else class="continue-ask">{{ t('qa.continue_to_ask') }}</div>
    </template>
    <div v-if="loading">
      <div v-if="position === 'input'" style="margin-bottom: 8px">{{ t('qa.guess_u_ask') }}</div>
      <el-button style="min-width: unset" type="primary" link loading />
    </div>
    <div v-else-if="position === 'input'" class="question-grid-input">
      <div
        v-for="(question, index) in computedQuestions"
        :key="index"
        class="question"
        :class="{ disabled: disabled }"
        @click="clickQuestion(question)"
      >
        {{ question }}
      </div>
    </div>
    <div v-else class="question-grid">
      <div
        v-for="(question, index) in computedQuestions"
        :key="index"
        class="question"
        :class="{ disabled: disabled }"
        @click="clickQuestion(question)"
      >
        {{ question }}
      </div>
    </div>
  </div>
  <div v-else-if="position === 'input'" class="recommend-questions-error">
    {{ $t('qa.retrieve_error') }}
  </div>
</template>

<style scoped lang="less">
.recommend-questions {
  width: 100%;
  font-size: 14px;
  font-weight: 500;
  line-height: 22px;
  display: flex;
  flex-direction: column;
  gap: 4px;

  .continue-ask {
    color: rgba(100, 106, 115, 1);
    font-weight: 400;
  }

  .question-grid-input {
    display: grid;
    grid-gap: 12px;
    grid-template-columns: repeat(1, calc(100% - 6px));
  }

  .question-grid {
    display: grid;
    grid-gap: 12px;
    grid-template-columns: repeat(2, calc(50% - 6px));
  }

  .question {
    font-weight: 400;
    cursor: pointer;
    background: rgba(245, 246, 247, 1);
    min-height: 32px;
    border-radius: 6px;
    padding: 5px 12px;
    line-height: 22px;
    &:hover {
      background: rgba(31, 35, 41, 0.1);
    }
    &.disabled {
      cursor: not-allowed;
      background: rgba(245, 246, 247, 1);
    }
  }
}

.recommend-questions-error {
  font-size: 12px;
  font-weight: 500;
  color: rgba(100, 106, 115, 1);
  margin-top: 70px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
}
</style>
