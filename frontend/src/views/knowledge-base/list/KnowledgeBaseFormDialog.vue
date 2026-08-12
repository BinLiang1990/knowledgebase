<script setup lang="ts">
// 新增/编辑知识库合体弹窗：open() 新增、open(kb) 编辑（规范 §8.2 非受控模式）。
import type { KnowledgeBase } from '@/api/knowledgeBase'
import { createKnowledgeBase, updateKnowledgeBase } from '@/api/knowledgeBase'

const emit = defineEmits<{
  /** 保存成功——父页面重载列表 */
  success: []
}>()

const visible = ref(false)
const submitting = ref(false)
const target = ref<KnowledgeBase | null>(null)
const name = ref('')
const description = ref('')
const error = ref('')

const isEdit = computed(() => target.value !== null)
const title = computed(() => (isEdit.value ? `编辑知识库 · ${target.value!.name}` : '新增知识库'))

function open(kb?: KnowledgeBase) {
  target.value = kb ?? null
  name.value = kb?.name ?? ''
  description.value = kb?.description ?? ''
  error.value = ''
  visible.value = true
}
defineExpose({ open })

async function submit() {
  const trimmedName = name.value.trim()
  if (!trimmedName) {
    error.value = '请填写知识库名称。'
    return
  }
  error.value = ''
  const input = { name: trimmedName, description: description.value.trim() }
  submitting.value = true
  try {
    if (target.value)
      await updateKnowledgeBase(target.value.id, input)
    else
      await createKnowledgeBase(input)
    ElMessage.success(isEdit.value ? `已更新知识库「${trimmedName}」` : `已创建知识库「${trimmedName}」`)
    visible.value = false
    emit('success')
  }
  catch {
    // 业务(444)/校验(422)错误已由 request 拦截器统一提示，保持弹窗打开供修改
  }
  finally {
    submitting.value = false
  }
}
</script>

<template>
  <el-dialog v-model="visible" class="app-dialog" :title="title" width="560px" :close-on-click-modal="false">
    <div class="mf">
      <label><span class="req">*</span>名称</label>
      <!-- maxlength 镜像后端 schemas/knowledge_base.py 的 max_length=255：后端
           422 报文是无字段明细的固定文案，客户端限长让真实 422 极少发生 -->
      <input v-model="name" type="text" placeholder="例如：产品知识库" maxlength="255">
    </div>
    <div class="mf">
      <label>描述(可选)</label>
      <textarea v-model="description" rows="2" placeholder="这个知识库用来存放什么类型的知识点" maxlength="2000" />
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
