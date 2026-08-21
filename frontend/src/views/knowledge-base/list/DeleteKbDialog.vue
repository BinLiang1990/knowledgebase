<script setup lang="ts">
// 删除知识库（进回收站）确认弹窗。仅已停用的库可删（入口已按状态隐藏，
// 后端仍强校验）；删除后可在回收站还原。
import type { KnowledgeBase } from '@/api/knowledgeBase'
import { deleteKnowledgeBase } from '@/api/knowledgeBase'

const emit = defineEmits<{
  /** 删除成功——父页面重载列表 */
  success: []
}>()

const visible = ref(false)
const submitting = ref(false)
const target = ref<KnowledgeBase | null>(null)

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
    await deleteKnowledgeBase(target.value.id)
    ElMessage.success('已删除，可在回收站还原')
    emit('success')
  }
  catch {
    // 错误提示由拦截器统一弹出，同 ToggleKbStatusDialog
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
    title="删除知识库"
    width="560px"
    :close-on-click-modal="false"
  >
    <p style="font-size: 13.5px; color: var(--ink-2); line-height: 1.8;">
      即将删除知识库 <b style="color: var(--ink-1)">{{ target?.name }}</b>。
    </p>
    <div class="risk">
      删除后该知识库进入<b>回收站</b>，其下知识点与答案数据不会丢失；如需继续使用，可在回收站还原（还原后为「已停用」状态）。回收站名称仍被占用，新建同名知识库会被拒绝。
    </div>
    <template #footer>
      <button type="button" class="btn" @click="visible = false">
        取 消
      </button>
      <button type="button" class="btn danger" :disabled="submitting" @click="confirm">
        删 除
      </button>
    </template>
  </el-dialog>
</template>
