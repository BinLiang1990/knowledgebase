/**
 * Pinia 装配（前端开发规范 §6.1）：只做 createPinia，不装 persistedstate——
 * 本系统没有任何需要持久化的 store。
 */
import { createPinia } from 'pinia'

const store = createPinia()

export default store
