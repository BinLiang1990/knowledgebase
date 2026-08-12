/**
 * 应用级 UI 上下文（规范 §6.3：只放跨组件共享的会话/界面上下文）。
 * 目前唯一的职责：让页面能把「知识库名」等动态信息注入顶栏面包屑——
 * 顶栏在 layout 里、页面在 router-view 里，二者没有 props 通路。
 */
import { defineStore } from 'pinia'

export const useAppStore = defineStore('app', {
  state: () => ({
    /** 非空时覆盖 route.meta.crumb；由页面通过 useCrumb 设置并在离开时清空 */
    crumbOverride: '',
  }),
})
