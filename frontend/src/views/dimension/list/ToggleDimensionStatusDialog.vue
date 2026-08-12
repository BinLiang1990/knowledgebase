<script setup lang="ts">
// 启用/停用维度确认弹窗。
import type { AdminDimension } from '@/api/dimension'
import { setDimensionStatus } from '@/api/dimension'

const emit = defineEmits<{
  /** 状态更新成功——父页面重载维度列表 */
  success: []
}>()

const visible = ref(false)
const submitting = ref(false)
const target = ref<AdminDimension | null>(null)

const willDeactivate = computed(() => target.value?.status === 'active')

function open(dim: AdminDimension) {
  target.value = dim
  visible.value = true
}
defineExpose({ open })

async function confirm() {
  if (!target.value)
    return
  submitting.value = true
  try {
    await setDimensionStatus(target.value.key, willDeactivate.value ? 'deprecated' : 'active')
    ElMessage.success('已更新维度状态')
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
    :title="willDeactivate ? '停用维度' : '启用维度'"
    width="560px"
    :close-on-click-modal="false"
  >
    <p style="font-size: 13.5px; color: var(--ink-2); line-height: 1.8;">
      即将{{ willDeactivate ? '停用' : '启用' }}维度 <b style="color: var(--ink-1)">{{ target?.label }}</b>。
    </p>
    <div v-if="willDeactivate" class="risk">
      已有 {{ target?.answer_count }} 条答案写入过该维度的取值，停用不会影响这些历史数据，仅新增/编辑答案时不再出现该字段。
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
