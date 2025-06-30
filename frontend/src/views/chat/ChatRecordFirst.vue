<script setup lang="ts">
import ChatBlock from './ChatBlock.vue'
import { ChatInfo, type ChatMessage } from '@/api/chat.ts'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const props = defineProps<{
  msg: ChatMessage
  currentChat: ChatInfo
}>()

const show = computed(() => {
  return props.msg.first_chat
})
</script>

<template>
  <ChatBlock v-if="show">
    <div class="welcome-content">
      <div class="ds-select-row">
        <div>{{ t('qa.selected_datasource') }}:</div>
      </div>
      <div>
        {{ currentChat.datasource_name }}
      </div>
    </div>
  </ChatBlock>
</template>

<style scoped lang="less">
.welcome-content {
  padding: 12px;
  display: flex;
}

.sub {
  color: grey;
  font-size: 0.8em;
}

.ds-select-row {
  margin-right: 8px;
}
</style>
