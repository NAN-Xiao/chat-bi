<template>
  <main class="login-container product-login-page">
    <section class="product-login-story">
      <img v-if="storyBg" class="product-login-bg" :src="storyBg" alt="" />
      <div class="product-login-story-main">
        <div class="product-login-brand">
          <div class="product-login-brand-mark">
            <img v-if="loginBg" :src="loginBg" alt="" />
            <el-icon v-else size="24">
              <custom_small v-if="appearanceStore.themeColor !== 'default'"></custom_small>
              <LOGO_fold v-else></LOGO_fold>
            </el-icon>
          </div>
          <div>
            <strong>{{ productName }}</strong>
            <span>智能问数 · 数据分析 · 数据看板洞察</span>
          </div>
        </div>

        <div class="product-login-headline">
          <h1>把数据资产、指标口径和业务问题，变成可追溯的分析答案。</h1>
          <p>{{ productSlogan }}</p>
        </div>

        <div class="product-login-capabilities">
          <div
            v-for="item in capabilities"
            :key="item.title"
            class="product-login-capability"
          >
            <span class="product-login-capability-icon">{{ item.icon }}</span>
            <b>{{ item.title }}</b>
            <span>{{ item.desc }}</span>
          </div>
        </div>
      </div>

      <div class="product-login-status-row">
        <span v-for="item in statusChips" :key="item" class="product-login-status-chip">
          <i class="product-login-dot"></i>
          {{ item }}
        </span>
      </div>
    </section>

    <section class="product-login-wrap">
      <div class="product-login-card">
        <h2>{{ $t('common.login') }}</h2>
        <p class="product-login-desc">
          使用你的账号进入 {{ productName }}，继续查询数据、管理数据看板和分析业务问题。
        </p>
        <div class="login-form">
          <div class="default-login-tabs">
            <el-form
              ref="loginFormRef"
              class="form-content_error product-login-form"
              :model="loginForm"
              :rules="rules"
              label-position="top"
              @keyup.enter="submitForm"
            >
              <el-form-item class="product-login-field" prop="username" label="账号">
                <el-input
                  v-model="loginForm.username"
                  clearable
                  :placeholder="$t('login.input_account')"
                  size="large"
                ></el-input>
              </el-form-item>
              <el-form-item class="product-login-field" prop="password" label="密码">
                <el-input
                  v-model="loginForm.password"
                  :placeholder="$t('common.enter_your_password')"
                  type="password"
                  show-password
                  clearable
                  size="large"
                ></el-input>
              </el-form-item>
              <el-form-item>
                <el-button type="primary" class="product-login-submit" @click="submitForm">{{
                  $t('common.login_')
                }}</el-button>
              </el-form-item>
            </el-form>
          </div>
        </div>
      </div>
    </section>
  </main>
</template>

<script lang="ts" setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useI18n } from 'vue-i18n'
import custom_small from '@/assets/svg/logo-custom_small.svg'
import LOGO_fold from '@/assets/LOGO-fold.svg'
import { useAppearanceStoreWithOut } from '@/stores/appearance'
import { toLoginSuccess } from '@/utils/utils'

const router = useRouter()
const userStore = useUserStore()
const appearanceStore = useAppearanceStoreWithOut()
const { t } = useI18n()
const loginForm = ref({
  username: '',
  password: '',
})
// const isLdap = computed(() => activeName.value == 'ldap')
const storyBg = computed(() => appearanceStore.getBg || '')

const loginBg = computed(() => {
  return appearanceStore.getLogin
})

const productName = computed(() => appearanceStore.name || '星通智数')

const productSlogan = computed(() => {
  if (appearanceStore.getShowSlogan && appearanceStore.slogan) {
    return appearanceStore.slogan
  }
  return '连接数据资产、语义口径与权限体系，帮助团队用自然语言完成查询、洞察和决策。'
})

const capabilities = [
  {
    icon: '问',
    title: '自然语言问数',
    desc: '面向业务问题生成查询、解释结果并保留可追溯上下文。',
  },
  {
    icon: '数',
    title: '多源数据连接',
    desc: '统一管理数据源、表字段和权限，让分析范围清晰可信。',
  },
  {
    icon: '径',
    title: '指标口径沉淀',
    desc: '通过语义层沉淀术语、示例 SQL 和推荐问题。',
  },
  {
    icon: '图',
    title: '图表智能呈现',
    desc: '自动选择合适图表，并支持进一步追问和对比分析。',
  },
  {
    icon: '板',
    title: '数据看板洞察',
    desc: '围绕业务主题组织看板，持续跟踪核心数据变化。',
  },
  {
    icon: '权',
    title: '权限安全控制',
    desc: '按组织、角色和数据源控制访问边界，保护敏感数据。',
  },
]

const statusChips = ['数据连接', '权限校验', '语义层', '图表分析', '数据看板', '安全审计']

const rules = {
  username: [{ required: true, message: t('common.your_account_email_address'), trigger: 'blur' }],
  password: [{ required: true, message: t('common.the_correct_password'), trigger: 'blur' }],
}

const loginFormRef = ref()

const submitForm = () => {
  loginFormRef.value.validate((valid: boolean) => {
    if (valid) {
      userStore.login(loginForm.value).then(() => {
        toLoginSuccess(router)
      })
    }
  })
}
</script>

<style lang="less" scoped>
.login-container {
  width: 100vw;
  min-height: 100vh;
  overflow: auto;
}

.product-login-page {
  display: grid;
  grid-template-columns: minmax(0, 47fr) minmax(520px, 53fr);
  color: var(--theme-text-primary);
  color-scheme: var(--theme-color-scheme, light);
  background:
    linear-gradient(135deg, var(--theme-shell-gradient-a), transparent 34%),
    linear-gradient(315deg, var(--theme-shell-gradient-b), transparent 35%),
    var(--theme-shell-bg);
}

.product-login-story {
  position: relative;
  min-width: 0;
  padding: 56px 70px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  overflow: hidden;
  background: #101828;
  color: #ffffff;

  &::before {
    content: '';
    position: absolute;
    inset: 0;
    background:
      linear-gradient(120deg, rgba(37, 99, 235, 0.35), transparent 42%),
      radial-gradient(circle at 78% 24%, rgba(20, 184, 166, 0.22), transparent 28%),
      linear-gradient(rgba(255, 255, 255, 0.045) 1px, transparent 1px),
      linear-gradient(90deg, rgba(255, 255, 255, 0.045) 1px, transparent 1px);
    background-size: auto, auto, 42px 42px, 42px 42px;
    opacity: 0.95;
  }
}

.product-login-bg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  opacity: 0.14;
  filter: saturate(0.85);
}

.product-login-story-main,
.product-login-status-row {
  position: relative;
  z-index: 1;
}

.product-login-brand {
  display: flex;
  align-items: center;
  gap: 12px;

  strong {
    display: block;
    font-size: 16px;
    line-height: 1.3;
  }

  span {
    display: block;
    margin-top: 2px;
    color: #b9c4d8;
    font-size: 12px;
  }
}

.product-login-brand-mark {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: grid;
  place-items: center;
  overflow: hidden;
  background: #2563eb;
  box-shadow: 0 14px 32px rgba(37, 99, 235, 0.35);
  color: #ffffff;

  img {
    max-width: 28px;
    max-height: 28px;
    object-fit: contain;
  }

  :deep(svg) {
    width: 24px;
    height: 24px;
  }
}

.product-login-headline {
  max-width: 680px;
  margin-top: 56px;

  h1 {
    margin: 0;
    color: #ffffff;
    font-size: 42px;
    line-height: 1.18;
    letter-spacing: 0;
  }

  p {
    max-width: 620px;
    margin: 18px 0 0;
    color: #c6d0e2;
    font-size: 16px;
    line-height: 1.8;
  }
}

.product-login-capabilities {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  max-width: 820px;
  margin-top: 72px;
}

.product-login-capability {
  min-height: 126px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  padding: 14px;
  background: rgba(255, 255, 255, 0.065);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.06);

  b {
    display: block;
    margin-bottom: 6px;
    color: #ffffff;
    font-size: 14px;
  }

  span {
    color: #b9c4d8;
    font-size: 12px;
    line-height: 1.6;
  }
}

.product-login-capability-icon {
  width: 28px;
  height: 28px;
  margin-bottom: 10px;
  border-radius: 7px;
  display: grid;
  place-items: center;
  color: #ffffff !important;
  background: rgba(37, 99, 235, 0.72);
  font-size: 13px !important;
  font-weight: 900;
}

.product-login-status-row {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  align-items: center;
  gap: 8px;
  width: min(760px, 100%);
  margin: 52px auto 0;
  color: #c6d0e2;
  font-size: 12px;
}

.product-login-status-chip {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 7px 10px;
  border: 1px solid rgba(255, 255, 255, 0.13);
  border-radius: 999px;
  background: rgba(16, 24, 40, 0.24);
  white-space: nowrap;
}

.product-login-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #94a3b8;
}

.product-login-wrap {
  --theme-panel-bg: #ffffff;
  --theme-panel-bg-soft: #f5f7fb;
  --theme-control-bg: #ffffff;
  --theme-control-hover-bg: #ffffff;
  --theme-hover-bg: #e8eef7;
  --theme-active-bg: #dde7f4;
  --theme-shell-border: #d7deea;
  --theme-text-primary: #172033;
  --theme-text-secondary: #53617a;
  --theme-text-tertiary: #7a879d;
  --theme-input-bg: #ffffff;
  --theme-input-border: #cbd5e1;
  --theme-card-shadow: 0 10px 28px rgba(16, 24, 40, 0.08);
  color-scheme: light;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
  background: var(--theme-panel-bg-soft);
}

.product-login-card {
  width: 100%;
  max-width: 420px;
  border: 1px solid var(--theme-shell-border);
  border-radius: 12px;
  background: var(--theme-panel-bg);
  box-shadow: var(--theme-card-shadow);
  padding: 32px;
  transform: scale(1.2);
  transform-origin: center;

  h2 {
    margin: 0;
    color: var(--theme-text-primary);
    font-size: 22px;
    line-height: 1.3;
    text-align: center;
  }
}

.product-login-desc {
  margin: 8px 0 24px;
  color: var(--theme-text-secondary);
  font-size: 13px;
  line-height: 1.7;
  text-align: center;
}

.product-login-form {
  color: var(--theme-text-primary);

  .product-login-field {
    margin-bottom: 15px;
  }

  :deep(.ed-form-item__content),
  :deep(.el-form-item__content) {
    color: var(--theme-text-primary);
  }

  :deep(.ed-form-item__label),
  :deep(.el-form-item__label) {
    margin-bottom: 7px;
    color: var(--theme-text-primary);
    font-size: 13px;
    font-weight: 700;
    line-height: 1.2;
  }

  :deep(.ed-input),
  :deep(.el-input) {
    --ed-input-bg-color: var(--theme-input-bg);
    --ed-input-border-color: var(--theme-input-border);
    --ed-input-clear-hover-color: var(--theme-text-secondary);
    --ed-input-focus-border-color: #2563eb;
    --ed-input-hover-border-color: #2563eb;
    --ed-input-icon-color: var(--theme-text-tertiary);
    --ed-input-placeholder-color: var(--theme-text-tertiary);
    --ed-input-text-color: var(--theme-text-primary);
    --el-input-bg-color: var(--theme-input-bg);
    --el-input-border-color: var(--theme-input-border);
    --el-input-clear-hover-color: var(--theme-text-secondary);
    --el-input-focus-border-color: #2563eb;
    --el-input-hover-border-color: #2563eb;
    --el-input-icon-color: var(--theme-text-tertiary);
    --el-input-placeholder-color: var(--theme-text-tertiary);
    --el-input-text-color: var(--theme-text-primary);
    color: var(--theme-text-primary);
  }

  :deep(.ed-input__wrapper),
  :deep(.el-input__wrapper) {
    height: 42px;
    border: 1px solid var(--theme-input-border);
    border-radius: 7px;
    box-shadow: none;
    padding: 0 12px;
    background: var(--theme-input-bg);
    transition:
      border-color 150ms ease,
      box-shadow 150ms ease;
  }

  :deep(.ed-input__wrapper.is-focus),
  :deep(.el-input__wrapper.is-focus),
  :deep(.ed-input__wrapper:hover),
  :deep(.el-input__wrapper:hover) {
    border-color: #2563eb;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
  }

  :deep(.ed-input__inner),
  :deep(.el-input__inner) {
    background: var(--theme-input-bg);
    color: var(--theme-text-primary);
    font-size: 14px;
  }

  :deep(.ed-input__inner:-webkit-autofill),
  :deep(.ed-input__inner:-webkit-autofill:hover),
  :deep(.ed-input__inner:-webkit-autofill:focus),
  :deep(.ed-input__inner:-webkit-autofill:active),
  :deep(.el-input__inner:-webkit-autofill),
  :deep(.el-input__inner:-webkit-autofill:hover),
  :deep(.el-input__inner:-webkit-autofill:focus),
  :deep(.el-input__inner:-webkit-autofill:active) {
    box-shadow: 0 0 0 1000px var(--theme-input-bg) inset;
    -webkit-box-shadow: 0 0 0 1000px var(--theme-input-bg) inset;
    -webkit-text-fill-color: var(--theme-text-primary);
    caret-color: var(--theme-text-primary);
  }

  :deep(.ed-input__inner::placeholder),
  :deep(.el-input__inner::placeholder) {
    color: var(--theme-text-tertiary);
  }

  :deep(.ed-input__suffix),
  :deep(.ed-input__suffix-inner),
  :deep(.el-input__suffix),
  :deep(.el-input__suffix-inner),
  :deep(.ed-input__clear),
  :deep(.el-input__clear),
  :deep(.ed-input__password),
  :deep(.el-input__password) {
    color: var(--theme-text-tertiary);
  }

  :deep(.ed-form-item__error),
  :deep(.el-form-item__error) {
    padding-top: 5px;
  }
}

.product-login-submit {
  width: 100%;
  height: 42px;
  border: 0;
  border-radius: 7px;
  background: #2563eb;
  color: #ffffff;
  font-size: 14px;
  font-weight: 800;
  cursor: pointer;
  box-shadow: 0 12px 26px rgba(37, 99, 235, 0.24);

  &:hover,
  &:focus {
    background: #1d4ed8;
    color: #ffffff;
  }
}

:deep(.sqlbot-other-login) {
  height: auto;
  min-height: 0;
}

:deep(.de-other-login-divider) {
  margin: 10px 0 12px;
}

@media (max-width: 1180px) {
  .product-login-card {
    transform: none;
  }
}

@media (max-width: 980px) {
  .product-login-page {
    grid-template-columns: 1fr;
  }

  .product-login-story {
    min-height: 420px;
    padding: 34px 24px;
  }

  .product-login-headline {
    margin-top: 54px;

    h1 {
      font-size: 30px;
    }
  }

  .product-login-capabilities {
    grid-template-columns: 1fr;
    margin-top: 32px;
  }

  .product-login-wrap {
    padding: 26px 16px 40px;
  }
}
</style>
