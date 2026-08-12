import 'vue-router'

// 路由 meta 字段统一约定（前端开发规范 §5.6）；本系统无权限体系，故没有 perm。
declare module 'vue-router' {
  interface RouteMeta {
    /** 菜单/页面标题，守卫写入 document.title */
    title?: string
    /** 顶栏面包屑的静态部分；页面可用 useCrumb 动态覆盖 */
    crumb?: string
    /** Element Plus 图标名字符串（layout/components/SidebarNav.vue 内映射） */
    icon?: string
    /** 侧边栏排序 */
    order?: number
    /** 侧边栏隐藏（详情页/子页） */
    hidden?: boolean
  }
}
