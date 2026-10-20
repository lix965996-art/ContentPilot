import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'

import App from './App.vue'
import router from './router'
import './styles/main.css'
import './styles/ios.css'
import { useAuthStore } from '@/stores/auth'

const app = createApp(App)

app.use(createPinia())
window.addEventListener('contentpilot:session-expired', () => {
  useAuthStore().clearSession()
  if (!['login', 'register'].includes(String(router.currentRoute.value.name))) {
    void router.replace({ name: 'login', query: { redirect: router.currentRoute.value.fullPath } })
  }
})
app.use(router)
app.use(ElementPlus, { locale: zhCn })

app.mount('#app')
