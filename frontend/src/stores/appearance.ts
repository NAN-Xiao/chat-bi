import { defineStore } from 'pinia'
import { store } from '@/stores/index'
import { setCurrentColor, setTitle } from '@/utils/utils'
import { isBtnShow } from '@/utils/utils'

interface AppearanceState {
  themeColor?: string
  customColor?: string
  navigateBg?: string
  navigate?: string
  mobileLogin?: string
  mobileLoginBg?: string
  help?: string
  showAi?: string
  showCopilot?: string
  showDoc?: string
  showAbout?: string
  bg?: string
  login?: string
  slogan?: string
  web?: string
  name?: string
  foot?: string
  showSlogan?: string
  pc_welcome?: string
  pc_welcome_desc?: string
  footContent?: string
  loaded: boolean
  showDemoTips?: boolean
  demoTipsContent?: string
  fontList?: Array<{ name: string; id: string; isDefault: boolean }>
}

const DEFAULT_BRAND_NAME = '星通智数'
const DEFAULT_THEME_COLOR = '#2563EB'

export const useAppearanceStore = defineStore('appearanceStore', {
  state: (): AppearanceState => {
    return {
      themeColor: 'default',
      customColor: '',
      navigateBg: '',
      navigate: '',
      mobileLogin: '',
      mobileLoginBg: '',
      help: '',
      showDoc: '0',
      showSlogan: '0',
      showAi: '0',
      showCopilot: '0',
      showAbout: '0',
      bg: '',
      login: '',
      slogan: '',
      web: '',
      name: DEFAULT_BRAND_NAME,
      foot: 'false',
      footContent: '',
      loaded: false,
      showDemoTips: false,
      demoTipsContent: '',
      fontList: [],
      pc_welcome: undefined,
      pc_welcome_desc: undefined,
    }
  },
  getters: {
    getNavigate(): string {
      return null!
    },
    getMobileLogin(): string {
      return null!
    },
    getMobileLoginBg(): string {
      return null!
    },
    getHelp(): string {
      return this.help!
    },
    getThemeColor(): string {
      return this.themeColor!
    },
    isBlue(): boolean {
      return this.themeColor! === 'blue'
    },
    getCustomColor(): string {
      return this.customColor!
    },
    getNavigateBg(): string {
      return this.navigateBg!
    },
    getBg(): string {
      return null!
    },
    getLogin(): string {
      return null!
    },
    getSlogan(): string {
      return this.slogan!
    },
    getWeb(): string {
      return null!
    },
    getName(): string {
      return this.name!
    },
    getLoaded(): boolean {
      return this.loaded
    },
    getFoot(): string {
      return this.foot!
    },
    getFootContent(): string {
      return this.footContent!
    },
    getShowDemoTips(): boolean {
      return this.showDemoTips!
    },
    getDemoTipsContent(): string {
      return this.demoTipsContent!
    },
    getShowAi(): boolean {
      return isBtnShow(this.showAi!)
    },
    getShowCopilot(): boolean {
      return isBtnShow(this.showCopilot!)
    },
    getShowSlogan(): boolean {
      return isBtnShow(this.showSlogan!)
    },
    getShowDoc(): boolean {
      return isBtnShow(this.showDoc!)
    },
    getShowAbout(): boolean {
      return isBtnShow(this.showAbout!)
    },
  },
  actions: {
    setNavigate(data: string) {
      this.navigate = data
    },
    setMobileLogin(data: string) {
      this.mobileLogin = data
    },
    setMobileLoginBg(data: string) {
      this.mobileLoginBg = data
    },
    setHelp(data: string) {
      this.help = data
    },
    setNavigateBg(data: string) {
      this.navigateBg = data
    },
    setThemeColor(data: string) {
      this.themeColor = data
    },
    setCustomColor(data: string) {
      this.customColor = data
    },
    setLoaded(data: boolean) {
      this.loaded = data
    },
    async setAppearance() {
      if (this.loaded) {
        return
      }
      this.loaded = true
      this.themeColor = 'default'
      this.customColor = ''
      this.name = DEFAULT_BRAND_NAME
      setCurrentColor(DEFAULT_THEME_COLOR)
      document.title = DEFAULT_BRAND_NAME
      setTitle(DEFAULT_BRAND_NAME)
      setLinkIcon()
    },
  },
})

const setLinkIcon = () => {
  const link = document.querySelector('link[rel="icon"]') as HTMLLinkElement
  if (link) {
    link.href = `${location.pathname}LOGO-fold.svg`
  }
}

export const useAppearanceStoreWithOut = () => {
  return useAppearanceStore(store)
}
