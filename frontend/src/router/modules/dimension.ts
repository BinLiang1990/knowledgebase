import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/dimensions',
    name: 'DimensionList',
    component: () => import('@/views/dimension/list/index.vue'),
    meta: { title: '维度管理', icon: 'SetUp', order: 2, crumb: '知识库管理 / 维度管理' },
  },
]

export default routes
