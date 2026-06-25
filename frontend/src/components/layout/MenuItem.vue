<script lang="ts">
import { h, defineComponent, onBeforeUnmount, ref } from 'vue'
import { ElMenuItem, ElSubMenu, ElIcon } from 'element-plus-secondary'
import { useRouter, useRoute } from 'vue-router'
import { emitWorkspaceContextChange, useEmitt } from '@/utils/useEmitt'
import { useUserStore } from '@/stores/user'
import { useDatasourceContextStore } from '@/stores/datasourceContext'
import { dashboardStoreWithOut } from '@/stores/dashboard/dashboard'
import { resolveBusinessDashboardLandingTarget } from '@/utils/dashboardLanding'
import { resolveManagementHome } from '@/utils/navigation'
import { rememberBusinessTenantBeforeAdmin } from '@/utils/workspaceAdminContext'

type IconNode = {
  tag: 'path' | 'circle' | 'rect' | 'ellipse' | 'polyline' | 'line'
  attrs: Record<string, any>
}

const iconNameMap: Record<string, string> = {
  chat: 'chat',
  noChat: 'chat',
  dashboard: 'dashboard',
  noDashboard: 'dashboard',
  overview: 'overview',
  noOverview: 'overview',
  ds: 'database',
  noDs: 'database',
  model: 'dataset',
  noModel: 'dataset',
  embedded: 'embedded',
  noEmbedded: 'embedded',
  user: 'user',
  noUser: 'user',
  users: 'users',
  noUsers: 'users',
  member: 'member',
  noMember: 'member',
  workspace: 'workspace',
  noWorkspace: 'workspace',
  set: 'settings',
  noSet: 'settings',
  permission: 'permission',
  noPermission: 'permission',
  log: 'log',
  noLog: 'log',
  usage: 'usage',
  noUsage: 'usage',
  terminology: 'terminology',
  noTerminology: 'terminology',
  knowledge: 'knowledge',
  noKnowledge: 'knowledge',
  sql: 'sql',
  noSql: 'sql',
  agent: 'agent',
  noAgent: 'agent',
  parameter: 'parameter',
  noParameter: 'parameter',
  variables: 'variables',
  noVariables: 'variables',
  dashboardStore: 'sharedDashboard',
  noDashboardStore: 'sharedDashboard',
}

const iconSpec: Record<string, IconNode[]> = {
  chat: [
    { tag: 'path', attrs: { d: 'M4 5.8A2.8 2.8 0 0 1 6.8 3h4.4A2.8 2.8 0 0 1 14 5.8v2.9a2.8 2.8 0 0 1-2.8 2.8H8.1L4.6 14v-2.7A2.8 2.8 0 0 1 4 8.7V5.8Z' } },
    { tag: 'line', attrs: { x1: 6.5, y1: 7.1, x2: 11.5, y2: 7.1 } },
    { tag: 'line', attrs: { x1: 6.5, y1: 9.4, x2: 9.5, y2: 9.4 } },
  ],
  dashboard: [
    { tag: 'rect', attrs: { x: 3.2, y: 3.2, width: 4.2, height: 4.2, rx: 1 } },
    { tag: 'rect', attrs: { x: 10.6, y: 3.2, width: 4.2, height: 4.2, rx: 1 } },
    { tag: 'rect', attrs: { x: 3.2, y: 10.6, width: 4.2, height: 4.2, rx: 1 } },
    { tag: 'path', attrs: { d: 'M10.6 11.2h4.2M10.6 13.5h3.1' } },
  ],
  overview: [
    { tag: 'path', attrs: { d: 'M3.2 14.2h11.6M4.2 12.5V6.8' } },
    { tag: 'path', attrs: { d: 'm5.2 10.8 2.4-2.5 2 1.7 3.3-4.1' } },
    { tag: 'circle', attrs: { cx: 5.2, cy: 10.8, r: 0.6 } },
    { tag: 'circle', attrs: { cx: 7.6, cy: 8.3, r: 0.6 } },
    { tag: 'circle', attrs: { cx: 12.9, cy: 5.9, r: 0.6 } },
  ],
  database: [
    { tag: 'ellipse', attrs: { cx: 9, cy: 4.5, rx: 5.2, ry: 2 } },
    { tag: 'path', attrs: { d: 'M3.8 4.5v4.4c0 1.1 2.3 2 5.2 2s5.2-.9 5.2-2V4.5M3.8 8.9v4.1c0 1.1 2.3 2 5.2 2s5.2-.9 5.2-2V8.9' } },
  ],
  dataset: [
    { tag: 'path', attrs: { d: 'M3.5 5.4 9 2.9l5.5 2.5L9 7.9 3.5 5.4ZM3.5 9 9 11.5 14.5 9M3.5 12.6 9 15.1l5.5-2.5' } },
  ],
  embedded: [
    { tag: 'rect', attrs: { x: 3, y: 4, width: 12, height: 10, rx: 1.6 } },
    { tag: 'path', attrs: { d: 'm7.4 7.1-2 1.9 2 1.9M10.6 7.1l2 1.9-2 1.9' } },
  ],
  user: [
    { tag: 'circle', attrs: { cx: 9, cy: 6.2, r: 2.6 } },
    { tag: 'path', attrs: { d: 'M4.2 14.5c.7-2.4 2.4-3.6 4.8-3.6s4.1 1.2 4.8 3.6' } },
  ],
  users: [
    { tag: 'circle', attrs: { cx: 7.2, cy: 6.1, r: 2.1 } },
    { tag: 'path', attrs: { d: 'M3.8 14.2c.6-2 1.8-3 3.4-3s2.9 1 3.5 3' } },
    { tag: 'circle', attrs: { cx: 12.2, cy: 6.5, r: 1.7 } },
    { tag: 'path', attrs: { d: 'M11.2 11.2c1.5.1 2.5 1.1 3 3' } },
  ],
  member: [
    { tag: 'circle', attrs: { cx: 8.1, cy: 6.1, r: 2.3 } },
    { tag: 'path', attrs: { d: 'M3.9 14.4c.7-2.3 2.1-3.4 4.2-3.4 1.2 0 2.2.4 3 1.1' } },
    { tag: 'path', attrs: { d: 'm11.1 14.1 1.3 1.2 2.5-3.1' } },
  ],
  workspace: [
    { tag: 'rect', attrs: { x: 4, y: 3.2, width: 10, height: 11.6, rx: 1.4 } },
    { tag: 'path', attrs: { d: 'M6.5 6h1.4M10.1 6h1.4M6.5 8.7h1.4M10.1 8.7h1.4M6.5 11.4h1.4M10.1 14.8v-3.2h1.8v3.2' } },
  ],
  settings: [
    { tag: 'circle', attrs: { cx: 9, cy: 9, r: 2.1 } },
    { tag: 'path', attrs: { d: 'M9 2.8v2M9 13.2v2M4.6 4.6 6 6M12 12l1.4 1.4M2.8 9h2M13.2 9h2M4.6 13.4 6 12M12 6l1.4-1.4' } },
  ],
  permission: [
    { tag: 'path', attrs: { d: 'M9 2.8 14 5v3.4c0 3.2-2 5.5-5 6.8-3-1.3-5-3.6-5-6.8V5l5-2.2Z' } },
    { tag: 'path', attrs: { d: 'm6.8 8.9 1.4 1.4 3-3.2' } },
  ],
  log: [
    { tag: 'rect', attrs: { x: 4.2, y: 3, width: 9.6, height: 12, rx: 1.5 } },
    { tag: 'path', attrs: { d: 'M6.8 6.2h4.4M6.8 9h4.4M6.8 11.8h2.8' } },
  ],
  usage: [
    { tag: 'rect', attrs: { x: 3.3, y: 4.2, width: 11.4, height: 9.6, rx: 1.5 } },
    { tag: 'path', attrs: { d: 'M4.9 9.6h2l1-3 2.1 5.1 1.2-2.1h2' } },
  ],
  terminology: [
    { tag: 'path', attrs: { d: 'M4.2 3.8h7.2a2.4 2.4 0 0 1 2.4 2.4v8.1H6.1a1.9 1.9 0 0 1-1.9-1.9V3.8Z' } },
    { tag: 'path', attrs: { d: 'M4.2 12.4a1.9 1.9 0 0 1 1.9-1.9h7.7M6.7 6.3h4.1M6.7 8.5h3.2' } },
  ],
  knowledge: [
    { tag: 'path', attrs: { d: 'M4 3.8h6.8a2.6 2.6 0 0 1 2.6 2.6v8H6.2A2.2 2.2 0 0 1 4 12.2V3.8Z' } },
    { tag: 'path', attrs: { d: 'M4 12.2A2.2 2.2 0 0 1 6.2 10h7.2M6.7 6.3h4M6.7 8.3h3.1' } },
    { tag: 'path', attrs: { d: 'M12.4 3.8v5l-1.3-.8-1.3.8V3.8' } },
  ],
  sql: [
    { tag: 'rect', attrs: { x: 3.1, y: 4, width: 11.8, height: 10, rx: 1.6 } },
    { tag: 'path', attrs: { d: 'm6.7 7.2-2 1.8 2 1.8M11.3 7.2l2 1.8-2 1.8M8.2 12.4l1.6-6.8' } },
  ],
  agent: [
    { tag: 'circle', attrs: { cx: 9, cy: 5.2, r: 2 } },
    { tag: 'circle', attrs: { cx: 5.2, cy: 12.4, r: 1.7 } },
    { tag: 'circle', attrs: { cx: 12.8, cy: 12.4, r: 1.7 } },
    { tag: 'path', attrs: { d: 'M8.1 7 6 10.9M9.9 7l2.1 3.9M6.9 12.4h4.2' } },
  ],
  parameter: [
    { tag: 'path', attrs: { d: 'M3.5 5.2h4.1M10.4 5.2h4.1M3.5 9h7.4M13.7 9h.8M3.5 12.8h1.9M8.2 12.8h6.3' } },
    { tag: 'circle', attrs: { cx: 9, cy: 5.2, r: 1.4 } },
    { tag: 'circle', attrs: { cx: 12.3, cy: 9, r: 1.4 } },
    { tag: 'circle', attrs: { cx: 6.8, cy: 12.8, r: 1.4 } },
  ],
  variables: [
    { tag: 'path', attrs: { d: 'M6.4 4.1c-1.2.4-1.8 1.2-1.8 2.5v1.3c0 .7-.4 1.1-1.2 1.1.8 0 1.2.4 1.2 1.1v1.3c0 1.3.6 2.1 1.8 2.5M11.6 4.1c1.2.4 1.8 1.2 1.8 2.5v1.3c0 .7.4 1.1 1.2 1.1-.8 0-1.2.4-1.2 1.1v1.3c0 1.3-.6 2.1-1.8 2.5M7.8 11.8l2.4-5.6' } },
  ],
  store: [
    { tag: 'path', attrs: { d: 'M3.4 6.2 9 3.1l5.6 3.1L9 9.3 3.4 6.2Z' } },
    { tag: 'path', attrs: { d: 'm4.1 9.6 4.9 2.8 4.9-2.8M4.1 12.9 9 15.7l4.9-2.8' } },
  ],
  sharedDashboard: [
    { tag: 'rect', attrs: { x: 3.1, y: 4.2, width: 8.6, height: 9.6, rx: 1.4 } },
    { tag: 'path', attrs: { d: 'M5.4 6.8h3.9M5.4 9.1h2.6M5.4 11.4h3.4' } },
    { tag: 'path', attrs: { d: 'M10.7 3.8h3.6v3.6M8.8 9.3l5.2-5.2' } },
  ],
}

const MenuLineIcon = defineComponent({
  name: 'MenuLineIcon',
  props: {
    name: {
      type: String,
      default: 'chat',
    },
  },
  setup(props) {
    return () =>
      h(
        'svg',
        {
          class: 'zhishu-menu-line-icon',
          width: 18,
          height: 18,
          viewBox: '0 0 18 18',
          fill: 'none',
          stroke: 'currentColor',
          strokeWidth: 1.45,
          strokeLinecap: 'round',
          strokeLinejoin: 'round',
          xmlns: 'http://www.w3.org/2000/svg',
          'aria-hidden': 'true',
        },
        (iconSpec[props.name] || iconSpec.chat).map((node) => h(node.tag, node.attrs))
      )
  },
})

const normalizeIconName = (icon: string) => iconNameMap[icon] || 'chat'

const MenuItem = defineComponent({
  name: 'MenuItem',
  props: {
    menu: {
      type: Object,
      required: true,
    },
    level: {
      type: Number,
      default: 0,
    },
  },
  setup(props) {
    const router = useRouter()
    const route = useRoute()
    const userStore = useUserStore()
    const datasourceContext = useDatasourceContextStore()
    const dashboardStore = dashboardStoreWithOut()
    const analysisAssistantExpanded = ref(false)
    const emitter = useEmitt().emitter
    const updateAnalysisAssistantExpanded = (expanded: unknown) => {
      analysisAssistantExpanded.value = expanded === true
    }
    emitter.on('analysis-assistant-expanded', updateAnalysisAssistantExpanded)
    onBeforeUnmount(() => {
      emitter.off('analysis-assistant-expanded', updateAnalysisAssistantExpanded)
    })
    const titleWithIcon = (props: any) => {
      const { title, icon } = props
      return [
        h(
          ElIcon,
          { size: 18, class: 'menu-line-icon-wrapper' },
          { default: () => h(MenuLineIcon, { name: normalizeIconName(icon) }) }
        ),
        h('span', { class: 'menu-title-text' }, title),
      ]
    }

    const handleMenuClick = async (e: any) => {
      const index = e.index || e.path
      if (e.meta?.action === 'analysis-assistant') {
        useEmitt().emitter.emit('analysis-assistant-toggle')
        router.push(await resolveBusinessDashboardLandingTarget(userStore))
        return
      }
      if (e.meta?.action === 'workspace-admin-entry') {
        await enterWorkspaceAdmin(e.tenant)
        return
      }
      if (index) {
        router.push(e.redirect || index)
      }
    }

    const currentBusinessTenant = () => ({
      id: userStore.getTenantId,
      public_id: userStore.getTenantPublicId,
      name: userStore.getTenantName,
      role: userStore.getTenantRole,
    })

    const enterWorkspaceAdmin = async (tenant?: any) => {
      const tenantId = String(tenant?.id || userStore.getTenantId || '')
      if (!tenantId) return
      rememberBusinessTenantBeforeAdmin(currentBusinessTenant())
      try {
        if (tenantId !== String(userStore.getTenantId || '')) {
          emitWorkspaceContextChange({ tenantId, phase: 'changing' })
          await userStore.switchTenant(tenantId)
          datasourceContext.clear(true)
          await datasourceContext.loadDatasources(true)
          dashboardStore.canvasDataInit()
          useEmitt().emitter.emit('datasource-context-change', null)
          emitWorkspaceContextChange({ tenantId, phase: 'changed' })
        }
        router.push(resolveManagementHome(userStore))
      } catch (error) {
        emitWorkspaceContextChange({ tenantId: userStore.getTenantId, phase: 'changed' })
        throw error
      }
    }

    return () => {
      const { children, hidden, path } = props.menu
      if (hidden) {
        return null
      }

      if (children?.length) {
        const { title, iconDeActive, iconActive } = props.menu?.meta || {}
        const active = props.menu?.meta?.activePrefix
          ? route.path.startsWith(props.menu.meta.activePrefix)
          : route.path.startsWith(path)
        const icon = active ? iconActive : iconDeActive
        return h(
          ElSubMenu,
          { index: path, class: active ? 'is-active' : '' },
          {
            title: () => titleWithIcon({ title, icon }),
            default: () => [
              !props.menu?.meta?.hidePopupTitle
                ? h(MenuItem, { menu: { meta: { title } }, class: 'subTitleMenu' })
                : null,
              children.map((ele: any) => h(MenuItem, { menu: ele, level: props.level + 1 })),
            ],
          }
        )
      }

      const { title, iconDeActive, iconActive } = props.menu?.meta || {}
      const active = props.menu?.meta?.action === 'analysis-assistant'
        ? analysisAssistantExpanded.value
        : props.menu?.meta?.activePrefix
          ? route.path.startsWith(props.menu.meta.activePrefix)
          : route.path === path
      const icon = active ? iconActive : iconDeActive
      const className = `${props.level > 0 ? `menu-level-${props.level}` : ''}${
        active ? ' is-active' : ''
      }`.trim()
      return h(
        ElMenuItem,
        {
          index: path,
          class: className,
          onClick: () => handleMenuClick(props.menu),
        },
        {
          default: () => [
            h(
              ElIcon,
              { size: 18, class: 'menu-line-icon-wrapper' },
              {
                default: () => h(MenuLineIcon, { name: normalizeIconName(icon) }),
              }
            ),
            h('span', { class: 'menu-title-text' }, title),
          ],
        }
      )
    }
  },
})
/* const MenuItem = (props: any) => {
const MenuItem = (props: any) => {
  const router = useRouter()

  const { children, hidden, path } = props.menu
  if (hidden) {
    return null
  }
  if (children?.length) {
    return h(
      ElSubMenu,
      { index: path, onClick: (e: any) => handleMenuClick(e) },
      {
        index: path,
      },
      {
        title: () => titleWithIcon(props),
        default: () => children.map((ele: any) => h(MenuItem, { menu: ele })),
      }
    )
  }
  const { title, icon } = props.menu?.meta || {}
  const iconCom: any = iconMap[icon] ? ElIcon : null
  return h(
    ElMenuItem,
    { index: path, onClick: (e: any) => handleMenuClick(e) },
    {
      index: path,
      onClick: () => {
        router.push(path)
      },
    },
    {
      title: h('span', null, { default: () => title }),
      default: h(iconCom, null, {
        default: () => h(iconMap[icon]),
      }),
    }
  )
} */
export default MenuItem
</script>
