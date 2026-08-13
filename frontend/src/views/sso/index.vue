<script setup lang="ts">
// SSO 接票页（issue #37，手册 §7.5）：统一工作台跳转落点。
// 红线：Ticket 只留在本函数内存——读取后立即清地址栏，不落任何存储、
// 不打日志、失败不自动用同一张 Ticket 重试（Ticket 一次性消费）。
import type { TicketType } from '@/api/auth'
import { useUserStore } from '@/store/modules/user'

defineOptions({ name: 'SsoEntry' })

const router = useRouter()
const userStore = useUserStore()

const status = ref<'working' | 'error'>('working')
const errorText = ref('')
/** 排障用：到达本页时收到了哪些参数（只记参数名，绝不记 Ticket 值） */
const receivedParams = ref('')

onMounted(async () => {
  // 兼容两种部署形态：Query 在 Hash 内（…/#/sso?ticket=）与 Hash 前（…/?ticket=#/sso）
  const pageQuery = new URLSearchParams(window.location.search)
  const hashQuery = new URLSearchParams(window.location.hash.split('?')[1] || '')
  const ticket = hashQuery.get('ticket') || pageQuery.get('ticket') || ''
  const rawType = String(hashQuery.get('ticketType') || pageQuery.get('ticketType') || 'SAME_DOMAIN').toUpperCase()

  const hashKeys = [...hashQuery.keys()]
  const pageKeys = [...pageQuery.keys()]
  receivedParams.value
    = `hash 内参数：${hashKeys.length ? hashKeys.join(', ') : '无'} · hash 前参数：${pageKeys.length ? pageKeys.join(', ') : '无'}`

  // 读取后立即清除地址栏里的 Ticket（含 Hash 前的 Query）
  window.history.replaceState({}, '', `${window.location.pathname}#/sso`)

  if (!ticket || !['SAME_DOMAIN', 'CROSS_DOMAIN'].includes(rawType)) {
    status.value = 'error'
    errorText.value = '单点登录参数无效，请从统一工作台重新进入。'
    return
  }

  try {
    await userStore.loginByTicket(ticket, rawType as TicketType)
    await router.replace('/')
  }
  catch {
    // 拦截器已弹出具体原因（Ticket 过期/已消费等）；此处只给指引，不重试
    status.value = 'error'
    errorText.value = '单点登录失败，请从统一工作台重新进入。'
  }
})
</script>

<template>
  <div class="sso-page">
    <div class="sso-card">
      <template v-if="status === 'working'">
        <span class="spin" />
        <p>正在登录，请稍候…</p>
      </template>
      <template v-else>
        <p class="err">
          {{ errorText }}
        </p>
        <p class="hint">
          Ticket 为一次性凭证，刷新本页无法重试。
        </p>
        <p v-if="receivedParams" class="hint" style="margin-top: 4px">
          排障信息（{{ receivedParams }}）
        </p>
      </template>
    </div>
  </div>
</template>

<style scoped>
.sso-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg, #f5f7fa);
}
.sso-card {
  text-align: center;
  padding: 48px 64px;
  background: #fff;
  border: 1px solid var(--line, #e2e8f0);
  border-radius: 12px;
  font-size: 14px;
  color: var(--ink-2, #334155);
}
.sso-card .err {
  color: var(--red, #dc2626);
  font-weight: 600;
}
.sso-card .hint {
  margin-top: 8px;
  font-size: 12.5px;
  color: var(--ink-5, #94a3b8);
}
</style>
