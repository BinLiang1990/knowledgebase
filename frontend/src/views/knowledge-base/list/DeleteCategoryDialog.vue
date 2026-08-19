<script setup lang="ts">
// 删除分类确认弹窗：仅允许删除空分类（PRD §4.11）——有子分类或有知识库
// 归属（含已停用）时禁用删除按钮并说明数量，让用户先迁移再删；空分类
// 二次确认后物理删除（分类无留痕诉求）。后端同样校验，这里的禁用只是
// 前置引导。
import { deleteCategory } from '@/api/category'

const emit = defineEmits<{
  success: []
}>()

const visible = ref(false)
const submitting = ref(false)
const target = ref<{ id: number, name: string, path: string } | null>(null)
const childCount = ref(0)
const kbCount = ref(0)

const blocked = computed(() => childCount.value > 0 || kbCount.value > 0)

function open(category: { id: number, name: string, path: string }, counts: { childCount: number, kbCount: number }) {
  target.value = category
  childCount.value = counts.childCount
  kbCount.value = counts.kbCount
  visible.value = true
}
defineExpose({ open })

async function confirm() {
  if (!target.value || blocked.value)
    return
  submitting.value = true
  try {
    await deleteCategory(target.value.id)
    ElMessage.success(`已删除分类「${target.value.name}」`)
    visible.value = false
    emit('success')
  }
  catch {
    // 并发窗口内变为非空等错误已由 request 拦截器提示
  }
  finally {
    submitting.value = false
  }
}
</script>

<template>
  <el-dialog v-model="visible" class="app-dialog" title="删除分类" width="480px" :close-on-click-modal="false">
    <p v-if="target" style="font-size: 13.5px; color: var(--ink-2); line-height: 1.8">
      即将删除分类 <b>{{ target.name }}</b>（{{ target.path }}）。
    </p>
    <div v-if="blocked" class="risk">
      无法删除：该分类下仍有 <b>{{ childCount }} 个子分类、{{ kbCount }} 个知识库</b>（含已停用）。
      请先把知识库改挂到其他分类或置为未分类、并清空子分类后再删。
    </div>
    <template #footer>
      <button type="button" class="btn" @click="visible = false">
        取 消
      </button>
      <button type="button" class="btn danger" :disabled="blocked || submitting" @click="confirm">
        删 除
      </button>
    </template>
  </el-dialog>
</template>
