import { ElMessage } from 'element-plus-secondary'
import { useCache } from '@/utils/useCache'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()
const { wsCache } = useCache()
const whiteList = ['/login']
export const watchRouter = (router: any) => {
  router.beforeEach(async (to: any, from: any, next: any) => {
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
