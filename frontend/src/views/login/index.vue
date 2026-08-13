<script setup lang="ts">
// 登录页（issue #37）：unified 模式下守卫已整页跳转统一平台，本组件只在
// 两种兜底情形渲染——未配置平台登录地址，或 off 模式误入 /login。
// 本系统刻意不做本地账号密码登录（设计文档 §D1）。
import { IDENTITY_LOGIN_URL, IS_UNIFIED_AUTH } from '@/settings'

defineOptions({ name: 'LoginPage' })

const router = useRouter()

onMounted(() => {
  if (!IS_UNIFIED_AUTH)
    router.replace('/') // off 模式无登录概念
})

function goPlatform() {
  if (IDENTITY_LOGIN_URL)
    window.location.replace(IDENTITY_LOGIN_URL)
}
</script>

<template>
  <div class="login-page">
    <div class="login-card">
      <template v-if="IDENTITY_LOGIN_URL">
        <p>本系统通过统一身份认证平台登录。</p>
        <button type="button" class="btn primary" @click="goPlatform">
          前往统一登录
        </button>
      </template>
      <template v-else>
        <p class="err">
          未配置统一平台登录地址（VITE_IDENTITY_LOGIN_URL）。
        </p>
        <p class="hint">
          请联系管理员检查前端构建配置。
        </p>
      </template>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg, #f5f7fa);
}
.login-card {
  text-align: center;
  padding: 48px 64px;
  background: #fff;
  border: 1px solid var(--line, #e2e8f0);
  border-radius: 12px;
  font-size: 14px;
  color: var(--ink-2, #334155);
}
.login-card .err {
  color: var(--red, #dc2626);
  font-weight: 600;
}
.login-card .hint {
  margin-top: 8px;
  font-size: 12.5px;
  color: var(--ink-5, #94a3b8);
}
.login-card button {
  margin-top: 16px;
}
</style>
