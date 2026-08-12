import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/change-log',
    name: 'OperationLog',
    component: () => import('@/views/change-log/list/index.vue'),
    meta: { title: '操作日志', icon: 'Clock', order: 3, crumb: '全局 / 操作日志' },
  },
]

export default routes
