import { createRouter, createWebHashHistory } from 'vue-router'

import Layout from '@/components/layout/index.vue'
import login from '@/views/login/index.vue'
import chat from '@/views/chat/index.vue'
import ds from '@/views/ds/index.vue'
import dashboard from '@/views/dashboard/index.vue'
import setting from '@/views/setting/index.vue'
import { watchRouter } from './watch'
const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: login
    },
    {
      path: '/chat',
      component: Layout,
      redirect: '/chat/index',
      children: [
        {
          path: 'index',
          name: 'chat',
          component: chat,
          meta: { title: 'ChatBI', icon: 'chat'}
        }
      ]
    },
    {
      path: '/ds',
      component: Layout,
      redirect: '/ds/index',
      children: [
        {
          path: 'index',
          name: 'ds',
          component: ds,
          meta: { title: 'Datasource', icon: 'ds' }
        }
      ]
    },
    {
      path: '/dashboard',
      component: Layout,
      redirect: '/dashboard/index',
      children: [
        {
          path: 'index',
          name: 'dashboard',
          component: dashboard,
          meta: { title: 'Dashboard', icon: 'dashboard' }
        }
      ]
    },
    {
      path: '/setting',
      component: Layout,
      redirect: '/setting/index',
      children: [
        {
          path: 'index',
          name: 'setting',
          component: setting,
          meta: { title: 'Setting', icon: 'setting' }
        }
      ]
    }
  ]
})
watchRouter(router)
export default router