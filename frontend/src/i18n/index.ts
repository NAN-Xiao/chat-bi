import { createI18n } from 'vue-i18n'
import en from './en.json'
import zhCN from './zh-CN.json'
import elementEnLocale from 'element-plus-secondary/es/locale/lang/en'
import elementZhLocale from 'element-plus-secondary/es/locale/lang/zh-cn'

const getDefaultLocale = () => {
  /* const savedLang = localStorage.getItem('lang')
  return savedLang || 'zh-CN' */
  return 'zh-CN'
}

const messages = {
  en: {
    ...en,
    el: elementEnLocale 
  },
  'zh-CN': {
    ...zhCN,
    el: elementZhLocale
  }
}

export const i18n = createI18n({
  legacy: false,
  locale: getDefaultLocale(),
  fallbackLocale: 'en',
  globalInjection: true,
  messages
})

export const getElementLocale = () => {
  return i18n.global.locale.value === 'en' ? elementEnLocale : elementZhLocale
}