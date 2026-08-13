/**
 * 全局守卫（main.ts 副作用引入，规范 §5.7）。
 *
 * unified 模式（issue #37，手册 §7.6）：
 * - /login 整页跳转统一平台登录页（本系统不渲染账号密码表单）；
 * - /sso 接票页无条件放行——浏览器残留旧 Token 不能阻止消费新 Ticket；
 * - 无 Token → /login；有 Token 先拉 /auth/me（失败清会话回登录）；
 * - role=none（未授权）只能访问 /no-permission；
 * - 路由 meta.minRole 不满足时回首页。
 *
 * off 模式（本地开发）：不拦截，仅保留 document.title 行为。
 */
import { IDENTITY_LOGIN_URL, IS_UNIFIED_AUTH } from '@/settings'
import { useUserStore } from '@/store/modules/user'
import { getToken } from '@/utils/auth'
import router from './index'

router.beforeEach(async (to) => {
  if (!IS_UNIFIED_AUTH)
    return true

  if (to.path === '/sso')
    return true

  if (to.path === '/login') {
    if (IDENTITY_LOGIN_URL) {
      window.location.replace(IDENTITY_LOGIN_URL)
      return false
    }
    return true // 未配置平台地址时兜底渲染提示页，而不是白屏死循环
  }

  if (!getToken())
    return { path: '/login' }

  const userStore = useUserStore()
  try {
    await userStore.ensureLoaded()
  }
  catch {
    // Token 失效（401 已由拦截器清 storage）或后端不可达：回登录
    userStore.clearSession()
    return { path: '/login' }
  }

  const unauthorized = userStore.role === 'none'
  if (unauthorized)
    return to.path === '/no-permission' ? true : { path: '/no-permission' }
  if (to.path === '/no-permission')
    return { path: '/' } // 已授权用户不该停在未授权页

  if (to.meta.minRole && !userStore.roleAtLeast(to.meta.minRole))
    return { path: '/' }

  return true
})

router.afterEach((to) => {
  const title = to.meta.title
  document.title = title ? `${title} · ${import.meta.env.VITE_APP_TITLE}` : import.meta.env.VITE_APP_TITLE
})
