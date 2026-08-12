/**
 * 全局守卫（main.ts 副作用引入，规范 §5.7）。本系统无登录，守卫只负责
 * 把 route.meta.title 写入 document.title。
 */
import router from './index'

router.afterEach((to) => {
  const title = to.meta.title
  document.title = title ? `${title} · ${import.meta.env.VITE_APP_TITLE}` : import.meta.env.VITE_APP_TITLE
})
