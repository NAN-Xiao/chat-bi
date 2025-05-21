import { createRouter, createWebHashHistory } from 'vue-router'

import Layout from '@/components/layout/index.vue'
import login from '@/views/login/index.vue'
import chat from '@/views/chat/index.vue'
import ds from '@/views/ds/index.vue'
import DashboardEditor from '@/views/dashboard/editor/index.vue'
import Dashboard from '@/views/dashboard/index.vue'
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
          meta: { title: 'Data Q&A', icon: 'chat' }
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
          meta: { title: 'Data Connections', icon: 'ds' }
        },
        {
          path: 'dsTable/:dsId/:dsName',
          name: 'dsTable',
          component: () => import('@/views/ds/TableList.vue'),
          props: true
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
          component: Dashboard,
          meta: { title: 'Dashboard', icon: 'dashboard' }
        }
      ]
    },
    {
      path: '/dashboard-edit',
      redirect: '/dashboard-edit/index',
      component: Layout,
      children: [
        {
          path: 'index',
          name: 'dashboard-edit',
          component: DashboardEditor,
          meta: { title: 'dashboard-edit', icon: 'dashboard' }
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
          meta: { title: 'Settings', icon: 'setting' }
        }
      ]
    },
    {
      path: '/system',
      component: Layout,
      redirect: '/system/user',
      children: [
        {
          path: 'user',
          name: 'user',
          component: () => import('@/views/system/user/index.vue'),
          meta: { title: 'User Management', icon: 'icon_user' }
        },
        {
          path: 'model',
          name: 'model',
          component: () => import('@/views/system/model/index.vue'),
          meta: { title: 'AI Model Configuration', icon: 'icon_ai' }
        }
      ]
    }
  ]
})
watchRouter(router)
export default router