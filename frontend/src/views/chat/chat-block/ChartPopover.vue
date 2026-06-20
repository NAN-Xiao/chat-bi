<script lang="ts" setup>
import icon_done_outlined from '@/assets/svg/icon_done_outlined.svg'
import { computed, ref } from 'vue'
import { ArrowDown } from '@element-plus/icons-vue'
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
        <el-icon class="expand" size="11">
          <ArrowDown />
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
  width: 132px !important;
  min-width: 132px !important;
  box-shadow: 0 14px 34px rgba(24, 46, 86, 0.14);
  border: 1px solid #e2e8f2;
  border-radius: 8px;
  background: var(--workspace-card-bg, #ffffff);

  .popover {
    .popover-content {
      padding: 0 4px;
      max-height: 300px;
      overflow-y: auto;

      .title {
        width: 100%;
        height: 28px;
        margin-bottom: 2px;
        display: flex;
        align-items: center;
        padding-left: 8px;
        color: #8090a6;
        font-size: 12px;
        font-weight: 500;
      }
    }
    .popover-item {
      height: 30px;
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
        background: #f2f6fc;
      }

      .model-name {
        margin-left: 8px;
        font-weight: 500;
        font-size: 13px;
        line-height: 20px;
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
  width: 44px;
  height: 30px;
  border-radius: 7px;
  padding: 0 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: #60728c;
  transition:
    background-color 0.16s ease,
    color 0.16s ease,
    box-shadow 0.16s ease;

  .expand {
    margin-left: 3px;
    opacity: 0.76;
  }

  &:hover {
    background: #f5f8fd;
    color: #34516f;
  }

  &.active {
    background: #edf4ff;
    color: #346fe8;
    box-shadow: inset 0 0 0 1px rgba(79, 125, 243, 0.22);
  }
}
</style>
