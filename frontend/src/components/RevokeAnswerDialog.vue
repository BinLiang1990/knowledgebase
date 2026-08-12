<script setup lang="ts">
// 撤回答案弹窗。知识点详情页「变更留痕」tab 与全局操作日志页共用——都从已有
// answer_id 发起撤回（issue #10 的约定：按 answer_id，不做客户端 coord 重建）。
// kbId/kpId 随目标一起传入 open()：全局留痕页每一行都可能属于不同的知识库，
// 不能由父级提前固定（issue #14 设计文档 §4.4）。
import { revokeAnswer } from '@/api/answer'

export interface RevokeTarget {
  kbId: number
  kpId: number
  answerId: number
  content: string
}

const emit = defineEmits<{
  /** 撤回成功——父级按需重载列表/留痕 */
  success: []
}>()

const visible = ref(false)
const submitting = ref(false)
const reason = ref('')
const error = ref('')
const target = ref<RevokeTarget | null>(null)

function open(t: RevokeTarget) {
  target.value = t
  reason.value = ''
  error.value = ''
  visible.value = true
}
defineExpose({ open })

async function submit() {
  const trimmedReason = reason.value.trim()
  if (!trimmedReason) {
    error.value = '请填写撤回原因。'
    return
  }
  if (!target.value)
    return
  error.value = ''
  submitting.value = true
  try {
    await revokeAnswer(target.value.kbId, target.value.kpId, target.value.answerId, trimmedReason)
    ElMessage.success('已撤回该条件下的答案')
    visible.value = false
    emit('success')
  }
  catch {
    // 服务端错误已由 request 拦截器统一提示，保持弹窗打开供用户重试
  }
  finally {
    submitting.value = false
  }
}
</script>

<template>
  <el-dialog v-model="visible" class="app-dialog" title="撤回答案" width="560px" :close-on-click-modal="false">
    <p style="font-size: 13.5px; color: var(--ink-2); line-height: 1.9; margin-bottom: 12px;">
      将撤回这个条件下的答案：
      <br>
      <b style="color: var(--ink-1)">{{ target?.content }}</b>
    </p>
    <div class="mf">
      <label><span class="req">*</span>撤回原因</label>
      <textarea v-model="reason" rows="2" placeholder="必填，写入留痕" maxlength="500" />
    </div>
    <div class="risk">
      撤回为逻辑删除：该条件下将不再返回此答案；历史版本与留痕永久保留。
    </div>
    <p v-if="error" class="hint" style="color: var(--red)">
      {{ error }}
    </p>
    <template #footer>
      <button type="button" class="btn" @click="visible = false">
        取 消
      </button>
      <button type="button" class="btn danger" :disabled="submitting" @click="submit">
        确 认 撤 回
      </button>
    </template>
  </el-dialog>
</template>
