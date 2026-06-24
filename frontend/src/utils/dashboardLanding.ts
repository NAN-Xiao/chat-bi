import type { RouteLocationRaw } from 'vue-router'
import { dashboardApi } from '@/api/dashboard'
import { useDatasourceContextStore } from '@/stores/datasourceContext'
import { useCache } from '@/utils/useCache'
import {
  MEMBER_HOME,
  resolveAuthenticatedHome,
  resolveBusinessHome,
  resolveLoginSuccessTarget,
  type NavigationUserState,
} from '@/utils/navigation'
import type { SQTreeNode } from '@/views/dashboard/utils/treeNode'

type DashboardLandingUserState = NavigationUserState & {
  getUid?: string
  uid?: string
  getTenantId?: string
  tenantId?: string
}

const { wsCache } = useCache()
const silentRequestConfig = { requestOptions: { silent: true } }

const dashboardRoute = (path: string, dashboardId: string | number): RouteLocationRaw => ({
  path,
  query: { resourceId: String(dashboardId) },
})

const userScope = (userStore?: DashboardLandingUserState) => {
  const userId = userStore?.getUid || userStore?.uid || 'default'
  const tenantId = userStore?.getTenantId || userStore?.tenantId || 'default'
  return `${userId}.${tenantId}`
}

export const lastDefaultDashboardCacheKey = (userStore?: DashboardLandingUserState) =>
  `dashboard.lastDefault.${userScope(userStore)}`

export const getRememberedDefaultDashboardId = (userStore?: DashboardLandingUserState) => {
  const value = wsCache.get(lastDefaultDashboardCacheKey(userStore))
  return value === undefined || value === null || value === '' ? null : String(value)
}

export const rememberDefaultDashboardId = (
  dashboardId?: string | number | null,
  userStore?: DashboardLandingUserState
) => {
  if (!dashboardId) return
  wsCache.set(lastDefaultDashboardCacheKey(userStore), String(dashboardId))
}

export const findFirstLeafDashboardNode = (nodes: SQTreeNode[] = []): SQTreeNode | undefined => {
  for (const node of nodes) {
    if (node.node_type === 'leaf' || node.leaf === true) return node
    const matched = findFirstLeafDashboardNode(node.children || [])
    if (matched) return matched
  }
  return undefined
}

export const findDashboardNodeById = (
  nodes: SQTreeNode[] = [],
  dashboardId?: string | number | null
): SQTreeNode | undefined => {
  if (!dashboardId) return undefined
  for (const node of nodes) {
    if (String(node.id) === String(dashboardId)) return node
    const matched = findDashboardNodeById(node.children || [], dashboardId)
    if (matched) return matched
  }
  return undefined
}

const resolveDefaultDashboardTarget = async (userStore: DashboardLandingUserState) => {
  try {
    const dashboards = ((await dashboardApi.default_list(silentRequestConfig)) || []) as SQTreeNode[]
    const rememberedId = getRememberedDefaultDashboardId(userStore)
    const candidate =
      findDashboardNodeById(dashboards, rememberedId) || findFirstLeafDashboardNode(dashboards)
    if (!candidate?.id) return null
    rememberDefaultDashboardId(candidate.id, userStore)
    return dashboardRoute('/default-dashboard/index', candidate.id)
  } catch (error) {
    console.warn('Failed to resolve recommended dashboard landing', error)
    return null
  }
}

const resolveMyDashboardTarget = async () => {
  const datasourceContext = useDatasourceContextStore()
  try {
    await datasourceContext.loadDatasources()
    const currentDatasourceId = datasourceContext.datasourceId
    const datasourceIds = datasourceContext.datasources
      .map((item) => item.id)
      .filter(Boolean)
      .map((id) => String(id))
    const orderedDatasourceIds = [
      ...(currentDatasourceId ? [String(currentDatasourceId)] : []),
      ...datasourceIds.filter((id) => id !== String(currentDatasourceId || '')),
    ]

    for (const datasourceId of orderedDatasourceIds) {
      const tree = ((await dashboardApi.list_resource(
        { datasource: datasourceId },
        silentRequestConfig
      )) || []) as SQTreeNode[]
      const candidate = findFirstLeafDashboardNode(tree)
      if (candidate?.id) {
        datasourceContext.setDatasourceById(datasourceId, true)
        return dashboardRoute('/dashboard/index', candidate.id)
      }
    }
  } catch (error) {
    console.warn('Failed to resolve my dashboard landing', error)
  }
  return null
}

const resolveDashboardLandingTarget = async (
  fallbackTarget: string,
  userStore: DashboardLandingUserState
): Promise<RouteLocationRaw> => {
  if (fallbackTarget !== MEMBER_HOME) return fallbackTarget

  const defaultTarget = await resolveDefaultDashboardTarget(userStore)
  if (defaultTarget) return defaultTarget

  const myDashboardTarget = await resolveMyDashboardTarget()
  return myDashboardTarget || MEMBER_HOME
}

export const resolveAuthenticatedDashboardLandingTarget = (userStore: DashboardLandingUserState) =>
  resolveDashboardLandingTarget(resolveAuthenticatedHome(userStore), userStore)

export const resolveBusinessDashboardLandingTarget = (userStore: DashboardLandingUserState) =>
  resolveDashboardLandingTarget(resolveBusinessHome(userStore), userStore)

export const resolveLoginSuccessDashboardTarget = async (
  userStore: DashboardLandingUserState,
  redirect?: string | null
) => {
  const target = resolveLoginSuccessTarget(userStore, redirect)
  if (target !== MEMBER_HOME) return target
  return resolveDashboardLandingTarget(target, userStore)
}
