/**
 * 应用装配入口：创建 app、use 插件、副作用 import（规范 §3）。
 */
import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import store from './store'
import './router/guard'
// ElMessage 走 AutoImport 的显式声明（见 vite.config.ts 注释），样式不会被
// resolver 按需注入，需在此全局引入一次
import 'element-plus/es/components/message/style/css'
// ElMessageBox 与 ElMessage 同理：显式声明在 AutoImport（vite.config.ts），
// 样式在此全局引入（RelationsPane 的删除确认用到）
import 'element-plus/es/components/message-box/style/css'
import './styles/index.scss'
import './styles/element.scss'
import './styles/dialog.scss'

createApp(App).use(store).use(router).mount('#app')
