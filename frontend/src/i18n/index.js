import { createI18n } from 'vue-i18n'
import en from './en.json'
import fr from './fr.json'
import es from './es.json'
import zh from './zh.json'

const savedLocale = localStorage.getItem('app-locale') || 'en'

const i18n = createI18n({
  legacy: false,
  locale: savedLocale,
  fallbackLocale: 'en',
  messages: { en, fr, es, zh },
})

export default i18n
