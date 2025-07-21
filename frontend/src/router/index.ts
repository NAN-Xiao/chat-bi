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
import Member from '@/views/system/member/index.vue'
import Permission from '@/views/system/permission/index.vue'
import User from '@/views/system/user/User.vue'
import Workspace from '@/views/system/workspace/index.vue'
import { i18n } from '@/i18n'
import { watchRouter } from './watch'

const t = i18n.global.t
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
          props: (route) => {
            return { startChatDsId: route.query.start_chat }
          },
          meta: { title: t('menu.Data Q&A'), icon: 'chat' },
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
          meta: { title: t('menu.Data Connections'), icon: 'ds' },
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
          meta: { title: t('dashboard.dashboard'), icon: 'dashboard' },
        },
      ],
    },
    {
      path: '/set',
      component: LayoutDsl,
      redirect: '/set/member',
      meta: { title: t('workspace.set'), icon: 'setting' },
      children: [
        {
          path: '/set/member',
          name: 'member',
          component: Member,
          meta: { title: t('workspace.member_management') },
        },
        {
          path: '/set/permission',
          name: 'permission',
          component: Permission,
          meta: { title: t('workspace.permission_configuration') },
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
          meta: { title: t('user.user_management'), icon: 'user' },
        },
        {
          path: 'workspace',
          name: 'workspace',
          component: Workspace,
          meta: { title: t('user.workspace'), icon: 'workspace' },
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
