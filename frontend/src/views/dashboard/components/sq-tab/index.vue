<script setup lang="ts">
import {computed, type PropType, reactive, ref, toRefs, nextTick} from 'vue'
import CustomTab from "@/views/dashboard/components/sq-tab/CustomTab.vue";
import {guid, type CanvasItem,} from "@/utils/canvas.ts";
import DragHandle from "@/views/dashboard/canvas/DragHandle.vue";
import {ArrowDown} from "@element-plus/icons-vue";

const editableTabsValue = ref(null)
const showTabTitleFlag = ref(true)
const props = defineProps({
  configItem: {
    type: Object as PropType<CanvasItem>,
    required: true
  }
})

const {configItem} = toRefs(props)

const state = reactive({
  activeTabName: '',
  curItem: {},
  textarea: '',
  dialogVisible: false,
  tabShow: true,
  hoverFlag: false,
  headFontColor: '#OOOOOO',
  headFontActiveColor: '#OOOOOO',
  headBorderColor: '#OOOOOO',
  headBorderActiveColor: '#OOOOOO'
})

function addTab() {
  const newName = guid()

  const newTab = {
    name: newName,
    title: 'New Tab',
    componentData: [],
    closable: true
  }
  configItem.value.propValue.push(newTab)
  editableTabsValue.value = newTab.name
}

function deleteCur(param:any) {
  state.curItem = param
  let len = configItem.value.propValue.length
  while (len--) {
    if (configItem.value.propValue[len].name === param.name) {
      configItem.value.propValue.splice(len, 1)
      const activeIndex =
          (len - 1 + configItem.value.propValue.length) % configItem.value.propValue.length
      editableTabsValue.value = configItem.value.propValue[activeIndex].name
      state.tabShow = false
      nextTick(() => {
        state.tabShow = true
      })
    }
  }
}

function editCurTitle(param:any) {
  state.activeTabName = param.name
  state.curItem = param
  state.textarea = param.title
  state.dialogVisible = true
}

function handleCommand(command:any) {
  switch (command.command) {
    case 'editTitle':
      editCurTitle(command.param)
      break
    case 'deleteCur':
      deleteCur(command.param)
      break
  }
}

const beforeHandleCommand = (item : any, param : any) => {
  return {
    command: item,
    param: param
  }
}

const titleStyle = (itemName: string) => {
  if (editableTabsValue.value === itemName) {
    return {}
  } else {
    return {}
  }
}

const isEditMode = computed(() => true)
</script>

<template>
  <div>
    <drag-handle></drag-handle>
    <custom-tab
        v-model="editableTabsValue"
        @tab-add="addTab"
        :addable="isEditMode"
        :font-color="state.headFontColor"
        :active-color="state.headFontActiveColor"
        :border-color="state.headBorderColor"
        :border-active-color="state.headBorderActiveColor"
        :hide-title="!showTabTitleFlag"
    >
      <template :key="tabItem.name" v-for="tabItem in configItem.propValue">
        <el-tab-pane
            class="el-tab-pane-custom"
            :lazy="isEditMode"
            :label="tabItem.title"
            :name="tabItem.name"
        >
          <template #label>
            <div class="custom-tab-title" @mousedown.stop>
              <span class="title-inner" :style="titleStyle(tabItem.name)"
              >{{ tabItem.title }}
                <span v-if="isEditMode">
                  <el-dropdown
                      popper-class="custom-de-tab-dropdown"
                      trigger="click"
                      @command="handleCommand"
                  >
                    <span class="el-dropdown-link">
                      <el-icon v-if="isEditMode"><ArrowDown/></el-icon>
                    </span>
                    <template #dropdown>
                      <el-dropdown-menu>
                        <el-dropdown-item :command="beforeHandleCommand('editTitle', tabItem)">
                          edit
                        </el-dropdown-item>
                        <el-dropdown-item :command="beforeHandleCommand('copyCur', tabItem)">
                          copy
                        </el-dropdown-item>
                        <el-dropdown-item
                            v-if="configItem.propValue.length > 1"
                            :command="beforeHandleCommand('deleteCur', tabItem)"
                        >
                          delete
                        </el-dropdown-item>
                      </el-dropdown-menu>
                    </template>
                  </el-dropdown>
                </span>
              </span>
            </div>
          </template>
        </el-tab-pane>
      </template>
      <div>
        this is a tab
      </div>
    </custom-tab>
  </div>

</template>

<style scoped lang="less">
.ed-dropdown-link{
  margin-top: 3px !important;
}

</style>