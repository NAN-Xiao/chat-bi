<script setup lang="ts">
import { computed } from 'vue'
import type { ChatLogHistoryItem } from '@/api/chat'
import BaseContent from './BaseContent.vue'
import SQLComponent from '@/views/chat/component/SQLComponent.vue'

const props = defineProps<{ item: ChatLogHistoryItem }>()
const details = computed(() => JSON.stringify(props.item.message ?? [], null, 2))
</script>

<template>
  <BaseContent>
    <SQLComponent :sql="details" />
  </BaseContent>
</template>
