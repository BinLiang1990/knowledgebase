import type { RouteRecordRaw } from 'vue-router'

/**
 * 知识库模块：列表 + 库内三个子页。路由 path 一律 kebab-case（规范 §4）。
 * 子页 hidden: true——侧边栏只挂知识库列表这一个入口。
 */
const routes: RouteRecordRaw[] = [
  {
    path: '/knowledge-bases',
    name: 'KnowledgeBaseList',
    component: () => import('@/views/knowledge-base/list/index.vue'),
    meta: { title: '知识库列表', icon: 'Grid', order: 1, crumb: '知识库管理 / 知识库列表' },
  },
  {
    path: '/knowledge-bases/:kbId/knowledge-points',
    name: 'KnowledgePointList',
    component: () => import('@/views/knowledge-base/points/index.vue'),
    meta: { title: '知识点列表', crumb: '知识库列表 / 知识点列表', hidden: true },
  },
  {
    path: '/knowledge-bases/:kbId/knowledge-points/:kpId',
    name: 'KnowledgePointDetail',
    component: () => import('@/views/knowledge-base/detail/index.vue'),
    meta: { title: '知识点详情', crumb: '知识库列表 / 知识点列表 / 详情', hidden: true },
  },
  {
    path: '/knowledge-bases/:kbId/settings',
    name: 'KnowledgeBaseSettings',
    component: () => import('@/views/knowledge-base/settings/index.vue'),
    meta: { title: '知识库设置', crumb: '知识库列表 / 知识库设置', hidden: true },
  },
]

export default routes
