<script setup lang="ts">
// 启用/停用知识库确认弹窗。
import type { KnowledgeBase } from '@/api/knowledgeBase'
import { setKnowledgeBaseStatus } from '@/api/knowledgeBase'

const emit = defineEmits<{
  /** 状态更新成功——父页面重载列表 */
  success: []
}>()

const visible = ref(false)
const submitting = ref(false)
const target = ref<KnowledgeBase | null>(null)

const willDeactivate = computed(() => target.value?.status === 'active')

function open(kb: KnowledgeBase) {
  target.value = kb
  visible.value = true
}
defineExpose({ open })

async function confirm() {
  if (!target.value)
    return
  submitting.value = true
  try {
    await setKnowledgeBaseStatus(target.value.id, willDeactivate.value ? 'deprecated' : 'active')
    ElMessage.success('已更新知识库状态')
    emit('success')
  }
  catch {
    // 确认弹窗没有可挂内联错误的表单项，错误提示由拦截器弹出后直接关窗
  }
  finally {
    submitting.value = false
    visible.value = false
  }
}
</script>

<template>
  <el-dialog
    v-model="visible"
    class="app-dialog"
    :title="willDeactivate ? '停用知识库' : '启用知识库'"
    width="560px"
    :close-on-click-modal="false"
  >
    <p style="font-size: 13.5px; color: var(--ink-2); line-height: 1.8;">
      即将{{ willDeactivate ? '停用' : '启用' }}知识库 <b style="color: var(--ink-1)">{{ target?.name }}</b>。
    </p>
    <div v-if="willDeactivate" class="risk">
      该知识库下有 {{ target?.active_knowledge_point_count }} 个知识点，停用后知识库列表不再显示、无法进入；知识点数据不会被删除，重新启用后可继续访问。
    </div>
    <template #footer>
      <button type="button" class="btn" @click="visible = false">
        取 消
      </button>
      <button
        type="button"
        class="btn"
        :class="willDeactivate ? 'danger' : 'primary'"
        :disabled="submitting"
        @click="confirm"
      >
        确 定
      </button>
    </template>
  </el-dialog>
</template>
