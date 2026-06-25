import { useCache } from '@/utils/useCache'
import { useAppearanceStoreWithOut } from '@/stores/appearance'
import { useUserStore } from '@/stores/user'
import type { Router } from 'vue-router'
import { generateDynamicRouters } from './dynamic'
import { toLoginPage } from '@/utils/utils'
import {
  applyPlatformWorkspaceDelegateRouteQuery,
  clearPlatformWorkspaceDelegateContext,
  isPlatformWorkspaceDelegateSession,
} from '@/utils/platformWorkspaceDelegate'
import {
  resolveAuthenticatedDashboardLandingTarget,
  resolveLoginSuccessDashboardTarget,
} from '@/utils/dashboardLanding'
import {
  clearRememberedBusinessTenant,
  getRememberedBusinessTenant,
} from '@/utils/workspaceAdminContext'
import { useDatasourceContextStore } from '@/stores/datasourceContext'
import { emitWorkspaceContextChange, useEmitt } from '@/utils/useEmitt'
import { canManageCurrentWorkspace } from '@/utils/workspacePermission'

const appearanceStore = useAppearanceStoreWithOut()
const userStore = useUserStore()
const datasourceContext = useDatasourceContextStore()
const { wsCache } = useCache()
const whiteList = ['/login', '/admin-login']
const assistantWhiteList = ['/assistant', '/embeddedPage', '/embeddedCommon', '/401']
const platformAdminHome = '/system/platform-overview'
const platformTenantManagementPath = '/system/tenant'
const tenantChatBIEntryPrefixes = [
  '/chat',
  '/default-dashboard',
  '/dashboard',
  '/dashboard-store',
  '/custom-agent',
  '/as',
  '/canvas',
  '/dashboard-preview',
  '/chatPreview',
  '/dsTable',
  '/set/permission',
  '/set/appearance',
  '/system/embedded',
  '/system/variables',
  '/system/setting/permission',
  '/system/setting/variables',
]

const defaultAuthenticatedPath = () => resolveAuthenticatedDashboardLandingTarget(userStore)

const matchesPathPrefix = (path: string, prefix: string) =>
  path === prefix || path.startsWith(`${prefix}/`)

const isTenantChatBIRoute = (path: string) =>
  tenantChatBIEntryPrefixes.some((prefix) => matchesPathPrefix(path, prefix))

const isPlatformTemplateCanvasRoute = (to: any) =>
  to?.path === '/canvas' && Boolean(to?.query?.platformTemplateId)

const restoreBusinessTenantAfterWorkspaceAdmin = async (to: any, from: any) => {
  if (!from?.path?.startsWith('/system') || to?.path?.startsWith('/system')) return
  if (!isTenantChatBIRoute(to.path)) return
  const rememberedTenant = getRememberedBusinessTenant()
  if (!rememberedTenant?.id) return
  const tenantId = String(rememberedTenant.id)
  if (tenantId !== String(userStore.getTenantId || '')) {
    emitWorkspaceContextChange({ tenantId, phase: 'changing' })
    await userStore.switchTenant(tenantId)
    datasourceContext.clear(true)
    await datasourceContext.loadDatasources(true)
    useEmitt().emitter.emit('datasource-context-change', null)
    emitWorkspaceContextChange({ tenantId, phase: 'changed' })
  }
  clearRememberedBusinessTenant()
}

export const watchRouter = (router: Router) => {
  router.beforeEach(async (to: any, from: any, next: any) => {
    await appearanceStore.setAppearance()
    const shouldEnterDelegate = applyPlatformWorkspaceDelegateRouteQuery(to.query || {})
    const shouldExitDelegate =
      !shouldEnterDelegate &&
      (to.path === platformAdminHome || to.path === platformTenantManagementPath) &&
      isPlatformWorkspaceDelegateSession() &&
      to.query?.platform_workspace_delegate !== '1'
    if (to.path.startsWith('/login') && userStore.getUid) {
      const redirect = Array.isArray(to?.query?.redirect)
        ? to.query.redirect[0]
        : to?.query?.redirect
      next(await resolveLoginSuccessDashboardTarget(userStore, redirect))
      return
    }
    if (assistantWhiteList.includes(to.path)) {
      next()
      return
    }
    const token = wsCache.get('user.token')
    if (whiteList.includes(to.path)) {
      next()
      return
    }
    if (!token) {
      // ElMessage.error('Please login first')
      next(toLoginPage(to.fullPath))
      return
    }
    if (shouldEnterDelegate || shouldExitDelegate) {
      try {
        if (shouldExitDelegate) {
          clearPlatformWorkspaceDelegateContext()
        }
        await userStore.info()
        if (!userStore.isSystemAdminUser || userStore.isPlatformWorkspaceDelegate) {
          try {
            await userStore.loadTenants(true)
          } catch (error) {
            console.warn('Failed to load workspace list before route access check', error)
          }
        }
        generateDynamicRouters(router)
      } catch {
        userStore.clear()
        next(toLoginPage(to.fullPath))
        return
      }
    } else if (!userStore.getUid) {
      try {
        await userStore.info()
        if (!userStore.isSystemAdminUser || userStore.isPlatformWorkspaceDelegate) {
          try {
            await userStore.loadTenants()
          } catch (error) {
            console.warn('Failed to load workspace list before route access check', error)
          }
        }
        generateDynamicRouters(router)
      } catch {
        userStore.clear()
        next(toLoginPage(to.fullPath))
        return
      }
    }
    if (to.path === '/docs') {
      location.href = to.fullPath
      return
    }
    try {
      await restoreBusinessTenantAfterWorkspaceAdmin(to, from)
    } catch (error) {
      console.warn('Failed to restore business workspace after leaving workspace admin', error)
    }
    if (to.path === '/' || accessCrossPermission(to)) {
      next(await defaultAuthenticatedPath())
      return
    }
    if (to.path === '/login' || to.path === '/admin-login') {
      console.info(from)
      next(await defaultAuthenticatedPath())
    } else {
      next()
    }
  })
}

const accessCrossPermission = (to: any) => {
  if (!to?.path) return false
  const platformDelegate = userStore.isPlatformWorkspaceDelegate
  const platformOnly = to.matched?.some((record: any) => record?.meta?.platformOnly)
  const platformOperation = to.matched?.some((record: any) => record?.meta?.platformOperation)
  const tenantAdminOnly = to.matched?.some((record: any) => record?.meta?.tenantAdminOnly)
  const tenantBusiness = to.matched?.some((record: any) => record?.meta?.tenantBusiness)
  const tenantSystemRoute = to.path.startsWith('/system') && (tenantAdminOnly || tenantBusiness)
  const canManageWorkspace = canManageCurrentWorkspace(userStore)
  const platformAdminOperation =
    userStore.isSystemAdminUser && !platformDelegate && platformOperation
  const platformTemplateCanvasOperation =
    userStore.isSystemAdminUser && !platformDelegate && isPlatformTemplateCanvasRoute(to)
  return (
    (userStore.isSystemAdminUser &&
      !platformDelegate &&
      isTenantChatBIRoute(to.path) &&
      !platformAdminOperation &&
      !platformTemplateCanvasOperation) ||
    (platformDelegate && platformOnly) ||
    (!userStore.isSystemAdminUser && !userStore.hasActiveWorkspace && isTenantChatBIRoute(to.path)) ||
    (to.path.startsWith('/system') && !tenantSystemRoute && !userStore.isSystemAdminUser) ||
    (tenantAdminOnly && !canManageWorkspace && !platformAdminOperation) ||
    (tenantBusiness && !userStore.hasActiveWorkspace && !platformAdminOperation) ||
    (to.path.startsWith('/set') && !userStore.isSystemManagerUser) ||
    (platformOnly && !userStore.isSystemAdminUser)
  )
}
