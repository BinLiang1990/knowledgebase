/**
 * 统一 Token / 设备类型的 localStorage 读写（issue #37，手册 §7.2）。
 * 独立成叶子模块：request 拦截器与 user store 都要用，放 store 里会循环依赖。
 * 红线：绝不使用 localStorage.clear()（同域部署的其他系统会被误清）；
 * Ticket 永不落盘（只在 /sso 接票页的函数内存里）。
 */
import { IDENTITY_APP_TYPE_KEY, TOKEN_KEY } from '@/settings'

export const getToken = () => localStorage.getItem(TOKEN_KEY) || ''
export const setToken = (token: string) => localStorage.setItem(TOKEN_KEY, token)
export const removeToken = () => localStorage.removeItem(TOKEN_KEY)

export const getIdentityAppType = () => localStorage.getItem(IDENTITY_APP_TYPE_KEY) || ''
export const setIdentityAppType = (value: string) => localStorage.setItem(IDENTITY_APP_TYPE_KEY, value)
export const removeIdentityAppType = () => localStorage.removeItem(IDENTITY_APP_TYPE_KEY)

/** 401 时清掉本地会话痕迹（不含平台侧 Token 生命周期，那归平台管） */
export function clearAuthStorage() {
  removeToken()
  removeIdentityAppType()
}
