/**
 * hash 模式（规范 §5.1）：配合 vite 的相对 base，dist 可部署到任意子目录
 * （正式环境挂 /kb-web），刷新/直链不再依赖 nginx 的 try_files 回退。
 * 认证路由（/sso 接票、/login、/no-permission）在 Layout 之外——接票页与
 * 未授权页不该出现侧边栏（issue #37）；权限过滤在 guard.ts。
 */
import { createRouter, createWebHashHistory } from 'vue-router'
import Layout from '@/layout/index.vue'
import { asyncRoutes } from './asyncRoutes'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    // 统一身份认证（issue #37）：接票页必须无条件可达（守卫放行），
    // 否则浏览器残留旧 Token 时会阻止消费新 Ticket（手册 §7.6）
    {
      path: '/sso',
      name: 'SsoEntry',
      component: () => import('@/views/sso/index.vue'),
      meta: { title: '单点登录' },
    },
    {
      path: '/login',
      name: 'Login',
      component: () => import('@/views/login/index.vue'),
      meta: { title: '登录' },
    },
    {
      path: '/no-permission',
      name: 'NoPermission',
      component: () => import('@/views/no-permission/index.vue'),
      meta: { title: '暂无权限' },
    },
    {
      path: '/',
      component: Layout,
      redirect: '/knowledge-bases',
      children: asyncRoutes,
    },
    // 兜底 404：本系统页面少，直接回列表页比专门的 404 页更省一次点击
    { path: '/:pathMatch(.*)*', redirect: '/knowledge-bases' },
  ],
})

export default router
