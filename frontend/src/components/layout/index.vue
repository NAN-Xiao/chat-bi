<template>
  <div class="app-container">
    <div class="sidebar">
      <div class="logo">SQLBot</div>

      <div class="workspace-area">
        <el-select
          v-model="workspace"
          placeholder="Select"
          class="workspace-select"
          size="large"
          style="width: 240px"
        >
          <template #label="{ label }">
            <div class="workspace-label">
              <el-icon><folder /></el-icon>
              <span>{{ label }}</span>
            </div>
          </template>
          <el-option
            v-for="item in options"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </el-select>
      </div>
      <el-menu
        :default-active="activeMenu"
        class="menu-container">

        <el-menu-item v-for="item in routerList" :key="item.path" :index="item.path" @click="menuSelect">
          <el-icon v-if="item.meta.icon">
            <component :is="resolveIcon(item.meta.icon)" />
          </el-icon>
          <span>{{ item.meta.title }}</span>
        </el-menu-item>

      </el-menu>
    </div>

    <div class="main-content">
      <div class="header-container">
        <div class="header">
          <h1>{{ currentPageTitle }}</h1>
          <div class="header-actions">
            <el-tooltip content="System manage" placement="bottom">
              <div class="header-icon-btn" @click="toSystem">
                <el-icon><iconsystem /></el-icon>
                <span>System manage</span>
              </div>
            </el-tooltip>
            <el-tooltip content="Help" placement="bottom">
              <div class="header-icon-btn">
                <el-icon><question-filled /></el-icon>
                <span>Help</span>
              </div>
            </el-tooltip>
            <el-tooltip content="Notice" placement="bottom">
              <div class="header-icon-btn">
                <el-icon><BellFilled /></el-icon>
                <span>Notice</span>
              </div>
            </el-tooltip>
            <el-dropdown trigger="click">
              <div class="user-info">
                <el-avatar size="small">{{ name?.charAt(0) }}</el-avatar>
                <span class="user-name">{{ name }}</span>
              </div>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item @click="logout">Logout</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>
      </div>
      
      <div v-if="sysRouterList.length && showHead" class="sys-setting-container">
        <el-menu
          :default-active="activeMenu"
          class="el-menu-demo"
          mode="horizontal"
        >
          <el-menu-item v-for="item in sysRouterList" :key="item.path" :index="item.path" @click="menuSelect">
            <el-icon v-if="item.meta.icon">
              <component :is="resolveIcon(item.meta.icon)" />
            </el-icon>
            <span>{{ item.meta.title }}</span>
          </el-menu-item>
        </el-menu>
      </div>
      
      <div v-if="sysRouterList.length && showHead" class="sys-page-content">
        <div class="sys-inner-container">
          <router-view />
        </div>
      </div>
      <div v-else class="page-content">
        <router-view />
      </div>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { ref, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useUserStore } from '@/stores/user'
import folder from '@/assets/svg/folder.svg'
import ds from '@/assets/svg/ds.svg'
import dashboard from '@/assets/svg/dashboard.svg'
import chat from '@/assets/svg/chat.svg'
import iconsetting from '@/assets/svg/setting.svg'
import iconsystem from '@/assets/svg/system.svg'
import {
  QuestionFilled,
  BellFilled
} from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const name = ref('admin')
const activeMenu = computed(() => route.path)
const routerList = computed(() => {
  return router.getRoutes().filter(route => {
    return route.path !== '/login' && !route.path.includes('/system') && !route.redirect && route.path !== '/:pathMatch(.*)*'
  })
})

const sysRouterList = computed(() => {
  return router.getRoutes().filter(route => route.path.includes('/system'))
})

const showHead = computed(() => {
  return route.path.includes('/system')
})
const workspace = ref('1')
const options = [
  { value: '1', label: 'Default workspace' },
  { value: '2', label: 'Workspace 2' },
  { value: '3', label: 'Workspace 3' }
]
const currentPageTitle = computed(() => {
  if (route.path.includes('/system')) {
    return 'System Settings'
  }
  return route.meta.title || 'Dashboard'
})
const resolveIcon = (iconName: any) => {
  const icons: Record<string, any> = {
    'ds': ds,
    'dashboard': dashboard,
    'chat': chat,
    'setting': iconsetting
  }
  return typeof icons[iconName] === 'function' ? icons[iconName]() : icons[iconName]
}

const menuSelect = (e: any) => {
  router.push(e.index)
}
const logout = () => {
  userStore.logout()
  router.push('/login')
}
const toSystem = () => {
  router.push('/system')
}
</script>

<style lang="less" scoped>
.app-container {
  display: flex;
  height: 100vh;
  
  .sidebar {
    width: 240px;
    background: #fff;
    border-right: 1px solid #e6e6e6;
    display: flex;
    flex-direction: column;
    .workspace-area {
      margin: 8px 16px;
      overflow: hidden;
      .workspace-select {
        width: 100% !important;
        :deep(.el-select__wrapper) {
          border-radius: 10px;
          box-shadow: none !important;
          background-color: #f1f3f4;
          line-height: 32px;
          min-height: 48px;
          .el-select__selected-item {
            height: 32px;
          }
          .workspace-label {
            color: #2d2e31;
            font-weight: 600;
            display: flex;
            column-gap: 8px;
            align-items: center;
            height: 32px;
          }
        }
      }
    }
    .logo {
      height: 68px;
      line-height: 68px;
      font-size: 24px;
      font-weight: bold;
      color: #4285f4;
      text-align: left;
      margin-left: 24px;
    }

    .menu-container {
      flex: 1;
      border-right: none;
    }
  }

  .main-content {
    flex: 1;
    display: flex;
    flex-direction: column;
    background-color: #f5f7fa;
    padding: 24px;
    box-sizing: border-box;
    .header-container {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      height: 60px;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
      .header {
        height: 36px;
        line-height: 36px;
        color: #202124;
        h1 {
          font-size: 24px;
          font-weight: 500;
          height: 36px;
          line-height: 36px;
        }
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 24px;
        .header-actions {
          display: flex;
          height: 36px;
          align-items: center;
          .header-icon-btn {
            display: flex;
            column-gap: 12px;
            align-items: center;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
            border: none;
            font-weight: 500;
            transition: all 0.3s;
            font-size: 14px;
            color: #5f6368;
            &:hover {
              background-color: rgba(0, 0, 0, 0.05);
            }
          }
          :deep(.user-info) {
            display: flex;
            column-gap: 4px;
            align-items: center;
            .el-avatar {
              background-color: #4285f4;
              color: #fff;
            }
            .user-name {
              font-size: 14px;
              font-weight: 500;
              color: #202124;
            }
          }
        }
      }
    }
    

    .page-content {
      flex: 1;
      overflow-y: auto;
    }
    .sys-page-content {
      background-color: var(--white);
      border-radius: var(--border-radius);
      padding: 24px;
      box-shadow: var(--shadow);
      margin-top: 24px;
      .sys-inner-container {
        background: #fff;
        border-radius: 8px;
        padding: 20px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
      }
    }
    .sys-setting-container {
      overflow: hidden;
      border-radius: 8px;
    }
  }
}
</style>