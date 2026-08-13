/// <reference types="vite/client" />

// 全部环境变量必须在此声明（前端开发规范 §2.5）；只在 dev 存在的声明为可选。
interface ImportMetaEnv {
  /** 页面标题 */
  readonly VITE_APP_TITLE: string
  /** 接口前缀，dev 走 vite 代理剥前缀，生产由 nginx 反代同一前缀 */
  readonly VITE_APP_BASE_API: string
  /** dev 代理的后端地址（仅 .env.development 提供） */
  readonly VITE_PROXY_TARGET?: string
  /** 认证模式：unified=统一身份认证（正式环境），其余值/缺省=off 免登录（issue #37） */
  readonly VITE_AUTH_MODE?: string
  /** 统一平台前端登录页地址（unified 模式必填） */
  readonly VITE_IDENTITY_LOGIN_URL?: string
  /** 统一平台认证域（storage key 命名空间用，缺省 PUBLIC） */
  readonly VITE_AUTH_DOMAIN?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
