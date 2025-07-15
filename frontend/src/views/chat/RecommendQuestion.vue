<script setup lang="ts">
import { computed } from 'vue'
import { endsWith, startsWith } from 'lodash-es'
import { useI18n } from 'vue-i18n'

const props = withDefaults(
  defineProps<{
    questions?: string
    firstChat?: boolean
  }>(),
  {
    questions: '[]',
    firstChat: false,
  }
)
const computedQuestions = computed<string>(() => {
  if (
    props.questions &&
    props.questions.length > 0 &&
    startsWith(props.questions.trim(), '[') &&
    endsWith(props.questions.trim(), ']')
  ) {
    return JSON.parse(props.questions)
  }
  return []
})

const emits = defineEmits(['clickQuestion'])

const { t } = useI18n()

function clickQuestion(question: string): void {
  emits('clickQuestion', question)
}
</script>

<template>
  <div v-if="computedQuestions.length > 0" class="recommend-questions">
    <div v-if="firstChat">{{ t('qa.guess_u_ask') }}</div>
    <div v-else>{{ t('qa.continue_to_ask') }}</div>
    <div v-for="(question, index) in computedQuestions" :key="index">
      <span class="question" @click="clickQuestion(question)">
        {{ question }}
      </span>
    </div>
  </div>
</template>

<style scoped lang="less">
.recommend-questions {
  padding: 8px;
  font-size: 12px;
  font-weight: 400;
  display: flex;
  flex-direction: column;
  gap: 4px;
  .question {
    cursor: pointer;
    background: lightgray;
    border-radius: 4px;
    padding: 4px;
    line-height: 20px;
    &:hover {
      background: grey;
    }
  }
}
</style>
