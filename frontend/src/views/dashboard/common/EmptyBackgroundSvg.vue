<script lang="ts" setup>
import { onUnmounted, ref } from 'vue'
import { getCurrentTheme, subscribeTheme } from '@/utils/theme'
import nothingSelectDashboard from '@/assets/img/none-dashboard.svg'
const theme = ref(getCurrentTheme())
onUnmounted(subscribeTheme(value => { theme.value = value }))
defineProps({
  imageSize: {
    type: Number,
    default: 125,
  },
  description: {
    type: String,
    default: '',
  },
})
</script>

<template>
  <el-empty v-if="theme === 'dark'" class="empty-info" :image-size="imageSize" :description="description">
    <slot></slot>
  </el-empty>
  <div v-else class="ed-empty empty-info">
    <div class="ed-empty__image" style="width: 125px">
      <el-icon size="125" class="icon-primary">
        <nothingSelectDashboard></nothingSelectDashboard>
      </el-icon>
    </div>
    <div class="ed-empty__description">
      <p>{{ description }}</p>
    </div>
    <slot></slot>
  </div>
</template>

<style lang="less" scoped>
.empty-info {
  height: 90%;
  padding-top: 0;
}
:deep(.ed-empty__description) {
  margin-top: 8px;
  color: var(--theme-text-secondary);
  text-align: center;
  font-size: 14px;
  font-style: normal;
  font-weight: 400;
  line-height: 22px;
}

:deep(.ed-empty__description p) { color: var(--theme-text-secondary); }
</style>
