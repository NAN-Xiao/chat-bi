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

const appearanceStore = useAppearanceStoreWithOut()
const userStore = useUserStore()
const { wsCache } = useCache()
const whiteList = ['/login', '/admin-login']
const assistantWhiteList = ['/assistant', '/embeddedPage', '/embeddedCommon', '/401']
const platformAdminHome = '/system/tenant'
const tenantAdminSystemHome = '/system/overview'
const tenantChatBIEntryPrefixes = [
  '/chat',
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
]

const defaultAuthenticatedPath = () =>
  userStore.isPlatformWorkspaceDelegate
    ? tenantAdminSystemHome
    : userStore.isSystemAdminUser
    ? platformAdminHome
    : userStore.hasActiveWorkspace
      ? userStore.isTenantAdminUser
        ? tenantAdminSystemHome
        : '/chat'
      : '/account/workspaces'

const matchesPathPrefix = (path: string, prefix: string) =>
  path === prefix || path.startsWith(`${prefix}/`)

const isTenantChatBIRoute = (path: string) =>
  tenantChatBIEntryPrefixes.some((prefix) => matchesPathPrefix(path, prefix))

export const watchRouter = (router: Router) => {
  router.beforeEach(async (to: any, from: any, next: any) => {
    await appearanceStore.setAppearance()
    const shouldEnterDelegate = applyPlatformWorkspaceDelegateRouteQuery(to.query || {})
    const shouldExitDelegate =
      !shouldEnterDelegate &&
      to.path === platformAdminHome &&
      isPlatformWorkspaceDelegateSession() &&
      to.query?.platform_workspace_delegate !== '1'
    if (to.path.startsWith('/login') && userStore.getUid) {
      next(to?.query?.redirect || '/')
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
    if (to.path === '/' || accessCrossPermission(to)) {
      next(defaultAuthenticatedPath())
      return
    }
    if (to.path === '/login' || to.path === '/admin-login') {
      console.info(from)
      next('/chat')
    } else {
      next()
    }
  })
}

const accessCrossPermission = (to: any) => {
  if (!to?.path) return false
  const platformDelegate = userStore.isPlatformWorkspaceDelegate
  const platformOnly = to.matched?.some((record: any) => record?.meta?.platformOnly)
  const tenantAdminOnly = to.matched?.some((record: any) => record?.meta?.tenantAdminOnly)
  const tenantBusiness = to.matched?.some((record: any) => record?.meta?.tenantBusiness)
  const tenantSystemRoute = to.path.startsWith('/system') && (tenantAdminOnly || tenantBusiness)
  return (
    (userStore.isSystemAdminUser && !platformDelegate && isTenantChatBIRoute(to.path)) ||
    (platformDelegate && !to.path.startsWith('/system') && isTenantChatBIRoute(to.path)) ||
    (platformDelegate && platformOnly) ||
    (!userStore.isSystemAdminUser && !userStore.hasActiveWorkspace && isTenantChatBIRoute(to.path)) ||
    (to.path.startsWith('/system') && !tenantSystemRoute && !userStore.isSystemAdminUser) ||
    (tenantAdminOnly && !userStore.isTenantAdminUser) ||
    (tenantBusiness && !userStore.hasActiveWorkspace) ||
    (to.path.startsWith('/set') && !userStore.isSystemManagerUser) ||
    (platformOnly && !userStore.isSystemAdminUser)
  )
}
