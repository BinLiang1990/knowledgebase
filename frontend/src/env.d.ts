/// <reference types="vite/client" />

// 全部环境变量必须在此声明（前端开发规范 §2.5）；只在 dev 存在的声明为可选。
interface ImportMetaEnv {
  /** 页面标题 */
  readonly VITE_APP_TITLE: string
  /** 接口前缀，dev 走 vite 代理剥前缀，生产由 nginx 反代同一前缀 */
  readonly VITE_APP_BASE_API: string
  /** dev 代理的后端地址（仅 .env.development 提供） */
  readonly VITE_PROXY_TARGET?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
