<script lang="ts">
import { h, defineComponent } from 'vue'
import { ElMenuItem, ElSubMenu, ElIcon } from 'element-plus-secondary'
import { useRouter } from 'vue-router'
import user from '@/assets/svg/icon_member_filled.svg'
import workspace from '@/assets/svg/icon_moments-categories_outlined.svg'
import model from '@/assets/svg/icon_dataset_filled.svg'
import ds from '@/assets/svg/ds.svg'
import dashboard from '@/assets/svg/dashboard.svg'
import chat from '@/assets/svg/chat.svg'
import icon_user from '@/assets/svg/icon_user.svg'
const iconMap = {
  icon_ai: model,
  ds,
  dashboard,
  chat,
  user,
  icon_user: icon_user,
  workspace,
} as { [key: string]: any }

const titleWithIcon = (props: any) => {
  const { title, icon } = props.menu?.meta || {}
  return [
    h(ElIcon, null, { default: () => h(iconMap[icon]) }),
    h('span', null, { default: () => title }),
  ]
}
const MenuItem = defineComponent({
  name: 'MenuItem',
  props: {
    menu: {
      type: Object,
      required: true,
    },
  },
  setup(props) {
    const router = useRouter()

    const handleMenuClick = (e: any) => {
      router.push(e.index)
    }

    return () => {
      const { children, hidden, path } = props.menu
      if (hidden) {
        return null
      }

      if (children?.length) {
        return h(
          ElSubMenu,
          { index: path, onClick: (e: any) => handleMenuClick(e) },
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
          default: () => [
            h(iconCom, null, {
              default: () => h(iconMap[icon]),
            }),
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
