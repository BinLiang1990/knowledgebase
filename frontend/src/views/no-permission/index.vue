<script setup lang="ts">
// 暂无权限页（issue #37）：统一用户首次进入默认未授权(role=none)的落点——
// 可登录但看不到业务数据，与打标系统「未关联租户」同一模式。
import { logout } from '@/api/auth'
import { useUserStore } from '@/store/modules/user'

defineOptions({ name: 'NoPermission' })

const userStore = useUserStore()

async function handleLogout() {
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
  <div class="np-page">
    <div class="np-card">
      <div class="np-icon">
        🔒
      </div>
      <p class="np-title">
        暂无权限
      </p>
      <p class="np-text">
        <template v-if="userStore.currentUser?.display_name">
          {{ userStore.currentUser.display_name }}，
        </template>您已成功登录，但还没有本系统的业务权限。<br>
        请联系系统管理员在「用户管理」中为您分配角色后刷新本页。
      </p>
      <button type="button" class="btn" @click="handleLogout">
        退出登录
      </button>
    </div>
  </div>
</template>

<style scoped>
.np-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg, #f5f7fa);
}
.np-card {
  text-align: center;
  padding: 48px 72px;
  background: #fff;
  border: 1px solid var(--line, #e2e8f0);
  border-radius: 12px;
}
.np-icon {
  font-size: 40px;
}
.np-title {
  margin-top: 12px;
  font-size: 17px;
  font-weight: 600;
  color: var(--ink-1, #1e293b);
}
.np-text {
  margin-top: 10px;
  font-size: 13.5px;
  line-height: 1.9;
  color: var(--ink-4, #64748b);
}
.np-card button {
  margin-top: 20px;
}
</style>
