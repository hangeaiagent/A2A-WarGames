import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from './router/index.js'
import i18n from './i18n/index.js'
import App from './App.vue'
import './styles/variables.css'
import './styles/global.css'
import { useAuthStore } from './stores/auth'

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)
app.use(router)
app.use(i18n)

const auth = useAuthStore(pinia)
auth.init().then(() => app.mount('#app'))
