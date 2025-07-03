<script lang="ts" setup>
import { ref } from 'vue'
import Default_avatar from '@/assets/svg/icon-member-default.svg'
import icon_admin_outlined from '@/assets/svg/icon_admin_outlined.svg'
import icon_maybe_outlined from '@/assets/svg/icon-maybe_outlined.svg'
import icon_key_outlined from '@/assets/svg/icon-key_outlined.svg'
import icon_translate_outlined from '@/assets/svg/icon_translate_outlined.svg'
import icon_logout_outlined from '@/assets/svg/icon_logout_outlined.svg'
import icon_right_outlined from '@/assets/svg/icon_right_outlined.svg'
import icon_done_outlined from '@/assets/svg/icon_done_outlined.svg'

defineProps({
  collapse: { type: [Boolean], required: true },
})

const name = ref('飞小致')
const currentLanguage = ref('zh-CN')
const emit = defineEmits(['selectPerson'])
const languageList = [
  {
    name: 'English',
    value: 'en',
  },
  {
    name: '简体中文',
    value: 'zh-CN',
  },
  {
    name: '繁體中文',
    value: 'zh-CN',
  },
]
const handlePersonChange = () => {
  emit('selectPerson')
}

const handleDefaultLanguageChange = (item: any) => {
  currentLanguage.value = item.value
}
</script>

<template>
  <el-popover popper-class="system-person" :placement="collapse ? 'right' : 'top'">
    <template #reference>
      <button class="person" :class="collapse && 'collapse'">
        <el-icon size="32" class="default-avatar">
          <Default_avatar></Default_avatar>
        </el-icon>
        <span v-if="!collapse" class="name">{{ name }}</span>
      </button></template
    >
    <div class="popover">
      <div class="popover-content">
        <div class="info">
          <el-icon style="transform: scale(1.25)" size="32">
            <Default_avatar></Default_avatar>
          </el-icon>
          <div class="top">{{ name }}</div>
          <div class="bottom">feixaozhi</div>
        </div>
        <div class="popover-item" @click="handlePersonChange">
          <el-icon size="16">
            <icon_admin_outlined></icon_admin_outlined>
          </el-icon>
          <div class="datasource-name">系统管理</div>
        </div>
        <div class="popover-item">
          <el-icon size="16">
            <icon_key_outlined></icon_key_outlined>
          </el-icon>
          <div class="datasource-name">修改密码</div>
        </div>
        <el-popover :teleported="false" popper-class="system-language" placement="right">
          <template #reference>
            <div class="popover-item">
              <el-icon size="16">
                <icon_translate_outlined></icon_translate_outlined>
              </el-icon>
              <div class="datasource-name">语言</div>
              <el-icon style="transform: scale(1.33)" class="right" size="16">
                <icon_right_outlined></icon_right_outlined>
              </el-icon>
            </div>
          </template>
          <div class="language-popover">
            <div
              v-for="ele in languageList"
              :key="ele.name"
              class="popover-item_language"
              :class="currentLanguage === ele.value && 'isActive'"
              @click="handleDefaultLanguageChange(ele)"
            >
              <div class="language-name">{{ ele.name }}</div>
              <el-icon size="16" class="done">
                <icon_done_outlined></icon_done_outlined>
              </el-icon>
            </div>
          </div>
        </el-popover>

        <div class="popover-item">
          <el-icon size="16">
            <icon_maybe_outlined></icon_maybe_outlined>
          </el-icon>
          <div class="datasource-name">帮助</div>
        </div>
        <div class="popover-item mr4">
          <el-icon size="16">
            <icon_logout_outlined></icon_logout_outlined>
          </el-icon>
          <div class="datasource-name">退出登录</div>
        </div>
      </div>
    </div>
  </el-popover>
</template>

<style lang="less" scoped>
.person {
  border-radius: 6px;
  padding: 0 8px;
  display: flex;
  align-items: center;
  cursor: pointer;
  width: 156px;
  height: 40px;
  border: none;
  background-color: transparent;

  &.collapse {
    width: 40px;
  }

  .name {
    font-weight: 400;
    font-size: 14px;
    line-height: 22px;
    margin-left: 8px;
  }

  &:hover,
  &:active {
    background: #1f23291a;
    border: 1px solid #1f23291a;
  }

  &:active {
    background: #1f232926;
    border: 1px solid #1f23291a;
  }
}
</style>

<style lang="less">
.system-person.system-person {
  padding: 0;
  width: 200px !important;
  box-shadow: 0px 4px 8px 0px #1f23291a;
  border: 1px solid #dee0e3;
  position: relative;

  &::after {
    content: '';
    position: absolute;
    bottom: 40px;
    left: 0;
    height: 1px;
    width: 100%;
    background: #dee0e3;
  }

  &::before {
    content: '';
    position: absolute;
    top: 62px;
    left: 0;
    height: 1px;
    width: 100%;
    background: #dee0e3;
  }

  .popover {
    .info {
      height: 62px;
      padding: 8px;

      .ed-icon {
        margin: 6px 8px 0 7px;
        float: left;
      }

      .top {
        float: left;
        font-weight: 500;
        font-size: 16px;
        line-height: 24px;
        width: calc(100% - 60px);
      }

      .bottom {
        float: left;
        font-weight: 400;
        font-size: 14px;
        line-height: 22px;
        width: calc(100% - 60px);
      }
    }
    .popover-item {
      height: 32px;
      display: flex;
      align-items: center;
      padding-left: 12px;
      padding-right: 8px;
      position: relative;
      cursor: pointer;
      .datasource-name {
        margin-left: 8px;
      }

      &.mr4 {
        margin: 4px 0;
      }

      .right {
        margin-left: auto;
      }
    }
  }
}

.system-language.system-language {
  padding: 4px 4px 2px 4px;
  width: 240px !important;
  box-shadow: 0px 4px 8px 0px #1f23291a;
  border: 1px solid #dee0e3;

  .language-popover {
    .popover-item_language {
      height: 32px;
      display: flex;
      align-items: center;
      padding-left: 8px;
      padding-right: 8px;
      margin-bottom: 2px;
      position: relative;
      border-radius: 4px;
      cursor: pointer;
      &:not(.empty):hover {
        background: #1f23291a;
      }

      .language-name {
        margin-left: 8px;
        font-weight: 400;
        font-size: 14px;
        line-height: 22px;
        margin-bottom: 2px;
      }

      .done {
        margin-left: auto;
        display: none;
      }

      &.isActive {
        color: var(--ed-color-primary);

        .done {
          display: block;
        }
      }
    }
  }
}
</style>
