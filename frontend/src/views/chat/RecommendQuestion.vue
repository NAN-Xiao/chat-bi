<script setup lang="ts">
import { computed } from 'vue'
import { endsWith, startsWith } from 'lodash-es'

const props = withDefaults(
  defineProps<{
    questions?: string
  }>(),
  {
    questions: '[]',
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

function clickQuestion(question: string): void {
  emits('clickQuestion', question)
}
</script>

<template>
  <div v-if="computedQuestions.length > 0" class="recommend-questions">
    <div>推荐提问:</div>
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
