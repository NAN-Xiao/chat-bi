import { createRouter, createWebHashHistory } from 'vue-router'
// @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
import Layout from '@/components/layout/index.vue'
import LayoutDsl from '@/components/layout/LayoutDsl.vue'
import SinglePage from '@/components/layout/SinglePage.vue'
import login from '@/views/login/index.vue'
import chat from '@/views/chat/index.vue'
import DashboardEditor from '@/views/dashboard/editor/index.vue'
import DashboardPreview from '@//views/dashboard/preview/SQPreviewSingle.vue'
import Dashboard from '@/views/dashboard/index.vue'
import Access from '@/views/access/index.vue'
import CustomAgent from '@/views/custom-agent/index.vue'
import DashboardStore from '@/views/dashboard/store/index.vue'
import Datasource from '@/views/ds/Datasource.vue'
import Model from '@/views/system/model/Model.vue'
// import Embedded from '@/views/system/embedded/index.vue'
// import SetAssistant from '@/views/system/embedded/iframe.vue'
import SystemEmbedded from '@/views/system/embedded/Page.vue'
import Variables from '@/views/system/variables/index.vue'

import assistantTest from '@/views/system/embedded/Test.vue'
import assistant from '@/views/embedded/index.vue'
import EmbeddedPage from '@/views/embedded/page.vue'
import EmbeddedCommon from '@/views/embedded/common.vue'
import Professional from '@/views/system/professional/index.vue'
import Training from '@/views/system/training/index.vue'
import Prompt from '@/views/system/prompt/index.vue'
import Audit from '@/views/system/audit/index.vue'
import Parameter from '@/views/system/parameter/index.vue'
import Permission from '@/views/system/permission/index.vue'
import Tenant from '@/views/system/tenant/Tenant.vue'
import TenantAccess from '@/views/system/tenant-access/TenantAccess.vue'
import TenantUsage from '@/views/system/tenant-usage/TenantUsage.vue'
import User from '@/views/system/user/User.vue'
import MyWorkspaces from '@/views/account/workspaces/MyWorkspaces.vue'
import Page401 from '@/views/error/index.vue'
import ChatPreview from '@/views/chat/preview.vue'

import { i18n } from '@/i18n'
import { watchRouter } from './watch'

const t = i18n.global.t
export const routes = [
  {
    path: '/',
    redirect: '/chat',
  },
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
        props: (route: any) => {
          return { startChatDsId: route.query.start_chat }
        },
        meta: { title: t('menu.Data Q&A'), iconActive: 'chat', iconDeActive: 'noChat' },
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
    path: '/dashboard',
    component: LayoutDsl,
    redirect: '/dashboard/index',
    children: [
      {
        path: 'index',
        name: 'dashboard',
        component: Dashboard,
        meta: {
          title: t('dashboard.dashboard'),
          iconActive: 'dashboard',
          iconDeActive: 'noDashboard',
        },
      },
    ],
  },
  {
    path: '/access',
    component: LayoutDsl,
    redirect: '/access/index',
    children: [
      {
        path: 'index',
        name: 'access',
        component: Access,
        meta: {
          title: t('access.my_permissions'),
          iconActive: 'user',
          iconDeActive: 'noUser',
        },
      },
    ],
  },
  {
    path: '/account',
    component: LayoutDsl,
    redirect: '/account/workspaces',
    children: [
      {
        path: 'workspaces',
        name: 'my-workspaces',
        component: MyWorkspaces,
        meta: {
          title: t('tenant.my_workspaces'),
          iconActive: 'user',
          iconDeActive: 'noUser',
        },
      },
    ],
  },
  {
    path: '/custom-agent',
    component: LayoutDsl,
    redirect: '/custom-agent/index',
    children: [
      {
        path: 'index',
        name: 'custom-agent',
        component: CustomAgent,
        meta: {
          title: t('access.custom_agents'),
          iconActive: 'embedded',
          iconDeActive: 'noEmbedded',
        },
      },
    ],
  },
  {
    path: '/dashboard-store',
    component: LayoutDsl,
    redirect: '/dashboard-store/index',
    children: [
      {
        path: 'index',
        name: 'dashboard-store',
        component: DashboardStore,
        meta: {
          title: t('dashboard.store'),
          iconActive: 'dashboardStore',
          iconDeActive: 'noDashboardStore',
        },
      },
    ],
  },
  {
    path: '/set/permission',
    redirect: '/system/setting/permission',
    hidden: true,
  },
  {
    path: '/set/appearance',
    redirect: '/system/setting/permission',
    hidden: true,
  },
  {
    path: '/system/setting/appearance',
    redirect: '/system/setting/permission',
    hidden: true,
  },
  {
    path: '/set/professional',
    redirect: '/system/setting/professional',
    hidden: true,
  },
  {
    path: '/set/training',
    redirect: '/system/setting/training',
    hidden: true,
  },
  {
    path: '/set/prompt',
    redirect: '/system/setting/prompt',
    hidden: true,
  },
  {
    path: '/set',
    redirect: '/system/setting/permission',
    hidden: true,
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
  {
    path: '/system',
    name: 'system',
    component: LayoutDsl,
    redirect: '/system/user',
    meta: { hidden: true },
    children: [
      {
        path: 'user',
        name: 'user',
        component: User,
        meta: { title: t('user.user_management'), iconActive: 'user', iconDeActive: 'noUser' },
      },
      {
        path: 'member-access',
        name: 'member-access',
        component: TenantAccess,
        meta: { title: t('tenant.member_access'), iconActive: 'user', iconDeActive: 'noUser' },
      },
      {
        path: 'tenant',
        name: 'tenant',
        component: Tenant,
        meta: {
          title: t('tenant.management'),
          iconActive: 'user',
          iconDeActive: 'noUser',
          platformOnly: true,
        },
      },
      {
        path: 'usage',
        name: 'tenant-usage',
        component: TenantUsage,
        meta: { title: t('tenant_usage.title'), iconActive: 'log', iconDeActive: 'noLog' },
      },
      {
        path: 'project',
        name: 'project',
        component: Datasource,
        meta: { title: t('ds.title'), iconActive: 'ds', iconDeActive: 'noDs' },
      },
      {
        path: 'model',
        name: 'model',
        component: Model,
        meta: {
          title: t('model.ai_model_configuration'),
          iconActive: 'model',
          iconDeActive: 'noModel',
          platformOnly: true,
        },
      },
      {
        path: 'embedded',
        name: 'embedded',
        component: SystemEmbedded,
        meta: {
          title: t('embedded.embedded_management'),
          iconActive: 'embedded',
          iconDeActive: 'noEmbedded',
        },
      },
      {
        path: 'setting',
        meta: { title: t('system.system_settings'), iconActive: 'set', iconDeActive: 'noSet' },
        redirect: '/system/setting/permission',
        name: 'setting',
        children: [
          {
            path: 'permission',
            name: 'permission',
            component: Permission,
            meta: { title: t('project.permission_configuration') },
          },
          {
            path: 'professional',
            name: 'professional',
            component: Professional,
            meta: { title: t('professional.professional_terminology') },
          },
          {
            path: 'training',
            name: 'training',
            component: Training,
            meta: { title: t('training.data_training') },
          },
          {
            path: 'prompt',
            name: 'prompt',
            component: Prompt,
            meta: { title: t('prompt.customize_prompt_words') },
          },
          {
            path: 'parameter',
            name: 'parameter',
            component: Parameter,
            meta: { title: t('parameter.parameter_configuration'), platformOnly: true },
          },
          {
            path: 'variables',
            name: 'variables',
            component: Variables,
            meta: { title: t('variables.system_variables'), platformOnly: true },
          },
        ],
      },
      {
        path: 'audit',
        name: 'audit',
        component: Audit,
        meta: { title: t('audit.system_log'), iconActive: 'log', iconDeActive: 'noLog' },
      },
    ],
  },

  {
    path: '/assistant',
    name: 'assistant',
    component: assistant,
  },
  {
    path: '/embeddedPage',
    name: 'embeddedPage',
    component: EmbeddedPage,
  },
  {
    path: '/embeddedCommon',
    name: 'embeddedCommon',
    component: EmbeddedCommon,
  },
  {
    path: '/assistantTest',
    name: 'assistantTest',
    component: assistantTest,
  },
  {
    path: '/chatPreview',
    name: 'chatPreview',
    component: ChatPreview,
  },
  {
    path: '/admin-login',
    name: 'admin-login',
    component: login,
  },
  {
    path: '/401',
    name: '401',
    hidden: true,
    meta: {},
    component: Page401,
  },
]
const router = createRouter({
  history: createWebHashHistory(),
  routes,
})
watchRouter(router)
export default router
