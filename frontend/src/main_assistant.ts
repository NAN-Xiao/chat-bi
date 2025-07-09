import { createApp } from 'vue'
import './style.less'
import App from './App.vue'
import router from './router/assistant'
import { i18n } from './i18n'

const app = createApp(App)

app.use(router)
app.use(i18n)
app.mount('#sqlbot_embedded_app')
