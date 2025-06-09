<script setup lang="ts">
import {dashboardStoreWithOut} from "@/stores/dashboard/dashboard.ts";
import {storeToRefs} from 'pinia'
import IconBack from '@/assets/svg/common-back.svg'
import ComponentButtonLabel from "@/views/dashboard/components/button-label/ComponentButtonLabel.vue";
import dvTab from '@/assets/svg/dv-tab.svg'
import dvText from '@/assets/svg/dv-text.svg'
import dvView from '@/assets/svg/dv-view.svg'
import ResourceGroupOpt from "@/views/dashboard/common/ResourceGroupOpt.vue";
import {ref} from 'vue'

const dashboardStore = dashboardStoreWithOut()
const {dashboardInfo} = storeToRefs(dashboardStore)
const emits = defineEmits(['addComponent'])
const resourceGroupOptRef = ref(null)
const openViewDialog = () => {
  // do addComponent
}

const saveCanvasWithCheck = () => {
  if (dashboardInfo.value.dataState === 'prepare') {
    const createParams = {
      name: dashboardInfo.value.name,
      pid: props.baseParams?.pid,
      opt: 'newLeaf',
      nodeType: 'leaf',
      parentSelect: true
    }
    // @ts-ignore
    resourceGroupOptRef.value?.optInit(createParams)
  }
}

const props = defineProps({
  baseParams: {
    type: Object,
    required: false,
  }
})

const groupOptFinish = (result: any) => {
  let url = window.location.href
  url = url.replace(/(#\/[^?]*)(?:\?[^#]*)?/, `$1?dvId=${result.id}`)
  window.history.replaceState( { path: url }, '', url )
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
    <div class="right-toolbar">
      <el-button @click="saveCanvasWithCheck()"
                 style="float: right; margin-right: 12px"
                 type="primary"
      >
        Save
      </el-button>
    </div>
    <ResourceGroupOpt @finish="groupOptFinish " ref="resourceGroupOptRef"></ResourceGroupOpt>
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

  .right-toolbar {
    display: flex;
    position: absolute;
    right: 12px;
  }
}

</style>