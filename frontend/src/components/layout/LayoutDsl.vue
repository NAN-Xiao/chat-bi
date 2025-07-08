<script lang="ts" setup>
import { ref, computed } from 'vue'
import Menu from './Menu.vue'
import Workspace from './Workspace.vue'
import Person from './Person.vue'
import LOGO from '@/assets/LOGO.svg'
import LOGO_fold from '@/assets/LOGO-fold.svg'
import icon_moments_categories_outlined from '@/assets/svg/icon_moments-categories_outlined.svg'
import icon_side_fold_outlined from '@/assets/svg/icon_side-fold_outlined.svg'
import icon_side_expand_outlined from '@/assets/svg/icon_side-expand_outlined.svg'
import { useRoute, useRouter } from 'vue-router'
const router = useRouter()
const collapse = ref(false)
const handleFoldExpand = () => {
  collapse.value = !collapse.value
}
const toWorkspace = () => {
  router.push('/')
}
const route = useRoute()
const showSysmenu = computed(() => {
  return route.path.includes('/system')
})
</script>

<template>
  <div class="system-layout">
    <div class="left-side" :class="collapse && 'left-side-collapse'">
      <LOGO_fold v-if="collapse" style="margin: 0 0 6px 5px"></LOGO_fold>
      <LOGO v-else style="margin-bottom: 6px"></LOGO>
      <Workspace v-if="!showSysmenu" :collapse="collapse"></Workspace>
      <Menu :collapse="collapse"></Menu>
      <div class="bottom">
        <div v-if="showSysmenu" class="back-to_workspace" @click="toWorkspace">
          <el-icon size="16">
            <icon_moments_categories_outlined></icon_moments_categories_outlined>
          </el-icon>
          {{ collapse ? '' : '返回工作空间' }}
        </div>
        <div class="personal-info">
          <Person :collapse="collapse"></Person>
          <el-icon size="20" class="fold" @click="handleFoldExpand">
            <icon_side_expand_outlined v-if="collapse"></icon_side_expand_outlined>
            <icon_side_fold_outlined v-else></icon_side_fold_outlined>
          </el-icon>
        </div>
      </div>
    </div>
    <div class="right-main">
      <div class="content">
        <router-view />
      </div>
    </div>
  </div>
</template>

<style lang="less" scoped>
.system-layout {
  width: 100vw;
  height: 100vh;
  background-color: #f1f4f3;
  display: flex;

  @keyframes rotate {
    0% {
      width: 240px;
    }
    100% {
      width: 64px;
    }
  }

  .left-side {
    width: 240px;
    height: 100%;
    padding: 16px;
    position: relative;

    .bottom {
      position: absolute;
      bottom: 20px;
      left: 16px;
      font-weight: 400;
      font-size: 14px;
      line-height: 22px;
      width: calc(100% - 32px);
      .back-to_workspace {
        background-color: #1f23290a;
        border: 1px solid #d0d3d6;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: 6px;
        height: 40px;
        cursor: pointer;
        &:hover {
          background-color: #1f23291a;
        }
        &:active {
          background-color: #1f232926;
        }
        .ed-icon {
          margin-right: 4.95px;
        }
      }

      .personal-info {
        display: flex;
        align-items: center;
        margin-top: 16px;

        .fold {
          cursor: pointer;
          margin-left: auto;
        }
      }
    }

    &.left-side-collapse {
      width: 64px;
      padding: 16px 12px;
      animation: rotate 1s ease-in-out;

      .ed-menu--collapse {
        --ed-menu-icon-width: 32px;
        width: 40px;
      }

      .bottom {
        left: 12px;
        width: calc(100% - 24px);
        .ed-icon {
          margin-right: 0;
        }
      }

      .personal-info {
        flex-wrap: wrap;

        .default-avatar {
          margin: 0 0 26px 4px;
        }

        .fold {
          margin: 0 auto;
        }
      }
    }
  }

  .right-main {
    flex: 1;
    padding: 8px 8px 8px 0;
    max-height: 100vh;

    .content {
      width: 100%;
      height: 100%;
      padding: 16px 24px;
      box-shadow: 0px 2px 4px 0px #1f23291f;
      background-color: #fff;
      border-radius: 12px;

      &:has(.no-padding) {
        padding: 0;
      }
    }
  }
}
</style>
