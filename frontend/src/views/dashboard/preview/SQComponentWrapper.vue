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
  border: 1px solid var(--workspace-border-soft, #eff4fa);
  border-radius: 12px;
  box-shadow: none;
  transform-origin: left center;
  transition:
    transform 0.18s ease,
    box-shadow 0.18s ease,
    border-color 0.18s ease;
  will-change: transform;

  &:hover {
    z-index: 20;
    border-color: rgba(47, 107, 255, 0.22);
    box-shadow:
      0 8px 20px rgba(18, 34, 66, 0.1),
      0 3px 8px rgba(18, 34, 66, 0.06);
    transform: translateY(-2px) scale(1.01);
  }

  &.is-frameless {
    border: none;
    border-radius: 0;

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
