/**
 * 登录用户会话（issue #37，规范 §6.3：跨组件共享的会话上下文）。
 * Token/设备类型走 utils/auth 的 localStorage（同域各系统共享统一 Token），
 * 用户信息与角色驻内存——刷新后由守卫重新拉 /auth/me。
 */
import type { CurrentUser, TicketType, UserRole } from '@/api/auth'
import { defineStore } from 'pinia'
import { getMe, ssoLogin } from '@/api/auth'
import { IS_UNIFIED_AUTH } from '@/settings'
import { clearAuthStorage, setIdentityAppType, setToken } from '@/utils/auth'

const ROLE_LEVELS: Record<UserRole, number> = { none: 0, viewer: 1, editor: 2, admin: 3, sysadmin: 4 }

export const useUserStore = defineStore('user', {
  state: () => ({
    currentUser: null as CurrentUser | null,
    /** 并发导航只发一次 /auth/me */
    loadPromise: null as Promise<void> | null,
  }),
  getters: {
    /** off 模式后端直通、菜单全量可见，等价 sysadmin；unified 未加载完按最低处理 */
    role(state): UserRole {
      return state.currentUser?.role ?? (IS_UNIFIED_AUTH ? 'none' : 'sysadmin')
    },
  },
  actions: {
    roleAtLeast(minimum: UserRole): boolean {
      return ROLE_LEVELS[this.role] >= ROLE_LEVELS[minimum]
    },
    /** /sso 接票页调用：换票成功即保存 Token 与设备类型（手册 §7.4） */
    async loginByTicket(ticket: string, ticketType: TicketType) {
      const result = await ssoLogin(ticket, ticketType)
      setToken(result.tokenInfo.tokenValue)
      if (result.tokenInfo.loginDeviceType)
        setIdentityAppType(result.tokenInfo.loginDeviceType)
      this.currentUser = result.user
    },
    /** 守卫调用：确保用户已加载；失败时抛出交守卫清会话跳登录 */
    async ensureLoaded() {
      if (this.currentUser)
        return
      this.loadPromise ??= getMe(true).then((user) => {
        this.currentUser = user
      }).finally(() => {
        this.loadPromise = null
      })
      await this.loadPromise
    },
    clearSession() {
      this.currentUser = null
      clearAuthStorage()
    },
  },
})
