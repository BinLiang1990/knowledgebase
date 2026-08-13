<script setup lang="ts">
// 授权弹窗（issue #37）：为统一下发的用户授予本系统角色。
import type { ManagedUser, UserRole } from '@/api/auth'
import { updateUserRole } from '@/api/auth'

const emit = defineEmits<{
  success: []
}>()

const visible = ref(false)
const submitting = ref(false)
const target = ref<ManagedUser | null>(null)
const role = ref<UserRole>('none')

const ROLE_OPTIONS: { value: UserRole, label: string, desc: string }[] = [
  { value: 'none', label: '未授权', desc: '可登录，看不到任何业务数据' },
  { value: 'viewer', label: '只读', desc: '查看知识库/知识点/关联，不能修改' },
  { value: 'editor', label: '编辑', desc: '读写知识点、答案与关联；不含维度配置与建删知识库' },
  { value: 'admin', label: '管理员', desc: '编辑权限 + 维度配置、新建/停用知识库' },
  { value: 'sysadmin', label: '系统管理员', desc: '管理员权限 + 用户管理（本页）' },
]

function open(user: ManagedUser) {
  target.value = user
  role.value = user.role
  visible.value = true
}
defineExpose({ open })

async function submit() {
  if (!target.value)
    return
  submitting.value = true
  try {
    await updateUserRole(target.value.id, role.value)
    ElMessage.success('已更新角色')
    visible.value = false
    emit('success')
  }
  catch {
    // request 拦截器已提示（如"不能修改自己的角色"）
  }
  finally {
    submitting.value = false
  }
}
</script>

<template>
  <el-dialog v-model="visible" class="app-dialog" title="用户授权" width="520px" :close-on-click-modal="false">
    <div class="mf">
      <label>用户</label>
      <div style="font-size: 14px; padding: 4px 0">
        <b>{{ target?.display_name }}</b>
        <span style="color: var(--ink-5); margin-left: 8px">{{ target?.identity_account }}</span>
      </div>
    </div>
    <div class="mf">
      <label><span class="req">*</span>本系统角色</label>
      <div class="role-options">
        <label v-for="opt in ROLE_OPTIONS" :key="opt.value" class="role-option" :class="{ sel: role === opt.value }">
          <input v-model="role" type="radio" :value="opt.value">
          <span class="role-name">{{ opt.label }}</span>
          <span class="role-desc">{{ opt.desc }}</span>
        </label>
      </div>
    </div>
    <template #footer>
      <button type="button" class="btn" @click="visible = false">
        取 消
      </button>
      <button type="button" class="btn primary" :disabled="submitting" @click="submit">
        保 存
      </button>
    </template>
  </el-dialog>
</template>

<style scoped>
.role-options {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.role-option {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 8px 12px;
  border: 1px solid var(--line, #e2e8f0);
  border-radius: 8px;
  cursor: pointer;
  font-size: 13.5px;
}
.role-option.sel {
  border-color: var(--blue, #1a56f0);
  background: rgb(26 86 240 / 4%);
}
.role-option .role-name {
  font-weight: 600;
  white-space: nowrap;
}
.role-option .role-desc {
  font-size: 12.5px;
  color: var(--ink-5, #94a3b8);
}
</style>
