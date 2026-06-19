<template>
  <main class="login-container power-login-page">
    <img v-if="storyBg" class="power-login-bg" :src="storyBg" alt="" />

    <header class="power-login-nav">
      <button type="button" class="power-login-brand" aria-label="返回主页" @click="goHomePage">
        <div class="power-login-brand-mark">
          <img v-if="loginBg" :src="loginBg" alt="" />
          <custom_small v-else-if="appearanceStore.themeColor !== 'default'"></custom_small>
          <img v-else :src="elexDataLogoUrl" alt="" />
        </div>
        <div class="power-login-brand-copy">
          <strong>{{ productName }}</strong>
          <span>ChatBI 数据问答与看板平台</span>
        </div>
      </button>

      <nav class="power-login-menu" aria-label="产品能力">
        <span v-for="item in navItems" :key="item">{{ item }}</span>
      </nav>

      <button v-if="isLoginFormPage" type="button" class="power-login-nav-action" @click="goHomePage">
        返回首页
      </button>
      <button v-else type="button" class="power-login-nav-action" @click="goLoginPage">登录</button>
    </header>

    <div v-if="!isLoginFormPage" class="home-announcement-strip">
      <span>星通智数平台主页</span>
      <strong>用 ChatBI、语义层和数据看板，把可信分析带给每个团队。</strong>
      <button type="button" @click="goLoginPage">进入工作台</button>
    </div>

    <section v-if="isLoginFormPage" class="power-login-account-page" aria-label="登录">
      <div class="account-login-shell">
        <section class="account-login-story">
          <p class="account-login-eyebrow">让可信数据分析从这里开始</p>
          <h1>登录 {{ productName }}，继续你的智能分析工作台</h1>
          <ul class="account-login-benefits">
            <li v-for="item in accountBenefits" :key="item">
              <i></i>
              <span>{{ item }}</span>
            </li>
          </ul>

          <div class="account-login-visual" aria-label="数据分析工作台预览">
            <div class="account-login-screen">
              <div class="account-login-screen-head">
                <span></span>
                <span></span>
                <span></span>
                <b>星通智数 · Smart Q&amp;A</b>
              </div>
              <div class="account-login-screen-body">
                <aside>
                  <span v-for="item in previewSources" :key="item"></span>
                </aside>
                <section>
                  <div class="account-login-prompt">本月核心指标变化如何？</div>
                  <div class="account-login-mini-metrics">
                    <div v-for="item in previewMetrics" :key="item.label">
                      <span>{{ item.label }}</span>
                      <strong>{{ item.value }}</strong>
                    </div>
                  </div>
                  <div class="account-login-mini-chart">
                    <span
                      v-for="item in previewBars"
                      :key="item"
                      :style="{ height: `${item}%` }"
                    ></span>
                  </div>
                </section>
              </div>
            </div>
            <div class="account-login-phone">
              <span></span>
              <strong>24</strong>
              <em>看板更新</em>
            </div>
          </div>
        </section>

        <aside class="product-login-wrap">
          <div class="product-login-card">
            <div class="product-login-card-head">
              <span>工作台入口</span>
              <h2>{{ $t('common.login') }}</h2>
              <p class="product-login-desc">
                使用你的账号进入 {{ productName }}，继续查询数据、管理数据看板和分析业务问题。
              </p>
            </div>

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
                <div class="product-login-divider">
                  <span>工作空间登录</span>
                </div>
                <el-button
                  class="product-login-feishu"
                  :loading="feishuLoading"
                  @click="startFeishuLogin"
                >
                  飞书登录
                </el-button>
              </div>
            </div>
          </div>
        </aside>
      </div>

      <section class="account-login-more" aria-label="平台能力">
        <h2>更多方式探索 {{ productName }}</h2>
        <div class="account-login-more-grid">
          <article v-for="item in accountExploreCards" :key="item.title">
            <span>{{ item.icon }}</span>
            <b>{{ item.title }}</b>
            <p>{{ item.desc }}</p>
          </article>
        </div>
      </section>
    </section>

    <section v-else class="power-login-hero">
      <div class="power-login-story">
        <div class="power-login-kicker">
          <span class="power-login-kicker-mark">BI</span>
          <span>语义层驱动的企业级智能分析</span>
        </div>

        <div class="power-login-headline">
          <h1>把数据资产、指标口径和业务问题，变成可追溯的分析答案。</h1>
          <p>{{ productSlogan }}</p>
        </div>

        <div class="power-login-actions">
          <button type="button" class="power-login-primary" @click="goLoginPage">进入 {{ productName }}</button>
          <span>数据源权限、语义层和 SQL 生成统一收敛</span>
        </div>

        <div class="power-login-status-row" aria-label="平台能力">
          <span v-for="item in statusChips" :key="item" class="power-login-status-chip">
            <i class="power-login-dot"></i>
            {{ item }}
          </span>
        </div>
      </div>

      <div class="home-hero-visual" aria-label="智能分析工作台预览">
        <div class="power-login-showcase" aria-label="智能分析工作台预览">
          <div class="power-login-window">
            <div class="power-login-window-bar">
              <span></span>
              <span></span>
              <span></span>
              <b>Smart Q&amp;A</b>
            </div>
            <div class="power-login-window-body">
              <aside class="power-login-sidebar">
                <span v-for="item in previewSources" :key="item"></span>
              </aside>
              <section class="power-login-report">
                <div class="power-login-question">
                  <span>业务提问</span>
                  <strong>本周各渠道转化表现如何？</strong>
                </div>

                <div class="power-login-metrics">
                  <div v-for="item in previewMetrics" :key="item.label" class="power-login-metric">
                    <span>{{ item.label }}</span>
                    <strong>{{ item.value }}</strong>
                    <em>{{ item.trend }}</em>
                  </div>
                </div>

                <div class="power-login-chart">
                  <span
                    v-for="item in previewBars"
                    :key="item"
                    :style="{ height: `${item}%` }"
                  ></span>
                </div>

                <div class="power-login-table">
                  <span v-for="item in previewRows" :key="item"></span>
                </div>
              </section>
            </div>
          </div>
        </div>

        <div class="home-hero-tile-grid">
          <article
            v-for="(item, index) in heroTiles"
            :key="item.title"
            :class="['home-hero-tile', { 'home-hero-tile-accent': index === 0 }]"
          >
            <span>{{ item.label }}</span>
            <strong>{{ item.title }}</strong>
            <p>{{ item.desc }}</p>
          </article>
        </div>
      </div>
    </section>

    <template v-if="!isLoginFormPage">
      <section class="home-section home-product-section" aria-label="核心能力">
        <div class="home-section-head home-section-head-center">
          <span>产品组合</span>
          <h2>探索 {{ productName }} 的智能分析能力</h2>
        </div>
        <div class="power-login-capabilities">
          <article v-for="item in capabilities" :key="item.title" class="power-login-capability">
            <span class="power-login-capability-icon">{{ item.icon }}</span>
            <b>{{ item.title }}</b>
            <p>{{ item.desc }}</p>
            <small>了解能力</small>
          </article>
        </div>
      </section>

      <section class="home-section home-proof-section" aria-label="平台指标">
        <div class="home-section-head home-section-head-center">
          <span>平台总览</span>
          <h2>从数据连接到业务答案，形成可运营的分析闭环</h2>
        </div>
        <div class="home-proof-grid">
          <article v-for="item in platformStats" :key="item.label">
            <strong>{{ item.value }}</strong>
            <span>{{ item.label }}</span>
            <p>{{ item.desc }}</p>
          </article>
        </div>
      </section>

      <section class="home-section home-flow-section" aria-label="分析工作流">
        <div class="home-section-head">
          <span>工作流</span>
          <h2>让每一次问数都沿着同一套可信路径前进</h2>
        </div>
        <div class="home-flow-grid">
          <article v-for="(item, index) in workflowSteps" :key="item.title">
            <em>{{ String(index + 1).padStart(2, '0') }}</em>
            <b>{{ item.title }}</b>
            <p>{{ item.desc }}</p>
          </article>
        </div>
      </section>

      <section class="home-section home-ai-section" aria-label="可信 AI 分析">
        <div class="home-ai-copy">
          <span>AI 分析工作台</span>
          <h2>让 AI 在正确的数据上下文里回答业务问题</h2>
          <p>
            星通智数把数据源权限、字段元数据、语义层和训练样例放在同一条路径上，
            让自然语言问数更接近真实业务场景中的数据治理方式。
          </p>
          <div class="home-ai-badges">
            <span v-for="item in homeAiBadges" :key="item">{{ item }}</span>
          </div>
        </div>
        <div class="home-ai-visual" aria-hidden="true">
          <div class="home-ai-ring">
            <span>TRUSTED</span>
            <strong>AI BI</strong>
            <em>Semantic Layer</em>
          </div>
          <div class="home-ai-lines">
            <i></i>
            <i></i>
            <i></i>
          </div>
        </div>
      </section>

      <section class="home-section home-semantic-section" aria-label="语义层能力">
        <div class="home-section-copy">
          <span>语义层</span>
          <h2>把指标口径、术语和 SQL 样例沉淀成团队共享资产</h2>
          <p>
            星通智数优先通过数据源范围、字段元数据、术语、训练样例和推荐问题来约束分析行为，
            让 Smart Q&amp;A、分析助手和看板都沿用同一套可信上下文。
          </p>
        </div>
        <div class="home-semantic-list">
          <article v-for="item in semanticHighlights" :key="item.title">
            <span>{{ item.icon }}</span>
            <div>
              <b>{{ item.title }}</b>
              <p>{{ item.desc }}</p>
            </div>
          </article>
        </div>
      </section>

      <section class="home-section home-governance-section" aria-label="数据源与权限治理">
        <div class="home-section-head">
          <span>治理能力</span>
          <h2>先确认上下文和权限，再生成 SQL 与图表</h2>
        </div>
        <div class="home-governance-layout">
          <div class="home-governance-panel">
            <div v-for="item in governanceItems" :key="item.title" class="home-governance-row">
              <i></i>
              <div>
                <b>{{ item.title }}</b>
                <p>{{ item.desc }}</p>
              </div>
            </div>
          </div>
          <div class="home-governance-preview" aria-hidden="true">
            <span>Datasource Context</span>
            <strong>SLG BI Mock</strong>
            <p>已授权表 18 · 语义记录 126 · 示例 SQL 42</p>
            <div>
              <em></em>
              <em></em>
              <em></em>
            </div>
          </div>
        </div>
      </section>

      <section class="home-section home-dashboard-section" aria-label="看板场景">
        <div class="home-section-head">
          <span>看板场景</span>
          <h2>从一次问答延展为长期跟踪的业务看板</h2>
        </div>
        <div class="home-dashboard-grid">
          <article v-for="item in dashboardScenarios" :key="item.title">
            <span>{{ item.icon }}</span>
            <b>{{ item.title }}</b>
            <p>{{ item.desc }}</p>
          </article>
        </div>
      </section>

      <section class="home-section home-story-section" aria-label="客户场景">
        <div class="home-section-head home-section-head-center">
          <span>团队场景</span>
          <h2>{{ productName }} 帮助团队把数据工作转向可信 AI</h2>
        </div>
        <div class="home-story-layout">
          <article class="home-story-feature">
            <span>Smart Q&amp;A</span>
            <h3>从“帮我取数”走向“共同沉淀分析资产”</h3>
            <p>
              业务用户可以直接提出问题，平台在授权数据源内生成 SQL 和图表；
              数据团队则把高频问题、指标口径和查询样例沉淀到语义层。
            </p>
            <div class="home-story-chart" aria-hidden="true">
              <i v-for="item in previewBars" :key="item" :style="{ height: `${item}%` }"></i>
            </div>
          </article>
          <div class="home-story-cards">
            <article v-for="item in customerStories" :key="item.title">
              <span>{{ item.label }}</span>
              <b>{{ item.title }}</b>
              <p>{{ item.desc }}</p>
            </article>
          </div>
        </div>
      </section>

      <section class="home-section home-resource-section" aria-label="资源中心">
        <div class="home-section-head home-section-head-center">
          <span>资源中心</span>
          <h2>围绕数据问题、语义治理和看板运营持续进化</h2>
        </div>
        <div class="home-resource-grid">
          <article v-for="item in resourceCards" :key="item.title">
            <span>{{ item.tag }}</span>
            <b>{{ item.title }}</b>
            <p>{{ item.desc }}</p>
            <small>{{ item.action }}</small>
          </article>
        </div>
      </section>

      <section class="home-section home-cta-section" aria-label="开始使用">
        <div>
          <span>开始使用</span>
          <h2>进入 {{ productName }}，把业务问题直接连接到可信数据</h2>
          <p>从自然语言问数开始，逐步沉淀语义层、推荐问题和数据看板。</p>
        </div>
        <button type="button" class="power-login-primary" @click="goLoginPage">登录工作台</button>
      </section>
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
import { toLoginSuccess } from '@/utils/utils'
import { AuthApi } from '@/api/login'
import { ElMessage } from 'element-plus-secondary'

const router = useRouter()
const userStore = useUserStore()
const appearanceStore = useAppearanceStoreWithOut()
const { t } = useI18n()
const loginForm = ref({
  username: '',
  password: '',
})
const feishuLoading = ref(false)
const feishuStatus = ref<{
  enabled: boolean
  authorize_url?: string | null
}>({
  enabled: false,
  authorize_url: null,
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

const navItems = ['智能问数', '语义层', '数据看板', '权限治理']

const capabilities = [
  {
    icon: '问',
    title: '自然语言报表',
    desc: '面向业务问题生成查询、解释结果并保留可追溯上下文。',
  },
  {
    icon: '源',
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
]

const statusChips = ['数据源权限优先', '语义层统一口径', 'SQL 可追溯', '图表与看板联动']
const previewSources = ['数据源', '语义层', '权限', '看板']
const previewMetrics = [
  { label: '查询命中', value: '96%', trend: '+8.2%' },
  { label: '响应时间', value: '1.8s', trend: '-21%' },
  { label: '看板更新', value: '24', trend: '+5' },
]
const previewBars = [48, 64, 42, 76, 58, 88, 72, 94, 67]
const previewRows = ['渠道', '指标', '趋势', '权限']
const heroTiles = [
  {
    label: 'Semantic',
    title: '统一口径',
    desc: '术语、字段、SQL 样例和推荐问题集中维护。',
  },
  {
    label: 'Governance',
    title: '先校验权限',
    desc: '当前数据源与授权范围优先于自然语言描述。',
  },
  {
    label: 'Dashboard',
    title: '持续看板',
    desc: '把高频问答沉淀为可追踪的业务视图。',
  },
]
const homeAiBadges = ['数据源上下文', '语义层检索', 'SQL 可复核', '图表联动']
const accountBenefits = [
  '继续使用自然语言查询数据、追问结果和生成图表。',
  '统一连接数据源、语义口径、权限校验和看板资产。',
  '在同一个工作台管理推荐问题、术语、SQL 示例和数据看板。',
  '面向工作空间团队沉淀可信分析过程，减少重复沟通和口径偏差。',
]
const accountExploreCards = [
  {
    icon: '问',
    title: '智能问数',
    desc: '通过业务语言发起查询，自动生成 SQL、解释结果并沉淀上下文。',
  },
  {
    icon: '径',
    title: '语义层治理',
    desc: '集中维护指标口径、术语、训练样例和推荐问题，统一分析边界。',
  },
  {
    icon: '板',
    title: '数据看板',
    desc: '围绕业务主题组织图表和看板，持续跟踪核心数据变化。',
  },
]
const platformStats = [
  {
    value: '统一',
    label: '数据上下文',
    desc: '围绕当前数据源、权限、表字段和语义记录组织分析范围。',
  },
  {
    value: '可追溯',
    label: 'SQL 与图表',
    desc: '保留查询路径、生成过程和结果解释，方便复核与迭代。',
  },
  {
    value: '共享',
    label: '语义资产',
    desc: '术语、推荐问题、训练样例和自定义提示可被多助手复用。',
  },
]
const workflowSteps = [
  {
    title: '选择数据源',
    desc: '先确认当前上下文和授权范围，避免跨项目、跨租户或跨数据源误用。',
  },
  {
    title: '理解业务问题',
    desc: '结合字段元数据、术语和 SQL 示例识别指标、维度、时间窗口和筛选条件。',
  },
  {
    title: '生成查询与图表',
    desc: '生成可执行 SQL，返回数据后选择合适图表，并支持继续追问。',
  },
  {
    title: '沉淀为资产',
    desc: '将高频问题、可靠口径和看板内容沉淀到语义层与分析工作台。',
  },
]
const semanticHighlights = [
  {
    icon: '词',
    title: '术语与口径',
    desc: '定义指标名称、业务别名和计算口径，让不同团队使用同一套语言。',
  },
  {
    icon: '例',
    title: '训练 SQL',
    desc: '用数据源范围内的样例指导 SQL 生成，而不是把业务逻辑写死在代码里。',
  },
  {
    icon: '问',
    title: '推荐问题',
    desc: '按数据源维护可复用的问题入口，帮助业务用户快速开始探索。',
  },
]
const governanceItems = [
  {
    title: '数据源上下文优先',
    desc: '当前选择的数据源和用户授权范围优先于用户自然语言描述。',
  },
  {
    title: '组织与角色边界',
    desc: '结合租户、项目、角色和数据源权限控制分析入口。',
  },
  {
    title: '安全查询路径',
    desc: 'SQL 生成、执行和图表呈现都围绕被授权元数据展开。',
  },
]
const dashboardScenarios = [
  {
    icon: '经',
    title: '经营复盘',
    desc: '把核心指标、趋势变化和异常问题汇总到可持续跟踪的看板中。',
  },
  {
    icon: '运',
    title: '运营分析',
    desc: '围绕渠道、活动、用户行为或业务流程快速提出问题并生成图表。',
  },
  {
    icon: '管',
    title: '管理驾驶舱',
    desc: '统一组织跨部门指标与权限，让管理者看到可信且一致的数据视图。',
  },
]
const customerStories = [
  {
    label: '业务团队',
    title: '少等取数，多做判断',
    desc: '围绕授权数据源直接提问，快速获得图表、解释和可继续追问的上下文。',
  },
  {
    label: '数据团队',
    title: '把口径沉淀下来',
    desc: '把反复沟通的指标解释、SQL 示例和推荐问题沉淀到语义层，降低重复支持成本。',
  },
  {
    label: '管理团队',
    title: '看同一套可信视图',
    desc: '通过看板和权限体系组织跨部门指标，让经营复盘建立在一致数据基础上。',
  },
]
const resourceCards = [
  {
    tag: '产品实践',
    title: '用自然语言开始问数',
    desc: '从业务问题出发，连接数据源、生成 SQL、解释结果并自动呈现图表。',
    action: '查看路径',
  },
  {
    tag: '治理方法',
    title: '把指标口径放进语义层',
    desc: '用术语、字段说明和训练 SQL 约束分析行为，让多个助手共享同一上下文。',
    action: '了解语义层',
  },
  {
    tag: '看板运营',
    title: '从一次追问到长期看板',
    desc: '把高频问题、核心指标和异常跟踪沉淀为团队可复用的数据看板。',
    action: '探索看板',
  },
]

const rules = {
  username: [{ required: true, message: t('common.your_account_email_address'), trigger: 'blur' }],
  password: [{ required: true, message: t('common.the_correct_password'), trigger: 'blur' }],
}

const loginFormRef = ref()
const isLoginFormPage = computed(() => {
  return router.currentRoute.value.path === '/admin-login' || router.currentRoute.value.query.view === 'account'
})

const goLoginPage = () => {
  const query = { ...router.currentRoute.value.query }
  delete query.code
  delete query.state
  router.push({ path: '/login', query: { ...query, view: 'account' } })
}

const goHomePage = () => {
  const query = { ...router.currentRoute.value.query }
  delete query.view
  delete query.code
  delete query.state
  router.push({ path: '/login', query })
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
  if (userStore.isSystemAdminUser) {
    await router.push('/system/tenant')
    return
  }
  toLoginSuccess(router)
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
  ElMessage.warning('飞书登录未启用或配置未完成')
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

onMounted(async () => {
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
  box-sizing: border-box;
  min-height: 100vh;
  overflow-x: hidden;
  overflow-y: auto;
}

.power-login-page {
  position: relative;
  overflow-x: hidden;
  color: #111827;
  color-scheme: light;
  background:
    linear-gradient(180deg, rgba(232, 249, 244, 0.82) 0, rgba(255, 255, 255, 0.98) 430px),
    linear-gradient(100deg, rgba(0, 166, 126, 0.08), rgba(0, 120, 212, 0.07) 54%, rgba(242, 200, 17, 0.08)),
    #ffffff;
}

.power-login-bg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 520px;
  object-fit: cover;
  opacity: 0.08;
  pointer-events: none;
}

.power-login-nav {
  position: relative;
  z-index: 20;
  display: flex;
  align-items: center;
  gap: 32px;
  min-height: 68px;
  padding: 0 56px;
  border-bottom: 1px solid rgba(17, 24, 39, 0.1);
  background: rgba(255, 255, 255, 0.94);
  backdrop-filter: blur(16px);
}

.power-login-brand {
  display: inline-flex;
  align-items: center;
  min-width: 260px;
  gap: 12px;
  border: 0;
  padding: 0;
  background: transparent;
  cursor: pointer;
  text-align: left;
}

.power-login-brand-mark {
  width: 42px;
  height: 42px;
  flex: 0 0 42px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  background: #ffffff;
  box-shadow: 0 8px 24px rgba(17, 24, 39, 0.12);

  img {
    width: 34px;
    height: 34px;
    object-fit: contain;
  }

  :deep(svg) {
    width: 30px;
    height: 30px;
  }
}

.power-login-brand-copy {
  min-width: 0;

  strong {
    display: block;
    color: #111827;
    font-size: 18px;
    line-height: 1.2;
  }

  span {
    display: block;
    margin-top: 3px;
    color: #5d6675;
    font-size: 12px;
    line-height: 1.25;
  }
}

.power-login-menu {
  display: flex;
  align-items: center;
  gap: 26px;
  flex: 1;
  color: #374151;
  font-size: 14px;

  span {
    white-space: nowrap;
  }
}

.power-login-nav-action,
.power-login-primary {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: 4px;
  background: #111827;
  color: #ffffff;
  cursor: pointer;
  font-weight: 700;
  transition:
    background 160ms ease,
    transform 160ms ease,
    box-shadow 160ms ease;

  &:hover,
  &:focus {
    background: #000000;
    box-shadow: 0 8px 18px rgba(17, 24, 39, 0.18);
  }

  &:active {
    transform: translateY(1px);
  }
}

.power-login-nav-action {
  height: 36px;
  padding: 0 16px;
  font-size: 13px;
}

.home-announcement-strip {
  position: relative;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
  min-height: 44px;
  padding: 8px 56px;
  background: #003b5c;
  color: #ffffff;
  text-align: center;

  span {
    flex: 0 0 auto;
    border-radius: 3px;
    padding: 4px 8px;
    background: #10b981;
    color: #ffffff;
    font-size: 12px;
    font-weight: 900;
  }

  strong {
    min-width: 0;
    color: #ffffff;
    font-size: 13px;
    line-height: 1.5;
  }

  button {
    flex: 0 0 auto;
    border: 1px solid rgba(255, 255, 255, 0.52);
    border-radius: 4px;
    padding: 6px 12px;
    background: transparent;
    color: #ffffff;
    cursor: pointer;
    font-size: 12px;
    font-weight: 800;

    &:hover,
    &:focus {
      background: rgba(255, 255, 255, 0.12);
    }
  }
}

.power-login-hero {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: minmax(0, 0.92fr) minmax(470px, 1.08fr);
  align-items: center;
  gap: 46px;
  max-width: 1280px;
  margin: 0 auto;
  padding: 64px 56px 72px;
}

.power-login-story {
  min-width: 0;
  max-width: 590px;
}

.power-login-kicker {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  color: #2f2f2f;
  font-size: 14px;
  font-weight: 700;
}

.power-login-kicker-mark {
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  border-radius: 4px;
  background: #0aa678;
  color: #111827;
  font-size: 14px;
  font-weight: 900;
  color: #ffffff;
  box-shadow: inset -8px 0 0 rgba(17, 24, 39, 0.08);
}

.power-login-headline {
  max-width: 590px;
  margin-top: 26px;

  h1 {
    margin: 0;
    color: #073b4c;
    font-size: 54px;
    line-height: 1.04;
    letter-spacing: 0;
  }

  p {
    max-width: 560px;
    margin: 20px 0 0;
    color: #4b5563;
    font-size: 18px;
    line-height: 1.8;
  }
}

.power-login-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
  margin-top: 28px;

  span {
    color: #5d6675;
    font-size: 13px;
  }
}

.power-login-primary {
  height: 44px;
  padding: 0 22px;
  background: #0aa678;
  color: #ffffff;
  font-size: 14px;

  &:hover,
  &:focus {
    background: #008866;
    color: #ffffff;
  }
}

.power-login-status-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  max-width: 560px;
  margin-top: 30px;
  color: #374151;
  font-size: 13px;
}

.power-login-status-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  padding: 10px 12px;
  border: 1px solid rgba(17, 24, 39, 0.12);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.72);
  white-space: nowrap;
}

.power-login-dot {
  width: 8px;
  height: 8px;
  flex: 0 0 8px;
  border-radius: 50%;
  background: #0aa678;
  box-shadow: 0 0 0 3px rgba(10, 166, 120, 0.18);
}

.home-hero-visual {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 168px;
  gap: 16px;
  align-items: stretch;
  min-width: 0;
}

.power-login-showcase {
  min-width: 0;
  max-width: none;
  margin-top: 0;
}

.power-login-window {
  overflow: hidden;
  border: 1px solid rgba(17, 24, 39, 0.12);
  border-radius: 8px;
  background: #ffffff;
  box-shadow: 0 30px 70px rgba(17, 24, 39, 0.16);
}

.power-login-window-bar {
  display: flex;
  align-items: center;
  gap: 7px;
  height: 38px;
  padding: 0 14px;
  border-bottom: 1px solid #e5e7eb;
  background: #f7f8fa;

  span {
    width: 9px;
    height: 9px;
    border-radius: 50%;
    background: #c8ced8;
  }

  b {
    margin-left: 8px;
    color: #4b5563;
    font-size: 12px;
  }
}

.power-login-window-body {
  display: grid;
  grid-template-columns: 108px minmax(0, 1fr);
  min-height: 360px;
}

.power-login-sidebar {
  display: grid;
  align-content: start;
  gap: 12px;
  padding: 20px 16px;
  border-right: 1px solid #e5e7eb;
  background: #fbfbfd;

  span {
    height: 12px;
    border-radius: 3px;
    background: #d8dce5;

    &:first-child {
      width: 72px;
      background: #f2c811;
    }

    &:nth-child(2) {
      width: 56px;
    }

    &:nth-child(3) {
      width: 80px;
    }

    &:nth-child(4) {
      width: 62px;
    }
  }
}

.power-login-report {
  min-width: 0;
  padding: 22px;
}

.power-login-question {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  min-height: 52px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 0 16px;
  background: #ffffff;

  span {
    color: #6b7280;
    font-size: 12px;
  }

  strong {
    color: #111827;
    font-size: 15px;
  }
}

.power-login-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 14px;
}

.power-login-metric {
  min-height: 82px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 12px;
  background: #ffffff;

  span,
  em {
    display: block;
    color: #6b7280;
    font-size: 12px;
    font-style: normal;
  }

  strong {
    display: block;
    margin: 8px 0 4px;
    color: #111827;
    font-size: 24px;
    line-height: 1;
  }

  em {
    color: #107c10;
  }
}

.power-login-chart {
  display: flex;
  align-items: end;
  gap: 10px;
  height: 118px;
  margin-top: 14px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 16px 18px 14px;
  background:
    linear-gradient(#f3f4f6 1px, transparent 1px),
    #ffffff;
  background-size: 100% 28px;

  span {
    flex: 1;
    min-width: 10px;
    border-radius: 3px 3px 0 0;
    background: #f2c811;

    &:nth-child(3n + 1) {
      background: #0078d4;
    }

    &:nth-child(3n + 2) {
      background: #0aa678;
    }
  }
}

.power-login-table {
  display: grid;
  grid-template-columns: 1fr 1.2fr 0.9fr 0.8fr;
  gap: 10px;
  margin-top: 14px;

  span {
    height: 12px;
    border-radius: 3px;
    background: #e5e7eb;

    &:first-child {
      background: #c8ced8;
    }
  }
}

.home-hero-tile-grid {
  display: grid;
  grid-template-rows: repeat(3, minmax(0, 1fr));
  gap: 16px;
  min-width: 0;
}

.home-hero-tile {
  min-width: 0;
  border: 1px solid #dce3ec;
  border-radius: 8px;
  padding: 16px;
  background: #ffffff;
  box-shadow: 0 16px 34px rgba(17, 24, 39, 0.08);

  span {
    color: #0078d4;
    font-size: 11px;
    font-weight: 900;
  }

  strong {
    display: block;
    margin-top: 10px;
    color: #073b4c;
    font-size: 19px;
    line-height: 1.2;
  }

  p {
    margin: 8px 0 0;
    color: #4b5563;
    font-size: 12px;
    line-height: 1.55;
  }
}

.home-hero-tile-accent {
  border-color: #0aa678;
  background: #003b5c;

  span,
  p {
    color: #d7f8ef;
  }

  strong {
    color: #ffffff;
  }
}

.product-login-wrap {
  --theme-panel-bg: #ffffff;
  --theme-panel-bg-soft: #f5f7fb;
  --theme-control-bg: #ffffff;
  --theme-control-hover-bg: #ffffff;
  --theme-hover-bg: #fff7d6;
  --theme-active-bg: #fff0ad;
  --theme-shell-border: #d1d5db;
  --theme-text-primary: #111827;
  --theme-text-secondary: #4b5563;
  --theme-text-tertiary: #6b7280;
  --theme-input-bg: #ffffff;
  --theme-input-border: #cbd5e1;
  --theme-card-shadow: 0 18px 46px rgba(17, 24, 39, 0.16);
  align-self: start;
  color-scheme: light;
}

.power-login-account-page {
  position: relative;
  z-index: 1;
  padding: 72px 56px 0;

  .product-login-wrap {
    width: 540px;
    flex: 0 0 540px;
    display: flex;
  }
}

.account-login-shell {
  display: grid;
  grid-template-columns: minmax(0, 560px) 540px;
  align-items: start;
  justify-content: center;
  gap: 64px;
  max-width: 1220px;
  margin: 0 auto;
}

.account-login-story {
  min-width: 0;
  padding-top: 34px;
}

.account-login-eyebrow {
  margin: 0;
  color: #4b5563;
  font-size: 14px;
  font-weight: 800;
  line-height: 1.4;
}

.account-login-story {
  h1 {
    max-width: 560px;
    margin: 10px 0 18px;
    color: #0b1f44;
    font-size: 44px;
    line-height: 1.12;
    letter-spacing: 0;
  }
}

.account-login-benefits {
  display: grid;
  gap: 12px;
  margin: 0;
  padding: 0;
  list-style: none;
  color: #4b5563;
  font-size: 14px;
  line-height: 1.55;

  li {
    display: grid;
    grid-template-columns: 20px minmax(0, 1fr);
    gap: 10px;
    align-items: start;
  }

  i {
    position: relative;
    width: 18px;
    height: 18px;
    display: inline-block;

    &::before {
      content: '';
      position: absolute;
      left: 4px;
      top: 2px;
      width: 8px;
      height: 12px;
      border: solid #0078d4;
      border-width: 0 2px 2px 0;
      transform: rotate(45deg);
    }
  }
}

.account-login-visual {
  position: relative;
  width: min(520px, 100%);
  margin-top: 46px;
  padding: 0 62px 34px 12px;
}

.account-login-screen {
  overflow: hidden;
  border: 1px solid #d9e1ec;
  border-radius: 8px;
  background: #ffffff;
  box-shadow: 0 24px 50px rgba(12, 32, 68, 0.14);
}

.account-login-screen-head {
  display: flex;
  align-items: center;
  gap: 7px;
  height: 34px;
  padding: 0 12px;
  border-bottom: 1px solid #e5e7eb;
  background: #f8fafc;

  span {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #cbd5e1;
  }

  b {
    margin-left: 8px;
    color: #475569;
    font-size: 12px;
  }
}

.account-login-screen-body {
  display: grid;
  grid-template-columns: 92px minmax(0, 1fr);
  min-height: 260px;

  aside {
    display: grid;
    align-content: start;
    gap: 12px;
    padding: 18px 14px;
    border-right: 1px solid #e5e7eb;
    background: #f8fafc;

    span {
      height: 12px;
      border-radius: 3px;
      background: #cfd7e3;

      &:first-child {
        width: 64px;
        background: #f2c811;
      }

      &:nth-child(2) {
        width: 48px;
      }

      &:nth-child(3) {
        width: 68px;
      }

      &:nth-child(4) {
        width: 56px;
      }
    }
  }

  section {
    min-width: 0;
    padding: 18px;
  }
}

.account-login-prompt {
  min-height: 44px;
  display: flex;
  align-items: center;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 0 14px;
  color: #0f172a;
  font-size: 14px;
  font-weight: 800;
}

.account-login-mini-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-top: 12px;

  div {
    border: 1px solid #e5e7eb;
    border-radius: 6px;
    padding: 10px;
    background: #ffffff;
  }

  span {
    display: block;
    color: #64748b;
    font-size: 11px;
  }

  strong {
    display: block;
    margin-top: 6px;
    color: #0f172a;
    font-size: 22px;
    line-height: 1;
  }
}

.account-login-mini-chart {
  display: flex;
  align-items: end;
  gap: 7px;
  height: 94px;
  margin-top: 12px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 14px 14px 10px;
  background:
    linear-gradient(#f1f5f9 1px, transparent 1px),
    #ffffff;
  background-size: 100% 24px;

  span {
    flex: 1;
    min-width: 8px;
    border-radius: 3px 3px 0 0;
    background: #f2c811;

    &:nth-child(3n + 1) {
      background: #0078d4;
    }

    &:nth-child(3n + 2) {
      background: #10b981;
    }
  }
}

.account-login-phone {
  position: absolute;
  right: 8px;
  bottom: 0;
  width: 86px;
  height: 150px;
  border: 1px solid #d9e1ec;
  border-radius: 14px;
  padding: 18px 12px;
  background: #ffffff;
  box-shadow: 0 18px 38px rgba(12, 32, 68, 0.18);

  span {
    display: block;
    width: 34px;
    height: 8px;
    margin: 0 auto 28px;
    border-radius: 999px;
    background: #d9e1ec;
  }

  strong {
    display: block;
    color: #0b1f44;
    font-size: 30px;
    line-height: 1;
    text-align: center;
  }

  em {
    display: block;
    margin-top: 7px;
    color: #64748b;
    font-size: 12px;
    font-style: normal;
    text-align: center;
  }
}

.account-login-more {
  margin: 82px -56px 0;
  padding: 54px 56px 64px;
  background: #f7f8fa;

  h2 {
    margin: 0 0 34px;
    color: #0b1f44;
    font-size: 32px;
    line-height: 1.2;
    text-align: center;
  }
}

.account-login-more-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 28px;
  max-width: 960px;
  margin: 0 auto;

  article {
    border-top: 1px solid #d9e1ec;
    padding-top: 22px;
  }

  span {
    width: 34px;
    height: 34px;
    display: grid;
    place-items: center;
    border-radius: 4px;
    background: #f2c811;
    color: #0b1f44;
    font-size: 13px;
    font-weight: 900;
  }

  b {
    display: block;
    margin-top: 18px;
    color: #0b1f44;
    font-size: 20px;
  }

  p {
    margin: 10px 0 0;
    color: #4b5563;
    font-size: 13px;
    line-height: 1.7;
  }
}

.product-login-card {
  width: 100%;
  min-height: 610px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  border: 1px solid var(--theme-shell-border);
  border-radius: 8px;
  background: var(--theme-panel-bg);
  box-shadow: var(--theme-card-shadow);
  padding: 42px 34px;
}

.product-login-card-head {
  margin-bottom: 30px;

  > span {
    display: inline-block;
    margin-bottom: 10px;
    color: #8a6d00;
    font-size: 12px;
    font-weight: 800;
  }

  h2 {
    margin: 0;
    color: var(--theme-text-primary);
    font-size: 24px;
    line-height: 1.3;
  }
}

.product-login-desc {
  max-width: 420px;
  margin: 10px 0 0;
  color: var(--theme-text-secondary);
  font-size: 13px;
  line-height: 1.8;
}

.product-login-form {
  width: min(100%, 420px);
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
    --ed-input-focus-border-color: #111827;
    --ed-input-hover-border-color: #111827;
    --ed-input-icon-color: var(--theme-text-tertiary);
    --ed-input-placeholder-color: var(--theme-text-tertiary);
    --ed-input-text-color: var(--theme-text-primary);
    --el-input-bg-color: var(--theme-input-bg);
    --el-input-border-color: var(--theme-input-border);
    --el-input-clear-hover-color: var(--theme-text-secondary);
    --el-input-focus-border-color: #111827;
    --el-input-hover-border-color: #111827;
    --el-input-icon-color: var(--theme-text-tertiary);
    --el-input-placeholder-color: var(--theme-text-tertiary);
    --el-input-text-color: var(--theme-text-primary);
    color: var(--theme-text-primary);
  }

  :deep(.ed-input__wrapper),
  :deep(.el-input__wrapper) {
    height: 44px;
    border: 1px solid var(--theme-input-border);
    border-radius: 4px;
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
    border-color: #111827;
    box-shadow: 0 0 0 3px rgba(242, 200, 17, 0.34);
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
  height: 44px;
  border: 0;
  border-radius: 4px;
  background: #111827;
  color: #ffffff;
  font-size: 14px;
  font-weight: 800;
  cursor: pointer;
  box-shadow: 0 14px 28px rgba(17, 24, 39, 0.18);

  &:hover,
  &:focus {
    background: #000000;
    color: #ffffff;
  }
}

.product-login-divider {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 8px 0 14px;
  color: var(--theme-text-tertiary);
  font-size: 12px;

  &::before,
  &::after {
    content: '';
    height: 1px;
    flex: 1;
    background: var(--theme-shell-border);
  }
}

.product-login-feishu {
  width: 100%;
  height: 44px;
  border-radius: 4px;
  border-color: #cbd5e1;
  color: #111827;
  background: #ffffff;
  font-size: 14px;
  font-weight: 800;

  &:hover,
  &:focus {
    border-color: #111827;
    color: #111827;
    background: #fffdf2;
  }
}

.power-login-capabilities {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  margin: 0;
}

.power-login-capability {
  min-height: 206px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 22px;
  background: #ffffff;
  box-shadow: 0 12px 28px rgba(17, 24, 39, 0.06);

  b {
    display: block;
    margin: 18px 0 10px;
    color: #073b4c;
    font-size: 18px;
    line-height: 1.3;
  }

  p {
    min-height: 64px;
    margin: 0;
    color: #4b5563;
    font-size: 13px;
    line-height: 1.7;
  }

  small {
    display: inline-block;
    margin-top: 18px;
    color: #0078d4;
    font-size: 12px;
    font-weight: 900;
  }
}

.power-login-capability-icon {
  width: 32px;
  height: 32px;
  display: grid !important;
  place-items: center;
  border-radius: 4px;
  color: #111827 !important;
  background: #f2c811;
  font-size: 13px !important;
  font-weight: 900;
}

.home-section {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: none;
  margin: 0;
  padding: 64px max(56px, calc((100vw - 1280px) / 2));
}

.home-section-head {
  max-width: 760px;
  margin-bottom: 28px;

  > span {
    display: inline-block;
    margin-bottom: 10px;
    color: #8a6d00;
    font-size: 12px;
    font-weight: 900;
  }

  h2 {
    margin: 0;
    color: #0b1f44;
    font-size: 32px;
    line-height: 1.24;
    letter-spacing: 0;
  }
}

.home-section-head-center {
  max-width: 760px;
  margin-right: auto;
  margin-left: auto;
  text-align: center;
}

.home-product-section {
  padding-top: 74px;
  background: #ffffff;
}

.home-proof-section {
  background: #f7fafb;
}

.home-proof-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 18px;

  article {
    min-height: 160px;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 22px;
    background: #ffffff;
    box-shadow: 0 12px 28px rgba(17, 24, 39, 0.06);
  }

  strong {
    display: block;
    color: #0b1f44;
    font-size: 30px;
    line-height: 1;
  }

  span {
    display: block;
    margin-top: 12px;
    color: #111827;
    font-size: 15px;
    font-weight: 800;
  }

  p {
    margin: 8px 0 0;
    color: #4b5563;
    font-size: 13px;
    line-height: 1.7;
  }
}

.home-flow-section {
  background: linear-gradient(180deg, rgba(247, 248, 250, 0) 0, #f7f8fa 100%);
}

.home-flow-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;

  article {
    border-top: 3px solid #f2c811;
    border-radius: 0 0 8px 8px;
    padding: 18px 16px 20px;
    background: #ffffff;
    box-shadow: 0 10px 24px rgba(17, 24, 39, 0.06);
  }

  em {
    color: #0078d4;
    font-size: 12px;
    font-style: normal;
    font-weight: 900;
  }

  b {
    display: block;
    margin-top: 12px;
    color: #111827;
    font-size: 15px;
  }

  p {
    margin: 8px 0 0;
    color: #4b5563;
    font-size: 13px;
    line-height: 1.7;
  }
}

.home-ai-section {
  display: grid;
  grid-template-columns: minmax(0, 0.94fr) minmax(330px, 0.72fr);
  align-items: center;
  gap: 54px;
  overflow: hidden;
  background:
    linear-gradient(90deg, rgba(0, 59, 92, 0.98), rgba(0, 91, 112, 0.98)),
    #003b5c;
  color: #ffffff;
}

.home-ai-copy {
  max-width: 680px;

  > span {
    color: #8cf4d0;
    font-size: 12px;
    font-weight: 900;
  }

  h2 {
    margin: 12px 0 14px;
    color: #ffffff;
    font-size: 40px;
    line-height: 1.12;
  }

  p {
    margin: 0;
    color: #d6edf2;
    font-size: 15px;
    line-height: 1.8;
  }
}

.home-ai-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 24px;

  span {
    border: 1px solid rgba(255, 255, 255, 0.22);
    border-radius: 999px;
    padding: 8px 12px;
    background: rgba(255, 255, 255, 0.08);
    color: #ffffff;
    font-size: 12px;
    font-weight: 800;
  }
}

.home-ai-visual {
  position: relative;
  min-height: 310px;
  display: grid;
  place-items: center;
}

.home-ai-ring {
  position: relative;
  z-index: 1;
  width: 260px;
  height: 260px;
  display: grid;
  place-items: center;
  border: 2px solid rgba(140, 244, 208, 0.78);
  border-radius: 50%;
  background: rgba(0, 166, 126, 0.12);
  text-align: center;
  box-shadow: inset 0 0 0 14px rgba(255, 255, 255, 0.04);

  span,
  em {
    position: absolute;
    color: #8cf4d0;
    font-size: 12px;
    font-style: normal;
    font-weight: 900;
  }

  span {
    top: 58px;
  }

  em {
    bottom: 56px;
  }

  strong {
    color: #ffffff;
    font-size: 48px;
    line-height: 1;
  }
}

.home-ai-lines {
  position: absolute;
  inset: 30px 0;
  display: grid;
  align-content: center;
  gap: 24px;
  opacity: 0.78;

  i {
    display: block;
    height: 2px;
    width: 390px;
    background: linear-gradient(90deg, transparent, #8cf4d0, transparent);
    transform: translateX(-54px);

    &:nth-child(2) {
      width: 320px;
      transform: translateX(20px);
    }

    &:nth-child(3) {
      width: 360px;
      transform: translateX(-8px);
    }
  }
}

.home-semantic-section,
.home-governance-layout {
  display: grid;
  grid-template-columns: minmax(0, 0.95fr) minmax(0, 1.05fr);
  gap: 36px;
  align-items: center;
}

.home-section-copy {
  > span {
    color: #8a6d00;
    font-size: 12px;
    font-weight: 900;
  }

  h2 {
    margin: 10px 0 14px;
    color: #0b1f44;
    font-size: 32px;
    line-height: 1.24;
  }

  p {
    margin: 0;
    color: #4b5563;
    font-size: 14px;
    line-height: 1.85;
  }
}

.home-semantic-list {
  display: grid;
  gap: 14px;

  article {
    display: grid;
    grid-template-columns: 38px minmax(0, 1fr);
    gap: 14px;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 16px;
    background: #ffffff;
    box-shadow: 0 10px 24px rgba(17, 24, 39, 0.05);
  }

  span {
    width: 34px;
    height: 34px;
    display: grid;
    place-items: center;
    border-radius: 4px;
    background: #f2c811;
    color: #0b1f44;
    font-size: 13px;
    font-weight: 900;
  }

  b {
    color: #111827;
    font-size: 15px;
  }

  p {
    margin: 6px 0 0;
    color: #4b5563;
    font-size: 13px;
    line-height: 1.65;
  }
}

.home-governance-section {
  background: #f7f8fa;
}

.home-governance-panel {
  display: grid;
  gap: 12px;
}

.home-governance-row {
  display: grid;
  grid-template-columns: 22px minmax(0, 1fr);
  gap: 12px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 16px;
  background: #ffffff;

  i {
    width: 12px;
    height: 12px;
    margin-top: 4px;
    border-radius: 50%;
    background: #f2c811;
    box-shadow: 0 0 0 5px rgba(242, 200, 17, 0.18);
  }

  b {
    color: #111827;
    font-size: 15px;
  }

  p {
    margin: 6px 0 0;
    color: #4b5563;
    font-size: 13px;
    line-height: 1.65;
  }
}

.home-governance-preview {
  border: 1px solid #d9e1ec;
  border-radius: 8px;
  padding: 28px;
  background: #ffffff;
  box-shadow: 0 18px 40px rgba(17, 24, 39, 0.08);

  > span {
    color: #64748b;
    font-size: 12px;
    font-weight: 800;
  }

  strong {
    display: block;
    margin-top: 10px;
    color: #0b1f44;
    font-size: 30px;
  }

  p {
    margin: 8px 0 18px;
    color: #4b5563;
    font-size: 13px;
  }

  div {
    display: grid;
    gap: 10px;
  }

  em {
    height: 12px;
    border-radius: 3px;
    background: #e5e7eb;

    &:first-child {
      width: 88%;
      background: #f2c811;
    }

    &:nth-child(2) {
      width: 66%;
    }

    &:nth-child(3) {
      width: 78%;
    }
  }
}

.home-dashboard-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 18px;

  article {
    min-height: 180px;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 22px;
    background: #ffffff;
    box-shadow: 0 10px 26px rgba(17, 24, 39, 0.06);
  }

  span {
    width: 34px;
    height: 34px;
    display: grid;
    place-items: center;
    border-radius: 4px;
    background: #f2c811;
    color: #0b1f44;
    font-size: 13px;
    font-weight: 900;
  }

  b {
    display: block;
    margin-top: 18px;
    color: #111827;
    font-size: 18px;
  }

  p {
    margin: 10px 0 0;
    color: #4b5563;
    font-size: 13px;
    line-height: 1.75;
  }
}

.home-story-section {
  background: #ffffff;
}

.home-story-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(320px, 0.8fr);
  gap: 22px;
  align-items: stretch;
}

.home-story-feature {
  min-height: 360px;
  border: 1px solid #dce3ec;
  border-radius: 8px;
  padding: 30px;
  background:
    linear-gradient(135deg, rgba(0, 59, 92, 0.72), rgba(7, 59, 76, 0.92)),
    #073b4c;
  color: #ffffff;
  box-shadow: 0 18px 38px rgba(17, 24, 39, 0.1);

  > span {
    color: #8cf4d0;
    font-size: 12px;
    font-weight: 900;
  }

  h3 {
    max-width: 520px;
    margin: 14px 0 12px;
    color: #ffffff;
    font-size: 30px;
    line-height: 1.22;
  }

  p {
    max-width: 600px;
    margin: 0;
    color: #d6edf2;
    font-size: 14px;
    line-height: 1.75;
  }
}

.home-story-chart {
  display: flex;
  align-items: end;
  gap: 12px;
  height: 120px;
  margin-top: 34px;
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 6px;
  padding: 18px 20px 14px;
  background:
    linear-gradient(rgba(255, 255, 255, 0.14) 1px, transparent 1px),
    rgba(255, 255, 255, 0.06);
  background-size: 100% 30px;

  i {
    flex: 1;
    min-width: 8px;
    border-radius: 3px 3px 0 0;
    background: #8cf4d0;

    &:nth-child(3n + 1) {
      background: #f2c811;
    }

    &:nth-child(3n + 2) {
      background: #79c7ff;
    }
  }
}

.home-story-cards {
  display: grid;
  gap: 14px;

  article {
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 20px;
    background: #ffffff;
    box-shadow: 0 12px 26px rgba(17, 24, 39, 0.06);
  }

  span {
    color: #0078d4;
    font-size: 12px;
    font-weight: 900;
  }

  b {
    display: block;
    margin-top: 10px;
    color: #073b4c;
    font-size: 18px;
  }

  p {
    margin: 8px 0 0;
    color: #4b5563;
    font-size: 13px;
    line-height: 1.7;
  }
}

.home-resource-section {
  background: #f7fafb;
}

.home-resource-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 22px;
}

.home-resource-grid article {
  min-height: 238px;
  border: 1px solid #e1e7ef;
  border-radius: 8px;
  padding: 22px;
  background: #ffffff;
  box-shadow: 0 12px 28px rgba(17, 24, 39, 0.06);

  span {
    display: inline-flex;
    border-radius: 3px;
    padding: 5px 8px;
    background: #e9f8f3;
    color: #008866;
    font-size: 12px;
    font-weight: 900;
  }

  b {
    display: block;
    margin-top: 18px;
    color: #073b4c;
    font-size: 20px;
    line-height: 1.3;
  }

  p {
    margin: 12px 0 0;
    color: #4b5563;
    font-size: 13px;
    line-height: 1.75;
  }

  small {
    display: inline-block;
    margin-top: 20px;
    color: #0078d4;
    font-size: 12px;
    font-weight: 900;
  }
}

.home-cta-section {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 28px;
  background:
    linear-gradient(110deg, rgba(0, 59, 92, 0.96), rgba(0, 120, 212, 0.84)),
    #003b5c;
  color: #ffffff;

  span {
    color: #8cf4d0;
    font-size: 12px;
    font-weight: 900;
  }

  h2 {
    max-width: 720px;
    margin: 10px 0 0;
    color: #ffffff;
    font-size: 30px;
    line-height: 1.25;
  }

  p {
    margin: 10px 0 0;
    color: #cbd5e1;
    font-size: 14px;
    line-height: 1.7;
  }

  .power-login-primary {
    flex: 0 0 auto;
    background: #ffffff;
    color: #073b4c;

    &:hover,
    &:focus {
      background: #e9f8f3;
      color: #073b4c;
    }
  }
}

:deep(.zhishu-other-login) {
  height: auto;
  min-height: 0;
}

:deep(.de-other-login-divider) {
  margin: 10px 0 12px;
}

@media (max-width: 1180px) {
  .power-login-nav {
    padding: 0 32px;
  }

  .power-login-menu {
    display: none;
  }

  .power-login-hero {
    grid-template-columns: 1fr;
    padding: 48px 32px 52px;
  }

  .power-login-story {
    max-width: 760px;
  }

  .power-login-headline {
    max-width: 760px;
  }

  .home-hero-visual {
    grid-template-columns: minmax(0, 1fr);
  }

  .home-hero-tile-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
    grid-template-rows: none;
  }

  .product-login-wrap {
    max-width: 480px;
  }

  .power-login-capabilities {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .home-section {
    padding: 54px 32px;
  }

  .home-flow-grid,
  .home-proof-grid,
  .home-dashboard-grid,
  .home-resource-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .home-semantic-section,
  .home-governance-layout,
  .home-ai-section,
  .home-story-layout {
    grid-template-columns: 1fr;
  }

  .home-ai-visual {
    min-height: 240px;
  }

  .home-cta-section {
    align-items: flex-start;
    flex-direction: column;
  }

  .power-login-account-page {
    padding: 48px 32px 0;

    .product-login-wrap {
      width: min(540px, 100%);
      flex: none;
      justify-self: center;
    }
  }

  .account-login-shell {
    grid-template-columns: 1fr;
    max-width: 760px;
    gap: 42px;
  }

  .account-login-story {
    padding-top: 0;
  }

  .account-login-more {
    margin: 64px -32px 0;
    padding: 48px 32px 56px;
  }
}

@media (max-width: 720px) {
  .power-login-nav {
    position: relative;
    min-height: auto;
    padding: 16px 18px;
    align-items: flex-start;
    gap: 10px;
  }

  .power-login-brand {
    max-width: calc(100% - 76px);
    min-width: 0;
    flex: 1 1 auto;
  }

  .power-login-brand-copy {
    strong {
      font-size: 17px;
    }

    span {
      max-width: 180px;
    }
  }

  .power-login-nav-action {
    position: absolute;
    top: 18px;
    right: 18px;
    display: inline-flex;
    height: 34px;
    padding: 0 14px;
    font-size: 13px;
  }

  .home-announcement-strip {
    align-items: flex-start;
    flex-direction: column;
    gap: 8px;
    padding: 12px 18px;
    text-align: left;

    button {
      padding: 6px 10px;
    }
  }

  .power-login-hero {
    padding: 34px 18px 42px;
    overflow: hidden;
  }

  .power-login-story {
    width: calc(100vw - 36px);
    max-width: calc(100vw - 36px);
  }

  .power-login-headline {
    width: calc(100vw - 36px);
    max-width: calc(100vw - 36px);
    margin-top: 22px;

    h1 {
      white-space: normal;
      word-break: break-all;
      font-size: 36px;
      line-height: 1.18;
      overflow-wrap: anywhere;
    }

    p {
      white-space: normal;
      word-break: break-all;
      font-size: 15px;
      overflow-wrap: anywhere;
    }
  }

  .power-login-actions {
    align-items: flex-start;
    width: calc(100vw - 36px);

    span {
      min-width: 0;
      flex: 0 0 100%;
      line-height: 1.5;
      white-space: normal;
      word-break: break-all;
    }
  }

  .power-login-status-row {
    grid-template-columns: 1fr;
  }

  .home-hero-visual {
    width: calc(100vw - 36px);
    max-width: calc(100vw - 36px);
    grid-template-columns: 1fr;
    overflow: hidden;
  }

  .power-login-showcase {
    width: calc(100vw - 36px);
    max-width: calc(100vw - 36px);
    overflow: hidden;
    margin-right: 0;
  }

  .home-hero-tile-grid {
    grid-template-columns: 1fr;
    gap: 12px;
  }

  .product-login-wrap {
    width: calc(100vw - 36px);
  }

  .power-login-window {
    width: 100%;
    min-width: 0;
    max-width: 100%;
    box-shadow: 0 18px 42px rgba(17, 24, 39, 0.14);
  }

  .power-login-window-body {
    grid-template-columns: 86px minmax(0, 1fr);
    min-height: 0;
  }

  .power-login-sidebar {
    padding: 18px 12px;

    span {
      max-width: 62px;
    }
  }

  .power-login-report {
    padding: 16px 12px;
  }

  .power-login-question {
    align-items: flex-start;
    flex-direction: column;
    justify-content: center;
    gap: 6px;
    padding: 12px;

    strong {
      font-size: 13px;
      line-height: 1.35;
    }
  }

  .power-login-metrics {
    grid-template-columns: 1fr;
  }

  .power-login-chart {
    gap: 5px;
    height: 100px;
    padding: 14px 10px 12px;

    span {
      min-width: 0;
    }
  }

  .power-login-table {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .product-login-card {
    padding: 24px 18px;
    min-height: auto;
  }

  .power-login-capabilities {
    grid-template-columns: 1fr;
  }

  .home-section {
    padding: 36px 18px;
  }

  .home-section-head {
    margin-bottom: 22px;

    h2 {
      font-size: 25px;
    }
  }

  .home-section-copy {
    h2 {
      font-size: 25px;
    }
  }

  .home-flow-grid,
  .home-proof-grid,
  .home-dashboard-grid,
  .home-resource-grid,
  .account-login-more-grid {
    grid-template-columns: 1fr;
  }

  .home-proof-grid article,
  .home-dashboard-grid article {
    min-height: 0;
  }

  .home-governance-preview {
    padding: 20px;

    strong {
      font-size: 24px;
    }
  }

  .home-ai-section {
    gap: 28px;
  }

  .home-ai-copy {
    h2 {
      font-size: 28px;
    }
  }

  .home-ai-visual {
    min-height: 220px;
    overflow: hidden;
  }

  .home-ai-ring {
    width: 196px;
    height: 196px;

    strong {
      font-size: 38px;
    }

    span {
      top: 40px;
    }

    em {
      bottom: 38px;
    }
  }

  .home-ai-lines {
    display: none;
  }

  .home-story-layout {
    grid-template-columns: 1fr;
  }

  .home-story-feature {
    min-height: 0;
    padding: 22px;

    h3 {
      font-size: 24px;
    }
  }

  .home-story-chart {
    gap: 7px;
    height: 104px;
    padding: 16px 12px 12px;
  }

  .home-resource-grid article {
    min-height: 0;
  }

  .home-cta-section {
    margin-bottom: 28px;

    h2 {
      font-size: 24px;
    }
  }

  .power-login-account-page {
    padding: 34px 18px 0;
    max-width: 100vw;
    overflow-x: hidden;

    .product-login-wrap {
      width: 100%;
      max-width: none;
    }
  }

  .account-login-shell {
    display: block;
    width: 100%;
    max-width: 100%;
  }

  .account-login-eyebrow {
    font-size: 13px;
  }

  .account-login-story {
    width: 100%;
    max-width: 100%;
    overflow-x: hidden;

    h1 {
      max-width: 100%;
      white-space: normal;
      font-size: 31px;
      line-height: 1.18;
      overflow-wrap: anywhere;
      word-break: break-all;
    }
  }

  .account-login-benefits {
    font-size: 13px;
  }

  .account-login-visual {
    width: 100%;
    margin-top: 30px;
    padding: 0;
  }

  .account-login-screen-body {
    grid-template-columns: 74px minmax(0, 1fr);
    min-height: 0;
    max-width: 100%;

    aside {
      padding: 16px 10px;

      span {
        max-width: 52px;
      }
    }

    section {
      padding: 14px 10px;
    }
  }

  .account-login-prompt {
    min-height: 48px;
    align-items: flex-start;
    padding: 10px;
    font-size: 13px;
    line-height: 1.35;
  }

  .account-login-mini-metrics {
    grid-template-columns: 1fr;
  }

  .account-login-mini-chart {
    gap: 5px;
    height: 92px;
    padding: 12px 8px 10px;

    span {
      min-width: 0;
    }
  }

  .account-login-phone {
    display: none;
  }

  .account-login-more {
    margin: 42px -18px 0;
    padding: 36px 18px 42px;

    h2 {
      margin-bottom: 24px;
      font-size: 25px;
      text-align: left;
    }
  }

  .account-login-more-grid {
    grid-template-columns: 1fr;
    gap: 22px;
  }
}
</style>
