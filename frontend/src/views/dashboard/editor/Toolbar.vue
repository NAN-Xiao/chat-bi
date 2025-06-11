<script setup lang="ts">
import {dashboardStoreWithOut} from "@/stores/dashboard/dashboard.ts";
import {storeToRefs} from 'pinia'
import ComponentButtonLabel from "@/views/dashboard/components/button-label/ComponentButtonLabel.vue";
import dvTab from '@/assets/svg/dv-tab.svg'
import dvText from '@/assets/svg/dv-text.svg'
import dvView from '@/assets/svg/dv-view.svg'
import ResourceGroupOpt from "@/views/dashboard/common/ResourceGroupOpt.vue";
import {ref, nextTick} from 'vue'
import {useI18n} from 'vue-i18n'
import {snapshotStoreWithOut} from "@/stores/dashboard/snapshot.ts";
import icon_undo_outlined from '@/assets/svg/icon_undo_outlined.svg'
import icon_redo_outlined from '@/assets/svg/icon_redo_outlined.svg'
import icon_left_outlined from '@/assets/svg/icon_left_outlined.svg'
import {saveDashboardResource} from "@/views/dashboard/utils/canvasUtils.ts";

const {t} = useI18n()
const dashboardStore = dashboardStoreWithOut()
const {dashboardInfo} = storeToRefs(dashboardStore)

const snapshotStore = snapshotStoreWithOut()
const {snapshotIndex} = storeToRefs(snapshotStore)
const emits = defineEmits(['addComponent'])
const resourceGroupOptRef = ref(null)
const openViewDialog = () => {
  // do addComponent
}

let nameEdit = ref(false)
let inputName = ref('')
let nameInput = ref(null)

const onDvNameChange = () => {

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
  } else if (dashboardInfo.value.id) {
    const updateParams = {
      opt: 'updateLeaf',
      id: dashboardInfo.value.id,
      name: dashboardInfo.value.name,
      pid: dashboardInfo.value.pid
    }
    saveDashboardResource(updateParams, function () {
      ElMessage({
        type: 'success',
        message: t('common.save_success'),
      })
    })
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
  url = url.replace(/(#\/[^?]*)(?:\?[^#]*)?/, `$1?resourceId=${result.resourceId}`)
  window.history.replaceState({path: url}, '', url)
}


const editCanvasName = () => {
  nameEdit.value = true
  //@ts-ignore
  inputName.value = dashboardInfo.value.name
  nextTick(() => {
    //@ts-ignore
    nameInput.value?.focus()
  })
}
const closeEditCanvasName = () => {
  nameEdit.value = false
  if (!inputName.value || !inputName.value.trim()) {
    return
  }
  if (inputName.value.trim() === dashboardInfo.value.name) {
    return
  }
  if (inputName.value.trim().length > 64 || inputName.value.trim().length < 1) {
    ElMessage.warning(t('dashboard.length_1_64_characters'))
    editCanvasName()
    return
  }
  //@ts-ignore
  dashboardInfo.value.name = inputName.value
  inputName.value = ''
}


const undo = () => {
  if (snapshotIndex.value > 0) {
    snapshotStore.undo()
  }
}

const redo = () => {
  if (snapshotIndex.value !== snapshotStore.snapshotData.length - 1) {
    snapshotStore.redo()
  }
}


const backToMain = () => {
  let url = '#/dashboard/index'
  if (dashboardInfo.value.id) {
    url = url + '?resourceId=' + dashboardInfo.value.id
  }
  if (!!history.state.back) {
    history.back()
  } else {
    window.open(url, '_self')
  }
}

</script>

<template>
  <div class="toolbar-main">
    <el-icon class="custom-el-icon back-icon" @click="backToMain()">
      <Icon name="icon_left_outlined">
        <icon_left_outlined class="toolbar-hover-icon toolbar-icon"/>
      </Icon>
    </el-icon>
    <div class="left-area">
          <span id="canvas-name" class="name-area" @dblclick="editCanvasName">
            {{ dashboardInfo.name }}
          </span>
      <div class="opt-area">
        <el-tooltip effect="dark" :content="t('dashboard.undo')" placement="bottom">
          <el-icon
              class="toolbar-hover-icon"
              :class="{ 'toolbar-icon-disabled': snapshotIndex < 1 }"
              :disabled="snapshotIndex < 1"
              @click="undo()"
          >
            <Icon name="icon_undo_outlined">
              <icon_undo_outlined class="svg-icon"/>
            </Icon>
          </el-icon>
        </el-tooltip>

        <el-tooltip effect="dark" :content="t('dashboard.reduction')" placement="bottom">
          <el-icon
              class="toolbar-hover-icon opt-icon-redo"
              :class="{
                  'toolbar-icon-disabled': snapshotIndex === snapshotStore.snapshotData.length - 1
                }"
              @click="redo()"
          >
            <Icon name="icon_redo_outlined">
              <icon_redo_outlined class="svg-icon"/>
            </Icon>
          </el-icon>
        </el-tooltip>
      </div>
    </div>
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
    <Teleport v-if="nameEdit" :to="'#canvas-name'">
      <input
          @change="onDvNameChange"
          ref="nameInput"
          v-model="inputName"
          @blur="closeEditCanvasName"
      />
    </Teleport>
    <ResourceGroupOpt @finish="groupOptFinish " ref="resourceGroupOptRef"></ResourceGroupOpt>
  </div>
</template>

<style scoped lang="less">
.toolbar-main {
  width: 100%;
  height: 56px;
  display: flex;
  align-items: center;
  background: #d1ddf6;
  padding-left: 8px;

  .left-area {
    margin-top: 8px;
    margin-left: 14px;
    width: 300px;
    display: flex;
    flex-direction: column;

    .name-area {
      position: relative;
      line-height: 24px;
      height: 24px;
      font-size: 16px;
      width: 300px;
      overflow: hidden;
      cursor: pointer;
      color: #fff;

      input {
        position: absolute;
        left: 0;
        width: 100%;
        color: #fff;
        background-color: #d1ddf6;
        outline: none;
        border: 1px solid #295acc;
        border-radius: 4px;
        padding: 0 4px;
        height: 100%;
      }
    }

    .opt-area {
      width: 300px;
      text-align: left;
      color: #a6a6a6;

      .opt-icon-redo {
        margin-left: 12px;
      }
    }
  }

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

.toolbar-icon {
  width: 20px;
  height: 20px;
  color: #fff;
}


.toolbar-hover-icon {
  cursor: pointer;
  font-size: 18px !important;
  width: 26px !important;
  height: 26px !important;
  color: rgba(255, 255, 255, 1);
  border-radius: 4px;

  &:hover {
    background: rgba(235, 235, 235, 0.1);
  }

  &:active {
    background: transparent;
  }
}

</style>