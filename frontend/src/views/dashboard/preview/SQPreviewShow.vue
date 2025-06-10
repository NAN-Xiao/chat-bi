<script setup lang="ts">
import icon_add_outlined from '@/assets/svg/icon_add_outlined.svg'
import {reactive, ref, toRefs, onBeforeMount, computed} from 'vue'
import {initCanvasData} from '@/views/dashboard/utils/canvasUtils'
import {Icon} from '@/components/icon-custom'
import ResourceTree from "@/views/dashboard/common/ResourceTree.vue";
import SQPreview from "@/views/dashboard/preview/SQPreview.vue";
import SQPreviewHead from "@/views/dashboard/preview/SQPreviewHead.vue";
import EmptyBackground from "@/views/dashboard/common/EmptyBackground.vue";
import {dashboardStoreWithOut} from "@/stores/dashboard/dashboard.ts";

const dashboardStore = dashboardStoreWithOut()
const previewCanvasContainer = ref(null)
const dashboardPreview = ref(null)
const slideShow = ref(true)
const dataInitState = ref(true)
const downloadStatus = ref(false)
const state = reactive({
  canvasDataPreview: null,
  canvasStylePreview: null,
  canvasViewInfoPreview: null,
  dashboardInfo: null,
  showOffset: {
    top: 110,
    left: 280
  }
})

const props = defineProps({
  showPosition: {
    required: false,
    type: String,
    default: 'preview'
  },
  noClose: {
    required: false,
    type: Boolean,
    default: false
  }
})

const {showPosition} = toRefs(props)

const resourceTreeRef = ref()

const hasTreeData = computed(() => {
  return resourceTreeRef.value?.hasData
})

const rootManage = computed(() => {
  return resourceTreeRef.value?.rootManage
})
const mounted = computed(() => {
  return resourceTreeRef.value?.mounted
})


function createNew() {
  resourceTreeRef.value?.createNewObject()
}

const loadCanvasData = (params: any) => {
  dataInitState.value = false
  //@ts-ignore
  initCanvasData({id:params.id}, function ({dashboardInfo, canvasDataResult, canvasStyleResult, canvasViewInfoPreview}) {
        state.canvasDataPreview = canvasDataResult
        state.canvasStylePreview = canvasStyleResult
        state.canvasViewInfoPreview = canvasViewInfoPreview
        state.dashboardInfo = dashboardInfo
        dataInitState.value = true
      }
  )
}

// @ts-ignore
const slideOpenChange = () => {
  slideShow.value = !slideShow.value
}

const getPreviewStateInfo = () => {
  return state
}

const reload = (params: any) => {
  loadCanvasData(params)
}

const resourceNodeClick = (prams: any) => {
  loadCanvasData(prams)
}

const previewShowFlag = computed(() => !!dashboardStore.dashboardInfo?.name)

onBeforeMount(() => {
  if (showPosition.value === 'preview') {
    dashboardStore.canvasDataInit()
  }
})
const sideTreeStatus = ref(true)
// @ts-ignore
const changeSideTreeStatus = val => {
  sideTreeStatus.value = val
}

const freezeStyle = computed(() => [
  {'--top-show-offset': state.showOffset.top},
  {'--left-show-offset': state.showOffset.left}
])

defineExpose({
  getPreviewStateInfo
})
</script>

<template>
  <div class="dv-preview dv-teleport-query" :style="freezeStyle">
    <el-aside
        class="resource-area"
        :class="{ 'close-side': !slideShow, retract: !sideTreeStatus }"
        ref="node"
        style="width: 280px"
    >
      <resource-tree
          ref="resourceTreeRef"
          v-show="slideShow"
          :cur-canvas-type="'dashboard'"
          :show-position="showPosition"
          @node-click="resourceNodeClick"
      />
    </el-aside>
    <el-container
        class="preview-area"
        :class="{ 'no-data': !state.dashboardInfo }"
        v-loading="!dataInitState"
    >
      <template v-if="previewShowFlag">
        <SQPreviewHead  @reload="reload"  />
        <div
            ref="previewCanvasContainer"
            class="content"
            id="sq-preview-content"
        >
          <SQPreview
              ref="dashboardPreview"
              v-if="state.canvasStylePreview && dataInitState"
              :dv-info="state.dashboardInfo"
              :component-data="state.canvasDataPreview"
              :canvas-style-data="state.canvasStylePreview"
              :canvas-view-info="state.canvasViewInfoPreview"
              :show-position="showPosition"
              :download-status="downloadStatus"
              :show-linkage-button="false"
          ></SQPreview>
        </div>
      </template>
      <template v-else-if="hasTreeData && mounted">
        <EmptyBackground :description="'Please Select Resource'" img-type="select"/>
      </template>
      <template v-else-if="mounted">
        <EmptyBackground :description="'No Resource'" img-type="none">
          <el-button v-if="rootManage" @click="createNew" type="primary">
            <template #icon>
              <Icon name="icon_add_outlined">
                <icon_add_outlined class="svg-icon"/>
              </Icon>
            </template>
            Create Dashboard
          </el-button>
        </EmptyBackground>
      </template>
    </el-container>
  </div>
</template>

<style lang="less">
.dv-preview {
  width: 100%;
  height: 100%;
  overflow: hidden;
  display: flex;
  background: #ffffff;
  position: relative;

  .resource-area {
    position: relative;
    height: 100%;
    width: 279px;
    padding: 0;
    border-right: 1px solid #d7d7d7;
    overflow: visible;

    &.retract {
      display: none;
    }
  }

  .preview-area {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow-x: hidden;
    overflow-y: auto;
    position: relative;
    //transition: 0.5s;

    &.no-data {
      background-color: rgba(245, 246, 247, 1);
    }

    .content {
      position: relative;
      display: flex;
      width: 100%;
      height: 100%;
      overflow-x: hidden;
      overflow-y: auto;
      align-items: center;
    }
  }
}

.close-side {
  width: 0px !important;
  padding: 0px !important;
}

.flexible-button-area {
  position: absolute;
  height: 60px;
  width: 16px;
  left: 0;
  top: calc(50% - 30px);
  background-color: #ffffff;
  border-radius: 0 4px 4px 0;
  cursor: pointer;
  z-index: 10;
  display: flex;
  align-items: center;
  border-top: 1px solid #d7d7d7;
  border-right: 1px solid #d7d7d7;
  border-bottom: 1px solid #d7d7d7;
}
</style>
