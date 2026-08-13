<script setup lang="ts">
// 用户管理页（issue #37，仅 sysadmin）：对齐打标系统模式——统一用户首次
// 进入后自动出现在这里；未授权时为普通用户且看不到业务数据，由本页授权。
import type { ManagedUser } from '@/api/auth'
import { listUsers } from '@/api/auth'
import { useAsyncData } from '@/composables/useAsyncData'
import { formatDateTime } from '@/utils/format'
import GrantRoleDialog from './GrantRoleDialog.vue'

defineOptions({ name: 'SystemUsers' })

const usersQuery = useAsyncData(async () => (await listUsers()).items)
const users = computed(() => usersQuery.data.value ?? [])

const ROLE_LABEL: Record<string, string> = {
  none: '未授权',
  viewer: '只读',
  editor: '编辑',
  admin: '管理员',
  sysadmin: '系统管理员',
}
const ROLE_TAG_CLASS: Record<string, string> = {
  none: 'gray',
  viewer: 'blue',
  editor: 'blue',
  admin: 'purple',
  sysadmin: 'red',
}

function sourceLabel(user: ManagedUser): string {
  return user.auth_source === 'unified' ? '统一平台' : '本地'
}

function platformRoleLabel(user: ManagedUser): string {
  if (!user.platform_role_code)
    return '—'
  return user.platform_role_code.includes('super_admin')
    ? `${user.platform_role_code}（自动系统管理员）`
    : user.platform_role_code
}

const grantDialogRef = ref<InstanceType<typeof GrantRoleDialog>>()
function openGrant(user: ManagedUser) {
  grantDialogRef.value?.open(user)
}
</script>

<template>
  <div class="notice">
    用户由<b>统一身份认证平台</b>下发：首次从统一工作台进入本系统后自动出现在这里，无需预建账号。未授权用户可登录但<b>看不到业务数据</b>；统一平台角色 <b>super_admin</b> 自动成为系统管理员，其余角色（含 admin）一律从未授权开始，由系统管理员在本页授予角色。平台角色变化不会覆盖本页人工授予的角色。
  </div>

  <div class="card ov">
    <div class="card-head">
      <span class="tick" />
      <h3>用户管理</h3>
      <span class="sub">共 <b class="num">{{ users.length }}</b> 人</span>
      <span class="spacer" />
      <span class="ops">
        <button type="button" class="btn sm" @click="usersQuery.load">刷新</button>
      </span>
    </div>

    <table class="tbl">
      <thead>
        <tr>
          <th>用户</th>
          <th>来源</th>
          <th>平台角色</th>
          <th>本系统角色</th>
          <th>授权记录</th>
          <th>首次进入</th>
          <th class="op-col">
            操作
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="usersQuery.loading.value">
          <td colspan="7" class="empty">
            <span class="spin" /> 加载中…
          </td>
        </tr>
        <tr v-else-if="usersQuery.error.value">
          <td colspan="7" class="empty">
            加载失败，请检查网络或后端服务后<a @click="usersQuery.load"> 重试</a>
          </td>
        </tr>
        <tr v-else-if="users.length === 0">
          <td colspan="7" class="empty">
            暂无用户——统一用户首次从工作台进入本系统后会自动出现在这里
          </td>
        </tr>
        <template v-else>
          <tr v-for="user in users" :key="user.id">
            <td>
              <b>{{ user.display_name || '—' }}</b>
              <div style="font-size: 12px; color: var(--ink-5)">
                {{ user.identity_account || '—' }}
              </div>
            </td>
            <td>{{ sourceLabel(user) }}</td>
            <td style="font-size: 12.5px">
              {{ platformRoleLabel(user) }}
            </td>
            <td>
              <span class="tag" :class="ROLE_TAG_CLASS[user.role]">{{ ROLE_LABEL[user.role] ?? user.role }}</span>
            </td>
            <td style="font-size: 12.5px; color: var(--ink-4)">
              <template v-if="user.role_granted_at">
                {{ user.role_granted_by }} · <span class="num">{{ formatDateTime(user.role_granted_at) }}</span>
              </template>
              <template v-else>
                —
              </template>
            </td>
            <td class="num" style="font-weight: 400">
              {{ user.first_login_at ? formatDateTime(user.first_login_at) : '—' }}
            </td>
            <td class="op-col ops">
              <a @click="openGrant(user)">授权</a>
            </td>
          </tr>
        </template>
      </tbody>
    </table>
  </div>

  <GrantRoleDialog ref="grantDialogRef" @success="usersQuery.load" />
</template>
