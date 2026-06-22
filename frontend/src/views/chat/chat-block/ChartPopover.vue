<script lang="ts" setup>
import icon_done_outlined from '@/assets/svg/icon_done_outlined.svg'
import { computed, ref } from 'vue'
import icon_expand_down_filled from '@/assets/svg/icon_down_outlined.svg'
const props = defineProps({
  chartTypeList: {
    type: Array<any>,
    default: () => [],
  },
  chartType: {
    type: String,
    default: 'table',
  },
  title: {
    type: String,
    default: '',
  },
})
const currentIcon = computed(() => {
  if (props.chartType === 'table') {
    const [ele] = props.chartTypeList || []
    if (ele.icon) {
      return ele.icon
    }
    return null
  }
  return props.chartTypeList.find((ele) => ele.value === props.chartType)?.icon ?? null
})

const firstItem = () => {
  if (props.chartType === 'table') {
    const [ele] = props.chartTypeList || []
    handleDefaultChatChange(ele || {})
  }
}
const emits = defineEmits(['typeChange'])
const selectRef = ref()
const handleDefaultChatChange = (val: any) => {
  emits('typeChange', val.value)
  selectRef.value?.hide()
}
</script>

<template>
  <el-popover ref="selectRef" trigger="click" popper-class="chat-type_select" placement="bottom">
    <template #reference>
      <div
        class="chat-select_type"
        :class="chartType && chartType !== 'table' && 'active'"
        @click="firstItem"
      >
        <component :is="currentIcon" />
        <el-icon class="expand" size="12">
          <icon_expand_down_filled></icon_expand_down_filled>
        </el-icon>
      </div>
    </template>
    <div class="popover">
      <div class="popover-content">
        <div v-if="!!title" class="title">{{ title }}</div>
        <div
          v-for="ele in chartTypeList"
          :key="ele.name"
          class="popover-item"
          :class="chartType === ele.value && 'isActive'"
          @click="handleDefaultChatChange(ele)"
        >
          <el-icon size="16">
            <component :is="ele.icon" :class="chartType === ele.value && 'icon-primary'" />
          </el-icon>
          <div class="model-name">{{ ele.name }}</div>
          <el-icon size="16" class="done">
            <icon_done_outlined></icon_done_outlined>
          </el-icon>
        </div>
      </div>
    </div>
  </el-popover>
</template>

<style lang="less">
.chat-type_select.chat-type_select {
  padding: 6px 0;
  width: 136px !important;
  min-width: 136px !important;
  box-shadow: 0 18px 44px rgba(24, 46, 86, 0.12);
  border: 1px solid rgba(211, 224, 241, 0.92);
  background: var(--workspace-card-bg, #ffffff);

  .popover {
    .popover-content {
      padding: 0 4px;
      max-height: 300px;
      overflow-y: auto;

      .title {
        width: 100%;
        height: 30px;
        margin-bottom: 2px;
        display: flex;
        align-items: center;
        padding-left: 8px;
        color: #8797ad;
        font-size: 12px;
      }
    }
    .popover-item {
      height: 34px;
      display: flex;
      align-items: center;
      padding-left: 12px;
      padding-right: 8px;
      margin-bottom: 2px;
      position: relative;
      border-radius: 6px;
      cursor: pointer;
      &:last-child {
        margin-bottom: 0;
      }
      &:hover {
        background: #f3f7ff;
      }

      .model-name {
        margin-left: 8px;
        font-weight: 400;
        font-size: 14px;
        line-height: 22px;
        max-width: 220px;
      }

      .done {
        margin-left: auto;
        display: none;
      }

      &.isActive {
        color: var(--ed-color-primary);

        .done {
          display: block;
        }
      }
    }
  }
}
</style>

<style lang="less" scoped>
.chat-select_type {
  width: 40px;
  height: 28px;
  border-radius: 6px;
  padding-left: 4px;
  display: flex;
  align-items: center;
  cursor: pointer;
  color: #6d7c93;

  .expand {
    margin-left: 4px;
  }

  &:hover {
    background: #f1f6ff;
    color: #263a59;
  }

  &.active {
    background: #eaf1ff;
    color: var(--ed-color-primary, #2f6bff);
  }
}
</style>
