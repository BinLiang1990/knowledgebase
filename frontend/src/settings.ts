/**
 * 全局协议常量（前端开发规范 §12.1）。
 */

/** 后端统一响应包成功码（docs/PRD.md §4.10：code 200 成功、444 业务/校验错误） */
export const API_SUCCESS_CODE = 200

// ---- 统一身份认证（issue #37，手册 §7.2） ----
/** unified=正式环境 SSO；其余值/缺省=off 免登录直通（本地开发，与接入前一致） */
export const AUTH_MODE = import.meta.env.VITE_AUTH_MODE === 'unified' ? 'unified' : 'off'
export const IS_UNIFIED_AUTH = AUTH_MODE === 'unified'
/** 统一平台前端登录页；unified 模式访问 /login 时整页跳转到这里 */
export const IDENTITY_LOGIN_URL = import.meta.env.VITE_IDENTITY_LOGIN_URL || ''
/** 认证域：同域各子系统共享同一把统一 Token 的 storage 命名空间 */
export const AUTH_DOMAIN = import.meta.env.VITE_AUTH_DOMAIN || 'PUBLIC'
export const TOKEN_KEY = `enterprise-platform:auth:${AUTH_DOMAIN}:token`
export const IDENTITY_APP_TYPE_KEY = `enterprise-platform:auth:${AUTH_DOMAIN}:app-type`
/** 请求头名（后端 auth/deps.py 同名读取） */
export const TOKEN_HEADER = 'IDENTITYTOKEN'
export const APP_TYPE_HEADER = 'X-Identity-App-Type'

/** 请求超时（毫秒）——防止挂起的请求永不 resolve（PR #22 评审结论，随 axios 迁移保留） */
export const REQUEST_TIMEOUT_MS = 10_000
