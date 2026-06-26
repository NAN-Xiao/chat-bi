<script lang="ts" setup>
import icon_more_outlined from '@/assets/svg/icon_more_outlined.svg'
import type { Placement } from 'element-plus-secondary'

export interface Menu {
  svgName?: string
  label?: string
  command: string
  divided?: boolean
  disabled?: boolean
}

withDefaults(
  defineProps<{
    menuList: Menu[]
    placement?: Placement
    offset?: number
    // eslint-disable-next-line vue/require-default-prop
    iconName?: any
    iconSize?: string
    inTable?: boolean
    verticalDots?: boolean
    compactTextOnly?: boolean
    createMenu?: boolean
  }>(),
  {
    placement: 'bottom-end',
    offset: 6,
    iconSize: '16px',
    inTable: false,
    verticalDots: false,
    compactTextOnly: false,
    createMenu: false,
  }
)

const handleCommand = (command: string | number | object) => {
  emit('handleCommand', command)
}

const emit = defineEmits(['handleCommand'])
</script>

<template>
  <el-dropdown
    :popper-class="
      createMenu
        ? 'menu-more_popper menu-more_popper-create'
        : compactTextOnly
          ? 'menu-more_popper menu-more_popper-compact-text'
          : 'menu-more_popper'
    "
    :placement="placement"
    :offset="offset"
    :persistent="false"
    trigger="click"
    @command="handleCommand"
  >
    <el-icon
      class="hover-icon"
      :class="[inTable && 'hover-icon-in-table', verticalDots && 'hover-icon-vertical-dots']"
      @click.stop
    >
      <span v-if="verticalDots" class="vertical-dots" aria-hidden="true">
        <span></span>
        <span></span>
        <span></span>
      </span>
      <component v-else :is="iconName || icon_more_outlined" class="svg-icon"></component>
    </el-icon>
    <template #dropdown>
      <el-dropdown-menu :persistent="false">
        <template v-for="ele in menuList" :key="ele">
          <el-dropdown-item :divided="ele.divided" :command="ele.command" :disabled="ele.disabled">
            <el-icon
              v-if="ele.svgName && !compactTextOnly"
              class="handle-icon"
              :style="{ fontSize: iconSize }"
            >
              <component :is="ele.svgName"></component>
            </el-icon>
            {{ ele.label }}
          </el-dropdown-item>
        </template>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<style lang="less">
.hover-icon-vertical-dots {
  .vertical-dots {
    width: 6px;
    height: 18px;
    display: inline-flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 2px;
  }

  .vertical-dots span {
    width: 3px;
    height: 3px;
    border-radius: 50%;
    background: currentColor;
  }
}

.menu-more_popper {
  box-shadow: 0px 4px 8px 0px #1f23291a !important;
  border-radius: 6px;
  border: 1px solid #dee0e3 !important;
  width: max-content !important;
  min-width: 120px !important;
  max-width: min(280px, calc(100vw - 24px)) !important;
  padding: 0 !important;

  .ed-dropdown-menu {
    min-width: 120px;
    padding: 4px;
  }

  .handle-icon {
    flex: 0 0 auto;
    color: #646a73;
    margin-right: 8px;
  }

  .ed-dropdown-menu__item--divided {
    margin: 4px 0;
  }

  .ed-dropdown-menu__item {
    position: relative;
    display: flex;
    align-items: center;
    min-width: 120px;
    min-height: 36px;
    max-width: min(280px, calc(100vw - 24px));
    padding: 0 12px;
    background: none;
    color: #1f2329;
    line-height: 20px;
    white-space: nowrap;
    &:focus {
      background: none;
      color: #1f2329;
    }
    &:hover {
      background: none;
      color: #1f2329;

      &::after {
        content: '';
        width: calc(100% - 8px);
        height: 32px;
        border-radius: 6px;
        position: absolute;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        background: #1f23291a;
      }
    }
  }
}

.menu-more_popper-compact-text {
  min-width: 92px !important;

  .ed-dropdown-menu {
    min-width: 92px;
    padding: 2px;
  }

  .ed-dropdown-menu__item {
    min-width: 92px;
    min-height: 28px;
    padding: 0 10px;
    font-size: 13px;
    line-height: 18px;
  }

  .ed-dropdown-menu__item:hover::after {
    width: calc(100% - 4px);
    height: 24px;
  }
}

.menu-more_popper-create {
  min-width: 88px !important;

  .ed-dropdown-menu {
    min-width: 88px;
    padding: 4px;
  }

  .ed-dropdown-menu__item {
    min-width: 80px;
    min-height: 36px;
    padding: 0 10px;
    font-size: 13px;
    line-height: 20px;
  }

  .handle-icon {
    margin-right: 8px;
    color: #646a73;
  }

  .ed-dropdown-menu__item:hover::after {
    width: calc(100% - 8px);
    height: 32px;
  }
}
</style>
