import { ElMessage } from 'element-plus-secondary'
import { useCache } from '@/utils/useCache'
import { useUserStore } from '@/stores/user'
import { request } from '@/utils/request'
const userStore = useUserStore()
const { wsCache } = useCache()
const whiteList = ['/login']
export const watchRouter = (router: any) => {
  router.beforeEach(async (to: any, from: any, next: any) => {
    await loadXpackStatic()
    const token = wsCache.get('user.token')
    if (whiteList.includes(to.path)) {
      next()
      return
    }
    if (!token) {
      ElMessage.error('Please login first')
      next('/login')
      return
    }
    if (!wsCache.get('user.uid')) {
      await userStore.info()
    }
    if (to.path === '/') {
      next('/chat')
      return
    }
    if (to.path === '/login') {
      console.log(from)
      next('/chat')
    } else {
      next()
    }
  })
}
const loadXpackStatic = () => {
  if (document.getElementById('sqlbot_xpack_static')) {
    return Promise.resolve()
  }
  const url = '/xpack_static/license-generator.umd.js'
  return request.loadRemoteScript(url, 'sqlbot_xpack_static', () => {
    // eslint-disable-next-line @typescript-eslint/ban-ts-comment
    // @ts-ignore
    LicenseGenerator?.init(import.meta.env.VITE_API_BASE_URL)
  })
}
