/**
 * import.meta.glob 自动收集 modules/ 下的路由（规范 §5.2）——新增业务模块
 * 只需在 modules/ 放一个文件，这里零改动。侧边栏菜单按 meta.order 排序，
 * 收集顺序本身不影响展示。
 */
import type { RouteRecordRaw } from 'vue-router'

const moduleFiles = import.meta.glob<{ default: RouteRecordRaw | RouteRecordRaw[] }>('./modules/*.ts', {
  eager: true,
})

export const asyncRoutes: RouteRecordRaw[] = Object.values(moduleFiles).flatMap(m =>
  Array.isArray(m.default) ? m.default : [m.default],
)
