<script setup lang="ts">
import { logout } from '@/api/auth'
import { IS_UNIFIED_AUTH } from '@/settings'
import { useAppStore } from '@/store/modules/app'
import { useUserStore } from '@/store/modules/user'

const route = useRoute()
const appStore = useAppStore()
const userStore = useUserStore()

const now = ref(new Date())
// 定时器统一 useIntervalFn，随组件销毁自动清理（规范 §8.5）
useIntervalFn(() => {
  now.value = new Date()
}, 1000)

// 页面可用 useCrumb 注入知识库名等动态信息，否则回退路由静态 crumb
const crumb = computed(() => appStore.crumbOverride || route.meta.crumb || '')

const ROLE_LABEL: Record<string, string> = {
  none: '未授权',
  viewer: '只读',
  editor: '编辑',
  admin: '管理员',
  sysadmin: '系统管理员',
}
const displayName = computed(() => userStore.currentUser?.display_name ?? '')
const roleLabel = computed(() => ROLE_LABEL[userStore.role] ?? userStore.role)
const avatarText = computed(() => (displayName.value ? displayName.value.slice(0, 1) : 'AD'))

async function handleLogout() {
  try {
    await ElMessageBox.confirm('确定退出登录？', '退出', {
      type: 'warning',
      confirmButtonText: '退 出',
      cancelButtonText: '取 消',
    })
  }
  catch {
    return // 用户取消
  }
  try {
    await logout()
  }
  catch {
    // 后端无会话可清，失败不阻塞本地退出
  }
  userStore.clearSession()
  window.location.hash = '#/login'
}
</script>

<template>
  <header class="top">
    <span class="h-bar" />
    <h1>{{ route.meta.title }}</h1>
    <span class="crumb">{{ crumb }}</span>
    <span class="spacer" />
    <span class="top-badge">已接入真实后端</span>
    <div class="top-clock">
      <div class="t num">
        {{ now.toLocaleTimeString('zh-CN', { hour12: false }) }}
      </div>
      <div class="d">
        {{ now.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' }) }}
      </div>
    </div>
    <div class="top-user">
      <div class="top-avatar" :title="displayName">
        {{ avatarText }}
      </div>
      <div v-if="IS_UNIFIED_AUTH && displayName" class="top-user-meta">
        <span class="name">{{ displayName }}</span>
        <span class="role">{{ roleLabel }} · <a @click="handleLogout">退出</a></span>
      </div>
    </div>
  </header>
</template>

<style scoped>
.top-user {
  display: flex;
  align-items: center;
  gap: 10px;
}
.top-user-meta {
  display: flex;
  flex-direction: column;
  line-height: 1.4;
}
.top-user-meta .name {
  font-size: 13px;
  font-weight: 600;
}
.top-user-meta .role {
  font-size: 11.5px;
  color: var(--ink-5, #94a3b8);
}
.top-user-meta .role a {
  cursor: pointer;
  color: var(--blue, #1a56f0);
}
</style>
