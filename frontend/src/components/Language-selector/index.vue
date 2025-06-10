<template>
  <el-dropdown @command="changeLanguage" trigger="hover">
    <div class="lang-switch">
      <span>{{ selectedLanguage === 'zh-CN' ? '中文' : 'English' }}</span>
      <el-icon class="el-icon--right">
        <ArrowDown />
      </el-icon>
    </div>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item command="en" :class="{ 'selected-lang': selectedLanguage === 'en' }">
          English
        </el-dropdown-item>
        <el-dropdown-item command="zh-CN" :class="{ 'selected-lang': selectedLanguage === 'zh-CN' }">
          中文
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useUserStore } from '@/stores/user'
import { ArrowDown } from '@element-plus/icons-vue'
import { userApi } from '@/api/auth'

const { locale } = useI18n()
const userStore = useUserStore()

const selectedLanguage = computed(() => {
  return userStore.language
})

const changeLanguage = (lang: string) => {
  locale.value = lang
  userStore.setLanguage(lang)

  const param = {
    language: lang
  }
  userApi.language(param)
}
</script>

<style scoped lang="less">
.lang-switch {
  display: flex;
  align-items: center;
  cursor: pointer;
  color: var(--el-text-color-primary);
  
  .el-icon--right {
    margin-left: 8px;
    font-size: 12px;
  }
}

.selected-lang {
  color: var(--el-color-primary);
}
</style>