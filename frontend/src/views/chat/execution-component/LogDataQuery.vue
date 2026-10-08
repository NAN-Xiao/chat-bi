<script setup lang="ts">
import BaseContent from './BaseContent.vue'
import { type ChatLogHistoryItem } from '@/api/chat.ts'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const props = withDefaults(
  defineProps<{
    item?: ChatLogHistoryItem
    error?: string
  }>(),
  {
    item: undefined,
    error: '',
  }
)

const { t } = useI18n()

const message = computed(() => {
  return props.item?.message ?? { count: 0 }
})
const title = computed(() => {
  return t('chat.query_count_title', [message.value.count])
})
</script>

<template>
  <BaseContent class="base-container">
    <template v-if="item.error">
      {{ error }}
    </template>
    <template v-else>
      <div class="inner-title">{{ title }}</div>
    </template>
  </BaseContent>
</template>

<style scoped lang="less">
.inner-title {
  color: var(--workspace-text-secondary);
  font-size: 12px;
  line-height: 20px;
  font-weight: 500;
  vertical-align: middle;
}
.item-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: stretch;
  flex-wrap: nowrap;
  .inner-item {
    border: 1px solid var(--workspace-border);
    display: flex;
    flex-direction: column;
    gap: 8px;
    border-radius: 12px;
    padding: 16px;
    background: var(--workspace-card-bg);

    .inner-item-title {
      color: var(--workspace-text-primary);
      font-weight: 500;
      line-height: 22px;
      font-size: 14px;
      vertical-align: middle;
    }
    .inner-item-description {
      color: var(--workspace-text-secondary);
      font-weight: 400;
      line-height: 22px;
      font-size: 14px;
      vertical-align: middle;
    }
  }
}
</style>
