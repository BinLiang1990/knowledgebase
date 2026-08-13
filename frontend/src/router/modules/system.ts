import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/system/users',
    name: 'SystemUsers',
    component: () => import('@/views/system/users/index.vue'),
    // 用户由统一平台下发（首登自动出现），本页只做本系统授权（issue #37）
    meta: { title: '用户管理', icon: 'User', order: 9, minRole: 'sysadmin', crumb: '系统设置 / 用户管理' },
  },
]

export default routes
