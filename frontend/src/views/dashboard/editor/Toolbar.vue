<script setup lang="ts">
import {dashboardStoreWithOut} from "@/stores/dashboard/dashboard.ts";
import {storeToRefs} from 'pinia'
import IconBack from '@/assets/svg/common-back.svg'
import ComponentButtonLabel from "@/views/dashboard/components/button-label/ComponentButtonLabel.vue";
import dvTab from '@/assets/svg/dv-tab.svg'
import dvText from '@/assets/svg/dv-text.svg'
import dvView from '@/assets/svg/dv-view.svg'

const dashboardStore = dashboardStoreWithOut()
const {dashboardInfo} = storeToRefs(dashboardStore)
const emits = defineEmits(['addComponent'])

const openViewDialog = () => {
  // do addComponent
}
</script>

<template>
  <div class="toolbar-main">
    <span>
      <el-icon><IconBack/></el-icon>
    </span>
    <span>{{ dashboardInfo.name }}</span>
    <div class="core-toolbar">
      <component-button-label
          :icon-name="dvView"
          title="Add View"
          themes="light"
          is-label
          @customClick="openViewDialog"
      ></component-button-label>
      <component-button-label
          :icon-name="dvText"
          title="Text"
          themes="light"
          is-label
          @customClick="() =>emits('addComponent', 'SQText')"
      ></component-button-label>
      <component-button-label
          :icon-name="dvTab"
          title="Tab Item"
          themes="light"
          is-label
          @customClick="() =>emits('addComponent', 'SQTab')"
      >
      </component-button-label>
    </div>
  </div>
</template>

<style scoped lang="less">
.toolbar-main {
  width: 100%;
  height: 56px;
  display: flex;
  align-items: center;
  background: #050e21;
  padding-left: 8px;
  .core-toolbar {
    display: flex;
    position: absolute;
    left: 50%;
    transform: translateX(-50%);
  }
}

</style>