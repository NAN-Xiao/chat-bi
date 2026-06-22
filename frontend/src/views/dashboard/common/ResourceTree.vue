<script setup lang="ts">
import icon_add_outlined from '@/assets/svg/icon_add_outlined.svg'
import icon_sidebar_outlined from '@/assets/svg/icon_sidebar_outlined.svg'
import { treeDraggableChart } from '@/views/dashboard/utils/treeDraggableChart'
import icon_searchOutline_outlined from '@/assets/svg/icon_search-outline_outlined.svg'
import icon_folder from '@/assets/svg/icon_folder.svg'
import icon_dashboard from '@/assets/permission/icon_dashboard.svg'
import icon_edit_outlined from '@/assets/svg/icon_edit_outlined.svg'
import icon_rename from '@/assets/svg/icon_rename.svg'
import icon_delete from '@/assets/svg/icon_delete.svg'
import icon_export_outlined from '@/assets/svg/icon_export_outlined.svg'
import icon_close_outlined from '@/assets/svg/icon_close_outlined.svg'
import icon_more_outlined from '@/assets/svg/icon_more_outlined.svg'
import dv_sort_asc from '@/assets/svg/dv-sort-asc.svg'
import dv_sort_desc from '@/assets/svg/dv-sort-desc.svg'
import { onMounted, reactive, ref, watch, nextTick, computed } from 'vue'
import { ElIcon, ElMessage, ElMessageBox, ElScrollbar } from 'element-plus-secondary'
import { Icon } from '@/components/icon-custom'
import { type SQTreeNode } from '@/views/dashboard/utils/treeNode'
import _ from 'lodash'
import router from '@/router'
import { dashboardStoreWithOut } from '@/stores/dashboard/dashboard.ts'
import ResourceGroupOpt from '@/views/dashboard/common/ResourceGroupOpt.vue'
import { dashboardApi } from '@/api/dashboard.ts'
import HandleMore from '@/views/dashboard/common/HandleMore.vue'
import { useI18n } from 'vue-i18n'
import treeSort from '@/views/dashboard/utils/treeSortUtils.ts'
import { useCache } from '@/utils/useCache.ts'
import { useDatasourceContextStore } from '@/stores/datasourceContext'
import { captureDashboardSharePreview } from '@/views/dashboard/utils/sharePreview'
const { wsCache } = useCache()

const { t } = useI18n()
const dashboardStore = dashboardStoreWithOut()
const datasourceContext = useDatasourceContextStore()
const resourceGroupOptRef = ref(null)

defineProps({
  curCanvasType: {
    type: String,
    required: true,
  },
  showPosition: {
    required: false,
    type: String,
    default: 'preview',
  },
  resourceTable: {
    required: false,
    type: String,
    default: 'core',
  },
})
const defaultProps = {
  children: 'children',
  label: 'name',
}
const mounted = ref(false)
const selectedNodeKey: any = ref(null)
const filterText = ref(null)
const expandedArray = ref([])
const resourceListTree = ref()
const returnMounted = ref(false)
const state = reactive({
  curSortType: 'name_asc',
  curSortTypePrefix: 'name',
  curSortTypeSuffix: '_asc',
  resourceTree: [] as SQTreeNode[],
  originResourceTree: [] as SQTreeNode[],
  sortType: [],
  templateCreatePid: 0,
  baseMenuList: [
    {
      label: t('dashboard.edit'),
      command: 'edit',
      svgName: icon_edit_outlined,
    },
    {
      label: t('dashboard.rename'),
      command: 'rename',
      svgName: icon_rename,
    },
    {
      label: t('dashboard.delete'),
      command: 'delete',
      svgName: icon_delete,
      divided: true,
    },
  ],
})

const { handleDrop, handleDragStart } = treeDraggableChart(state, 'resourceTree', 'dashboard')

const routerDashboardId = router.currentRoute.value.query.dashboardId
if (routerDashboardId) {
  selectedNodeKey.value = routerDashboardId
  returnMounted.value = true
}
const nodeExpand = (data: any) => {
  if (data.id) {
    // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
    expandedArray.value.push(data.id)
  }
}

const nodeCollapse = (data: any) => {
  if (data.id) {
    // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
    expandedArray.value.splice(expandedArray.value.indexOf(data.id), 1)
  }
}

const filterNode = (value: string, data: SQTreeNode) => {
  if (!value) return true
  return data.name?.toLocaleLowerCase().includes(value.toLocaleLowerCase())
}

const nodeClick = (data: SQTreeNode, node: any) => {
  dashboardStore.setCurComponent({ component: null, index: null })
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
    if (data.node_type === 'leaf') {
      emit('nodeClick', data)
    } else {
      resourceListTree.value.setCurrentKey(null)
    }
  }
}

const getTree = async () => {
  await datasourceContext.loadDatasources()
  state.originResourceTree = []
  if (!datasourceContext.datasourceId) {
    state.resourceTree = []
    afterTreeInit()
    return
  }
  const params = { datasource: datasourceContext.datasourceId }
  dashboardApi.list_resource(params).then((res: SQTreeNode[]) => {
    state.originResourceTree = res || []
    state.resourceTree = _.cloneDeep(state.originResourceTree)
    handleSortTypeChange('name_asc')
    afterTreeInit()
  })
}

const hasData = computed<boolean>(() => state.resourceTree.length > 0)
const canCreateDashboard = computed<boolean>(() => datasourceContext.canCreateDashboard)
const canManageNode = (data: SQTreeNode) => data.can_edit === true
const canShareNode = (data: SQTreeNode) =>
  data.node_type === 'leaf' && (data.can_share === true || data.can_edit === true)
const nodeMenuList = (data: SQTreeNode) => {
  const list = canManageNode(data) ? [...state.baseMenuList] : []
  if (canShareNode(data)) {
    list.splice(list.length > 0 ? 2 : 0, 0, {
      label: data.is_shared ? t('dashboard.cancel_share') : t('dashboard.share'),
      command: data.is_shared ? 'unshare' : 'share',
      svgName: data.is_shared ? icon_close_outlined : icon_export_outlined,
    })
  }
  return list
}
const findTreeNode = (nodes: SQTreeNode[], id: string | number): SQTreeNode | undefined => {
  for (const item of nodes) {
    if (item.id === id) return item
    const matched = findTreeNode(item.children || [], id)
    if (matched) return matched
  }
  return undefined
}

const afterTreeInit = () => {
  mounted.value = true
  if (selectedNodeKey.value && returnMounted.value) {
    // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
    expandedArray.value = getDefaultExpandedKeys()
    returnMounted.value = false
  }
  nextTick(() => {
    resourceListTree.value.setCurrentKey(selectedNodeKey.value)
    resourceListTree.value.filter(filterText.value)
    nextTick(() => {
      // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
      document.querySelector('.is-current')?.firstChild?.click()
    })
  })
}

const copyLoading = ref(false)
const emit = defineEmits(['nodeClick', 'deleteCurResource', 'toggleSidebar'])

function createNewObject() {
  if (!canCreateDashboard.value) return
  addOperation({ opt: 'newLeaf' })
}

function onClickSideBarBtn() {
  emit('toggleSidebar')
}

// @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
const resourceEdit = (resourceId) => {
  window.open(`#/canvas?resourceId=${resourceId}`, '_self')
}

// @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
const getParentKeys = (tree: any, targetKey: any, parentKeys = []) => {
  for (const node of tree) {
    if (node.id === targetKey) {
      return parentKeys
    }
    if (node.children) {
      const newParentKeys = [...parentKeys, node.id]
      // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
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

watch(filterText, (val) => {
  resourceListTree.value.filter(val)
})

const loadInit = () => {}
onMounted(() => {
  loadInit()
  getTree()
})

watch(
  () => datasourceContext.datasourceId,
  () => {
    selectedNodeKey.value = null
    dashboardStore.canvasDataInit()
    emit('deleteCurResource')
    getTree()
  }
)

const addOperation = (params: any) => {
  if (!canCreateDashboard.value) return
  if (params?.id) {
    const folder = findTreeNode(state.originResourceTree, params.id)
    if (!folder || !canManageNode(folder)) return
  }
  if (params.opt === 'newLeaf') {
    const datasourceQuery = datasourceContext.datasourceId
      ? `&datasource=${datasourceContext.datasourceId}`
      : ''
    const newCanvasUrl =
      '#/canvas?opt=create' + (params?.id ? `&pid=${params?.id}` : '') + datasourceQuery
    window.open(newCanvasUrl, '_self')
    dashboardStore.canvasDataInit()
  } else {
    // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
    resourceGroupOptRef.value?.optInit(params)
  }
}

const operation = async (opt: string, data: SQTreeNode) => {
  if (['delete', 'rename', 'edit'].includes(opt) && !canManageNode(data)) return
  if (['share', 'unshare'].includes(opt) && !canShareNode(data)) return
  if (opt === 'delete') {
    const msg = data.node_type === 'leaf' ? '' : t('dashboard.delete_tips')
    ElMessageBox.confirm(t('dashboard.delete_dashboard_warn', [data.name]), {
      confirmButtonType: 'danger',
      type: 'warning',
      tip: msg,
      autofocus: false,
      showClose: false,
    }).then(() => {
      dashboardApi.delete_resource({ id: data.id, name: data.name }).then(() => {
        ElMessage.success(t('dashboard.delete_success'))
        getTree()
        dashboardStore.canvasDataInit()
        emit('deleteCurResource')
      })
    })
  } else if (opt === 'rename') {
    // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
    resourceGroupOptRef.value?.optInit({ opt: 'rename', id: data.id, name: data.name })
  } else if (opt === 'edit') {
    resourceEdit(data.id)
  } else if (opt === 'share') {
    const previewImage = selectedNodeKey.value === data.id ? await captureDashboardSharePreview() : ''
    dashboardApi
      .share({
        dashboard_id: data.id,
        share_type: 'dashboard',
        preview_image: previewImage,
      })
      .then(() => {
        ElMessage.success(t('dashboard.share_success'))
        getTree()
      })
  } else if (opt === 'unshare') {
    if (!data.share_id) return
    ElMessageBox.confirm(t('dashboard.cancel_share_warn', [data.name]), {
      confirmButtonType: 'danger',
      type: 'warning',
      autofocus: false,
      showClose: false,
    }).then(() => {
      dashboardApi.share_delete({ id: data.share_id }).then(() => {
        ElMessage.success(t('dashboard.cancel_share_success'))
        getTree()
      })
    })
  }
}

const baseInfoChangeFinish = () => {
  getTree()
}

const handleSortTypeChange = (menuSortType: string) => {
  state.curSortTypePrefix = ['name', 'time'].includes(menuSortType)
    ? menuSortType
    : state.curSortTypePrefix
  state.curSortTypeSuffix = ['_asc', '_desc'].includes(menuSortType)
    ? menuSortType
    : state.curSortTypeSuffix
  const curMenuSortType = state.curSortTypePrefix + state.curSortTypeSuffix
  state.resourceTree = treeSort(state.originResourceTree, curMenuSortType)
  state.curSortType = curMenuSortType
  wsCache.set('TreeSort-dashboard', state.curSortType)
}

const sortColumnList = [
  {
    name: t('dashboard.time'),
    value: 'time',
  },
  {
    name: t('dashboard.name'),
    value: 'name',
    divided: true,
  },
]

const sortTypeList = [
  {
    name: t('dashboard.sort_asc'),
    value: '_asc',
  },
  {
    name: t('dashboard.sort_desc'),
    value: '_desc',
  },
]

const sortList = [
  {
    name: t('dashboard.time_asc'),
    value: 'time_asc',
  },
  {
    name: t('dashboard.time_desc'),
    value: 'time_desc',
    divided: true,
  },
  {
    name: t('dashboard.name_asc'),
    value: 'name_asc',
  },
  {
    name: t('dashboard.name_desc'),
    value: 'name_desc',
  },
]

const sortTypeTip = computed(() => {
  // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
  return sortList.find((ele) => ele.value === state.curSortType).name
})

defineExpose({
  hasData,
  canCreateDashboard,
  createNewObject,
  mounted,
})
</script>

<template>
  <div class="resource-tree">
    <div class="tree-header">
      <div class="icon-methods">
        <span class="title">{{ t('dashboard.dashboard') }} </span>
        <el-button link type="primary" class="icon-btn" @click="onClickSideBarBtn">
          <el-icon>
            <icon_sidebar_outlined />
          </el-icon>
        </el-button>
      </div>
      <el-button
        v-if="canCreateDashboard"
        class="create-dashboard-btn"
        type="primary"
        @click="addOperation({ opt: 'newLeaf', type: 'dashboard' })"
      >
        <template #icon>
          <Icon name="icon_add_outlined">
            <icon_add_outlined class="svg-icon" />
          </Icon>
        </template>
        {{ t('dashboard.new_dashboard') }}
      </el-button>
      <div class="search-row">
        <el-input
          v-model="filterText"
          :placeholder="t('dashboard.search')"
          clearable
          class="search-bar"
        >
          <template #prefix>
            <el-icon>
              <Icon name="icon_search-outline_outlined">
                <icon_searchOutline_outlined class="svg-icon" />
              </Icon>
            </el-icon>
          </template>
        </el-input>
        <el-dropdown
          popper-class="tree-sort-menu-custom"
          trigger="click"
          placement="bottom-end"
          @command="handleSortTypeChange"
        >
          <el-icon class="filter-icon-span" :class="state.curSortType !== 'name_asc' && 'active'">
            <el-tooltip :offset="16" effect="dark" :content="sortTypeTip" placement="top">
              <span class="sort-trigger-icon">
                <Icon v-if="state.curSortType.includes('asc')" name="dv-sort-asc"
                  ><dv_sort_asc class="svg-icon opt-icon"
                /></Icon>
                <Icon v-else name="dv-sort-desc"
                  ><dv_sort_desc class="svg-icon opt-icon"
                /></Icon>
              </span>
            </el-tooltip>
          </el-icon>
          <template #dropdown>
            <el-dropdown-menu style="width: 120px">
              <span class="sort_menu">{{ t('dashboard.sort_column') }}</span>
              <template v-for="ele in sortColumnList" :key="ele.value">
                <el-dropdown-item
                  class="ed-select-dropdown__item"
                  :class="state.curSortType.includes(ele.value) && 'selected'"
                  :command="ele.value"
                >
                  {{ ele.name }}
                </el-dropdown-item>
                <li v-if="ele.divided" class="ed-dropdown-menu__item--divided"></li>
              </template>
              <span class="sort_menu">{{ t('dashboard.sort_type') }}</span>
              <template v-for="ele in sortTypeList" :key="ele.value">
                <el-dropdown-item
                  class="ed-select-dropdown__item"
                  :class="state.curSortType.includes(ele.value) && 'selected'"
                  :command="ele.value"
                >
                  {{ ele.name }}
                </el-dropdown-item>
              </template>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>
    <el-scrollbar v-loading="copyLoading" class="custom-tree">
      <el-tree
        ref="resourceListTree"
        class="dashboard-resource-tree"
        style="overflow-x: hidden"
        menu
        :empty-text="t('dashboard.no_dashboard')"
        :default-expanded-keys="expandedArray"
        :data="state.resourceTree"
        :props="defaultProps"
        node-key="id"
        highlight-current
        :expand-on-click-node="true"
        :filter-node-method="filterNode"
        draggable
        @node-expand="nodeExpand"
        @node-collapse="nodeCollapse"
        @node-click="nodeClick"
        @node-drag-start="handleDragStart"
        @node-drop="handleDrop"
      >
        <template #default="{ node, data }">
          <span class="custom-tree-node">
            <el-icon v-if="data.node_type !== 'leaf'" class="tree-node-icon">
              <Icon name="icon_folder"><icon_folder class="svg-icon" /></Icon>
            </el-icon>
            <el-icon v-else class="tree-node-icon icon-primary">
              <Icon name="icon_dashboard"><icon_dashboard class="svg-icon" /></Icon>
            </el-icon>
            <span :title="node.label" class="label-tooltip">
              {{ node.label }}
            </span>
            <span v-if="data.node_type === 'leaf' && data.is_shared" class="shared-mark">
              {{ t('dashboard.shared') }}
            </span>
            <div class="icon-more">
              <el-icon
                v-if="data.node_type !== 'leaf' && canManageNode(data)"
                class="hover-icon"
                @click.stop
                @click="addOperation({ opt: 'newLeaf', type: 'dashboard', id: data.id })"
              >
                <Icon><icon_add_outlined class="svg-icon" /></Icon>
              </el-icon>
              <HandleMore
                v-if="canManageNode(data) || canShareNode(data)"
                :menu-list="nodeMenuList(data)"
                :icon-name="icon_more_outlined"
                placement="bottom-end"
                @handle-command="(opt: string) => operation(opt, data)"
              ></HandleMore>
            </div>
          </span>
        </template>
      </el-tree>
    </el-scrollbar>
    <ResourceGroupOpt ref="resourceGroupOptRef" @finish="baseInfoChangeFinish"></ResourceGroupOpt>
  </div>
</template>
<style lang="less" scoped>
.filter-icon-span {
  border: 1px solid var(--workspace-border, #d9dcdf);
  width: 34px;
  height: 34px;
  border-radius: 6px;
  color: var(--workspace-text-primary, #1f2329);
  background: var(--workspace-card-bg, #ffffff);
  padding: 8px;
  margin-left: 0;
  font-size: 16px;
  cursor: pointer;

  .sort-trigger-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 100%;
    height: 100%;
    color: inherit;
  }

  .opt-icon:focus {
    outline: none !important;
  }

  &:hover,
  &:focus {
    background: var(--workspace-control-hover-bg, #eef2f8);
  }

  &:active {
    background: var(--workspace-border-soft, #eff0f1);
  }

  &.active {
    border: 1px solid var(--ed-color-primary);
    color: var(--ed-color-primary);

    &:hover,
    &:focus {
      background: var(--workspace-primary-soft-bg, rgba(37, 99, 235, 0.1));
    }

    &:active {
      background: var(--ed-color-primary-60, #a4e3d3);
    }
  }
}

.resource-tree {
  --ed-bg-color: var(--workspace-card-bg, #ffffff);
  --ed-bg-color-page: var(--workspace-panel-bg, var(--theme-panel-bg));
  --ed-bg-color-overlay: var(--workspace-card-bg, #ffffff);
  --ed-fill-color: var(--workspace-control-hover-bg, #eef2f8);
  --ed-fill-color-light: var(--workspace-control-hover-bg, #eef2f8);
  --ed-fill-color-lighter: var(--workspace-control-bg, #f8f9fa);
  --ed-fill-color-extra-light: var(--workspace-card-bg, #ffffff);
  --ed-fill-color-blank: var(--workspace-card-bg, #ffffff);
  --ed-text-color-primary: var(--workspace-text-primary, #1f2329);
  --ed-text-color-regular: var(--workspace-text-primary, #1f2329);
  --ed-text-color-secondary: var(--workspace-text-secondary, #646a73);
  --ed-text-color-placeholder: var(--workspace-text-tertiary, #8f959e);
  --ed-text-color-disabled: var(--workspace-text-tertiary, #8f959e);
  --ed-border-color: var(--workspace-border, #d9dcdf);
  --ed-border-color-light: var(--workspace-border, #d9dcdf);
  --ed-border-color-lighter: var(--workspace-border-soft, #eff0f1);
  --ed-color-primary-light-9: var(--workspace-primary-soft-bg, rgba(37, 99, 235, 0.1));
  --ed-tree-node-hover-bg-color: var(--workspace-control-hover-bg, #eef2f8);
  --ed-tree-text-color: var(--workspace-text-primary, #1f2329);

  padding: 14px 0 0;
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--workspace-panel-bg, var(--theme-panel-bg));
  color: var(--workspace-text-primary, #1f2329);
  font-family: 'PingFang SC', 'Microsoft YaHei', 'Helvetica Neue', Arial, sans-serif;

  .tree-header {
    padding: 0 14px;
  }

  .icon-methods {
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 24px;
    margin-bottom: 10px;
    font-size: 20px;
    font-weight: 500;
    color: var(--workspace-text-primary, var(--TextPrimary, #1f2329));

    .title {
      margin-right: auto;
      font-size: 15px;
      font-style: normal;
      font-weight: 600;
      line-height: 24px;
      white-space: nowrap;
    }

    .icon-btn {
      min-width: unset;
      width: 28px;
      height: 28px;
      padding: 0;
      border-radius: 6px;
      font-size: 18px;
      margin-left: 0;
      color: var(--workspace-text-primary, var(--theme-text-primary));

      :deep(.ed-icon),
      :deep(svg) {
        color: inherit;
      }

      :deep(svg path) {
        fill: currentColor !important;
      }

      &:hover {
        background: var(--workspace-control-hover-bg, var(--theme-hover-bg));
        color: var(--workspace-text-primary, var(--theme-text-primary));
      }
    }
  }

  .create-dashboard-btn {
    width: 100%;
    height: 38px;
    margin-bottom: 10px;
    border-radius: 10px;
    justify-content: center;
    border: 0;
    font-family: inherit;
    font-size: 14px;
    font-weight: 600;
    letter-spacing: 0.1px;
    background: linear-gradient(135deg, #2f6bff 0%, #1d8dff 100%);
    box-shadow: 0 8px 18px rgba(47, 107, 255, 0.18);
    transition:
      transform 0.18s ease,
      box-shadow 0.18s ease,
      filter 0.18s ease;

    --ed-button-text-color: #ffffff;
    --ed-button-bg-color: #2f6bff;
    --ed-button-border-color: transparent;
    --ed-button-hover-bg-color: #235df0;
    --ed-button-hover-text-color: #ffffff;
    --ed-button-hover-border-color: transparent;
    --ed-button-active-bg-color: #1f55de;
    --ed-button-active-border-color: transparent;

    &:hover {
      background: linear-gradient(135deg, #235df0 0%, #137fe8 100%);
      box-shadow: 0 10px 20px rgba(47, 107, 255, 0.24);
      filter: saturate(1.04);
    }

    &:active {
      transform: translateY(1px);
      box-shadow: 0 6px 14px rgba(47, 107, 255, 0.18);
    }

    :deep(.ed-icon),
    :deep(svg) {
      width: 18px;
      height: 18px;
      color: inherit;
    }

    :deep(svg path) {
      fill: currentColor !important;
    }
  }

  .search-row {
    position: relative;
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    height: 34px;
  }

  .search-bar {
    flex: 1 1 auto;
    width: 0;
    height: 34px;
    padding-bottom: 0;

    :deep(.ed-input__wrapper) {
      min-height: 34px;
      padding: 0 10px;
      border-radius: 10px;
      background-color: #ffffff !important;
      box-shadow:
        0 0 0 1px rgba(118, 134, 166, 0.22) inset,
        0 4px 12px rgba(18, 34, 66, 0.04) !important;
      transition:
        box-shadow 0.18s ease,
        background-color 0.18s ease;
    }

    :deep(.ed-input__wrapper:hover) {
      box-shadow:
        0 0 0 1px rgba(47, 107, 255, 0.28) inset,
        0 6px 14px rgba(18, 34, 66, 0.06) !important;
    }

    :deep(.ed-input__wrapper.is-focus) {
      box-shadow:
        0 0 0 1px rgba(47, 107, 255, 0.52) inset,
        0 0 0 3px rgba(47, 107, 255, 0.1) !important;
    }

    :deep(.ed-input__inner) {
      color: var(--workspace-text-primary, #1f2329) !important;
      font-family: inherit;
      font-size: 13px;
      font-weight: 400;
      letter-spacing: 0.1px;
    }

    :deep(.ed-input__inner::placeholder) {
      color: var(--workspace-text-tertiary, #8f959e) !important;
    }

    :deep(.ed-input__prefix),
    :deep(.ed-input__suffix) {
      color: var(--workspace-text-tertiary, #8f959e) !important;
    }

    :deep(.ed-input__prefix .ed-icon),
    :deep(.ed-input__suffix .ed-icon),
    :deep(.ed-input__prefix-inner .ed-icon) {
      width: 15px;
      height: 15px;
      color: var(--workspace-text-tertiary, #8f959e) !important;
    }
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
  width: 100%;
}

.custom-tree {
  --hover-color: var(--workspace-control-hover-bg, var(--theme-hover-bg));
  --active-color: var(--workspace-active-bg, var(--theme-control-bg));

  flex: 1;
  min-height: 0;
  height: auto;
  padding: 0;
  background: var(--workspace-panel-bg, var(--theme-panel-bg));
  color: var(--workspace-text-primary, #1f2329);

  :deep(.ed-scrollbar__view),
  :deep(.ed-tree) {
    background: var(--workspace-panel-bg, var(--theme-panel-bg)) !important;
    color: var(--workspace-text-primary, #1f2329) !important;
  }

  :deep(.ed-tree__empty-text),
  :deep(.ed-tree-node__label) {
    color: inherit !important;
  }

  :deep(.ed-tree__empty-block) {
    min-height: 200px;
  }

  :deep(.ed-tree__empty-text) {
    color: var(--workspace-text-secondary, var(--theme-text-secondary)) !important;
    font-size: 14px;
    line-height: 22px;
  }

  :deep(.ed-tree-node__content) {
    margin: 0 16px 2px;
    height: 40px;
    padding: 8px;
    border-radius: 6px;
    font-size: 14px;
    line-height: 22px;
    font-weight: 400;
    color: var(--workspace-text-primary, #1f2329) !important;
    background: transparent;
  }

  :deep(.ed-tree-node__content:hover),
  :deep(.ed-tree-node:focus > .ed-tree-node__content) {
    background-color: var(--hover-color) !important;
  }

  :deep(.dashboard-resource-tree.dashboard-resource-tree.ed-tree.is-menu .ed-tree-node.is-current > .ed-tree-node__content),
  :deep(.dashboard-resource-tree.dashboard-resource-tree.ed-tree--highlight-current .ed-tree-node.is-current > .ed-tree-node__content),
  :deep(.dashboard-resource-tree.dashboard-resource-tree.ed-tree.is-menu .ed-tree-node.is-current > .ed-tree-node__content:hover),
  :deep(.dashboard-resource-tree.dashboard-resource-tree.ed-tree--highlight-current .ed-tree-node.is-current > .ed-tree-node__content:hover),
  :deep(.dashboard-resource-tree.dashboard-resource-tree.ed-tree .ed-tree-node.is-current:focus > .ed-tree-node__content) {
    background-color: var(--active-color) !important;
    color: var(--workspace-text-primary, var(--theme-text-primary)) !important;
    font-weight: 500;
  }

  :deep(.dashboard-resource-tree.dashboard-resource-tree.ed-tree .ed-tree-node.is-current > .ed-tree-node__content .custom-tree-node),
  :deep(.dashboard-resource-tree.dashboard-resource-tree.ed-tree .ed-tree-node.is-current > .ed-tree-node__content .ed-tree-node__label),
  :deep(.dashboard-resource-tree.dashboard-resource-tree.ed-tree .ed-tree-node.is-current > .ed-tree-node__content .label-tooltip),
  :deep(.dashboard-resource-tree.dashboard-resource-tree.ed-tree .ed-tree-node.is-current > .ed-tree-node__content .tree-node-icon),
  :deep(.dashboard-resource-tree.dashboard-resource-tree.ed-tree .ed-tree-node.is-current > .ed-tree-node__content .tree-node-icon svg) {
    color: var(--workspace-text-primary, var(--theme-text-primary)) !important;
  }

  :deep(.dashboard-resource-tree.dashboard-resource-tree.ed-tree .ed-tree-node.is-current > .ed-tree-node__content .tree-node-icon svg path) {
    fill: currentColor !important;
    stroke: currentColor !important;
  }

  :deep(.dashboard-resource-tree.dashboard-resource-tree.ed-tree .ed-tree-node.is-current > .ed-tree-node__content .label-tooltip) {
    font-weight: 500;
  }

  :deep(.ed-tree-node) {
    margin-bottom: 2px;
  }
}

.custom-tree-node {
  width: 100%;
  display: flex;
  align-items: center;
  box-sizing: content-box;
  color: inherit;

  .tree-node-icon {
    flex: 0 0 18px;
    width: 18px;
    height: 18px;
    font-size: 18px;
  }

  .label-tooltip {
    width: 100%;
    margin-left: 8px;
    font-size: 14px;
    font-weight: 400;
    line-height: 22px;
    color: inherit;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .shared-mark {
    flex: 0 0 auto;
    margin-left: 6px;
    padding: 0 6px;
    border-radius: 999px;
    background: rgba(37, 99, 235, 0.1);
    color: #2563eb;
    font-size: 11px;
    line-height: 18px;
    font-weight: 500;
  }

  .icon-more {
    margin-left: auto;
    display: none;
    color: var(--workspace-text-tertiary, #bbbfc4);
  }

  &:hover {
    .label-tooltip {
      width: calc(100% - 96px);
    }

    .icon-more {
      display: inline-flex;
    }
  }

  .icon-screen-new {
    border-radius: 6px;
    color: #fff;
    padding: 3px;
  }
}
</style>

<style lang="less">
.tree-sort-menu-custom {
  padding: 4px !important;
  li {
    border-radius: 6px;
    padding: 0 8px !important;
  }
  .ed-dropdown-menu__item:not(.is-disabled):not(.selected):hover {
    color: #1f2329;
  }
}
.menu-outer-dv_popper {
  min-width: 140px;
  margin-top: -2px !important;

  .ed-icon {
    border-radius: 6px;
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

.sort_menu {
  color: rgba(143, 149, 158, 1);
  font-size: 14px;
  margin-left: 8px;
}
</style>
