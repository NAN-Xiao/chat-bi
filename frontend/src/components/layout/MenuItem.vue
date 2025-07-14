<script lang="ts">
import { h } from 'vue'
import { ElMenuItem, ElSubMenu, ElIcon } from 'element-plus-secondary'
import { useRouter } from 'vue-router'

import model from '@/assets/svg/icon_dataset_filled.svg'
import ds from '@/assets/svg/ds.svg'
import user from '@/assets/svg/icon_member_filled.svg'
import workspace from '@/assets/svg/icon_moments-categories_outlined.svg'

const iconMap = {
  icon_ai: model,
  ds,
  user,
  workspace,
} as { [key: string]: any }

const titleWithIcon = (props: any) => {
  const { title, icon } = props.menu?.meta || {}
  return [
    h(ElIcon, null, { default: () => h(iconMap[icon]) }),
    h('span', null, { default: () => title }),
  ]
}

const MenuItem = (props: any) => {
  const router = useRouter()

  const { children, hidden, path } = props.menu
  if (hidden) {
    return null
  }
  if (children?.length) {
    return h(
      ElSubMenu,
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
}
export default MenuItem
</script>
