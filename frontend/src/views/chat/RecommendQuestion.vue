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
    <div v-else class="continue-ask">{{ t('qa.continue_to_ask') }}</div>
    <div class="question-grid">
      <div
        v-for="(question, index) in computedQuestions"
        :key="index"
        class="question"
        @click="clickQuestion(question)"
      >
        {{ question }}
      </div>
    </div>
  </div>
</template>

<style scoped lang="less">
.recommend-questions {
  padding: 8px;
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

  .question-grid {
    display: grid;
    grid-gap: 12px;
    grid-template-columns: repeat(2, 50%);
  }

  .question {
    font-weight: 400;
    cursor: pointer;
    background: rgba(245, 246, 247, 1);
    min-height: 46px;
    border-radius: 6px;
    padding: 12px;
    line-height: 22px;
    &:hover {
      background: rgba(31, 35, 41, 0.1);
    }
  }
}
</style>
