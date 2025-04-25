import { ElMessage } from 'element-plus'
import { useCache } from '@/utils/useCache'
const { wsCache } = useCache()
// 不需要验证token的白名单路由
const whiteList = ['/login']
export const watchRouter = (router: any) => {
  router.beforeEach(async (to: any, from: any, next: any) => {
    // 获取token
    const token = wsCache.get('user.token')
    // 如果没有token
    if (!token) {
      if (whiteList.includes(to.path)) {
        next()
      } else {
        ElMessage.error('请先登录')
        next('/login')
      }
      return
    }
    // 处理根路径重定向
    if (to.path === '/') {
      next('/chat')
      return
    }
    // 已有token和用户信息，允许访问
    if (to.path === '/login') {
      next('/chat')
    } else {
      next()
    }
  })
}
