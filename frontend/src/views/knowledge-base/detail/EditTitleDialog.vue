<script setup lang="ts">
// 编辑知识点标题弹窗。
import { updateKnowledgePointTitle } from '@/api/knowledgePoint'

const props = defineProps<{
  kbId: number
  kpId: number
}>()

const emit = defineEmits<{
  /** 更新成功——父页面重载知识点详情 */
  success: []
}>()

const visible = ref(false)
const submitting = ref(false)
const title = ref('')
const error = ref('')

function open(currentTitle: string) {
  title.value = currentTitle
  error.value = ''
  visible.value = true
}
defineExpose({ open })

async function submit() {
  const trimmed = title.value.trim()
  if (!trimmed) {
    error.value = '请填写标题。'
    return
  }
  error.value = ''
  submitting.value = true
  try {
    await updateKnowledgePointTitle(props.kbId, props.kpId, trimmed)
    ElMessage.success('已更新标题')
    visible.value = false
    emit('success')
  }
  catch {
    // 服务端错误已由 request 拦截器统一提示，保持弹窗打开供修改
  }
  finally {
    submitting.value = false
  }
}
</script>

<template>
  <el-dialog v-model="visible" class="app-dialog" title="编辑标题" width="560px" :close-on-click-modal="false">
    <div class="mf">
      <label><span class="req">*</span>标题</label>
      <input v-model="title" type="text" maxlength="255">
    </div>
    <p v-if="error" class="hint" style="color: var(--red)">
      {{ error }}
    </p>
    <template #footer>
      <button type="button" class="btn" @click="visible = false">
        取 消
      </button>
      <button type="button" class="btn primary" :disabled="submitting" @click="submit">
        确 定
      </button>
    </template>
  </el-dialog>
</template>
