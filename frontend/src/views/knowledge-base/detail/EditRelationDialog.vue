<script setup lang="ts">
// 编辑关联描述（docs/PRD-答案关联.md §3.4）：人工改写后 source 转 manual，
// 后续 AI 分析不再覆盖这条关联。
import type { AnswerRelation } from '@/api/relation'
import { updateRelationDescription } from '@/api/relation'

const emit = defineEmits<{
  success: []
}>()

const visible = ref(false)
const submitting = ref(false)
const error = ref('')
const description = ref('')
const relationId = ref<number | null>(null)

function open(relation: AnswerRelation) {
  relationId.value = relation.id
  description.value = relation.description
  error.value = ''
  visible.value = true
}
defineExpose({ open })

async function submit() {
  const trimmed = description.value.trim()
  if (!trimmed) {
    error.value = '描述不能为空。'
    return
  }
  if (relationId.value == null)
    return
  error.value = ''
  submitting.value = true
  try {
    await updateRelationDescription(relationId.value, trimmed)
    ElMessage.success('已更新描述')
    visible.value = false
    emit('success')
  }
  catch {
    // request 拦截器已提示
  }
  finally {
    submitting.value = false
  }
}
</script>

<template>
  <el-dialog v-model="visible" class="app-dialog" title="编辑关联描述" width="560px" :close-on-click-modal="false">
    <div class="mf">
      <label><span class="req">*</span>关联描述</label>
      <textarea v-model="description" rows="5" maxlength="2000" />
    </div>
    <div class="hint">
      人工改写后该关联标记为「手动」，后续 AI 分析不再覆盖它。
    </div>
    <p v-if="error" class="hint" style="color: var(--red)">
      {{ error }}
    </p>
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
