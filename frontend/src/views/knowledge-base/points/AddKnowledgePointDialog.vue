<script setup lang="ts">
// 新增知识点弹窗：标题必填，默认答案内容可选（留空则不建默认答案）。
import { createKnowledgePoint } from '@/api/knowledgePoint'
import { today } from '@/utils/format'

const props = defineProps<{ kbId: number }>()

const emit = defineEmits<{
  /** 创建成功——父页面重载知识点列表与知识库统计 */
  success: []
}>()

const visible = ref(false)
const submitting = ref(false)
const title = ref('')
const content = ref('')
const effectiveTime = ref(today())
const error = ref('')

function open() {
  title.value = ''
  content.value = ''
  effectiveTime.value = today()
  error.value = ''
  visible.value = true
}
defineExpose({ open })

async function submit() {
  const trimmedTitle = title.value.trim()
  if (!trimmedTitle || !effectiveTime.value) {
    error.value = '标题、生效时间为必填项。'
    return
  }
  error.value = ''
  const trimmedContent = content.value.trim()
  submitting.value = true
  try {
    await createKnowledgePoint(props.kbId, {
      title: trimmedTitle,
      default_answer: trimmedContent
        ? { content: trimmedContent, effective_time: effectiveTime.value }
        : undefined,
    })
    ElMessage.success(`已创建知识点「${trimmedTitle}」`)
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
  <el-dialog v-model="visible" class="app-dialog" title="新增知识点" width="560px" :close-on-click-modal="false">
    <div class="mf">
      <label><span class="req">*</span>标题</label>
      <input v-model="title" type="text" placeholder="知识点标题，例如：退款政策" maxlength="255">
    </div>
    <div class="mf">
      <label>默认答案内容(可选)</label>
      <textarea v-model="content" rows="3" placeholder="不填条件、处处适用的默认说法；也可以先留空，之后再到详情页写答案" />
    </div>
    <div class="mf">
      <label><span class="req">*</span>生效时间</label>
      <input v-model="effectiveTime" type="date">
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
