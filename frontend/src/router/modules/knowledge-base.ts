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
    // 静态段路由优先于下面的 :kbId 参数路由（vue-router 按具体度匹配）
    path: '/knowledge-bases/recycle-bin',
    name: 'KnowledgeBaseRecycleBin',
    component: () => import('@/views/knowledge-base/recycle-bin/index.vue'),
    meta: { title: '知识库回收站', crumb: '知识库管理 / 回收站', hidden: true },
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
