/**
 * 认证与用户管理接口（issue #37）。前端只与本系统后端交互，Ticket 换票、
 * Token 校验全部由后端转发统一平台（手册 §10 红线：前端不直连平台后端）。
 */
import { request } from '@/utils/request'

/** 本系统角色梯度（与后端 auth/roles.py 一致） */
export type UserRole = 'none' | 'viewer' | 'editor' | 'admin' | 'sysadmin'

export type TicketType = 'SAME_DOMAIN' | 'CROSS_DOMAIN'

export interface CurrentUser {
  id: number
  display_name: string
  role: UserRole
  auth_source: 'unified' | 'dev'
}

export interface SsoTokenInfo {
  tokenName: string
  tokenValue: string
  tokenTimeout?: number
  loginDeviceType?: 'PORTAL' | 'ADMIN' | 'H5' | 'DASHBOARD'
}

export interface SsoLoginResult {
  tokenInfo: SsoTokenInfo
  user: CurrentUser
}

export function ssoLogin(ticket: string, ticketType: TicketType) {
  return request.post<SsoLoginResult>('/auth/sso_login', { ticket, ticketType })
}

export function getMe(silent = false) {
  return request.get<CurrentUser>('/auth/me', { silent })
}

export function logout() {
  return request.post<Record<string, never>>('/auth/logout', undefined, { silent: true })
}

// ---- 用户管理（仅 sysadmin，issue #37） ----

export interface ManagedUser {
  id: number
  identity_account: string | null
  display_name: string
  auth_source: 'unified' | 'dev'
  org_name: string | null
  platform_role_code: string | null
  role: UserRole
  role_granted_by: string | null
  role_granted_at: string | null
  first_login_at: string | null
}

export function listUsers() {
  return request.get<{ items: ManagedUser[] }>('/users')
}

export function updateUserRole(userId: number, role: UserRole) {
  return request.patch<ManagedUser>(`/users/${userId}/role`, { role })
}
