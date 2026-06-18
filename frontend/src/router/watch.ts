import { useCache } from '@/utils/useCache'
import { useAppearanceStoreWithOut } from '@/stores/appearance'
import { useUserStore } from '@/stores/user'
import type { Router } from 'vue-router'
import { generateDynamicRouters } from './dynamic'
import { toLoginPage } from '@/utils/utils'

const appearanceStore = useAppearanceStoreWithOut()
const userStore = useUserStore()
const { wsCache } = useCache()
const whiteList = ['/login', '/admin-login']
const assistantWhiteList = ['/assistant', '/embeddedPage', '/embeddedCommon', '/401']
const platformAdminHome = '/system/tenant'
const tenantChatBIEntryPrefixes = [
  '/chat',
  '/dashboard',
  '/dashboard-store',
  '/custom-agent',
  '/access',
  '/account',
  '/as',
  '/canvas',
  '/dashboard-preview',
  '/chatPreview',
  '/dsTable',
  '/set/permission',
  '/set/appearance',
  '/system/project',
  '/system/embedded',
  '/system/setting/permission',
]

const defaultAuthenticatedPath = () =>
  userStore.isSystemAdminUser ? platformAdminHome : '/chat'

const matchesPathPrefix = (path: string, prefix: string) =>
  path === prefix || path.startsWith(`${prefix}/`)

const isTenantChatBIRoute = (path: string) =>
  tenantChatBIEntryPrefixes.some((prefix) => matchesPathPrefix(path, prefix))

export const watchRouter = (router: Router) => {
  router.beforeEach(async (to: any, from: any, next: any) => {
    await appearanceStore.setAppearance()
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
    if (!userStore.getUid) {
      try {
        await userStore.info()
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
  const platformOnly = to.matched?.some((record: any) => record?.meta?.platformOnly)
  return (
    (userStore.isSystemAdminUser && isTenantChatBIRoute(to.path)) ||
    (to.path.startsWith('/system') && !userStore.isSystemManagerUser) ||
    (to.path.startsWith('/set') && !userStore.isSystemManagerUser) ||
    (platformOnly && !userStore.isSystemAdminUser)
  )
}
