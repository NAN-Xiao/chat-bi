<script setup lang="ts">
import { toRefs } from 'vue'
import icon_delete from '@/assets/svg/icon_delete.svg'
import { Icon } from '@/components/icon-custom'
import { useEmitt } from '@/utils/useEmitt.ts'

const props = defineProps({
  active: {
    type: Boolean,
    default: false,
  },
  configItem: {
    type: Object,
    required: true,
  },
  showPosition: {
    required: false,
    type: String,
    default: 'preview',
  },
  canvasId: {
    type: String,
    default: 'canvas-main',
  },
})

const { configItem } = toRefs(props)

const doDeleteComponent = (e: MouseEvent) => {
  e.stopPropagation()
  e.preventDefault()
  useEmitt().emitter.emit(`editor-delete-${props.canvasId}`, configItem.value.id)
}
</script>

<template>
  <div class="component-bar-main" :class="{ 'bar-hidden': !active }">
    <div>
      <el-icon class="handle-icon" @click="doDeleteComponent">
        <Icon>
          <icon_delete class="svg-icon"></icon_delete>
        </Icon>
      </el-icon>
    </div>
  </div>
</template>

<style scoped lang="less">
.component-bar-main {
  height: 20px;
  position: absolute;
  right: 5px;
  top: 5px;
  display: flex;
  z-index: 5;
  cursor: pointer !important;
  .handle-icon {
    color: #646a73;
  }
  &:hover {
    background-color: #e8f0fe;
    color: var(--el-color-primary);
  }
}

.bar-hidden {
  display: none;
}
</style>
