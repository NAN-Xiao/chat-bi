<script setup lang="ts">
import { ref, toRefs, computed } from 'vue'
import { findComponent } from '@/views/dashboard/components/component-list.ts'

const componentWrapperInnerRef = ref(null)

const props = defineProps({
  active: {
    type: Boolean,
    default: false,
  },
  configItem: {
    type: Object,
    required: true,
  },
  canvasViewInfo: {
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
  frameless: {
    type: Boolean,
    default: false,
  },
})
const { configItem, showPosition } = toRefs(props)
const component = ref(null)
const wrapperId = 'wrapper-outer-id-' + configItem.value.id
const viewDemoInnerId = computed(() => 'enlarge-inner-content-' + configItem.value.id)
</script>

<template>
  <div :id="wrapperId" class="wrapper-outer" :class="{ 'is-frameless': frameless }">
    <div :id="viewDemoInnerId" ref="componentWrapperInnerRef" class="wrapper-inner">
      <div class="wrapper-inner-adaptor">
        <component
          :is="findComponent(configItem['component'])"
          ref="component"
          class="component"
          :canvas-view-info="canvasViewInfo"
          :view-info="canvasViewInfo[configItem.id]"
          :config-item="configItem"
          :show-position="showPosition"
          :disabled="true"
          :active="active"
        />
      </div>
    </div>
  </div>
</template>

<style lang="less" scoped>
.wrapper-outer {
  position: absolute;
  overflow: hidden;
  background: var(--workspace-card-bg, #ffffff);
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 12px;
  box-shadow:
    0 2px 8px rgba(18, 34, 66, 0.035),
    0 1px 2px rgba(18, 34, 66, 0.025);
  transform-origin: center;
  transition:
    transform 0.14s ease,
    box-shadow 0.14s ease,
    border-color 0.14s ease;
  will-change: transform, box-shadow;

  &:hover {
    z-index: 20;
    border-color: rgba(47, 107, 255, 0.18);
    box-shadow:
      0 8px 20px rgba(18, 34, 66, 0.1),
      0 3px 8px rgba(18, 34, 66, 0.06);
    transform: translateY(-2px);
  }

  &:active {
    box-shadow:
      0 6px 16px rgba(18, 34, 66, 0.08),
      0 2px 6px rgba(18, 34, 66, 0.05);
    transform: translateY(0);
  }

  &.is-frameless {
    border: none;
    border-radius: 0;
    box-shadow: none;
    transition: none;
    will-change: auto;

    &:hover {
      z-index: auto;
      border-color: transparent;
      box-shadow: none;
      transform: none;
    }

    .wrapper-inner {
      border-radius: 0;
    }
  }

  .wrapper-inner {
    width: 100%;
    height: 100%;
    position: relative;
    background: var(--workspace-card-bg, #ffffff);
    background-size: 100% 100% !important;
    .wrapper-inner-adaptor {
      position: relative;
      transform-style: preserve-3d;
      width: 100%;
      height: 100%;
      .component {
        width: 100%;
        height: 100%;
      }
    }
  }
}
</style>
