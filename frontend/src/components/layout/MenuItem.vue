<script lang="ts">
import { h } from 'vue'
import { ElMenuItem, ElSubMenu, ElIcon } from 'element-plus-secondary'

import model from '@/assets/svg/icon_dataset_filled.svg'

const iconMap = {
  icon_ai: model,
} as { [key: string]: any }

const titleWithIcon = (props: any) => {
  const { title, icon } = props.menu?.meta || {}
  return [
    h(ElIcon, null, { default: () => h(iconMap[icon]) }),
    h('span', null, { default: () => title }),
  ]
}

const MenuItem = (props: any) => {
  const { children, hidden, path } = props.menu
  if (hidden) {
    return null
  }
  if (children?.length) {
    return h(
      ElSubMenu,
      { index: path },
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
    { index: path },
    {
      title: h('span', null, { default: () => title }),
      default: h(iconCom, null, {
        default: () => h(iconMap[icon]),
      }),
    }
  )
}
export default MenuItem
</script>
