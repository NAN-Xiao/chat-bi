<script setup lang="ts">
import icon_sidebar_outlined from '@/assets/svg/icon_sidebar_outlined.svg'
import icon_searchOutline_outlined from '@/assets/svg/icon_search-outline_outlined.svg'
import icon_folder from '@/assets/svg/icon_folder.svg'
import icon_folder_open from '@/assets/svg/folder-open-svgrepo-com.svg'
import icon_dashboard from '@/assets/permission/icon_dashboard.svg'
import icon_dashboard_grid_add from '@/assets/svg/icon_dashboard_grid_add.svg'
import icon_dashboard_group_color from '@/assets/svg/icon_dashboard_group_color.svg'
import icon_edit_outlined from '@/assets/svg/icon_edit_outlined.svg'
import icon_rename from '@/assets/svg/icon_rename.svg'
import icon_delete from '@/assets/svg/icon_delete.svg'
import icon_export_outlined from '@/assets/svg/icon_export_outlined.svg'
import icon_close_outlined from '@/assets/svg/icon_close_outlined.svg'
import icon_copy_outlined from '@/assets/svg/icon_copy_outlined.svg'
import icon_done_outlined from '@/assets/svg/icon_done_outlined.svg'
import icon_more_outlined from '@/assets/svg/icon_more_outlined.svg'
import icon_start_outlined from '@/assets/svg/icon_start_outlined.svg'
import icon_tree_list from '@/assets/svg/icon_tree_list.svg'
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
import { useDatasourceContextStore } from '@/stores/datasourceContext'
import { useUserStore } from '@/stores/user'
import { captureDashboardSharePreview } from '@/views/dashboard/utils/sharePreview'
import { useEmitt, WORKSPACE_CONTEXT_CHANGE_EVENT } from '@/utils/useEmitt'
import {
  findDashboardNodeById,
  findFirstLeafDashboardNode,
  getRememberedDefaultDashboardId,
  rememberDefaultDashboardId,
} from '@/utils/dashboardLanding'

const { t } = useI18n()
const dashboardStore = dashboardStoreWithOut()
const datasourceContext = useDatasourceContextStore()
const userStore = useUserStore()
const resourceGroupOptRef = ref(null)
let treeRequestSeq = 0
const workspaceContextSwitching = ref(false)

const props = defineProps({
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
  defaultMode: {
    required: false,
    type: Boolean,
    default: false,
  },
})
const defaultProps = {
  children: 'children',
  label: 'name',
}
type DashboardScope = 'default' | 'my'
type TreeOrderItem = {
  id: string | number
  pid: string | number
  sort: number
}
type TreeMenuItem = {
  label: string
  command: string
  svgName: any
  disabled?: boolean
  divided?: boolean
}
const DEFAULT_GROUP_ID = '__dashboard_group_default__'
const MY_GROUP_ID = '__dashboard_group_my__'
const DEFAULT_SCOPE: DashboardScope = 'default'
const MY_SCOPE: DashboardScope = 'my'
const TREE_NODE_INDENT = 28
const mounted = ref(false)
const selectedNodeKey: any = ref(null)
const filterText = ref(null)
const expandedArray = ref<Array<string | number>>([])
const resourceListTree = ref()
const returnMounted = ref(false)
const isTreeEditing = ref(false)
const draggingTreeNode = ref<any>(null)
const treeDropIndicator = reactive({
  visible: false,
  nodeId: '',
  placement: '',
})
const state = reactive({
  resourceTree: [] as SQTreeNode[],
  originResourceTree: [] as SQTreeNode[],
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

const canEditDefaultOrder = computed<boolean>(() => userStore.isTenantAdminUser === true)
const isCombinedDashboardTree = computed<boolean>(() => !props.defaultMode)
const treeEditButtonTip = computed(() =>
  isTreeEditing.value ? t('dashboard.finish_order_edit') : t('dashboard.edit_order')
)

const normalizeDashboardScope = (value: unknown): DashboardScope => {
  const scope = Array.isArray(value) ? value[0] : value
  return scope === DEFAULT_SCOPE ? DEFAULT_SCOPE : MY_SCOPE
}

const currentRouteDashboardScope = (): DashboardScope =>
  props.defaultMode
    ? DEFAULT_SCOPE
    : normalizeDashboardScope(router.currentRoute.value.query.dashboardMode)

const expandedStorageKey = () => {
  const tenantId = userStore.getTenantId || 'default'
  const datasourceId = props.defaultMode ? 'default' : datasourceContext.datasourceId || 'none'
  const mode = props.defaultMode ? 'default' : 'combined'
  return `dashboard-tree-expanded:${tenantId}:${datasourceId}:${mode}`
}

const collectExpandableKeys = (nodes: SQTreeNode[] = [], result: Array<string | number> = []) => {
  nodes.forEach((node) => {
    if (node.id && node.node_type !== 'leaf') {
      result.push(node.id)
    }
    collectExpandableKeys(node.children || [], result)
  })
  return result
}

const readStoredExpandedKeys = () => {
  try {
    const raw = window.localStorage.getItem(expandedStorageKey())
    const value = raw ? JSON.parse(raw) : []
    return Array.isArray(value) ? value : []
  } catch {
    return []
  }
}

const persistExpandedKeys = () => {
  try {
    window.localStorage.setItem(expandedStorageKey(), JSON.stringify(expandedArray.value))
  } catch {
    // Ignore storage failures; the tree still falls back to expanding all folders.
  }
}

const restoreExpandedKeys = () => {
  const expandableKeys = collectExpandableKeys(state.resourceTree)
  const expandableKeySet = new Set(expandableKeys.map((key) => String(key)))
  const storedKeys = readStoredExpandedKeys().filter((key) => expandableKeySet.has(String(key)))
  expandedArray.value = storedKeys.length ? storedKeys : expandableKeys
  if (!storedKeys.length) {
    persistExpandedKeys()
  }
}

const ensureSelectedNodeExpanded = () => {
  const parentKeys = getDefaultExpandedKeys().filter((key) => key)
  const keyMap = new Map(expandedArray.value.map((key) => [String(key), key]))
  parentKeys.forEach((key) => {
    if (!keyMap.has(String(key))) {
      keyMap.set(String(key), key)
    }
  })
  expandedArray.value = Array.from(keyMap.values())
  persistExpandedKeys()
}

const getRawDashboardId = (node?: SQTreeNode | null) => (node as any)?.raw_id ?? node?.id
const getDashboardScope = (node?: SQTreeNode | null): DashboardScope =>
  props.defaultMode ? DEFAULT_SCOPE : ((node as any)?.dashboard_scope || MY_SCOPE)

const getDashboardNodeKey = (scope: DashboardScope, dashboardId?: string | number | null) => {
  if (!dashboardId) return dashboardId
  return scope === DEFAULT_SCOPE && isCombinedDashboardTree.value
    ? `${DEFAULT_SCOPE}:${dashboardId}`
    : dashboardId
}

const isDefaultDashboardNode = (node?: SQTreeNode | null) =>
  getDashboardScope(node) === DEFAULT_SCOPE
const isMyDashboardNode = (node?: SQTreeNode | null) => getDashboardScope(node) === MY_SCOPE
const isDefaultGroupNode = (node?: SQTreeNode | null) =>
  isVirtualNode(node as SQTreeNode) && String(node?.id || '') === DEFAULT_GROUP_ID
const isMyGroupNode = (node?: SQTreeNode | null) =>
  isVirtualNode(node as SQTreeNode) && String(node?.id || '') === MY_GROUP_ID
const findDefaultGroupNode = (nodes: SQTreeNode[] = []) =>
  nodes.find((item) => String(item.id) === DEFAULT_GROUP_ID)
const findMyGroupNode = (nodes: SQTreeNode[] = []) =>
  nodes.find((item) => String(item.id) === MY_GROUP_ID)

const createDashboardGroup = (
  id: string,
  name: string,
  scope: DashboardScope,
  children: SQTreeNode[]
): SQTreeNode =>
  ({
    id,
    pid: 'root',
    name,
    leaf: false,
    weight: 0,
    type: 'dashboard',
    node_type: 'folder',
    virtual: true,
    dashboard_scope: scope,
    children,
  }) as SQTreeNode

const normalizeDefaultDashboardNodes = (
  nodes: SQTreeNode[] = [],
  pid: string | number = DEFAULT_GROUP_ID
): SQTreeNode[] =>
  nodes.map((item) => {
    const rawId = getRawDashboardId(item)
    const nodeKey = getDashboardNodeKey(DEFAULT_SCOPE, rawId) || ''
    const children: SQTreeNode[] = item.children?.length
      ? normalizeDefaultDashboardNodes(item.children, nodeKey)
      : []
    return {
      ...item,
      id: nodeKey,
      raw_id: rawId,
      pid,
      dashboard_scope: DEFAULT_SCOPE,
      children,
    } as SQTreeNode
  })

const normalizeMyDashboardNodes = (
  nodes: SQTreeNode[] = [],
  pid: string | number = MY_GROUP_ID
): SQTreeNode[] =>
  nodes.map((item) => {
    const rawId = getRawDashboardId(item)
    const children: SQTreeNode[] = item.children?.length
      ? normalizeMyDashboardNodes(item.children, rawId)
      : []
    return {
      ...item,
      id: rawId,
      raw_id: rawId,
      pid,
      dashboard_scope: MY_SCOPE,
      children,
    } as SQTreeNode
  })

const buildCombinedTree = (defaultNodes: SQTreeNode[] = [], myNodes: SQTreeNode[] = []) => [
  createDashboardGroup(
    DEFAULT_GROUP_ID,
    t('dashboard.default_dashboard'),
    DEFAULT_SCOPE,
    normalizeDefaultDashboardNodes(defaultNodes)
  ),
  createDashboardGroup(
    MY_GROUP_ID,
    t('dashboard.dashboard'),
    MY_SCOPE,
    normalizeMyDashboardNodes(myNodes)
  ),
]

const findDashboardNode = (
  nodes: SQTreeNode[] = [],
  dashboardId?: string | number | null,
  scope?: DashboardScope
): SQTreeNode | undefined => {
  if (!dashboardId) return undefined
  for (const node of nodes) {
    const rawId = getRawDashboardId(node)
    if (
      isLeafDashboardNode(node) &&
      String(rawId) === String(dashboardId) &&
      (!scope || getDashboardScope(node) === scope)
    ) {
      return node
    }
    const matched = findDashboardNode(node.children || [], dashboardId, scope)
    if (matched) return matched
  }
  return undefined
}

const currentRouteDashboardId = () => {
  const resourceId =
    router.currentRoute.value.query.resourceId || router.currentRoute.value.query.dashboardId
  return Array.isArray(resourceId) ? resourceId[0] : resourceId
}
const routeDashboardId = currentRouteDashboardId()
if (routeDashboardId) {
  selectedNodeKey.value = getDashboardNodeKey(currentRouteDashboardScope(), routeDashboardId)
  returnMounted.value = true
}
const nodeExpand = (data: any) => {
  if (!data.id) return
  if (!expandedArray.value.some((id) => String(id) === String(data.id))) {
    expandedArray.value.push(data.id)
  }
  persistExpandedKeys()
}

const nodeCollapse = (data: any) => {
  if (!data.id) return
  const collapsedKeys = new Set(collectExpandableKeys([data]).map((id) => String(id)))
  expandedArray.value = expandedArray.value.filter((id) => !collapsedKeys.has(String(id)))
  persistExpandedKeys()
}

const resetTreeState = () => {
  treeRequestSeq += 1
  selectedNodeKey.value = null
  returnMounted.value = false
  expandedArray.value = []
  state.originResourceTree = []
  state.resourceTree = []
  dashboardStore.canvasDataInit()
  nextTick(() => {
    resourceListTree.value?.setCurrentKey?.(null)
    resourceListTree.value?.filter?.(filterText.value)
  })
}

const filterNode = (value: string, data: SQTreeNode) => {
  if (!value) return true
  if (isVirtualNode(data)) return true
  return data.name?.toLocaleLowerCase().includes(value.toLocaleLowerCase())
}

const syncDashboardRoute = (node: SQTreeNode) => {
  if (props.showPosition !== 'preview') return
  const currentRoute = router.currentRoute.value
  const expectedPath = props.defaultMode ? '/default-dashboard/index' : '/dashboard/index'
  if (currentRoute.path !== expectedPath) return
  const resourceId = getRawDashboardId(node)
  const dashboardMode = getDashboardScope(node)
  if (!resourceId) return
  const currentMode = props.defaultMode ? DEFAULT_SCOPE : currentRouteDashboardScope()
  if (
    String(currentRoute.query.resourceId || '') === String(resourceId) &&
    currentMode === dashboardMode
  ) {
    return
  }
  router.replace({
    path: currentRoute.path,
    query: {
      ...currentRoute.query,
      resourceId,
      ...(props.defaultMode
        ? {}
        : {
            dashboardMode,
          }),
    },
  })
}

const shouldAutoSelectDashboard = () => props.showPosition === 'preview'
const isVirtualNode = (node?: SQTreeNode) => (node as any)?.virtual === true
const isRealNode = (node?: SQTreeNode | null) => !!node && !isVirtualNode(node as SQTreeNode)
const isLeafDashboardNode = (node?: SQTreeNode) =>
  (node?.node_type === 'leaf' || node?.leaf === true) && !isVirtualNode(node)

const getTreeNodeDepth = (node: any, data?: SQTreeNode) => {
  if (isVirtualNode(data)) {
    return 0
  }
  const level = Number(node?.level || 1)
  const rootLevel = isCombinedDashboardTree.value ? 2 : 1
  return Math.max(level - rootLevel, 0)
}

const shouldShiftTopLevelFolder = (node: any, data?: SQTreeNode) =>
  data?.node_type !== 'leaf' && !isVirtualNode(data) && getTreeNodeDepth(node, data) === 0

const getTreeNodeStyle = (node: any, data: SQTreeNode) => {
  const depth = getTreeNodeDepth(node, data)
  return {
    '--dashboard-tree-indent': `${depth * TREE_NODE_INDENT}px`,
  }
}

const resolveInitialDashboardNode = () => {
  if (!shouldAutoSelectDashboard()) return undefined
  const routeResourceId = currentRouteDashboardId()
  if (routeResourceId) {
    const routeNode = findDashboardNode(
      state.resourceTree,
      routeResourceId,
      currentRouteDashboardScope()
    )
    if (isLeafDashboardNode(routeNode)) return routeNode
  }
  if (props.defaultMode) {
    const rememberedNode = findDashboardNode(
      state.resourceTree,
      getRememberedDefaultDashboardId(userStore),
      DEFAULT_SCOPE
    )
    if (rememberedNode) return rememberedNode
  }
  return findFirstLeafDashboardNode(state.resourceTree)
}

const selectDashboardNode = (node?: SQTreeNode) => {
  if (!node?.id || !isLeafDashboardNode(node)) return false
  selectedNodeKey.value = node.id
  returnMounted.value = true
  if (isDefaultDashboardNode(node)) {
    rememberDefaultDashboardId(getRawDashboardId(node), userStore)
  }
  syncDashboardRoute(node)
  return true
}

const emitDashboardNodeClick = (data?: SQTreeNode) => {
  const dashboardNode = data
  if (!dashboardNode || !isLeafDashboardNode(dashboardNode)) return
  emit('nodeClick', {
    ...dashboardNode,
    id: getRawDashboardId(dashboardNode),
    dashboardScope: getDashboardScope(dashboardNode),
    dashboardKey: dashboardNode.id,
  })
}

const nodeClick = (data: SQTreeNode, node: any) => {
  dashboardStore.setCurComponent({ component: null, index: null })
  if (isVirtualNode(data)) {
    resourceListTree.value?.setCurrentKey?.(null)
    return
  }
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
      if (isDefaultDashboardNode(data)) {
        rememberDefaultDashboardId(getRawDashboardId(data), userStore)
      }
      syncDashboardRoute(data)
      emitDashboardNodeClick(data)
    } else {
      resourceListTree.value.setCurrentKey(null)
    }
  }
}

const getTree = async () => {
  const requestSeq = ++treeRequestSeq
  const requestTenantId = userStore.getTenantId || 'default'
  if (props.defaultMode) {
    state.originResourceTree = []
    dashboardApi.default_list().then(async (res: SQTreeNode[]) => {
      if (
        requestSeq !== treeRequestSeq ||
        (userStore.getTenantId || 'default') !== requestTenantId
      ) {
        return
      }
      state.originResourceTree = normalizeDefaultDashboardNodes(res || [], 'root')
      state.resourceTree = _.cloneDeep(state.originResourceTree)
      afterTreeInit()
    })
    return
  }
  await datasourceContext.loadDatasources()
  const requestDatasourceId = datasourceContext.datasourceId
  state.originResourceTree = []
  const defaultListRequest = dashboardApi.default_list()
  const myListRequest = requestDatasourceId
    ? dashboardApi.list_resource({ datasource: requestDatasourceId })
    : Promise.resolve([])
  Promise.all([defaultListRequest, myListRequest]).then(async ([defaultRes, myRes]) => {
    if (
      requestSeq !== treeRequestSeq ||
      (userStore.getTenantId || 'default') !== requestTenantId ||
      datasourceContext.datasourceId !== requestDatasourceId
    ) {
      return
    }
    state.originResourceTree = buildCombinedTree(defaultRes || [], myRes || [])
    state.resourceTree = _.cloneDeep(state.originResourceTree)
    afterTreeInit()
  })
}

const hasData = computed<boolean>(() => !!findFirstLeafDashboardNode(state.resourceTree))
const canCreateDashboard = computed<boolean>(() => datasourceContext.canCreateDashboard)
const canManageNode = (data: SQTreeNode) => data.can_edit === true
const canShareNode = (data: SQTreeNode) =>
  isMyDashboardNode(data) &&
  data.node_type === 'leaf' &&
  (data.can_share === true || data.can_edit === true || data.is_shared === true)
const canSetDefaultNode = (data: SQTreeNode) =>
  isMyDashboardNode(data) && data.node_type === 'leaf' && data.can_set_default === true
const canRemoveDefaultNode = (data: SQTreeNode) =>
  data.node_type === 'leaf' &&
  data.is_default === true &&
  (canSetDefaultNode(data) || (isDefaultDashboardNode(data) && canEditDefaultOrder.value))
const canCopyDefaultNode = (data: SQTreeNode) =>
  isDefaultDashboardNode(data) && data.node_type === 'leaf'
const canCopyPlatformTemplateNode = (data: SQTreeNode) =>
  userStore.isPlatformWorkspaceDelegate &&
  !props.defaultMode &&
  isMyDashboardNode(data) &&
  data.node_type === 'leaf' &&
  (data as any).can_copy_to_platform_template === true
const hasNodeMenu = (data: SQTreeNode) => {
  if (isDefaultGroupNode(data)) return canEditDefaultOrder.value
  if (isDefaultDashboardNode(data) && data.node_type !== 'leaf') return canEditDefaultOrder.value
  if (canCopyDefaultNode(data)) return true
  if (isMyGroupNode(data)) return canOpenCreateDashboard.value
  if (!isMyDashboardNode(data)) return false
  return (
    canManageNode(data) ||
    canShareNode(data) ||
    canSetDefaultNode(data) ||
    canCopyPlatformTemplateNode(data)
  )
}
const nodeMenuList = (data: SQTreeNode) => {
  if (isDefaultGroupNode(data)) {
    return canEditDefaultOrder.value
      ? [
          {
            label: t('dashboard.new_folder'),
            command: 'newFolder',
            svgName: icon_folder,
          },
        ]
      : []
  }
  if (canCopyDefaultNode(data)) {
    const list: TreeMenuItem[] = [
      {
        label: t('dashboard.copy_to_my_dashboard'),
        command: 'copyDefault',
        svgName: icon_copy_outlined,
        disabled: copyLoading.value,
      },
    ]
    if (canRemoveDefaultNode(data)) {
      list.push({
        label: t('dashboard.remove_default_dashboard'),
        command: 'removeDefault',
        svgName: icon_close_outlined,
      })
    }
    return list
  }
  if (isDefaultDashboardNode(data)) {
    if (data.node_type !== 'leaf' && canEditDefaultOrder.value) {
      return [
        {
          label: t('dashboard.new_folder'),
          command: 'newFolder',
          svgName: icon_folder,
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
      ]
    }
    return []
  }
  if (isMyGroupNode(data)) {
    return canOpenCreateDashboard.value
      ? [
          {
            label: t('dashboard.new_dashboard'),
            command: 'newLeaf',
            svgName: icon_dashboard,
          },
          {
            label: t('dashboard.new_folder'),
            command: 'newFolder',
            svgName: icon_folder,
          },
        ]
      : []
  }
  if (!isMyDashboardNode(data)) {
    return []
  }
  if (data.node_type !== 'leaf') {
    return [
      {
        label: t('dashboard.new_dashboard'),
        command: 'newLeaf',
        svgName: icon_dashboard,
      },
      {
        label: t('dashboard.new_folder'),
        command: 'newFolder',
        svgName: icon_folder,
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
    ]
  }
  const list = canManageNode(data) ? [...state.baseMenuList] : []
  if (canCopyPlatformTemplateNode(data)) {
    list.push({
      label: t('dashboard.copy_to_platform_template'),
      command: 'copyToPlatformTemplate',
      svgName: icon_copy_outlined,
    })
  }
  if (canSetDefaultNode(data)) {
    list.splice(canManageNode(data) ? 2 : 0, 0, {
      label: data.is_default ? t('dashboard.remove_default_dashboard') : t('dashboard.set_default_dashboard'),
      command: data.is_default ? 'removeDefault' : 'setDefault',
      svgName: data.is_default ? icon_close_outlined : icon_start_outlined,
    })
  }
  if (data.node_type === 'leaf' && canShareNode(data)) {
    list.splice(canManageNode(data) ? 2 : 0, 0, {
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

const normalizePersistPid = (pid: string | number, scope: DashboardScope) => {
  if (scope === DEFAULT_SCOPE && String(pid) === DEFAULT_GROUP_ID) return 'root'
  if (scope === MY_SCOPE && String(pid) === MY_GROUP_ID) return 'root'
  return pid
}

const collectTreeOrderItems = (
  nodes: SQTreeNode[] = [],
  parentId: string | number,
  scope: DashboardScope,
  result: TreeOrderItem[] = [],
  includeNode: (node: SQTreeNode) => boolean = () => true
) => {
  nodes.forEach((node, index) => {
    if (isVirtualNode(node)) {
      collectTreeOrderItems(node.children || [], node.id, scope, result, includeNode)
      return
    }
    if (!includeNode(node)) return
    const rawId = getRawDashboardId(node)
    const rawPid = normalizePersistPid(parentId, scope)
    result.push({
      id: rawId,
      pid: rawPid,
      sort: index + 1,
    })
    collectTreeOrderItems(node.children || [], rawId, scope, result, includeNode)
  })
  return result
}

const afterTreeInit = () => {
  mounted.value = true
  const selectedNode = selectedNodeKey.value
    ? findDashboardNodeById(state.resourceTree, selectedNodeKey.value)
    : undefined
  const routeResourceId = currentRouteDashboardId()
  if (!isLeafDashboardNode(selectedNode) && (!routeResourceId || props.defaultMode)) {
    selectedNodeKey.value = null
  }
  if (!selectedNodeKey.value) {
    selectDashboardNode(resolveInitialDashboardNode())
  }
  restoreExpandedKeys()
  if (selectedNodeKey.value && returnMounted.value) {
    ensureSelectedNodeExpanded()
    returnMounted.value = false
  }
  nextTick(() => {
    resourceListTree.value.setCurrentKey(selectedNodeKey.value, false)
    resourceListTree.value.filter(filterText.value)
    emitDashboardNodeClick(findDashboardNodeById(state.resourceTree, selectedNodeKey.value))
  })
}

const copyLoading = ref(false)
const emit = defineEmits(['nodeClick', 'deleteCurResource', 'toggleSidebar'])
const canCreateFromPlatformTemplate = computed<boolean>(
  () => userStore.isPlatformWorkspaceDelegate && !props.defaultMode
)
const canOpenCreateDashboard = computed<boolean>(
  () => canCreateDashboard.value || canCreateFromPlatformTemplate.value
)
const canEditDashboardTree = computed<boolean>(() => canOpenCreateDashboard.value || canEditDefaultOrder.value)

function createNewObject() {
  if (!canOpenCreateDashboard.value) return
  addOperation({ opt: 'newLeaf' })
}

function onClickSideBarBtn() {
  emit('toggleSidebar')
}

// @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
const resourceEdit = (resourceId) => {
  router.push({
    path: '/canvas',
    query: { resourceId },
  })
}

const openCopiedDashboard = async (record: any) => {
  if (record?.datasource) {
    const activated = await datasourceContext.activateDatasourceById(record.datasource, true)
    if (!activated) {
      await datasourceContext.loadDatasources(true)
      await datasourceContext.activateDatasourceById(record.datasource, true)
    }
  }
  await router.push({
    path: '/dashboard/index',
    query: { resourceId: record.id, dashboardMode: MY_SCOPE },
  })
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

const openCreateDashboardDialog = (params: any = {}) => {
  dashboardStore.canvasDataInit()
  // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
  resourceGroupOptRef.value?.optInit({
    opt: 'newLeaf',
    type: 'dashboard',
    nodeType: 'leaf',
    name: '',
    placeholder: t('dashboard.add_dashboard_name_tips'),
    pid: params?.id || 'root',
    datasource: datasourceContext.datasourceId,
  })
}

watch(filterText, (val) => {
  resourceListTree.value.filter(val)
})

const loadInit = () => {}
onMounted(() => {
  loadInit()
  getTree()
})

useEmitt({
  name: WORKSPACE_CONTEXT_CHANGE_EVENT,
  callback: (event?: any) => {
    workspaceContextSwitching.value = event?.phase === 'changing' || event?.phase === 'changed'
    resetTreeState()
    emit('deleteCurResource')
    if (event?.phase === 'changing') {
      return
    }
    datasourceContext.loadDatasources().finally(() => {
      workspaceContextSwitching.value = false
      getTree()
    })
  },
})

watch(
  () => datasourceContext.datasourceId,
  () => {
    if (workspaceContextSwitching.value) return
    if (props.defaultMode) return
    const routeResourceId = currentRouteDashboardId()
    if (routeResourceId) {
      selectedNodeKey.value = getDashboardNodeKey(currentRouteDashboardScope(), routeResourceId)
      returnMounted.value = true
      getTree()
      return
    }
    resetTreeState()
    emit('deleteCurResource')
    getTree()
  }
)

watch(
  () => [currentRouteDashboardId(), currentRouteDashboardScope()],
  ([resourceId, dashboardScope]) => {
    if (!shouldAutoSelectDashboard()) return
    const routeNodeKey = getDashboardNodeKey(dashboardScope as DashboardScope, resourceId)
    if (!resourceId || String(routeNodeKey) === String(selectedNodeKey.value || '')) return
    const node = findDashboardNode(state.resourceTree, resourceId, dashboardScope as DashboardScope)
    if (!isLeafDashboardNode(node)) {
      if (state.resourceTree.length && props.defaultMode) {
        selectedNodeKey.value = null
        selectDashboardNode(resolveInitialDashboardNode())
        return
      }
      selectedNodeKey.value = getDashboardNodeKey(dashboardScope as DashboardScope, resourceId)
      returnMounted.value = true
      return
    }
    selectDashboardNode(node)
    ensureSelectedNodeExpanded()
    returnMounted.value = false
    nextTick(() => {
      resourceListTree.value?.setCurrentKey?.(selectedNodeKey.value, false)
      emitDashboardNodeClick(node)
    })
  }
)

const addOperation = (params: any) => {
  const creatingDefaultFolder =
    params?.opt === 'newFolder' && (params?.dashboardScope === DEFAULT_SCOPE || props.defaultMode)
  if (!creatingDefaultFolder && (props.defaultMode || !canOpenCreateDashboard.value)) return
  if (creatingDefaultFolder && !canEditDefaultOrder.value) return
  if (params?.id) {
    const folder = findTreeNode(state.originResourceTree, params.id)
    if (!folder || !canManageNode(folder)) return
  }
  if (params.opt === 'newLeaf') {
    openCreateDashboardDialog(params)
  } else {
    // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
    resourceGroupOptRef.value?.optInit(params)
  }
}

const operation = async (opt: string, data: SQTreeNode) => {
  const resourceId = getRawDashboardId(data)
  if (opt === 'toggleTreeEditing') {
    await toggleTreeEditing()
    return
  }
  if (opt === 'newLeaf') {
    addOperation({ opt: 'newLeaf', type: 'dashboard', id: isMyGroupNode(data) ? undefined : resourceId })
    return
  }
  if (opt === 'newFolder') {
    const dashboardScope = getDashboardScope(data)
    const isRootGroup = isMyGroupNode(data) || isDefaultGroupNode(data)
    addOperation({
      opt: 'newFolder',
      type: 'dashboard',
      nodeType: 'folder',
      name: '',
      placeholder: t('dashboard.length_1_64_characters'),
      pid: isRootGroup ? 'root' : resourceId,
      id: isRootGroup ? undefined : data.id,
      datasource: dashboardScope === DEFAULT_SCOPE ? null : datasourceContext.datasourceId,
      isDefault: dashboardScope === DEFAULT_SCOPE,
      dashboardScope,
    })
    return
  }
  if (opt === 'delete') {
    const msg = data.node_type === 'leaf' ? '' : t('dashboard.delete_tips')
    ElMessageBox.confirm(t('dashboard.delete_dashboard_warn', [data.name]), {
      confirmButtonType: 'danger',
      type: 'warning',
      tip: msg,
      autofocus: false,
      showClose: false,
    }).then(() => {
      dashboardApi.delete_resource({ id: resourceId, name: data.name }).then(() => {
        ElMessage.success(t('dashboard.delete_success'))
        getTree()
        dashboardStore.canvasDataInit()
        emit('deleteCurResource')
      })
    })
  } else if (opt === 'rename') {
    // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
    resourceGroupOptRef.value?.optInit({ opt: 'rename', id: resourceId, name: data.name })
  } else if (opt === 'edit') {
    resourceEdit(resourceId)
  } else if (opt === 'copyToPlatformTemplate') {
    if (!canCopyPlatformTemplateNode(data)) return
    await dashboardApi.platform_template_copy_from_dashboard({ dashboard_id: resourceId })
    ElMessage.success(t('dashboard.copy_to_platform_template_success'))
  } else if (opt === 'share') {
    if (!canShareNode(data)) return
    const previewImage = selectedNodeKey.value === data.id ? await captureDashboardSharePreview() : ''
    dashboardApi
      .share({
        dashboard_id: resourceId,
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
  } else if (opt === 'setDefault' || opt === 'removeDefault') {
    if (opt === 'setDefault' && !canSetDefaultNode(data)) return
    if (opt === 'removeDefault' && !canRemoveDefaultNode(data)) return
    dashboardApi
      .default_set({
        dashboard_id: resourceId,
        is_default: opt === 'setDefault',
      })
      .then(() => {
        ElMessage.success(
          opt === 'setDefault'
            ? t('dashboard.set_default_dashboard_success')
            : t('dashboard.remove_default_dashboard_success')
        )
        getTree()
      })
  } else if (opt === 'copyDefault') {
    if (!canCopyDefaultNode(data) || copyLoading.value) return
    copyLoading.value = true
    try {
      const record = await dashboardApi.default_copy({ dashboard_id: resourceId })
      ElMessage.success(t('dashboard.copy_default_dashboard_success'))
      await openCopiedDashboard(record)
    } finally {
      copyLoading.value = false
    }
  }
}

const baseInfoChangeFinish = (result?: any) => {
  if (result?.opt === 'newLeaf' && result?.resourceId) {
    selectedNodeKey.value = result.resourceId
    returnMounted.value = true
    syncDashboardRoute({
      id: result.resourceId,
      raw_id: result.resourceId,
      pid: result.pid || 'root',
      name: result.name || '',
      leaf: true,
      weight: 0,
      type: 'dashboard',
      node_type: 'leaf',
      dashboard_scope: MY_SCOPE,
    } as SQTreeNode)
  }
  getTree()
}

const saveTreeOrder = async () => {
  const requests: Promise<any>[] = []
  const defaultNodes = isCombinedDashboardTree.value
    ? findDefaultGroupNode(state.resourceTree)?.children || []
    : state.resourceTree
  const defaultItems = collectTreeOrderItems(defaultNodes, props.defaultMode ? 'root' : DEFAULT_GROUP_ID, DEFAULT_SCOPE)
  if (defaultItems.length && canEditDefaultOrder.value) {
    requests.push(dashboardApi.reorder({ scope: DEFAULT_SCOPE, items: defaultItems }))
  }
  if (!props.defaultMode) {
    const myNodes = findMyGroupNode(state.resourceTree)?.children || []
    const myItems = collectTreeOrderItems(
      myNodes,
      MY_GROUP_ID,
      MY_SCOPE,
      [],
      (node) => !node.is_default
    )
    if (myItems.length) {
      requests.push(dashboardApi.reorder({ scope: MY_SCOPE, items: myItems }))
    }
  }
  if (requests.length) {
    await Promise.all(requests)
  }
  state.originResourceTree = _.cloneDeep(state.resourceTree)
}

const toggleTreeEditing = async () => {
  if (!canEditDashboardTree.value) return
  if (isTreeEditing.value) {
    await saveTreeOrder()
    ElMessage.success(t('common.save_success'))
    isTreeEditing.value = false
    return
  }
  isTreeEditing.value = true
}

const sameDashboardScope = (left?: SQTreeNode | null, right?: SQTreeNode | null) =>
  getDashboardScope(left) === getDashboardScope(right)

const allowNodeDrag = (draggingNode: any) => isTreeEditing.value && isRealNode(draggingNode?.data)

const allowNodeDrop = (draggingNode: any, dropNode: any, type: string) => {
  if (!isTreeEditing.value || !isRealNode(draggingNode?.data) || !dropNode?.data) return false
  if (!sameDashboardScope(draggingNode.data, dropNode.data)) return false
  if (type === 'inner') {
    return dropNode.data.node_type !== 'leaf'
  }
  return isRealNode(dropNode.data)
}

const handleTreeDrop = () => {
  state.originResourceTree = _.cloneDeep(state.resourceTree)
  hideTreeDropIndicator()
  draggingTreeNode.value = null
}

const hideTreeDropIndicator = () => {
  treeDropIndicator.visible = false
  treeDropIndicator.nodeId = ''
  treeDropIndicator.placement = ''
}

const getNodeDropPlacement = (draggingNode: any, dropNode: any, event: DragEvent, contentRect: DOMRect) => {
  let dropPrev = allowNodeDrop(draggingNode, dropNode, 'prev')
  let dropInner = allowNodeDrop(draggingNode, dropNode, 'inner')
  let dropNext = allowNodeDrop(draggingNode, dropNode, 'next')

  if (dropNode?.nextSibling === draggingNode) {
    dropNext = false
  }
  if (dropNode?.previousSibling === draggingNode) {
    dropPrev = false
  }
  if (dropNode?.contains?.(draggingNode, false)) {
    dropInner = false
  }
  if (draggingNode === dropNode || draggingNode?.contains?.(dropNode)) {
    dropPrev = false
    dropInner = false
    dropNext = false
  }

  const prevPercent = dropPrev ? (dropInner ? 0.25 : dropNext ? 0.45 : 1) : -1
  const nextPercent = dropNext ? (dropInner ? 0.75 : dropPrev ? 0.55 : 0) : 1
  const distance = event.clientY - contentRect.top

  if (distance < contentRect.height * prevPercent) return 'prev'
  if (distance > contentRect.height * nextPercent) return 'next'
  if (dropInner) return 'inner'
  return ''
}

const onNodeDragOver = (draggingNode: any, dropNode: any, event: DragEvent) => {
  if (!isTreeEditing.value) return
  const target = event.target as HTMLElement | null
  const contentElement = target?.closest('.ed-tree-node__content') as HTMLElement | null
  const treeElement = resourceListTree.value?.$el as HTMLElement | undefined
  if (!contentElement || !treeElement) {
    hideTreeDropIndicator()
    return
  }
  const contentRect = contentElement.getBoundingClientRect()
  const dropType = getNodeDropPlacement(
    draggingTreeNode.value || draggingNode,
    dropNode,
    event,
    contentRect
  )
  if (!dropType) {
    hideTreeDropIndicator()
    return
  }
  treeDropIndicator.nodeId = String(dropNode?.data?.id || '')
  treeDropIndicator.placement = dropType
  treeDropIndicator.visible = true
}

const onNodeDragStart = (node: any) => {
  if (!allowNodeDrag(node)) return
  draggingTreeNode.value = node
  hideTreeDropIndicator()
}

const onNodeDrop = () => {
  if (isTreeEditing.value) {
    handleTreeDrop()
  }
}

const onNodeDragEnd = () => {
  hideTreeDropIndicator()
  draggingTreeNode.value = null
}

defineExpose({
  hasData,
  canCreateDashboard: canOpenCreateDashboard,
  createNewObject,
  mounted,
})
</script>

<template>
  <div
    class="resource-tree"
    :class="{
      'is-default-mode': defaultMode,
      'is-tree-editing': isTreeEditing,
    }"
  >
    <div class="tree-header">
      <div v-if="defaultMode" class="icon-methods">
        <span class="title">{{
          defaultMode ? t('dashboard.default_dashboard') : t('dashboard.dashboard')
        }}</span>
        <el-button link type="primary" class="icon-btn sidebar-toggle-btn" @click="onClickSideBarBtn">
          <el-icon>
            <icon_sidebar_outlined />
          </el-icon>
        </el-button>
      </div>
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
        <el-button
          v-if="canEditDashboardTree"
          link
          type="primary"
          class="filter-icon-span tree-edit-btn"
          :class="isTreeEditing && 'active'"
          @click="toggleTreeEditing"
        >
          <el-tooltip :offset="16" effect="dark" :content="treeEditButtonTip" placement="top">
            <span class="sort-trigger-icon">
              <Icon :name="isTreeEditing ? 'icon_done_outlined' : 'icon_tree_list'">
                <component
                  :is="isTreeEditing ? icon_done_outlined : icon_tree_list"
                  class="svg-icon opt-icon"
                />
              </Icon>
            </span>
          </el-tooltip>
        </el-button>
      </div>
    </div>
    <el-scrollbar v-loading="copyLoading" class="custom-tree">
      <el-tree
        ref="resourceListTree"
        class="dashboard-resource-tree"
        style="overflow-x: hidden"
        menu
        :empty-text="defaultMode ? t('dashboard.no_default_dashboard') : t('dashboard.no_dashboard')"
        :draggable="isTreeEditing"
        :allow-drag="allowNodeDrag"
        :allow-drop="allowNodeDrop"
        :default-expanded-keys="expandedArray"
        :auto-expand-parent="false"
        :data="state.resourceTree"
        :props="defaultProps"
        node-key="id"
        highlight-current
        :expand-on-click-node="true"
        :filter-node-method="filterNode"
        @node-expand="nodeExpand"
        @node-collapse="nodeCollapse"
        @node-click="nodeClick"
        @node-drag-start="onNodeDragStart"
        @node-drag-over="onNodeDragOver"
        @node-drag-end="onNodeDragEnd"
        @node-drop="onNodeDrop"
      >
        <template #default="{ node, data }">
          <span
            class="custom-tree-node"
            :style="getTreeNodeStyle(node, data)"
            :data-tree-depth="getTreeNodeDepth(node, data)"
            :data-shift-folder="shouldShiftTopLevelFolder(node, data) ? 'true' : undefined"
            :class="{
              'is-group-node': data.node_type !== 'leaf',
              'is-leaf-node': data.node_type === 'leaf',
              'is-real-folder-node': data.node_type !== 'leaf' && !isVirtualNode(data),
              'is-empty-folder-node':
                data.node_type !== 'leaf' && !isVirtualNode(data) && !(data.children || []).length,
              'is-default-order-drop-prev':
                treeDropIndicator.visible &&
                treeDropIndicator.nodeId === String(data.id) &&
                treeDropIndicator.placement === 'prev',
              'is-default-order-drop-next':
                treeDropIndicator.visible &&
                treeDropIndicator.nodeId === String(data.id) &&
                treeDropIndicator.placement === 'next',
              'is-tree-drop-inner':
                treeDropIndicator.visible &&
                treeDropIndicator.nodeId === String(data.id) &&
                treeDropIndicator.placement === 'inner',
            }"
          >
            <el-icon
              v-if="data.node_type !== 'leaf' && !isVirtualNode(data)"
              class="tree-node-icon folder-directory-icon"
            >
              <Icon name="folder-open-svgrepo-com">
                <icon_folder_open class="svg-icon" />
              </Icon>
            </el-icon>
            <el-icon
              v-else-if="data.node_type !== 'leaf'"
              class="tree-node-icon"
              :class="{ 'group-color-icon': isVirtualNode(data) }"
            >
              <Icon v-if="isVirtualNode(data)" name="icon_dashboard_group_color">
                <icon_dashboard_group_color class="svg-icon" />
              </Icon>
              <Icon v-else name="icon_folder"><icon_folder class="svg-icon" /></Icon>
            </el-icon>
            <el-icon v-else class="tree-node-icon icon-primary">
              <Icon name="icon_dashboard_grid_add">
                <icon_dashboard_grid_add class="svg-icon" />
              </Icon>
            </el-icon>
            <span :title="node.label" class="label-tooltip">
              {{ node.label }}
            </span>
            <span
              v-if="
                data.node_type === 'leaf' &&
                (data.is_shared || (!defaultMode && isMyDashboardNode(data) && data.is_default))
              "
              class="tree-node-status"
            >
              <span v-if="data.is_shared" class="shared-mark">
                {{ t('dashboard.shared') }}
              </span>
              <span
                v-if="!defaultMode && isMyDashboardNode(data) && data.is_default"
                class="default-mark"
              >
                {{ t('dashboard.default_mark') }}
              </span>
            </span>
            <div class="icon-more">
              <HandleMore
                v-if="hasNodeMenu(data)"
                class="tree-node-more-menu"
                :menu-list="nodeMenuList(data)"
                :icon-name="icon_more_outlined"
                vertical-dots
                :create-menu="isMyGroupNode(data)"
                placement="bottom"
                :offset="6"
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
  background: var(--dashboard-preview-card-bg, var(--workspace-card-bg, #ffffff));
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

    :deep(svg) {
      width: 16px;
      height: 16px;
      color: inherit;
    }
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

  &.tree-edit-btn {
    flex: 0 0 34px;
    min-width: 34px;
    margin-left: 0;
    color: var(--workspace-text-secondary, #667085);
  }

  &.compact-icon-btn {
    flex: 0 0 34px;
    min-width: 34px;
    display: inline-flex;
    align-items: center;
    justify-content: center;

    :deep(.ed-icon),
    :deep(svg) {
      width: 16px;
      height: 16px;
      color: inherit;
    }

    :deep(svg path) {
      fill: currentColor !important;
    }
  }

  &.sidebar-toggle-btn {
    color: var(--workspace-text-secondary, #667085);
  }

  &.create-compact-btn {
    color: var(--ed-color-primary, #2f6bff);
    background: var(--workspace-primary-soft-bg, rgba(47, 107, 255, 0.1));

    &:hover,
    &:focus {
      background: rgba(47, 107, 255, 0.16);
      color: var(--ed-color-primary, #2f6bff);
    }
  }
}

.resource-tree {
  --dashboard-sidebar-surface: var(--dashboard-preview-sidebar-bg, var(--workspace-panel-bg, var(--theme-panel-bg)));
  --ed-bg-color: var(--dashboard-sidebar-surface);
  --ed-bg-color-page: var(--dashboard-sidebar-surface);
  --ed-bg-color-overlay: var(--dashboard-preview-card-bg, var(--workspace-card-bg, #ffffff));
  --ed-fill-color: var(--workspace-control-hover-bg, #eef2f8);
  --ed-fill-color-light: var(--workspace-control-hover-bg, #eef2f8);
  --ed-fill-color-lighter: var(--workspace-control-bg, #f8f9fa);
  --ed-fill-color-extra-light: var(--dashboard-sidebar-surface);
  --ed-fill-color-blank: var(--dashboard-sidebar-surface);
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

  padding: 8px 0 0;
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--dashboard-sidebar-surface);
  color: var(--workspace-text-primary, #1f2329);
  font-family: 'PingFang SC', 'Microsoft YaHei', 'Helvetica Neue', Arial, sans-serif;

  .tree-header {
    padding: 0 8px;
  }

  &.is-default-mode {
    .custom-tree {
      padding-top: 8px;
    }
  }

  &.is-tree-editing {
    :deep(.dashboard-resource-tree.ed-tree .ed-tree__drop-indicator) {
      display: none !important;
    }
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

      &.sidebar-toggle-btn {
        color: var(--workspace-text-secondary, var(--TextSecondary, #667085));
        opacity: 0.78;

        :deep(svg) {
          width: 17px;
          height: 17px;
        }

        :deep(svg g),
        :deep(svg path),
        :deep(svg rect) {
          stroke-width: 1.05 !important;
        }

        &:hover {
          opacity: 1;
          color: var(--workspace-text-primary, var(--theme-text-primary));
        }
      }
    }
  }

  .search-row {
    position: relative;
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    height: 34px;
    margin-bottom: 8px;
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
      background-color: var(--dashboard-preview-card-bg, #ffffff) !important;
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
  --active-color: #e8f0ff;

  flex: 1;
  position: relative;
  min-height: 0;
  height: auto;
  padding: 0;
  background: var(--dashboard-sidebar-surface);
  color: var(--workspace-text-primary, #1f2329);

  :deep(.ed-scrollbar__view),
  :deep(.ed-tree) {
    background: var(--dashboard-sidebar-surface) !important;
    color: var(--workspace-text-primary, #1f2329) !important;
    max-width: 100%;
    overflow-x: hidden !important;
  }

  :deep(.ed-scrollbar__bar.is-vertical) {
    width: 4px;
    right: 2px;
  }

  :deep(.ed-scrollbar__bar.is-horizontal) {
    height: 4px;
    bottom: 2px;
  }

  :deep(.ed-scrollbar__thumb) {
    border-radius: 999px;
    background-color: rgba(100, 106, 115, 0.28);
  }

  :deep(.ed-scrollbar__bar:hover .ed-scrollbar__thumb) {
    background-color: rgba(100, 106, 115, 0.42);
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
    font-size: 13px;
    line-height: 20px;
  }

  :deep(.ed-tree-node__content) {
    margin: 0 8px 1px;
    width: calc(100% - 16px);
    max-width: calc(100% - 16px);
    box-sizing: border-box;
    height: 32px;
    padding: 0 !important;
    border-radius: 6px;
    font-size: 13px;
    line-height: 20px;
    font-weight: 400;
    color: var(--workspace-text-primary, #1f2329) !important;
    background: transparent;
    overflow: hidden;
  }

  :deep(.dashboard-resource-tree > .ed-tree-node > .ed-tree-node__content) {
    height: 32px;
    margin-top: 0;
    margin-bottom: 1px;
  }

  :deep(.dashboard-resource-tree .ed-tree-node__children) {
    margin-left: 0 !important;
    padding-left: 0 !important;
    max-width: 100%;
    overflow-x: hidden;
  }

  :deep(.dashboard-resource-tree > .ed-tree-node > .ed-tree-node__children .ed-tree-node__content) {
    margin: 0 8px 1px;
    width: calc(100% - 16px);
    max-width: calc(100% - 16px);
  }

  :deep(.dashboard-resource-tree.ed-tree .ed-tree-node > .ed-tree-node__content .tree-node-icon.icon-primary) {
    color: var(--workspace-text-secondary, #667085) !important;
    opacity: 1;
    transform: scale(1);
    transform-origin: center;
    transition:
      color 0.22s ease,
      opacity 0.22s ease,
      transform 0.22s cubic-bezier(0.2, 0.8, 0.2, 1);
  }

  :deep(.dashboard-resource-tree.ed-tree .ed-tree-node > .ed-tree-node__content .tree-node-icon.icon-primary svg) {
    color: inherit !important;
  }

  :deep(.dashboard-resource-tree.ed-tree .ed-tree-node > .ed-tree-node__content .tree-node-icon.icon-primary svg path) {
    fill: currentColor !important;
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
  }

  :deep(.dashboard-resource-tree.dashboard-resource-tree.ed-tree .ed-tree-node.is-current > .ed-tree-node__content .tree-node-icon.icon-primary) {
    color: var(--ed-color-primary, #2f6bff) !important;
    opacity: 1;
    transform: scale(1.18);
  }

  :deep(.dashboard-resource-tree.dashboard-resource-tree.ed-tree .ed-tree-node.is-current > .ed-tree-node__content .tree-node-icon.icon-primary svg) {
    color: inherit !important;
  }

  :deep(.dashboard-resource-tree.dashboard-resource-tree.ed-tree .ed-tree-node.is-current > .ed-tree-node__content .tree-node-icon.icon-primary svg path) {
    fill: currentColor !important;
  }

  :deep(.dashboard-resource-tree.dashboard-resource-tree.ed-tree .ed-tree-node.is-current > .ed-tree-node__content .label-tooltip) {
    font-weight: 500;
  }

  :deep(.ed-tree-node) {
    margin-bottom: 1px;
    max-width: 100%;
    overflow-x: hidden;
  }

  :deep(.ed-tree-node__expand-icon.is-leaf) {
    visibility: hidden;
    display: inline-flex !important;
    flex: 0 0 2px;
    width: 2px;
  }

  :deep(
    .ed-tree-node__content:has(
        > .custom-tree-node.is-real-folder-node[data-shift-folder='true']
      )
      > .ed-tree-node__expand-icon
  ) {
    position: relative;
    z-index: 2;
    transform: translateX(10px);
  }

  :deep(
    .ed-tree-node__content:has(
        > .custom-tree-node.is-real-folder-node[data-shift-folder='true']
      )
      > .ed-tree-node__expand-icon.expanded
  ) {
    transform: translateX(10px) rotate(90deg);
  }

}

.custom-tree-node {
  position: relative;
  width: 100%;
  min-width: 0;
  max-width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  box-sizing: border-box;
  padding-left: calc(var(--dashboard-tree-indent, 0px) + 6px);
  color: inherit;

  &.is-default-order-drop-prev::before,
  &.is-default-order-drop-next::before {
    content: '';
    position: absolute;
    left: 6px;
    right: 6px;
    height: 2px;
    border-radius: 999px;
    background: var(--ed-color-primary, #2f6bff);
    box-shadow: 0 0 0 2px rgba(47, 107, 255, 0.1);
    pointer-events: none;
    z-index: 4;
  }

  &.is-default-order-drop-prev::after,
  &.is-default-order-drop-next::after {
    content: '';
    position: absolute;
    left: 2px;
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--ed-color-primary, #2f6bff);
    pointer-events: none;
    z-index: 5;
  }

  &.is-default-order-drop-prev::before {
    top: 1px;
  }

  &.is-default-order-drop-prev::after {
    top: -1px;
  }

  &.is-default-order-drop-next::before {
    bottom: 1px;
  }

  &.is-default-order-drop-next::after {
    bottom: -1px;
  }

  &.is-tree-drop-inner {
    border-radius: 6px;
    background: rgba(47, 107, 255, 0.09);
    box-shadow:
      0 0 0 1px rgba(47, 107, 255, 0.48) inset,
      0 6px 14px rgba(47, 107, 255, 0.12);
    color: var(--workspace-text-primary, #1f2329);
  }

  &.is-tree-drop-inner .tree-node-icon {
    color: var(--ed-color-primary, #2f6bff);
  }

  .tree-node-icon {
    flex: 0 0 16px;
    width: 16px;
    height: 16px;
    font-size: 16px;
  }

  .tree-node-icon :deep(svg) {
    width: 16px;
    height: 16px;
  }

  .tree-node-icon.group-color-icon {
    flex-basis: 20px;
    width: 20px;
    height: 20px;
    font-size: 20px;

    :deep(svg) {
      width: 20px;
      height: 20px;
    }
  }

  .folder-directory-icon {
    color: var(--workspace-text-secondary, #667085);

    :deep(.ed-icon),
    :deep(svg) {
      width: 16px;
      height: 16px;
      min-width: 16px;
      min-height: 16px;
      color: inherit;
    }

    :deep(svg path) {
      fill: currentColor !important;
    }
  }

  .tree-node-icon.icon-primary {
    flex-basis: 14px;
    width: 14px;
    height: 14px;
    font-size: 14px;

    :deep(svg) {
      width: 14px;
      height: 14px;
    }
  }

  &.is-real-folder-node {
    padding-left: calc(var(--dashboard-tree-indent, 0px) + 10px);
  }

  &.is-leaf-node,
  &.is-empty-folder-node {
    padding-left: calc(var(--dashboard-tree-indent, 0px) + 18px);
  }

  .label-tooltip {
    flex: 1 1 auto;
    width: auto;
    min-width: 0;
    margin-left: 8px;
    font-size: 13px;
    font-weight: 400;
    line-height: 20px;
    color: inherit;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: clip;
  }

  .tree-node-status {
    position: absolute;
    top: 50%;
    right: 34px;
    transform: translateY(-50%);
    display: inline-flex;
    flex-direction: row-reverse;
    align-items: center;
    gap: 6px;
    max-width: 112px;
    overflow: hidden;
    z-index: 1;
  }

  .shared-mark {
    flex: 0 0 auto;
    padding: 0 6px;
    border-radius: 999px;
    background: rgba(37, 99, 235, 0.1);
    color: #2563eb;
    font-size: 10px;
    line-height: 16px;
    font-weight: 500;
  }

  .default-mark {
    flex: 0 0 auto;
    padding: 0 6px;
    border-radius: 999px;
    background: rgba(245, 158, 11, 0.14);
    color: #b45309;
    font-size: 10px;
    line-height: 16px;
    font-weight: 500;
  }

  .icon-more {
    position: absolute;
    top: 50%;
    right: 6px;
    transform: translateY(-50%);
    display: none;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    color: var(--workspace-text-secondary, #667085);
    z-index: 2;
  }

  .tree-node-more-menu {
    flex: 0 0 24px;
    width: 24px;
    height: 24px;
    display: inline-flex;
    align-items: center;
    justify-content: center;

    :deep(.hover-icon) {
      width: 24px;
      height: 24px;
      border-radius: 6px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      background: #f8faff;
      box-shadow: none;
      color: #8aa3ea;
      cursor: pointer;
      opacity: 1;
      transition:
        background-color 0.18s ease,
        box-shadow 0.18s ease,
        color 0.18s ease,
        transform 0.18s ease,
        opacity 0.18s ease;
    }

    :deep(.hover-icon svg),
    :deep(.hover-icon .vertical-dots) {
      color: inherit;
    }

    :deep(.hover-icon .vertical-dots span) {
      width: 3.5px;
      height: 3.5px;
    }

    :deep(.hover-icon svg path) {
      fill: currentColor !important;
    }

    :deep(.hover-icon:hover),
    :deep(.hover-icon:focus) {
      background: #f8f9fb;
      box-shadow: none;
      color: #8a94a3;
      opacity: 1;
      transform: translateY(-1px);
    }
  }

  &:hover {
    .label-tooltip {
      width: auto;
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
.menu-outer-dv_popper {
  min-width: 140px;
  margin-top: -2px !important;

  .ed-icon {
    border-radius: 6px;
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
