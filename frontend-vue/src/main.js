import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import App from './App.vue'
import router, { setupRouterGuard } from './router'
import './assets/main.css'
import './styles/themes.css'

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)
app.use(router)
app.use(ElementPlus)
// 注册所有图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}
// 设置路由守卫（必须在 Pinia 之后）
setupRouterGuard(app)
app.mount('#app')

// 暴露 chatStore 到 window，方便在 DevTools / 自动化里排查/验证
import { useChatStore } from '@/stores/chat.js'
try { window.__chatStore = useChatStore(pinia) } catch {}
