<template>
  <main class="login-container shuzhi-landing-page">
    <img v-if="storyBg" class="shuzhi-brand-bg" :src="storyBg" alt="" />

    <header class="shuzhi-nav">
      <button type="button" class="shuzhi-brand" aria-label="返回星通数智首页" @click="goHomePage">
        <span class="shuzhi-brand-mark">
          <img v-if="loginBg" :src="loginBg" alt="" />
          <custom_small v-else-if="appearanceStore.themeColor !== 'default'"></custom_small>
          <img v-else :src="elexDataLogoUrl" alt="" />
        </span>
        <span class="shuzhi-brand-copy">
          <strong>{{ productName }}</strong>
          <span>智能 BI 与数据分析工作台</span>
        </span>
      </button>

      <nav class="shuzhi-nav-links" aria-label="产品导航">
        <button
          v-for="item in navItems"
          :key="item.target"
          type="button"
          @click="isWorkspaceEntryPage ? goHomePage() : scrollToHomeSection(item.target)"
        >
          {{ item.label }}
        </button>
      </nav>

      <div class="shuzhi-nav-actions">
        <button
          v-if="isWorkspaceEntryPage"
          type="button"
          class="shuzhi-link-button"
          @click="goHomePage"
        >
          返回首页
        </button>
        <button v-else type="button" class="shuzhi-link-button" @click="goLoginPage">登录</button>
        <button
          type="button"
          class="shuzhi-primary-button shuzhi-nav-primary"
          @click="isTrialApplicationPage ? goLoginPage() : goTrialPage()"
        >
          <span>{{ isTrialApplicationPage ? '账号登录' : '免费试用' }}</span>
          <el-icon><ArrowRight /></el-icon>
        </button>
      </div>
    </header>

    <section
      v-if="isWorkspaceEntryPage"
      class="shuzhi-login-stage"
      :class="{ 'is-trial-stage': isTrialApplicationPage }"
      :aria-label="isTrialApplicationPage ? '申请试用星通数智' : '登录星通数智'"
    >
      <div class="shuzhi-login-shell">
        <section class="shuzhi-login-story">
          <span class="shuzhi-pill">
            <i></i>
            {{ entryStoryPill }}
          </span>
          <h1>{{ entryStoryTitle }}</h1>
          <p>
            {{ entryStoryDesc }}
          </p>

          <ul class="shuzhi-check-list">
            <li v-for="item in currentEntryBenefits" :key="item">
              <el-icon><Check /></el-icon>
              <span>{{ item }}</span>
            </li>
          </ul>

          <div class="login-preview-card" aria-hidden="true">
            <div class="mini-window-head">
              <span></span>
              <span></span>
              <span></span>
              <b>{{ productName }} · Smart Q&amp;A</b>
            </div>
            <div class="login-preview-body">
              <div class="login-preview-question">本周收入和转化有哪些异常？</div>
              <div class="login-preview-chart">
                <i v-for="item in previewBars" :key="item" :style="{ height: `${item}%` }"></i>
              </div>
              <div class="login-preview-note">
                <span>已识别 3 个异常指标</span>
                <strong>自动生成归因路径</strong>
              </div>
            </div>
          </div>
        </section>

        <aside class="product-login-wrap">
          <div class="product-login-card" :class="{ 'is-trial-card': isTrialApplicationPage }">
            <div class="product-login-card-head">
              <span>{{ isTrialApplicationPage ? '申请试用' : '工作台入口' }}</span>
              <h2>{{ isTrialApplicationPage ? '申请试用' : '账号登录' }}</h2>
              <p class="product-login-desc">
                {{ entryCardDesc }}
              </p>
            </div>

            <div class="login-form">
              <div v-if="isTrialApplicationPage" class="trial-application-panel">
                <div v-if="trialSubmitted" class="trial-submit-result">
                  <el-icon><CircleCheckFilled /></el-icon>
                  <h3>申请已提交</h3>
                  <p>
                    管理员审核通过后，你就可以使用申请的账号和密码在登录页进入 {{ productName }}。
                  </p>
                  <el-button type="primary" class="product-login-submit" @click="goLoginPage">
                    去登录页
                  </el-button>
                </div>
                <el-form
                  v-else
                  ref="trialApplicationFormRef"
                  class="form-content_error product-login-form trial-application-form"
                  :model="trialApplicationForm"
                  :rules="trialApplicationRules"
                  label-position="top"
                  @keyup.enter="submitTrialApplication"
                >
                  <el-form-item class="product-login-field" prop="account" label="账号">
                    <el-input
                      v-model="trialApplicationForm.account"
                      clearable
                      placeholder="请输入 3 位以上账号"
                      maxlength="100"
                      size="large"
                    ></el-input>
                  </el-form-item>
                  <el-form-item class="product-login-field" prop="password" label="密码">
                    <el-input
                      v-model="trialApplicationForm.password"
                      type="password"
                      show-password
                      clearable
                      placeholder="8-20 位，含大小写字母、数字和特殊字符"
                      maxlength="20"
                      size="large"
                    ></el-input>
                  </el-form-item>
                  <el-form-item
                    class="product-login-field"
                    prop="confirmPassword"
                    label="确认密码"
                  >
                    <el-input
                      v-model="trialApplicationForm.confirmPassword"
                      type="password"
                      show-password
                      clearable
                      placeholder="请再次输入密码"
                      maxlength="20"
                      size="large"
                    ></el-input>
                  </el-form-item>
                  <el-form-item class="product-login-field" prop="name" label="姓名">
                    <el-input
                      v-model="trialApplicationForm.name"
                      clearable
                      placeholder="请输入姓名或联系人"
                      maxlength="100"
                      size="large"
                    ></el-input>
                  </el-form-item>
                  <el-form-item class="product-login-field" prop="email" label="邮箱">
                    <el-input
                      v-model="trialApplicationForm.email"
                      clearable
                      placeholder="请输入可接收审核通知的邮箱"
                      maxlength="100"
                      size="large"
                    ></el-input>
                  </el-form-item>
                  <el-form-item class="product-login-field" prop="company" label="公司/团队">
                    <el-input
                      v-model="trialApplicationForm.company"
                      clearable
                      placeholder="选填"
                      maxlength="255"
                      size="large"
                    ></el-input>
                  </el-form-item>
                  <el-form-item class="product-login-field" prop="reason" label="试用说明">
                    <el-input
                      v-model="trialApplicationForm.reason"
                      type="textarea"
                      :rows="3"
                      maxlength="2000"
                      show-word-limit
                      placeholder="选填：简单说明希望使用的数据分析场景"
                    ></el-input>
                  </el-form-item>
                  <el-form-item>
                    <el-button
                      type="primary"
                      class="product-login-submit"
                      :loading="trialSubmitting"
                      @click="submitTrialApplication"
                    >
                      提交申请
                    </el-button>
                  </el-form-item>
                  <p class="trial-application-tip">
                    提交后需等待管理员审核。审核通过前，申请账号暂不能登录工作台。
                  </p>
                </el-form>
              </div>
              <div v-else class="default-login-tabs">
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
                <div class="product-login-divider">
                  <span>工作空间登录</span>
                </div>
                <el-button
                  class="product-login-feishu"
                  :loading="feishuLoading"
                  @click="startFeishuLogin"
                >
                  <span class="product-login-feishu-content">
                    <span class="product-login-feishu-logo-wrap" aria-hidden="true">
                      <svg
                        class="product-login-feishu-logo"
                        viewBox="0 0 64 64"
                        focusable="false"
                      >
                        <path
                          fill="#16d2bd"
                          d="M12.2 9.4h20.2c4.3 0 7.6 2.5 10.1 7.4l6 12-18.2 8.7L12.2 9.4z"
                        />
                        <path
                          fill="#3370ff"
                          d="M5.5 23.1c8.3 7.1 18 12.6 29 16.4 8 2.7 15.2 3 21.4 1-4.8 9.2-14.4 14.1-28.6 14.1-7.7 0-13.3-1.3-16.9-3.9-3.3-2.4-4.9-6-4.9-10.8V23.1z"
                        />
                        <path
                          fill="#1f43a8"
                          d="M28.2 38.1C36.6 27.9 45.2 22.7 54 22.7c2.3 0 4.5.3 6.5 1-4.7 8-9.8 13.8-15.3 17.2-5.7 3.6-11.4 3-17-1.7v-1.1z"
                        />
                      </svg>
                    </span>
                    <span>飞书登录</span>
                  </span>
                </el-button>
              </div>
            </div>
          </div>
        </aside>
      </div>

      <section class="login-capability-strip" aria-label="登录页能力摘要">
        <article v-for="item in accountExploreCards" :key="item.title">
          <el-icon>
            <component :is="item.icon" />
          </el-icon>
          <b>{{ item.title }}</b>
          <p>{{ item.desc }}</p>
        </article>
      </section>
    </section>

    <template v-else>
      <section class="shuzhi-hero" aria-label="星通数智首页">
        <div class="shuzhi-hero-copy">
          <span class="shuzhi-pill">
            <i></i>
            星通数智 3.0 已发布
          </span>
          <h1>让数据从噪音，变成你的决策力</h1>
          <p>{{ productSlogan }}</p>

          <div class="shuzhi-hero-actions">
            <button type="button" class="shuzhi-primary-button" @click="goTrialPage">
              <span>免费开始使用</span>
              <el-icon><ArrowRight /></el-icon>
            </button>
            <button
              type="button"
              class="shuzhi-secondary-button"
              @click="scrollToHomeSection('product-flow')"
            >
              <el-icon><VideoPlay /></el-icon>
              <span>观看演示</span>
            </button>
          </div>

          <div class="shuzhi-trust-row">
            <span v-for="item in trustDots" :key="item" :class="`trust-dot-${item}`"></span>
            <strong>数据源、语义层、问答与看板在同一个工作台协同</strong>
          </div>
        </div>

        <div class="hero-dashboard" aria-label="星通数智看板预览">
          <div class="hero-dashboard-window">
            <div class="mini-window-head">
              <span></span>
              <span></span>
              <span></span>
              <b>{{ productName }} · 智能分析看板</b>
            </div>
            <div class="hero-dashboard-body">
              <div class="metric-grid">
                <article v-for="item in heroMetrics" :key="item.label">
                  <span>{{ item.label }}</span>
                  <strong>{{ item.value }}</strong>
                  <em :class="{ danger: item.tone === 'danger' }">{{ item.trend }}</em>
                </article>
              </div>

              <section class="trend-panel">
                <div class="panel-title">
                  <b>营收趋势</b>
                  <span>本周</span>
                </div>
                <svg viewBox="0 0 420 160" role="img" aria-label="营收趋势折线图">
                  <defs>
                    <linearGradient id="heroLineFill" x1="0" x2="0" y1="0" y2="1">
                      <stop offset="0%" stop-color="#6258f6" stop-opacity="0.24" />
                      <stop offset="100%" stop-color="#6258f6" stop-opacity="0" />
                    </linearGradient>
                  </defs>
                  <path
                    d="M20 128 L72 104 L122 116 L170 80 L222 96 L270 54 L322 72 L370 34 L400 24 L400 150 L20 150 Z"
                    fill="url(#heroLineFill)"
                  />
                  <polyline
                    points="20,128 72,104 122,116 170,80 222,96 270,54 322,72 370,34 400,24"
                    fill="none"
                    stroke="#6258f6"
                    stroke-width="5"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  />
                  <circle cx="370" cy="34" r="6" fill="#ffffff" stroke="#6258f6" stroke-width="4" />
                </svg>
              </section>

              <section class="channel-panel">
                <b>渠道占比</b>
                <div class="donut-chart">
                  <span>总计<br />100%</span>
                </div>
                <div class="channel-legend">
                  <span><i></i>自然搜索 48%</span>
                  <span><i></i>付费投放 32%</span>
                </div>
              </section>
            </div>
          </div>
        </div>
      </section>

      <section id="product-flow" class="home-section flow-section" aria-label="为什么选择星通数智">
        <div class="section-heading center">
          <span>为什么选择 {{ productName }}</span>
          <h2>从数据混乱，到决策清晰</h2>
          <p>
            多数团队的数据散落在系统、报表和手工口径里。{{ productName }} 用三步打通从原始数据到可执行洞察的链路。
          </p>
        </div>

        <div class="flow-card-grid">
          <article v-for="(item, index) in capabilities" :key="item.title">
            <el-icon>
              <component :is="item.icon" />
            </el-icon>
            <em>{{ String(index + 1).padStart(2, '0') }}</em>
            <b>{{ item.title }}</b>
            <p>{{ item.desc }}</p>
          </article>
        </div>
      </section>

      <section id="platform" class="home-section platform-section" aria-label="分析全链路">
        <div class="section-heading center">
          <span>核心能力</span>
          <h2>一个平台，覆盖分析全链路</h2>
          <p>从数据接入到智能问数、异常归因和团队协作，星通数智把分析流程装进同一个工作台。</p>
        </div>

        <div class="feature-row">
          <div class="feature-copy">
            <span>01 实时看板</span>
            <h3>用拖拽搭建任何你想要的看板</h3>
            <p>
              业务指标、自由图表和问答结果可以沉淀为持续运营的看板，让团队成员围绕同一份事实沟通。
            </p>
            <ul class="shuzhi-check-list compact">
              <li v-for="item in dashboardBullets" :key="item">
                <el-icon><Check /></el-icon>
                <span>{{ item }}</span>
              </li>
            </ul>
          </div>
          <div class="dashboard-builder" aria-hidden="true">
            <div class="mini-window-head">
              <span></span>
              <span></span>
              <span></span>
              <b>实时看板编辑器</b>
            </div>
            <div class="builder-body">
              <div class="builder-card metric">
                <span>今日活跃</span>
                <strong>12,840</strong>
              </div>
              <div class="builder-card bars">
                <b>渠道分布</b>
                <i v-for="item in builderBars" :key="item" :style="{ height: `${item}%` }"></i>
              </div>
              <div class="builder-card line">
                <b>访问趋势</b>
                <span v-for="item in lineDots" :key="item"></span>
              </div>
            </div>
          </div>
        </div>

        <div class="feature-row reverse">
          <div class="feature-copy">
            <span>02 智能归因</span>
            <h3>让异常无处可藏，归因一钻到底</h3>
            <p>
              指标波动自动捕捉，AI 结合维度拆解和业务语义提示，让问题定位从经验猜测走向可复核路径。
            </p>
            <ul class="shuzhi-check-list compact">
              <li v-for="item in anomalyBullets" :key="item">
                <el-icon><Check /></el-icon>
                <span>{{ item }}</span>
              </li>
            </ul>
          </div>
          <div class="anomaly-card" aria-hidden="true">
            <div class="mini-window-head">
              <span></span>
              <span></span>
              <span></span>
              <b>智能归因下钻</b>
            </div>
            <div class="anomaly-body">
              <div class="alert-line">
                <el-icon><Bell /></el-icon>
                <strong>订单量较昨日下降 18.2%</strong>
                <span>2 分钟前</span>
              </div>
              <div class="root-cause-list">
                <div>
                  <span><i></i>渠道 · 付费搜索</span>
                  <strong>贡献 -12.4%</strong>
                </div>
                <div>
                  <span><i></i>地域 · 华东区</span>
                  <strong>贡献 -4.1%</strong>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="feature-row">
          <div class="feature-copy">
            <span>03 协同分析</span>
            <h3>让分析成为团队的共同语言</h3>
            <p>
              看板评论、指标订阅和问数记录可以沉淀为团队知识，让每一次决策都有上下文、有过程、可追溯。
            </p>
            <ul class="shuzhi-check-list compact">
              <li v-for="item in collaborationBullets" :key="item">
                <el-icon><Check /></el-icon>
                <span>{{ item }}</span>
              </li>
            </ul>
          </div>
          <div class="collaboration-card" aria-hidden="true">
            <div class="mini-window-head">
              <span></span>
              <span></span>
              <span></span>
              <b>看板协同评论</b>
            </div>
            <div class="collaboration-body">
              <div class="collab-chart">
                <i v-for="item in collaborationBars" :key="item" :style="{ height: `${item}%` }"></i>
              </div>
              <div class="comment-panel">
                <b>评论 (3)</b>
                <p><span></span>增长放缓来自新客转化</p>
                <p><span></span>建议同步检查渠道预算</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section id="solutions" class="home-section scenario-section" aria-label="解决方案">
        <div class="section-heading">
          <span>解决方案</span>
          <h2>让不同角色都能在同一套可信数据上工作</h2>
        </div>
        <div class="scenario-grid">
          <article v-for="item in scenarioCards" :key="item.title">
            <el-icon>
              <component :is="item.icon" />
            </el-icon>
            <b>{{ item.title }}</b>
            <p>{{ item.desc }}</p>
          </article>
        </div>
      </section>

      <section id="resources" class="home-section cta-section" aria-label="开始使用">
        <div>
          <span>开始使用</span>
          <h2>进入 {{ productName }}，把业务问题直接连接到可信数据</h2>
          <p>从自然语言问数开始，逐步沉淀语义层、推荐问题和数据看板。</p>
        </div>
        <button type="button" class="shuzhi-primary-button" @click="goTrialPage">
          <span>申请试用</span>
          <el-icon><ArrowRight /></el-icon>
        </button>
      </section>

      <footer class="shuzhi-footer">
        <div class="footer-brand">
          <span class="shuzhi-brand-mark">
            <img v-if="loginBg" :src="loginBg" alt="" />
            <custom_small v-else-if="appearanceStore.themeColor !== 'default'"></custom_small>
            <img v-else :src="elexDataLogoUrl" alt="" />
          </span>
          <strong>{{ productName }}</strong>
          <p>让每个团队都能从数据走向决策。统一的实时分析工作台，服务企业的数据协同与 AI 问数。</p>
        </div>
        <div class="footer-links">
          <div v-for="group in footerLinks" :key="group.title">
            <b>{{ group.title }}</b>
            <span v-for="item in group.items" :key="item">{{ item }}</span>
          </div>
        </div>
      </footer>
    </template>
  </main>
</template>

<script lang="ts" setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useI18n } from 'vue-i18n'
import custom_small from '@/assets/svg/logo-custom_small.svg'
import elexDataLogoUrl from '@/assets/elex_data.png'
import { useAppearanceStoreWithOut } from '@/stores/appearance'
import { AuthApi } from '@/api/login'
import { ElMessage } from 'element-plus-secondary'
import { resolveLoginSuccessDashboardTarget } from '@/utils/dashboardLanding'
import {
  ArrowRight,
  Bell,
  ChatDotRound,
  Check,
  CircleCheckFilled,
  Collection,
  Connection,
  DataBoard,
  DocumentChecked,
  Histogram,
  Lock,
  MagicStick,
  Monitor,
  PieChart,
  TrendCharts,
  VideoPlay,
} from '@element-plus/icons-vue'

const router = useRouter()
const userStore = useUserStore()
const appearanceStore = useAppearanceStoreWithOut()
const { t } = useI18n()
const loginForm = ref({
  username: '',
  password: '',
})
const trialApplicationForm = ref({
  account: '',
  password: '',
  confirmPassword: '',
  name: '',
  email: '',
  company: '',
  reason: '',
})
const trialSubmitting = ref(false)
const trialSubmitted = ref(false)
const feishuLoading = ref(false)
const feishuStatus = ref<{
  enabled: boolean
  authorize_url?: string | null
}>({
  enabled: false,
  authorize_url: null,
})

const storyBg = computed(() => appearanceStore.getBg || '')

const loginBg = computed(() => {
  return appearanceStore.getLogin
})

const productName = computed(() => appearanceStore.name || '星通数智')

const productSlogan = computed(() => {
  if (appearanceStore.getShowSlogan && appearanceStore.slogan) {
    return appearanceStore.slogan
  }
  return '把分散在业务系统里的数据汇聚成统一分析工作台，自动建模、实时看板、智能洞察，帮助团队在几分钟内从数据走向决策。'
})

const navItems = [
  { label: '产品', target: 'product-flow' },
  { label: '解决方案', target: 'solutions' },
  { label: '能力', target: 'platform' },
  { label: '资源', target: 'resources' },
]
const trustDots = ['blue', 'violet', 'coral', 'teal']
const heroMetrics = [
  { label: '总营收', value: '¥1,284,560', trend: '+12.5% 较上周' },
  { label: '活跃用户', value: '48,295', trend: '+8.2% 较上周' },
  { label: '转化率', value: '7.84%', trend: '-1.3% 较上周', tone: 'danger' },
]
const capabilities = [
  {
    icon: Connection,
    title: '一键连接数据源',
    desc: '接入数据库、Excel、SaaS 工具和业务系统，统一管理字段、权限与数据上下文。',
  },
  {
    icon: DataBoard,
    title: '自动建模与看板',
    desc: 'AI 自动识别字段关系、生成数据模型，并将高频问题沉淀为可复用的看板资产。',
  },
  {
    icon: Bell,
    title: '智能洞察与预警',
    desc: '异常自动识别、归因下钻、关键指标波动实时推送，让决策系统快人一步。',
  },
]
const accountBenefits = [
  '继续使用自然语言查询数据、追问结果和生成图表。',
  '统一连接数据源、语义口径、权限校验和看板资产。',
  '在工作空间内复用 Data Skills、推荐问题和分析记录。',
]
const trialBenefits = [
  '填写账号、密码和邮箱后提交申请，管理员审核通过后即可登录试用。',
  '申请阶段不直接开通数据权限，先由管理员确认团队和使用场景。',
  '通过后继续使用同一账号密码进入工作台，沉淀问数、图表和看板资产。',
]
const accountExploreCards = [
  {
    icon: ChatDotRound,
    title: '智能问数',
    desc: '用业务语言提问，自动生成 SQL、图表和可复核解释。',
  },
  {
    icon: Lock,
    title: '权限优先',
    desc: '先确认工作空间、数据源和用户授权，再进入分析路径。',
  },
  {
    icon: Collection,
    title: '资产沉淀',
    desc: '把高频问题、指标口径和看板沉淀为团队共享资产。',
  },
]
const previewBars = [34, 58, 44, 72, 64, 86, 76]
const builderBars = [48, 66, 78, 88, 62, 46]
const lineDots = ['a', 'b', 'c', 'd', 'e']
const collaborationBars = [46, 58, 76, 62, 52]
const dashboardBullets = ['40+ 可组合图表组件，自由拖拽排版', '秒级数据刷新，团队共享同一份数据真相']
const anomalyBullets = ['异常波动秒级识别，自动推送归因报告', '多维下钻，定位到具体人群与渠道']
const collaborationBullets = ['看板内评论与订阅，分析讨论就地沉淀', '报表定时推送邮件和 IM，决策不等人']
const scenarioCards = [
  {
    icon: Monitor,
    title: '业务团队',
    desc: '直接用自然语言提出问题，快速获得图表、解释和可继续追问的上下文。',
  },
  {
    icon: MagicStick,
    title: '数据团队',
    desc: '把反复沟通的指标口径、查询范式和推荐问题沉淀到语义层。',
  },
  {
    icon: PieChart,
    title: '管理团队',
    desc: '通过看板和权限体系组织跨部门指标，让经营复盘建立在一致事实上。',
  },
  {
    icon: Histogram,
    title: '运营团队',
    desc: '围绕渠道、活动、用户行为或业务流程快速探索波动原因。',
  },
  {
    icon: TrendCharts,
    title: '增长团队',
    desc: '持续跟踪漏斗、留存和转化趋势，发现机会并验证策略效果。',
  },
  {
    icon: DocumentChecked,
    title: '合规协作',
    desc: '保留问题、SQL、图表和解释过程，让关键分析结果可追溯、可复核。',
  },
]
const footerLinks = [
  { title: '产品', items: ['功能特性', '定价方案', '数据源', '更新日志'] },
  { title: '公司', items: ['关于我们', '客户案例', '加入我们', '联系我们'] },
  { title: '资源', items: ['帮助中心', '开发者文档', '数据博客', 'API 参考'] },
]

const rules = {
  username: [{ required: true, message: t('common.your_account_email_address'), trigger: 'blur' }],
  password: [{ required: true, message: t('common.the_correct_password'), trigger: 'blur' }],
}

const loginFormRef = ref()
const trialApplicationFormRef = ref()
const passwordPattern =
  /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[~!@#$%^&*()_+\-={}|:"<>?`[\];',./])[A-Za-z\d~!@#$%^&*()_+\-={}|:"<>?`[\];',./]{8,20}$/
const emailPattern = /^[a-zA-Z0-9]+([._-][a-zA-Z0-9]+)*@([a-zA-Z0-9]+(-[a-zA-Z0-9]+)*\.)+[a-zA-Z]{2,}$/
const validateTrialPassword = (_rule: any, value: string, callback: (error?: Error) => void) => {
  if (!value) {
    callback(new Error('请输入密码'))
    return
  }
  if (!passwordPattern.test(value)) {
    callback(new Error('密码需为 8-20 位，包含大小写字母、数字和特殊字符'))
    return
  }
  callback()
}
const validateTrialConfirmPassword = (
  _rule: any,
  value: string,
  callback: (error?: Error) => void
) => {
  if (!value) {
    callback(new Error('请再次输入密码'))
    return
  }
  if (value !== trialApplicationForm.value.password) {
    callback(new Error('两次输入的密码不一致'))
    return
  }
  callback()
}
const validateTrialEmail = (_rule: any, value: string, callback: (error?: Error) => void) => {
  if (!value) {
    callback(new Error('请输入邮箱'))
    return
  }
  if (!emailPattern.test(value)) {
    callback(new Error('邮箱格式不正确'))
    return
  }
  callback()
}
const trialApplicationRules = {
  account: [
    { required: true, message: '请输入账号', trigger: 'blur' },
    { min: 3, max: 100, message: '账号需为 3-100 位', trigger: 'blur' },
  ],
  password: [{ validator: validateTrialPassword, trigger: 'blur' }],
  confirmPassword: [{ validator: validateTrialConfirmPassword, trigger: 'blur' }],
  name: [
    { required: true, message: '请输入姓名', trigger: 'blur' },
    { max: 100, message: '姓名不能超过 100 位', trigger: 'blur' },
  ],
  email: [{ validator: validateTrialEmail, trigger: 'blur' }],
  company: [{ max: 255, message: '公司/团队不能超过 255 位', trigger: 'blur' }],
  reason: [{ max: 2000, message: '试用说明不能超过 2000 位', trigger: 'blur' }],
}
const isLoginFormPage = computed(() => {
  return router.currentRoute.value.path === '/admin-login' || router.currentRoute.value.query.view === 'account'
})
const isTrialApplicationPage = computed(() => {
  return router.currentRoute.value.query.view === 'trial'
})
const isWorkspaceEntryPage = computed(() => isLoginFormPage.value || isTrialApplicationPage.value)
const currentEntryBenefits = computed(() =>
  isTrialApplicationPage.value ? trialBenefits : accountBenefits
)
const entryStoryPill = computed(() =>
  isTrialApplicationPage.value ? '申请试用，审核通过后启用' : '可信分析，从统一入口开始'
)
const entryStoryTitle = computed(() =>
  isTrialApplicationPage.value
    ? `申请试用 ${productName.value}，先完成账号审核再进入工作台`
    : `登录 ${productName.value}，继续把问题变成可追溯的数据答案`
)
const entryStoryDesc = computed(() =>
  isTrialApplicationPage.value
    ? '提交必要账号信息后，管理员会审核账号、邮箱和使用场景。通过后即可使用申请的账号密码登录试用。'
    : '在同一个工作台里完成自然语言问数、语义口径复用、图表生成和团队看板协同。'
)
const entryCardDesc = computed(() =>
  isTrialApplicationPage.value
    ? '填写账号、密码、姓名和邮箱等必要信息。申请通过前账号不会被开通，审核通过后可直接在登录页使用。'
    : `使用你的账号进入 ${productName.value}，继续查询数据、管理看板和沉淀团队分析资产。`
)

const scrollToHomeSection = (id: string) => {
  if (isWorkspaceEntryPage.value) {
    goHomePage()
    return
  }
  window.requestAnimationFrame(() => {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  })
}

const goLoginPage = () => {
  const query = { ...router.currentRoute.value.query }
  delete query.code
  delete query.state
  router.push({ path: '/login', query: { ...query, view: 'account' } })
}

const goTrialPage = () => {
  const query = { ...router.currentRoute.value.query }
  delete query.code
  delete query.state
  router.push({ path: '/login', query: { ...query, view: 'trial' } })
}

const goHomePage = () => {
  router.push({ path: '/login' })
}

const getCallbackParam = (name: string) => {
  const searchValue = new URLSearchParams(window.location.search).get(name)
  if (searchValue) {
    return searchValue
  }
  const hash = window.location.hash || ''
  const queryIndex = hash.indexOf('?')
  if (queryIndex < 0) {
    return null
  }
  return new URLSearchParams(hash.slice(queryIndex + 1)).get(name)
}

const currentRedirect = () => {
  const redirect = router.currentRoute.value.query.redirect
  const value = Array.isArray(redirect) ? redirect[0] : redirect
  return value || undefined
}

const goLoginSuccess = async () => {
  await userStore.info()
  await router.push(await resolveLoginSuccessDashboardTarget(userStore, currentRedirect()))
}

const loadFeishuStatus = async () => {
  try {
    const res: any = await AuthApi.feishuStatus({ redirect: currentRedirect() })
    feishuStatus.value = {
      enabled: Boolean(res?.enabled),
      authorize_url: res?.authorize_url || null,
    }
  } catch {
    feishuStatus.value = { enabled: false, authorize_url: null }
  }
}

const handleFeishuCallback = async () => {
  const code = getCallbackParam('code')
  const state = getCallbackParam('state')
  if (!code || !state || !state.includes('feishu')) {
    return false
  }
  feishuLoading.value = true
  try {
    const res: any = await AuthApi.feishuCallback({ code, state })
    userStore.setToken(res.access_token)
    if (res.platform_info) {
      userStore.setPlatformInfo(res.platform_info)
    }
    const cleanQuery = { ...router.currentRoute.value.query }
    delete cleanQuery.code
    delete cleanQuery.state
    await router.replace({ path: '/login', query: cleanQuery })
    if (res.platform_info?.redirect) {
      await router.push(res.platform_info.redirect)
    } else {
      await goLoginSuccess()
    }
    return true
  } finally {
    feishuLoading.value = false
  }
}

const startFeishuLogin = async () => {
  if (!feishuStatus.value.authorize_url) {
    await loadFeishuStatus()
  }
  if (feishuStatus.value.authorize_url) {
    window.location.href = feishuStatus.value.authorize_url
    return
  }
  ElMessage.warning('飞书登录暂不可用，请联系管理员检查企业飞书配置')
}

const normalizeLoginBrowserUrl = async () => {
  const { pathname, search, hash } = window.location
  if ((pathname === '/' || pathname === '') && !search) {
    return
  }
  if (!hash.startsWith('#/login') && !hash.startsWith('#/admin-login')) {
    return
  }

  const hashRoute = hash.slice(1)
  const queryIndex = hashRoute.indexOf('?')
  const hashPath = queryIndex >= 0 ? hashRoute.slice(0, queryIndex) : hashRoute
  const hashQuery = queryIndex >= 0 ? hashRoute.slice(queryIndex + 1) : ''
  const nextQuery = new URLSearchParams(hashQuery)
  const outerQuery = new URLSearchParams(search)
  outerQuery.forEach((value, key) => {
    if (!nextQuery.has(key)) {
      nextQuery.set(key, value)
    }
  })

  const query: Record<string, string> = {}
  nextQuery.forEach((value, key) => {
    query[key] = value
  })

  await router.replace({
    path: hashPath,
    query,
  })
  window.history.replaceState(
    window.history.state,
    document.title,
    `${window.location.origin}/${window.location.hash}`
  )
}

const submitForm = () => {
  loginFormRef.value.validate((valid: boolean) => {
    if (valid) {
      userStore.login(loginForm.value).then(() => {
        goLoginSuccess()
      })
    }
  })
}

const submitTrialApplication = () => {
  if (trialSubmitting.value || trialSubmitted.value) return
  trialApplicationFormRef.value.validate((valid: boolean) => {
    if (!valid) return
    trialSubmitting.value = true
    const form = trialApplicationForm.value
    AuthApi.submitTrialApplication({
      account: form.account.trim(),
      password: form.password,
      name: form.name.trim(),
      email: form.email.trim(),
      company: form.company.trim() || undefined,
      reason: form.reason.trim() || undefined,
    })
      .then(() => {
        trialSubmitted.value = true
        ElMessage.success('申请已提交，请等待管理员审核')
      })
      .finally(() => {
        trialSubmitting.value = false
      })
  })
}

onMounted(async () => {
  await normalizeLoginBrowserUrl()
  const handled = await handleFeishuCallback()
  if (!handled) {
    await loadFeishuStatus()
  }
})
</script>

<style lang="less" scoped>
.login-container {
  width: 100%;
  max-width: 100%;
  min-height: 100vh;
  box-sizing: border-box;
  overflow-x: hidden;
  overflow-y: auto;
}

.shuzhi-landing-page {
  --page-bg: #ffffff;
  --soft-bg: #f7f8fc;
  --text-main: #171927;
  --text-strong: #101323;
  --text-muted: #7a8194;
  --line: #e7e9f2;
  --primary: #6258f6;
  --primary-dark: #4b42df;
  --primary-soft: #eeedff;
  --teal: #19c7a5;
  --blue: #2f8cff;
  --coral: #ff6b6b;
  --shadow: 0 24px 70px rgba(61, 58, 124, 0.12);
  position: relative;
  color: var(--text-main);
  color-scheme: light;
  background: var(--page-bg);
}

.shuzhi-brand-bg {
  position: absolute;
  inset: 0 0 auto;
  width: 100%;
  height: 520px;
  object-fit: cover;
  opacity: 0.06;
  pointer-events: none;
}

.shuzhi-nav {
  position: sticky;
  top: 0;
  z-index: 20;
  min-height: 64px;
  display: flex;
  align-items: center;
  gap: 34px;
  padding: 0 max(40px, calc((100vw - 1280px) / 2));
  border-bottom: 1px solid rgba(231, 233, 242, 0.72);
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(16px);
}

.shuzhi-brand {
  min-width: 230px;
  display: inline-flex;
  align-items: center;
  gap: 11px;
  border: 0;
  padding: 0;
  background: transparent;
  cursor: pointer;
  text-align: left;
}

.shuzhi-brand-mark {
  width: 32px;
  height: 32px;
  flex: 0 0 32px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  background: #ffffff;
  box-shadow: 0 10px 24px rgba(81, 72, 220, 0.16);

  img {
    width: 25px;
    height: 25px;
    object-fit: contain;
  }

  :deep(svg) {
    width: 24px;
    height: 24px;
  }
}

.shuzhi-brand-copy {
  min-width: 0;

  strong {
    display: block;
    color: var(--text-strong);
    font-size: 17px;
    line-height: 1.15;
  }

  span {
    display: block;
    margin-top: 2px;
    color: var(--text-muted);
    font-size: 11px;
    line-height: 1.3;
  }
}

.shuzhi-nav-links {
  flex: 1;
  display: flex;
  justify-content: center;
  gap: 34px;

  button {
    border: 0;
    padding: 4px 0;
    background: transparent;
    color: #5f6678;
    cursor: pointer;
    font-size: 14px;
    font-weight: 700;

    &:hover,
    &:focus {
      color: var(--primary);
    }
  }
}

.shuzhi-nav-actions {
  display: inline-flex;
  align-items: center;
  gap: 14px;
}

.shuzhi-link-button,
.shuzhi-primary-button,
.shuzhi-secondary-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border: 0;
  cursor: pointer;
  font-weight: 800;
  transition:
    transform 160ms ease,
    box-shadow 160ms ease,
    background 160ms ease,
    color 160ms ease,
    border-color 160ms ease;

  &:active {
    transform: translateY(1px);
  }
}

.shuzhi-link-button {
  height: 38px;
  padding: 0 6px;
  background: transparent;
  color: var(--text-main);
  font-size: 14px;

  &:hover,
  &:focus {
    color: var(--primary);
  }
}

.shuzhi-primary-button {
  min-height: 46px;
  border-radius: 6px;
  padding: 0 22px;
  background: var(--primary);
  color: #ffffff;
  font-size: 14px;
  box-shadow: 0 14px 30px rgba(98, 88, 246, 0.26);

  &:hover,
  &:focus {
    background: var(--primary-dark);
    color: #ffffff;
    box-shadow: 0 18px 38px rgba(98, 88, 246, 0.32);
  }
}

.shuzhi-secondary-button {
  min-height: 46px;
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 0 20px;
  background: #ffffff;
  color: var(--text-main);
  font-size: 14px;

  &:hover,
  &:focus {
    border-color: rgba(98, 88, 246, 0.34);
    color: var(--primary);
    box-shadow: 0 12px 28px rgba(61, 58, 124, 0.1);
  }
}

.shuzhi-nav-primary {
  min-height: 38px;
  padding: 0 16px;
  box-shadow: 0 10px 22px rgba(98, 88, 246, 0.22);
}

.shuzhi-pill {
  width: fit-content;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  border-radius: 999px;
  padding: 7px 12px;
  background: var(--primary-soft);
  color: var(--primary);
  font-size: 13px;
  font-weight: 800;

  i {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--primary);
  }
}

.shuzhi-hero {
  position: relative;
  z-index: 1;
  min-height: 500px;
  display: grid;
  grid-template-columns: minmax(0, 0.92fr) minmax(520px, 1.08fr);
  gap: 70px;
  align-items: center;
  max-width: 1280px;
  margin: 0 auto;
  padding: 70px 40px 74px;
}

.shuzhi-hero-copy {
  min-width: 0;

  h1 {
    max-width: 620px;
    margin: 32px 0 20px;
    color: var(--primary);
    font-size: 56px;
    line-height: 1.1;
    letter-spacing: 0;
    overflow-wrap: anywhere;
  }

  p {
    max-width: 620px;
    margin: 0;
    color: #687083;
    font-size: 17px;
    line-height: 1.8;
  }
}

.shuzhi-hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  margin-top: 26px;
}

.shuzhi-trust-row {
  display: flex;
  align-items: center;
  gap: 0;
  margin-top: 28px;

  span {
    width: 24px;
    height: 24px;
    margin-right: -7px;
    border: 2px solid #ffffff;
    border-radius: 50%;
    box-shadow: 0 8px 18px rgba(61, 58, 124, 0.12);
  }

  strong {
    margin-left: 17px;
    color: #6f7586;
    font-size: 13px;
    line-height: 1.5;
  }
}

.trust-dot-blue {
  background: var(--blue);
}

.trust-dot-violet {
  background: var(--primary);
}

.trust-dot-coral {
  background: var(--coral);
}

.trust-dot-teal {
  background: var(--teal);
}

.hero-dashboard {
  min-width: 0;
}

.hero-dashboard-window,
.dashboard-builder,
.anomaly-card,
.collaboration-card,
.login-preview-card {
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #ffffff;
  box-shadow: var(--shadow);
}

.hero-dashboard-window {
  width: 100%;
}

.mini-window-head {
  height: 42px;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 0 18px;
  border-bottom: 1px solid #edf0f6;
  background: #fbfbfe;

  span {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #ff6b57;

    &:nth-child(2) {
      background: #ffc145;
    }

    &:nth-child(3) {
      background: #28c4a0;
    }
  }

  b {
    flex: 1;
    color: #a0a7b7;
    font-size: 12px;
    text-align: center;
  }
}

.hero-dashboard-body {
  display: grid;
  grid-template-columns: minmax(0, 1.7fr) minmax(170px, 0.72fr);
  gap: 18px;
  padding: 18px;
}

.metric-grid {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;

  article {
    min-height: 86px;
    border: 1px solid #e9ebf3;
    border-radius: 8px;
    padding: 14px 16px;
    background: #fcfcff;
  }

  span,
  em {
    display: block;
    color: #8c94a8;
    font-size: 12px;
    font-style: normal;
    line-height: 1.3;
  }

  strong {
    display: block;
    margin: 10px 0 8px;
    color: var(--text-strong);
    font-size: 23px;
    line-height: 1;
  }

  em {
    color: #10a978;
    font-weight: 800;
  }

  .danger {
    color: #ec5f6b;
  }
}

.trend-panel,
.channel-panel {
  min-width: 0;
  border: 1px solid #e9ebf3;
  border-radius: 8px;
  background: #ffffff;
}

.trend-panel {
  padding: 18px 18px 8px;

  svg {
    display: block;
    width: 100%;
    height: 190px;
  }
}

.panel-title {
  display: flex;
  align-items: center;
  justify-content: space-between;

  b {
    color: var(--text-strong);
    font-size: 14px;
  }

  span {
    color: var(--primary);
    font-size: 12px;
    font-weight: 800;
  }
}

.channel-panel {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  padding: 18px 14px;

  b {
    align-self: flex-start;
    color: var(--text-strong);
    font-size: 14px;
  }
}

.donut-chart {
  width: 128px;
  height: 128px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: conic-gradient(var(--teal) 0 48%, var(--primary) 48% 80%, #e9ecf7 80% 100%);

  &::before {
    content: '';
    position: absolute;
  }

  span {
    width: 74px;
    height: 74px;
    display: grid;
    place-items: center;
    border-radius: 50%;
    background: #ffffff;
    color: #606779;
    font-size: 13px;
    font-weight: 900;
    line-height: 1.25;
    text-align: center;
  }
}

.channel-legend {
  display: grid;
  gap: 8px;
  width: 100%;

  span {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    color: #7f8799;
    font-size: 12px;
    line-height: 1.3;
  }

  i {
    width: 8px;
    height: 8px;
    flex: 0 0 8px;
    border-radius: 50%;
    background: var(--primary);
  }

  span:first-child i {
    background: var(--teal);
  }
}

.home-section {
  position: relative;
  z-index: 1;
  padding: 72px max(40px, calc((100vw - 1180px) / 2));
}

.section-heading {
  max-width: 780px;
  margin-bottom: 36px;

  &.center {
    margin-right: auto;
    margin-left: auto;
    text-align: center;
  }

  > span {
    display: inline-flex;
    margin-bottom: 14px;
    border-radius: 999px;
    padding: 6px 12px;
    background: var(--primary-soft);
    color: var(--primary);
    font-size: 12px;
    font-weight: 900;
  }

  h2 {
    margin: 0;
    color: var(--text-strong);
    font-size: 36px;
    line-height: 1.22;
    letter-spacing: 0;
  }

  p {
    max-width: 720px;
    margin: 16px auto 0;
    color: #7a8194;
    font-size: 15px;
    line-height: 1.8;
  }
}

.flow-section {
  background: #ffffff;
}

.flow-card-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 86px;

  article {
    min-height: 238px;
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 26px;
    background: #ffffff;
    box-shadow: 0 16px 40px rgba(61, 58, 124, 0.06);
  }

  .el-icon {
    width: 42px;
    height: 42px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: 8px;
    background: var(--primary-soft);
    color: var(--primary);
    font-size: 21px;
  }

  em {
    display: block;
    margin-top: 24px;
    color: #9aa2b7;
    font-size: 12px;
    font-style: normal;
    font-weight: 900;
  }

  b {
    display: block;
    margin-top: 14px;
    color: var(--text-strong);
    font-size: 18px;
  }

  p {
    margin: 12px 0 0;
    color: #7a8194;
    font-size: 13px;
    line-height: 1.75;
  }
}

.platform-section {
  background: var(--soft-bg);
}

.feature-row {
  display: grid;
  grid-template-columns: minmax(0, 0.92fr) minmax(420px, 1.08fr);
  align-items: center;
  gap: 76px;
  max-width: 1140px;
  margin: 0 auto;
  padding: 42px 0;

  &.reverse {
    grid-template-columns: minmax(420px, 1.08fr) minmax(0, 0.92fr);

    .feature-copy {
      order: 2;
    }
  }
}

.feature-copy {
  min-width: 0;

  > span {
    color: var(--primary);
    font-size: 13px;
    font-weight: 900;
  }

  h3 {
    margin: 18px 0 16px;
    color: var(--text-strong);
    font-size: 31px;
    line-height: 1.22;
    letter-spacing: 0;
  }

  p {
    margin: 0;
    color: #7a8194;
    font-size: 15px;
    line-height: 1.8;
  }
}

.shuzhi-check-list {
  display: grid;
  gap: 13px;
  margin: 24px 0 0;
  padding: 0;
  list-style: none;
  color: #676e82;
  font-size: 14px;
  line-height: 1.55;

  li {
    display: grid;
    grid-template-columns: 18px minmax(0, 1fr);
    gap: 10px;
    align-items: start;
  }

  .el-icon {
    margin-top: 2px;
    color: var(--teal);
    font-size: 15px;
  }

  &.compact {
    gap: 10px;
    margin-top: 20px;
    font-size: 13px;
  }
}

.dashboard-builder,
.anomaly-card,
.collaboration-card {
  width: 100%;
}

.builder-body {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  padding: 18px;
}

.builder-card {
  min-height: 118px;
  border: 1px solid #e9ebf3;
  border-radius: 8px;
  background: #ffffff;
}

.builder-card.metric {
  padding: 18px;

  span {
    color: #9aa2b7;
    font-size: 12px;
  }

  strong {
    display: block;
    margin-top: 10px;
    color: var(--text-strong);
    font-size: 25px;
  }
}

.builder-card.bars {
  grid-row: span 2;
  display: flex;
  align-items: end;
  gap: 16px;
  padding: 42px 26px 22px;
  position: relative;

  b {
    position: absolute;
    top: 18px;
    left: 18px;
    color: var(--text-strong);
    font-size: 14px;
  }

  i {
    flex: 1;
    min-width: 16px;
    border-radius: 4px 4px 0 0;
    background: var(--primary);

    &:nth-child(2n) {
      opacity: 0.72;
    }
  }
}

.builder-card.line {
  position: relative;
  display: flex;
  align-items: end;
  gap: 24px;
  padding: 44px 22px 26px;

  b {
    position: absolute;
    top: 18px;
    left: 18px;
    color: var(--text-strong);
    font-size: 14px;
  }

  span {
    width: 9px;
    height: 9px;
    border-radius: 50%;
    background: var(--primary);

    &:nth-child(2) {
      margin-bottom: 18px;
    }

    &:nth-child(3) {
      margin-bottom: 10px;
    }

    &:nth-child(4) {
      margin-bottom: 34px;
    }

    &:nth-child(5) {
      margin-bottom: 28px;
    }
  }
}

.anomaly-body,
.collaboration-body {
  padding: 28px;
}

.alert-line {
  min-height: 48px;
  display: grid;
  grid-template-columns: 26px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  border-radius: 8px;
  padding: 0 14px;
  background: #fff8df;
  color: #f19a1a;

  .el-icon {
    font-size: 16px;
  }

  strong {
    min-width: 0;
    color: #e68b0a;
    font-size: 14px;
    overflow-wrap: anywhere;
  }

  span {
    color: #aeb4c2;
    font-size: 12px;
  }
}

.root-cause-list {
  display: grid;
  gap: 12px;
  margin-top: 22px;

  div {
    display: flex;
    justify-content: space-between;
    gap: 16px;
    border-radius: 8px;
    padding: 14px;
    background: #fafbff;
  }

  span {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    color: #677086;
    font-size: 13px;
  }

  i {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--primary);
  }

  strong {
    color: #ec5f6b;
    font-size: 13px;
  }
}

.collaboration-body {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(180px, 0.8fr);
  gap: 22px;
  align-items: center;
}

.collab-chart {
  height: 190px;
  display: flex;
  align-items: end;
  gap: 20px;
  border-bottom: 1px solid #dfe3ed;
  padding: 0 18px 0 0;

  i {
    flex: 1;
    min-width: 20px;
    border-radius: 4px 4px 0 0;
    background: var(--primary);

    &:nth-child(2n) {
      opacity: 0.76;
    }
  }
}

.comment-panel {
  border: 1px solid #e9ebf3;
  border-radius: 8px;
  padding: 16px;
  background: #ffffff;

  b {
    display: block;
    color: var(--text-strong);
    font-size: 14px;
  }

  p {
    display: grid;
    grid-template-columns: 22px minmax(0, 1fr);
    gap: 8px;
    margin: 14px 0 0;
    color: #697186;
    font-size: 12px;
    line-height: 1.5;
  }

  span {
    width: 22px;
    height: 22px;
    border-radius: 50%;
    background: var(--blue);
  }

  p:last-child span {
    background: var(--teal);
  }
}

.scenario-section {
  background: #ffffff;
}

.scenario-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 18px;

  article {
    min-height: 196px;
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 24px;
    background: #ffffff;
    box-shadow: 0 12px 30px rgba(61, 58, 124, 0.05);
  }

  .el-icon {
    width: 38px;
    height: 38px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: 8px;
    background: var(--primary-soft);
    color: var(--primary);
    font-size: 19px;
  }

  b {
    display: block;
    margin-top: 18px;
    color: var(--text-strong);
    font-size: 18px;
  }

  p {
    margin: 10px 0 0;
    color: #7a8194;
    font-size: 13px;
    line-height: 1.72;
  }
}

.cta-section {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 30px;
  background: #f5f6fb;

  span {
    color: var(--primary);
    font-size: 13px;
    font-weight: 900;
  }

  h2 {
    max-width: 720px;
    margin: 10px 0 0;
    color: var(--text-strong);
    font-size: 32px;
    line-height: 1.25;
  }

  p {
    margin: 12px 0 0;
    color: #7a8194;
    font-size: 14px;
    line-height: 1.7;
  }

  .shuzhi-primary-button {
    flex: 0 0 auto;
  }
}

.shuzhi-footer {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(460px, 0.85fr);
  gap: 60px;
  padding: 64px max(40px, calc((100vw - 1180px) / 2)) 58px;
  background: #111224;
  color: #ffffff;
}

.footer-brand {
  max-width: 450px;

  .shuzhi-brand-mark {
    display: inline-grid;
  }

  strong {
    display: inline-block;
    margin-left: 10px;
    vertical-align: middle;
    color: #ffffff;
    font-size: 18px;
  }

  p {
    margin: 22px 0 0;
    color: #9ba2b8;
    font-size: 13px;
    line-height: 1.8;
  }
}

.footer-links {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 36px;

  b,
  span {
    display: block;
  }

  b {
    color: #ffffff;
    font-size: 14px;
  }

  span {
    margin-top: 14px;
    color: #8d94aa;
    font-size: 13px;
  }
}

.shuzhi-login-stage {
  position: relative;
  z-index: 1;
  min-height: calc(100vh - 64px);
  padding: 42px max(40px, calc((100vw - 1180px) / 2)) 0;
  background:
    linear-gradient(180deg, rgba(247, 248, 252, 0.68) 0, rgba(255, 255, 255, 0.96) 360px),
    #ffffff;

  &.is-trial-stage {
    .shuzhi-login-shell {
      min-height: 735px;
    }
  }
}

.shuzhi-login-shell {
  min-height: 590px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 460px;
  align-items: stretch;
  gap: 70px;
}

.shuzhi-login-story {
  min-width: 0;
  display: flex;
  flex-direction: column;
  padding-top: 0;

  h1 {
    max-width: 620px;
    margin: 24px 0 18px;
    color: var(--text-strong);
    font-size: 45px;
    line-height: 1.14;
    letter-spacing: 0;
    overflow-wrap: anywhere;
  }

  > p {
    max-width: 610px;
    margin: 0;
    color: #737b90;
    font-size: 16px;
    line-height: 1.8;
  }
}

.login-preview-card {
  max-width: 560px;
  margin-top: auto;
}

.login-preview-body {
  padding: 18px;
}

.login-preview-question {
  border: 1px solid #e9ebf3;
  border-radius: 8px;
  padding: 14px 16px;
  color: var(--text-strong);
  background: #fcfcff;
  font-size: 14px;
  font-weight: 900;
}

.login-preview-chart {
  height: 132px;
  display: flex;
  align-items: end;
  gap: 14px;
  margin-top: 16px;
  border: 1px solid #e9ebf3;
  border-radius: 8px;
  padding: 18px 20px 14px;
  background: #ffffff;

  i {
    flex: 1;
    min-width: 14px;
    border-radius: 4px 4px 0 0;
    background: var(--primary);

    &:nth-child(3n + 1) {
      background: var(--blue);
    }

    &:nth-child(3n + 2) {
      background: var(--teal);
    }
  }
}

.login-preview-note {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  margin-top: 16px;
  border-radius: 8px;
  padding: 12px 14px;
  background: var(--primary-soft);
  color: var(--primary);
  font-size: 13px;

  strong {
    color: var(--primary);
  }
}

.product-login-wrap {
  --theme-panel-bg: #ffffff;
  --theme-text-primary: #171927;
  --theme-text-secondary: #6f7689;
  --theme-text-tertiary: #9aa2b7;
  --theme-input-bg: #ffffff;
  --theme-input-border: #dfe3ed;
  align-self: stretch;
  display: flex;
  align-items: flex-end;
  padding-top: 36px;
  color-scheme: light;
}

.product-login-card {
  width: 100%;
  min-height: 552px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--theme-panel-bg);
  box-shadow: var(--shadow);
  padding: 42px 34px;

  &.is-trial-card {
    min-height: 706px;
    justify-content: flex-start;
  }
}

.product-login-card-head {
  width: 100%;
  margin-bottom: 28px;

  > span {
    display: inline-flex;
    margin-bottom: 10px;
    border-radius: 999px;
    padding: 5px 10px;
    background: var(--primary-soft);
    color: var(--primary);
    font-size: 12px;
    font-weight: 900;
  }

  h2 {
    margin: 0;
    color: var(--theme-text-primary);
    font-size: 26px;
    line-height: 1.3;
  }
}

.product-login-desc {
  margin: 10px 0 0;
  color: var(--theme-text-secondary);
  font-size: 13px;
  line-height: 1.75;
}

.login-form,
.default-login-tabs,
.trial-application-panel {
  width: 100%;
}

.product-login-form {
  width: 100%;
  color: var(--theme-text-primary);

  .product-login-field {
    margin-bottom: 16px;
  }

  :deep(.ed-form-item__content),
  :deep(.el-form-item__content) {
    color: var(--theme-text-primary);
  }

  :deep(.ed-form-item__label),
  :deep(.el-form-item__label) {
    margin-bottom: 8px;
    color: var(--theme-text-primary);
    font-size: 13px;
    font-weight: 800;
    line-height: 1.2;
  }

  :deep(.ed-input),
  :deep(.el-input) {
    --ed-input-bg-color: var(--theme-input-bg);
    --ed-input-border-color: var(--theme-input-border);
    --ed-input-clear-hover-color: var(--theme-text-secondary);
    --ed-input-focus-border-color: var(--primary);
    --ed-input-hover-border-color: var(--primary);
    --ed-input-icon-color: var(--theme-text-tertiary);
    --ed-input-placeholder-color: var(--theme-text-tertiary);
    --ed-input-text-color: var(--theme-text-primary);
    --el-input-bg-color: var(--theme-input-bg);
    --el-input-border-color: var(--theme-input-border);
    --el-input-clear-hover-color: var(--theme-text-secondary);
    --el-input-focus-border-color: var(--primary);
    --el-input-hover-border-color: var(--primary);
    --el-input-icon-color: var(--theme-text-tertiary);
    --el-input-placeholder-color: var(--theme-text-tertiary);
    --el-input-text-color: var(--theme-text-primary);
    color: var(--theme-text-primary);
  }

  :deep(.ed-input__wrapper),
  :deep(.el-input__wrapper) {
    height: 46px;
    border: 1px solid var(--theme-input-border);
    border-radius: 6px;
    box-shadow: none;
    padding: 0 13px;
    background: var(--theme-input-bg);
    transition:
      border-color 150ms ease,
      box-shadow 150ms ease;
  }

  :deep(.ed-input__wrapper.is-focus),
  :deep(.el-input__wrapper.is-focus),
  :deep(.ed-input__wrapper:hover),
  :deep(.el-input__wrapper:hover) {
    border-color: var(--primary);
    box-shadow: 0 0 0 3px rgba(98, 88, 246, 0.12);
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

  :deep(.ed-textarea__inner),
  :deep(.el-textarea__inner) {
    min-height: 92px;
    border-color: var(--theme-input-border);
    border-radius: 6px;
    box-shadow: none;
    background: var(--theme-input-bg);
    color: var(--theme-text-primary);
    font-size: 14px;
    line-height: 1.6;
    resize: none;
    transition:
      border-color 150ms ease,
      box-shadow 150ms ease;

    &:hover,
    &:focus {
      border-color: var(--primary);
      box-shadow: 0 0 0 3px rgba(98, 88, 246, 0.12);
    }
  }
}

.trial-application-form {
  .product-login-field {
    margin-bottom: 13px;
  }
}

.trial-application-tip {
  margin: -2px 0 0;
  color: var(--theme-text-tertiary);
  font-size: 12px;
  line-height: 1.6;
}

.trial-submit-result {
  display: flex;
  min-height: 430px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;

  .el-icon {
    color: var(--teal);
    font-size: 48px;
  }

  h3 {
    margin: 18px 0 10px;
    color: var(--theme-text-primary);
    font-size: 24px;
    line-height: 1.3;
  }

  p {
    max-width: 330px;
    margin: 0 0 28px;
    color: var(--theme-text-secondary);
    font-size: 14px;
    line-height: 1.8;
  }
}

.product-login-submit {
  width: 100%;
  height: 46px;
  border: 0;
  border-radius: 6px;
  background: var(--primary);
  color: #ffffff;
  font-size: 15px;
  font-weight: 900;
  text-shadow: none;
  -webkit-text-stroke-width: 0;
  cursor: pointer;
  box-shadow: 0 14px 30px rgba(98, 88, 246, 0.26);

  &:hover,
  &:focus {
    background: var(--primary-dark);
    color: #ffffff;
  }
}

.product-login-divider {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 14px 0 16px;
  color: var(--theme-text-tertiary);
  font-size: 12px;

  &::before,
  &::after {
    content: '';
    height: 1px;
    flex: 1;
    background: var(--line);
  }
}

.product-login-feishu {
  width: 100%;
  height: 46px;
  border-radius: 6px;
  border-color: #3370ff;
  color: #ffffff;
  background: #3370ff;
  font-size: 15px;
  font-weight: 900;
  text-shadow: none;
  -webkit-text-stroke-width: 0;
  box-shadow: 0 14px 28px rgba(51, 112, 255, 0.24);

  &:hover,
  &:focus {
    border-color: #245bdb;
    color: #ffffff;
    background: #245bdb;
  }
}

.product-login-feishu-content {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  line-height: 1;
  text-shadow: none;
  -webkit-text-stroke-width: 0;
}

.product-login-feishu-logo-wrap {
  width: 22px;
  height: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  background: #ffffff;
}

.product-login-feishu-logo {
  width: 18px;
  height: 18px;
  display: block;
}

.login-capability-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 18px;
  margin: 68px -40px 0;
  padding: 50px max(40px, calc((100vw - 1180px) / 2));
  background: var(--soft-bg);

  article {
    min-height: 170px;
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 22px;
    background: #ffffff;
  }

  .el-icon {
    width: 38px;
    height: 38px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: 8px;
    background: var(--primary-soft);
    color: var(--primary);
    font-size: 19px;
  }

  b {
    display: block;
    margin-top: 16px;
    color: var(--text-strong);
    font-size: 17px;
  }

  p {
    margin: 10px 0 0;
    color: #7a8194;
    font-size: 13px;
    line-height: 1.7;
  }
}

@media (max-width: 1180px) {
  .shuzhi-nav {
    padding: 0 28px;
  }

  .shuzhi-nav-links {
    display: none;
  }

  .shuzhi-hero,
  .shuzhi-login-shell {
    grid-template-columns: 1fr;
    gap: 44px;
  }

  .shuzhi-hero {
    padding: 54px 28px 62px;
  }

  .shuzhi-login-stage {
    padding: 54px 28px 0;
  }

  .product-login-wrap {
    max-width: 520px;
  }

  .flow-card-grid {
    gap: 20px;
  }

  .feature-row,
  .feature-row.reverse {
    grid-template-columns: 1fr;
    gap: 32px;
  }

  .feature-row.reverse .feature-copy {
    order: 0;
  }

  .scenario-grid,
  .login-capability-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .shuzhi-footer {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .shuzhi-nav {
    position: relative;
    min-height: auto;
    align-items: flex-start;
    padding: 16px 18px;
    gap: 12px;
  }

  .shuzhi-brand {
    min-width: 0;
    max-width: calc(100% - 126px);
  }

  .shuzhi-brand-copy span {
    display: none;
  }

  .shuzhi-nav-actions {
    margin-left: auto;
    gap: 8px;
  }

  .shuzhi-link-button {
    display: none;
  }

  .shuzhi-nav-primary {
    min-height: 34px;
    padding: 0 12px;
    font-size: 13px;
  }

  .shuzhi-hero {
    grid-template-columns: 1fr;
    padding: 34px 18px 44px;
  }

  .shuzhi-hero-copy h1 {
    margin-top: 24px;
    font-size: 38px;
    line-height: 1.16;
  }

  .shuzhi-hero-copy p,
  .shuzhi-login-story > p {
    font-size: 15px;
  }

  .shuzhi-hero-actions {
    align-items: stretch;
    flex-direction: column;
  }

  .shuzhi-primary-button,
  .shuzhi-secondary-button {
    width: 100%;
  }

  .shuzhi-trust-row {
    align-items: flex-start;

    strong {
      min-width: 0;
    }
  }

  .hero-dashboard-body {
    grid-template-columns: 1fr;
    padding: 12px;
  }

  .metric-grid {
    grid-template-columns: 1fr;
  }

  .metric-grid article {
    min-height: 0;
  }

  .trend-panel svg {
    height: 150px;
  }

  .home-section {
    padding: 42px 18px;
  }

  .section-heading {
    margin-bottom: 26px;

    &.center {
      text-align: left;
    }

    h2 {
      font-size: 28px;
    }

    p {
      margin-left: 0;
      margin-right: 0;
      font-size: 14px;
    }
  }

  .flow-card-grid,
  .scenario-grid,
  .login-capability-strip {
    grid-template-columns: 1fr;
    gap: 14px;
  }

  .flow-card-grid article,
  .scenario-grid article {
    min-height: 0;
  }

  .feature-row {
    padding: 26px 0;
  }

  .feature-copy h3 {
    font-size: 25px;
  }

  .builder-body,
  .collaboration-body {
    grid-template-columns: 1fr;
  }

  .builder-card.bars {
    min-height: 170px;
    grid-row: auto;
    gap: 10px;
    padding-left: 18px;
    padding-right: 18px;
  }

  .collab-chart {
    height: 150px;
    gap: 10px;
  }

  .alert-line {
    grid-template-columns: 22px minmax(0, 1fr);

    span {
      grid-column: 2;
    }
  }

  .root-cause-list div,
  .login-preview-note,
  .cta-section {
    align-items: flex-start;
    flex-direction: column;
  }

  .cta-section {
    display: flex;

    h2 {
      font-size: 25px;
    }
  }

  .shuzhi-footer {
    grid-template-columns: 1fr;
    gap: 34px;
    padding: 44px 18px;
  }

  .footer-links {
    grid-template-columns: 1fr;
    gap: 24px;
  }

  .shuzhi-login-stage {
    padding: 34px 18px 0;
  }

  .shuzhi-login-story h1 {
    font-size: 32px;
    line-height: 1.18;
  }

  .login-preview-card {
    margin-top: 32px;
  }

  .login-preview-chart {
    gap: 7px;
    padding: 14px 12px 10px;
  }

  .product-login-wrap {
    max-width: none;
  }

  .product-login-card {
    min-height: auto;
    padding: 28px 18px;
  }

  .login-capability-strip {
    margin: 42px -18px 0;
    padding: 36px 18px 42px;
  }
}
</style>
