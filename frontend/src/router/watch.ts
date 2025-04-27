import { ElMessage } from 'element-plus'
import { useCache } from '@/utils/useCache'
const { wsCache } = useCache()
const whiteList = ['/login']
export const watchRouter = (router: any) => {
  router.beforeEach(async (to: any, from: any, next: any) => {
    const token = wsCache.get('user.token')
    if (!token) {
      if (whiteList.includes(to.path)) {
        next()
      } else {
        ElMessage.error('Please login first')
        next('/login')
      }
      return
    }
    if (to.path === '/') {
      next('/chat')
      return
    }
    if (to.path === '/login') {
      next('/chat')
    } else {
      next()
    }
  })
}
