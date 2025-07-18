import { createRouter, createWebHashHistory } from 'vue-router'
// @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
import Layout from '@/components/layout/index.vue'
import LayoutDsl from '@/components/layout/LayoutDsl.vue'
import SinglePage from '@/components/layout/SinglePage.vue'
import login from '@/views/login/index.vue'
import chat from '@/views/chat/index.vue'
import Datasource from '@/views/ds/Datasource.vue'
import DashboardEditor from '@/views/dashboard/editor/index.vue'
import DashboardPreview from '@//views/dashboard/preview/SQPreviewSingle.vue'
import Dashboard from '@/views/dashboard/index.vue'
import Model from '@/views/system/model/Model.vue'
import assistant from '@/views/embedded/assistant.vue'
import User from '@/views/system/user/User.vue'
import Workspace from '@/views/system/workspace/index.vue'
import { watchRouter } from './watch'
const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: login,
    },
    {
      path: '/chat',
      component: LayoutDsl,
      redirect: '/chat/index',
      children: [
        {
          path: 'index',
          name: 'chat',
          component: chat,
          meta: { title: 'Data Q&A', icon: 'chat' },
        },
      ],
    },
    {
      path: '/dsTable',
      component: SinglePage,
      children: [
        {
          path: ':dsId/:dsName',
          name: 'dsTable',
          component: () => import('@/views/ds/TableList.vue'),
          props: true,
        },
      ],
    },
    {
      path: '/ds',
      component: LayoutDsl,
      redirect: '/ds/index',
      children: [
        {
          path: 'index',
          name: 'ds',
          component: Datasource,
          meta: { title: 'Data Connections', icon: 'ds' },
        },
      ],
    },
    {
      path: '/dashboard',
      component: LayoutDsl,
      redirect: '/dashboard/index',
      children: [
        {
          path: 'index',
          name: 'dashboard',
          component: Dashboard,
          meta: { title: 'Dashboard', icon: 'dashboard' },
        },
      ],
    },
    {
      path: '/canvas',
      name: 'canvas',
      component: DashboardEditor,
      meta: { title: 'canvas', icon: 'dashboard' },
    },
    {
      path: '/dashboard-preview',
      name: 'preview',
      component: DashboardPreview,
      meta: { title: 'DashboardPreview', icon: 'dashboard' },
    },
    /* {
      path: "/setting",
      component: Layout,
      redirect: "/setting/index",
      children: [
        {
          path: "index",
          name: "setting",
          component: setting,
          meta: { title: "Settings", icon: "setting" },
        },
      ],
    }, */
    // {
    //   path: '/system',
    //   component: Layout,
    //   redirect: '/system/model',
    //   children: [
    //     /*  {
    //       path: "user",
    //       name: "user",
    //       component: User,
    //       meta: { title: "User Management", icon: "icon_user" },
    //     }, */
    //     {
    //       path: 'model',
    //       name: 'model',
    //       component: Model,
    //       meta: { title: 'AI Model Configuration', icon: 'icon_ai' },
    //     },
    //   ],
    // },
    {
      path: '/system',
      component: LayoutDsl,
      redirect: '/system/user',
      children: [
        {
          path: 'user',
          name: 'user',
          component: User,
          meta: { title: '用户管理', icon: 'user' },
        },
        {
          path: 'workspace',
          name: 'workspace',
          component: Workspace,
          meta: { title: '工作空间', icon: 'workspace' },
        },
        {
          path: 'model',
          name: 'model',
          component: Model,
          meta: { title: 'AI Model Configuration', icon: 'icon_ai' },
        },
      ],
    },
    {
      path: '/assistant',
      name: 'assistant',
      component: assistant,
    },
  ],
})
watchRouter(router)
export default router
