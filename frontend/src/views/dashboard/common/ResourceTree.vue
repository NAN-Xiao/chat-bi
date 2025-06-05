<script setup lang="ts">
import icon_add_outlined from '@/assets/svg/icon_add_outlined.svg'
import {treeDraggableChart} from '@/views/dashboard/utils/treeDraggableChart'
import newFolder from '@/assets/svg/new-folder.svg'
import icon_searchOutline_outlined from '@/assets/svg/icon_search-outline_outlined.svg'
import Folder from '@/assets/svg/folder.svg'
import icon_fileAdd_outlined from '@/assets/svg/icon_file-add_outlined.svg'
import icon_operationAnalysis_outlined from '@/assets/svg/icon_operation-analysis_outlined.svg'
import icon_edit_outlined from '@/assets/svg/icon_edit_outlined.svg'
import {onMounted, reactive, ref, watch, nextTick, computed} from 'vue'
import {ElIcon, ElScrollbar} from 'element-plus-secondary'
import {Icon} from '@/components/icon-custom'
import {type SQTreeNode} from '@/views/dashboard/utils/treeNode'
import _ from 'lodash'
import router from '@/router'
import {dashboardStoreWithOut} from "@/stores/dashboard/dashboard.ts";
import HandleMore from "@/views/dashboard/common/HandleMore.vue";
import ResourceGroupOpt from "@/views/dashboard/common/ResourceGroupOpt.vue";

const dashboardStore = dashboardStoreWithOut()
const resourceGroupOptRef = ref(null)

defineProps({
  curCanvasType: {
    type: String,
    required: true
  },
  showPosition: {
    required: false,
    type: String,
    default: 'preview'
  },
  resourceTable: {
    required: false,
    type: String,
    default: 'core'
  }
})
const defaultProps = {
  children: 'children',
  label: 'name',
  disabled: (data: any) => data.extraFlag1 === 0
}
const mounted = ref(false)
const selectedNodeKey: any = ref(null)
const filterText = ref(null)
const expandedArray = ref([])
const resourceListTree = ref()
const returnMounted = ref(false)
const state = reactive({
  curSortType: 'time_desc',
  resourceTree: [] as SQTreeNode[],
  originResourceTree: [] as SQTreeNode[],
  folderMenuList: [],
  sortType: [],
  templateCreatePid: 0
})


const resourceTypeList = computed(() => {
  return []
})

// @ts-ignore
const {handleDrop, allowDrop, handleDragStart} = treeDraggableChart(
    state,
    'resourceTree',
    'dashboard'
)


const routerDashboardId = router.currentRoute.value.query.dashboardId
if (routerDashboardId) {
  selectedNodeKey.value = routerDashboardId
  returnMounted.value = true
}
const nodeExpand = (data: any) => {
  if (data.id) {
    // @ts-ignore
    expandedArray.value.push(data.id)
  }
}

const nodeCollapse = (data: any) => {
  if (data.id) {
    // @ts-ignore
    expandedArray.value.splice(expandedArray.value.indexOf(data.id), 1)
  }
}

const filterNode = (value: string, data: SQTreeNode) => {
  if (!value) return true
  return data.name?.toLocaleLowerCase().includes(value.toLocaleLowerCase())
}

const nodeClick = (data: SQTreeNode, node: any) => {
  dashboardStore.setCurComponent({component: null, index: null})
  if (node.disabled) {
    nextTick(() => {
      const currentNode = resourceListTree.value.$el.querySelector('.is-current')
      if (currentNode) {
        currentNode.classList.remove('is-current')
      }
      return
    })
  } else {
    selectedNodeKey.value = data.id
    if (data.leaf) {
      emit('nodeClick', data)
    } else {
      resourceListTree.value.setCurrentKey(null)
    }
  }
}

const getTree = async () => {
  state.originResourceTree = []
  afterTreeInit()
}
// @ts-ignore
const flattedTree = computed<SQTreeNode[]>(() => {
  return _.filter(flatTree(state.resourceTree), node => node.leaf)
})

const hasData = computed<boolean>(() => flattedTree.value.length > 0)

function flatTree(tree: SQTreeNode[]) {
  let result = _.cloneDeep(tree)
  _.forEach(tree, node => {
    if (node.children && node.children.length > 0) {
      result = _.union(result, flatTree(node.children))
    }
  })
  return result
}

const afterTreeInit = () => {
  mounted.value = true
  if (selectedNodeKey.value && returnMounted.value) {
    // @ts-ignore
    expandedArray.value = getDefaultExpandedKeys()
    returnMounted.value = false
  }
  nextTick(() => {
    resourceListTree.value.setCurrentKey(selectedNodeKey.value)
    resourceListTree.value.filter(filterText.value)
    nextTick(() => {
      // @ts-ignore
      document.querySelector('.is-current')?.firstChild?.click()
    })
  })
}

const copyLoading = ref(false)
const emit = defineEmits(['nodeClick'])


function createNewObject() {
}

// @ts-ignore
const resourceEdit = resourceId => {

}

// @ts-ignore
const getParentKeys = (tree: any, targetKey: any, parentKeys = []) => {
  for (const node of tree) {
    if (node.id === targetKey) {
      return parentKeys
    }
    if (node.children) {
      const newParentKeys = [...parentKeys, node.id]
      // @ts-ignore
      const result = getParentKeys(node.children, targetKey, newParentKeys)
      if (result) {
        return result
      }
    }
  }
  return null
}

const getDefaultExpandedKeys = () => {
  const parentKeys = getParentKeys(state.resourceTree, selectedNodeKey.value)
  if (parentKeys) {
    return [selectedNodeKey.value, ...parentKeys]
  } else {
    return []
  }
}

watch(filterText, val => {
  resourceListTree.value.filter(val)
})


const loadInit = () => {
}
onMounted(() => {
  loadInit()
  getTree()
})

// @ts-ignore
const addOperation = (params: any) => {
  if (params.cmd === 'newLeaf') {
    const newCanvasUrl = '#/canvas?opt=create' + params.data?.id ? `&pid=${params.data?.id}` : ''
    window.open(newCanvasUrl, '_blank')
  } else {
    // @ts-ignore
    resourceGroupOptRef.value?.optInit(params)
  }
}


defineExpose({
  hasData,
  createNewObject,
  mounted
})
</script>

<template>
  <div class="resource-tree">
    <div class="tree-header">
      <div class="icon-methods">
        <span class="title"> Dashboard </span>
        <div class="flex-align-center">
          <el-tooltip :content="'New Folder'" placement="top" effect="dark">
            <el-icon
                class="custom-icon btn"
                style="margin-right: 10px"
                @click="addOperation({cmd:'newFolder',type:'folder'} )"
            >
              <Icon name="dv-new-folder">
                <newFolder class="svg-icon"/>
              </Icon>
            </el-icon>
          </el-tooltip>
          <el-tooltip :content="'Add Dashboard'" placement="top" effect="dark">
            <el-icon
                class="custom-icon btn"
                style="margin-right: 10px"
            >
              <Icon name="dv-new-folder">
                <icon_fileAdd_outlined class="svg-icon"/>
              </Icon>
            </el-icon>
          </el-tooltip>
        </div>
      </div>
      <el-input
          :placeholder="'Search'"
          v-model="filterText"
          clearable
          class="search-bar"
      >
        <template #prefix>
          <el-icon>
            <Icon name="icon_search-outline_outlined"
            >
              <icon_searchOutline_outlined class="svg-icon"
              />
            </Icon>
          </el-icon>
        </template>
      </el-input>
    </div>
    <el-scrollbar class="custom-tree" v-loading="copyLoading">
      <el-tree
          menu
          ref="resourceListTree"
          :default-expanded-keys="expandedArray"
          :data="state.resourceTree"
          :props="defaultProps"
          node-key="id"
          highlight-current
          :expand-on-click-node="true"
          :filter-node-method="filterNode"
          @node-expand="nodeExpand"
          @node-collapse="nodeCollapse"
          @node-click="nodeClick"
          @node-drag-start="handleDragStart"
          @node-drop="handleDrop"
          draggable
      >
        <template #default="{ data }">
          <span class="custom-tree-node" :class="{ 'node-disabled-custom': data.extraFlag1 === 0 }">
            <el-icon style="font-size: 18px" v-if="!data.leaf">
              <Icon name="dv-folder"><Folder class="svg-icon"/></Icon>
            </el-icon>
            <el-icon
                class="icon-screen-new color-dataV"
                :class="{ 'color-dataV': data.extraFlag1, 'color-dataV-disabled': !data.extraFlag1 }"
                style="font-size: 18px"
                v-else
            >
              <Icon name="icon_operation-analysis_outlined"
              ><icon_operationAnalysis_outlined class="svg-icon"
              /></Icon>
            </el-icon>
            <div class="icon-more">
              <el-icon
                  v-on:click.stop
                  v-if="data.leaf"
                  class="hover-icon"
                  @click="resourceEdit(data.id)"
              >
                <Icon><icon_edit_outlined class="svg-icon"/></Icon>
              </el-icon>
              <HandleMore
                  @handle-command=" (cmd:string) => addOperation({cmd})
                "
                  :menu-list="resourceTypeList"
                  :icon-name="icon_add_outlined"
                  placement="bottom-start"
                  v-if="!data.leaf"
              ></HandleMore>
            </div>
          </span>
        </template>
      </el-tree>
    </el-scrollbar>
    <ResourceGroupOpt ref="resourceGroupOptRef"></ResourceGroupOpt>
  </div>
</template>
<style lang="less" scoped>
.filter-icon-span {
  border: 1px solid #bbbfc4;
  width: 32px;
  height: 32px;
  border-radius: 4px;
  color: #1f2329;
  padding: 8px;
  margin-left: 8px;
  font-size: 16px;
  cursor: pointer;

  .opt-icon:focus {
    outline: none !important;
  }

  &:hover {
    background: #f5f6f7;
  }

  &:active {
    background: #eff0f1;
  }
}

.resource-tree {
  padding: 16px 0 0;
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;

  .tree-header {
    padding: 0 16px;
  }

  .icon-methods {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    font-size: 20px;
    font-weight: 500;
    color: var(--TextPrimary, #1f2329);
    padding-bottom: 16px;

    .title {
      margin-right: auto;
      font-size: 16px;
      font-style: normal;
      font-weight: 500;
      line-height: 24px;
    }

    .custom-icon {
      font-size: 20px;

      &.btn {
        color: var(--ed-color-primary);
      }

      &:hover {
        cursor: pointer;
      }
    }
  }

  .search-bar {
    padding-bottom: 10px;
    width: calc(100% - 40px);
  }
}

.title-area {
  margin-left: 6px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.title-area-outer {
  display: flex;
  flex: 1 1 0%;
  width: 0px;
}

.custom-tree-node-list {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 14px;
  padding: 0 8px;
}

.father .child {
  visibility: hidden;
}

.father:hover .child {
  visibility: visible;
}

:deep(.ed-input__wrapper) {
  width: 80px;
}

.custom-tree {
  height: calc(100vh - 148px);
  padding: 0 8px;
}

.custom-tree-node {
  width: calc(100% - 30px);
  display: flex;
  align-items: center;
  box-sizing: content-box;
  padding-right: 4px;

  .label-tooltip {
    width: 100%;
    margin-left: 8.75px;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .icon-more {
    margin-left: auto;
    display: none;
  }

  &:hover {
    .label-tooltip {
      width: calc(100% - 78px);
    }

    .icon-more {
      display: inline-flex;
    }
  }

  .icon-screen-new {
    border-radius: 4px;
    color: #fff;
    padding: 3px;
  }
}
</style>

<style lang="less">
.menu-outer-dv_popper {
  min-width: 140px;
  margin-top: -2px !important;

  .ed-icon {
    border-radius: 4px;
  }
}

.sort-type-normal {
  i {
    display: none;
  }
}

.sort-type-checked {
  color: var(--ed-color-primary);

  i {
    display: block;
  }
}

.node-disabled-custom {
  color: rgba(187, 191, 196, 1);
  cursor: not-allowed;
}

.color-dataV-disabled {
  background: #bbbfc4 !important;
}
</style>
