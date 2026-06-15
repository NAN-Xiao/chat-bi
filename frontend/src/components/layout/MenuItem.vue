<script lang="ts">
import { h, defineComponent } from 'vue'
import { ElMenuItem, ElSubMenu, ElIcon } from 'element-plus-secondary'
import { useRouter, useRoute } from 'vue-router'
import { useEmitt } from '@/utils/useEmitt'

type IconNode = {
  tag: 'path' | 'circle' | 'rect' | 'ellipse' | 'polyline' | 'line'
  attrs: Record<string, any>
}

const iconNameMap: Record<string, string> = {
  chat: 'chat',
  noChat: 'chat',
  dashboard: 'dashboard',
  noDashboard: 'dashboard',
  ds: 'database',
  noDs: 'database',
  model: 'dataset',
  noModel: 'dataset',
  embedded: 'embedded',
  noEmbedded: 'embedded',
  user: 'user',
  noUser: 'user',
  set: 'settings',
  noSet: 'settings',
  log: 'log',
  noLog: 'log',
  dashboardStore: 'store',
  noDashboardStore: 'store',
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
  settings: [
    { tag: 'circle', attrs: { cx: 9, cy: 9, r: 2.1 } },
    { tag: 'path', attrs: { d: 'M9 2.8v2M9 13.2v2M4.6 4.6 6 6M12 12l1.4 1.4M2.8 9h2M13.2 9h2M4.6 13.4 6 12M12 6l1.4-1.4' } },
  ],
  log: [
    { tag: 'rect', attrs: { x: 4.2, y: 3, width: 9.6, height: 12, rx: 1.5 } },
    { tag: 'path', attrs: { d: 'M6.8 6.2h4.4M6.8 9h4.4M6.8 11.8h2.8' } },
  ],
  store: [
    { tag: 'path', attrs: { d: 'M3.4 6.2 9 3.1l5.6 3.1L9 9.3 3.4 6.2Z' } },
    { tag: 'path', attrs: { d: 'm4.1 9.6 4.9 2.8 4.9-2.8M4.1 12.9 9 15.7l4.9-2.8' } },
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
          class: 'sqlbot-menu-line-icon',
          width: 18,
          height: 18,
          viewBox: '0 0 18 18',
          fill: 'none',
          stroke: 'currentColor',
          strokeWidth: 1.55,
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
    const titleWithIcon = (props: any) => {
      const { title, icon } = props
      return [
        h(
          ElIcon,
          { size: 18, class: 'menu-line-icon-wrapper' },
          { default: () => h(MenuLineIcon, { name: normalizeIconName(icon) }) }
        ),
        h('span', null, { default: () => title }),
      ]
    }

    const handleMenuClick = (e: any) => {
      const index = e.index || e.path
      if (e.meta?.action === 'analysis-assistant') {
        useEmitt().emitter.emit('analysis-assistant-toggle')
        return
      }
      if (index) {
        router.push(e.redirect || index)
      }
    }

    return () => {
      const { children, hidden, path } = props.menu
      if (hidden) {
        return null
      }

      if (children?.length) {
        const { title, iconDeActive, iconActive } = props.menu?.meta || {}
        const icon = route.path.startsWith(path) ? iconActive : iconDeActive
        return h(
          ElSubMenu,
          { index: path },
          {
            title: () => titleWithIcon({ title, icon }),
            default: () => [
              h(MenuItem, { menu: { meta: { title } }, class: 'subTitleMenu' }),
              children.map((ele: any) => h(MenuItem, { menu: ele, level: props.level + 1 })),
            ],
          }
        )
      }

      const { title, iconDeActive, iconActive } = props.menu?.meta || {}
      const icon = route.path === path ? iconActive : iconDeActive
      return h(
        ElMenuItem,
        {
          index: path,
          class: props.level > 0 ? `menu-level-${props.level}` : '',
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
            h('span', null, { default: () => title }),
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
