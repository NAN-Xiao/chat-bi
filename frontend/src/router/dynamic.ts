import LayoutDsl from '@/components/layout/LayoutDsl.vue'

import AnalysisAssistantEntry from '@/views/analysis-assistant/Entry.vue'
import { i18n } from '@/i18n'
import type { Router } from 'vue-router'
const t = i18n.global.t

const dynamicRouterList = [
  {
    path: '/as',
    component: LayoutDsl,
    name: 'as-menu',
    redirect: '/as/index',
    children: [
      {
        path: 'index',
        name: 'as',
        component: AnalysisAssistantEntry,
        meta: {
          title: t('embedded.assistant_app'),
          iconActive: 'embedded',
          iconDeActive: 'noEmbedded',
          action: 'analysis-assistant',
        },
      },
    ],
    meta: { title: t('embedded.assistant_app') },
  },
] as any[]

export const generateDynamicRouters = (router: Router) => {
  dynamicRouterList.forEach((item: any) => {
    if (!item.parent) {
      router.addRoute(item)
    } else {
      router.addRoute(item.parent, item)
      const parentRoute: any = router.getRoutes().find((r: any) => r.name === item.parent)
      if (parentRoute?.children) {
        parentRoute.children.push(item)
      }
    }
  })
}
