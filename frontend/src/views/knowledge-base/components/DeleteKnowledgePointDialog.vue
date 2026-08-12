<script setup lang="ts">
// 删除知识点弹窗。知识点列表页（issue #7）与详情页（issue #8）共用——两处
// 需要完全相同的删除原因校验与错误处理，抽出而非复制。
import { deleteKnowledgePoint } from '@/api/knowledgePoint'

interface DeleteTarget {
  kbId: number
  id: number
  title: string
}

const emit = defineEmits<{
  /** 删除成功——父页面重载列表/详情与知识库统计 */
  success: []
}>()

const visible = ref(false)
const submitting = ref(false)
const reason = ref('')
const error = ref('')
const target = ref<DeleteTarget | null>(null)

function open(t: DeleteTarget) {
  target.value = t
  reason.value = ''
  error.value = ''
  visible.value = true
}
defineExpose({ open })

async function submit() {
  const trimmedReason = reason.value.trim()
  if (!trimmedReason) {
    error.value = '请填写删除原因。'
    return
  }
  if (!target.value)
    return
  error.value = ''
  submitting.value = true
  try {
    await deleteKnowledgePoint(target.value.kbId, target.value.id, trimmedReason)
    // 不承诺回收站可恢复：本应用尚无回收站页面，后端虽支持恢复但用户今天
    // 没有任何 UI 入口可达（Kimi 终审，PR #24）
    ElMessage.success(`已删除「${target.value.title}」`)
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
  <el-dialog v-model="visible" class="app-dialog" title="删除知识点" width="560px" :close-on-click-modal="false">
    <p style="font-size: 13.5px; color: var(--ink-2); margin-bottom: 12px;">
      即将删除知识点 <b style="color: var(--ink-1)">{{ target?.title }}</b>，及其全部答案。
    </p>
    <div class="mf">
      <label><span class="req">*</span>删除原因</label>
      <textarea v-model="reason" rows="2" placeholder="请说明删除原因，将记录在留痕中" maxlength="500" />
    </div>
    <div class="risk">
      采用软删除：删除后不再出现在知识点列表与查询结果中；数据与全部历史答案会保留，如需恢复请联系管理员。
    </div>
    <p v-if="error" class="hint" style="color: var(--red)">
      {{ error }}
    </p>
    <template #footer>
      <button type="button" class="btn" @click="visible = false">
        取 消
      </button>
      <button type="button" class="btn danger" :disabled="submitting" @click="submit">
        确 定 删 除
      </button>
    </template>
  </el-dialog>
</template>
