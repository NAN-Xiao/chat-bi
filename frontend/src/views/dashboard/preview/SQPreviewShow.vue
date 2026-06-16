<script setup lang="ts">
import icon_add_outlined from '@/assets/svg/icon_add_outlined.svg'
import icon_sidebar_outlined from '@/assets/svg/icon_sidebar_outlined.svg'
import { reactive, ref, toRefs, onBeforeMount, computed } from 'vue'
import { load_resource_prepare } from '@/views/dashboard/utils/canvasUtils'
import ResourceTree from '@/views/dashboard/common/ResourceTree.vue'
import SQPreview from '@/views/dashboard/preview/SQPreview.vue'
import SQPreviewHead from '@/views/dashboard/preview/SQPreviewHead.vue'
import EmptyBackground from '@/views/dashboard/common/EmptyBackground.vue'
import EmptyBackgroundSvg from '@/views/dashboard/common/EmptyBackgroundSvg.vue'
import { dashboardStoreWithOut } from '@/stores/dashboard/dashboard.ts'
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
const dashboardStore = dashboardStoreWithOut()
const previewCanvasContainer = ref(null)
const dashboardPreview = ref(null)
const slideShow = ref(true)
const dataInitState = ref(true)
const state = reactive({
  canvasDataPreview: [],
  canvasStylePreview: {},
  canvasViewInfoPreview: {},
  dashboardInfo: {},
})

const props = defineProps({
  showPosition: {
    required: false,
    type: String,
    default: 'preview',
  },
  noClose: {
    required: false,
    type: Boolean,
    default: false,
  },
})

const { showPosition } = toRefs(props)

const resourceTreeRef = ref()

const hasTreeData = computed(() => {
  return resourceTreeRef.value?.hasData
})
const mounted = computed(() => {
  return resourceTreeRef.value?.mounted
})
const canCreateDashboard = computed(() => {
  return resourceTreeRef.value?.canCreateDashboard === true
})

const stateInit = () => {
  state.canvasDataPreview = []
  state.canvasStylePreview = {}
  state.canvasViewInfoPreview = {}
  state.dashboardInfo = {}
}
const loadCanvasData = (params: any) => {
  dataInitState.value = false
  load_resource_prepare(
    { id: params.id },
    function ({ dashboardInfo, canvasDataResult, canvasStyleResult, canvasViewInfoPreview }) {
      state.canvasDataPreview = canvasDataResult
      state.canvasStylePreview = canvasStyleResult
      state.canvasViewInfoPreview = canvasViewInfoPreview
      state.dashboardInfo = dashboardInfo
      dataInitState.value = true
    }
  )
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

// @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
const previewShowFlag = computed(() => !!state.dashboardInfo?.name)
onBeforeMount(() => {
  if (showPosition.value === 'preview') {
    dashboardStore.canvasDataInit()
  }
})
const sideTreeStatus = ref(true)

function toggleSidebar() {
  sideTreeStatus.value = !sideTreeStatus.value
}

function createDashboard() {
  resourceTreeRef.value?.createNewObject()
}
defineExpose({
  getPreviewStateInfo,
})
</script>

<template>
  <div class="dv-preview dv-teleport-query no-padding">
    <div v-if="!sideTreeStatus" class="collapsed-dashboard-actions">
      <el-icon class="floating-icon-btn" size="18" @click="toggleSidebar">
        <icon_sidebar_outlined></icon_sidebar_outlined>
      </el-icon>
      <el-icon
        v-if="canCreateDashboard"
        class="floating-icon-btn create-icon-btn"
        size="18"
        @click="createDashboard"
      >
        <icon_add_outlined></icon_add_outlined>
      </el-icon>
    </div>
    <el-aside
      ref="node"
      class="resource-area"
      :class="{ 'close-side': !slideShow, retract: !sideTreeStatus }"
    >
      <resource-tree
        v-show="slideShow"
        ref="resourceTreeRef"
        :cur-canvas-type="'dashboard'"
        :show-position="showPosition"
        @node-click="resourceNodeClick"
        @delete-cur-resource="stateInit"
        @toggle-sidebar="toggleSidebar"
      />
    </el-aside>
    <section
      v-loading="!dataInitState"
      class="preview-area"
      :class="{
        'is-empty': !previewShowFlag,
        'sidebar-collapsed': !sideTreeStatus,
        'sidebar-collapsed-with-create': !sideTreeStatus && canCreateDashboard,
      }"
    >
      <div class="preview-stage">
        <SQPreviewHead :dashboard-info="previewShowFlag ? state.dashboardInfo : {}" @reload="reload" />
        <div
          id="sq-preview-content"
          ref="previewCanvasContainer"
          class="content"
          :class="{ 'content--empty': !previewShowFlag }"
        >
          <SQPreview
            v-if="previewShowFlag && state.canvasStylePreview && dataInitState"
            ref="dashboardPreview"
            :dashboard-info="state.dashboardInfo"
            :component-data="state.canvasDataPreview"
            :canvas-style-data="state.canvasStylePreview"
            :canvas-view-info="state.canvasViewInfoPreview"
            :show-position="showPosition"
          ></SQPreview>
          <EmptyBackgroundSvg
            v-else-if="hasTreeData && mounted"
            :description="t('dashboard.select_dashboard_tips')"
          />
          <EmptyBackground v-else-if="mounted" :description="t('dashboard.no_dashboard_info')" img-type="none" />
        </div>
      </div>
    </section>
  </div>
</template>

<style lang="less">
.dv-preview {
  width: 100%;
  height: 100%;
  overflow: hidden;
  display: flex;
  background: var(--workspace-panel-bg, var(--theme-panel-bg));
  color: var(--workspace-text-primary, #1f2329);
  position: relative;
  font-family: 'PingFang SC', 'Microsoft YaHei', 'Helvetica Neue', Arial, sans-serif;

  .resource-area {
    --ed-aside-width: 280px;

    position: relative;
    height: 100%;
    padding: 0;
    background: var(--workspace-panel-bg, var(--theme-panel-bg));
    color: var(--workspace-text-primary, #1f2329);
    border-right: 1px solid var(--workspace-border, var(--theme-shell-border));
    z-index: 1;
    overflow: hidden;

    &.retract {
      display: none;
    }
  }

  .preview-area {
    flex: 1;
    display: flex;
    min-width: 0;
    min-height: 0;
    overflow-x: hidden;
    overflow-y: auto;
    position: relative;
    background: var(--workspace-panel-bg, var(--theme-panel-bg));

    .preview-stage {
      display: flex;
      flex: 1;
      min-width: 0;
      min-height: 0;
      flex-direction: column;
    }

    .content {
      position: relative;
      display: flex;
      flex: 1;
      min-height: 0;
      width: 100%;
      overflow-x: hidden;
      overflow-y: auto;
      padding: 0;
      align-items: stretch;

      &.content--empty {
        align-items: center;
        justify-content: center;
      }
    }
  }
}

.preview-area.sidebar-collapsed {
  .preview-head {
    padding-left: 58px;
  }

  &.sidebar-collapsed-with-create .preview-head {
    padding-left: 94px;
  }
}

.preview-area.is-empty {
  .preview-stage {
    min-height: 0;
  }

  .content {
    min-height: 0;
  }
}

.preview-area .content.content--empty {
  :deep(.empty-info),
  :deep(.ed-empty) {
    width: 100%;
    height: 100%;
    padding-top: 0;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    background: var(--workspace-panel-bg, var(--theme-panel-bg));
  }

  :deep(.ed-empty__description) {
    color: var(--workspace-text-secondary, #66758f);
  }
}

.collapsed-dashboard-actions {
  position: absolute;
  top: 14px;
  left: 14px;
  z-index: 199;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.floating-icon-btn {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  cursor: pointer;
  color: var(--workspace-text-primary, var(--theme-text-primary));
  transition:
    background-color 0.18s ease,
    color 0.18s ease;

  &:hover {
    background: var(--workspace-control-hover-bg, var(--theme-hover-bg));
  }

  &.create-icon-btn {
    color: var(--ed-color-primary, #2f6bff);

    &:hover {
      background: var(--workspace-primary-soft-bg, rgba(47, 107, 255, 0.1));
      color: var(--ed-color-primary, #2f6bff);
    }
  }

  svg,
  :deep(svg) {
    color: inherit;
  }

  :deep(svg path) {
    fill: currentColor !important;
  }
}

.close-side {
  width: 0 !important;
  padding: 0 !important;
}

.flexible-button-area {
  position: absolute;
  height: 60px;
  width: 16px;
  left: 0;
  top: calc(50% - 30px);
  background-color: var(--workspace-card-bg, #ffffff);
  border-radius: 0 8px 8px 0;
  cursor: pointer;
  z-index: 10;
  display: flex;
  align-items: center;
  border-top: 1px solid var(--workspace-border-soft, #eff4fa);
  border-right: 1px solid var(--workspace-border-soft, #eff4fa);
  border-bottom: 1px solid var(--workspace-border-soft, #eff4fa);
}
</style>
