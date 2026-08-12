/**
 * hash 模式（规范 §5.1）：配合 vite 的相对 base，dist 可部署到任意子目录
 * （正式环境挂 /kb-web），刷新/直链不再依赖 nginx 的 try_files 回退。
 * 本系统无登录/权限，路由全量静态挂载，没有动态路由与守卫过滤。
 */
import { createRouter, createWebHashHistory } from 'vue-router'
import Layout from '@/layout/index.vue'
import { asyncRoutes } from './asyncRoutes'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
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
