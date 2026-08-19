<script setup lang="ts">
// 新增/编辑分类合体弹窗：open() 顶级新增、open(undefined, parentId) 指定
// 父级新增、open(category) 编辑。编辑时更换父分类 = 移动节点（子树随迁，
// 排到新同级末尾）；父级下拉排除自己与全部子孙（防成环，后端仍会兜底校验）。
import type { Category } from '@/api/category'
import { createCategory, updateCategory } from '@/api/category'

const props = defineProps<{
  /** 全量分类（构建父级下拉；来自 CategoryTree 已加载的数据） */
  categories: Category[]
}>()

const emit = defineEmits<{
  success: []
}>()

/** 父级下拉的「顶级分类」哨兵——el-select 的 option 值不便直接用 null */
const TOP_LEVEL = 0

const visible = ref(false)
const submitting = ref(false)
const target = ref<Category | null>(null)
const name = ref('')
const parentValue = ref<number>(TOP_LEVEL)
const error = ref('')

const isEdit = computed(() => target.value !== null)
const title = computed(() => {
  if (isEdit.value)
    return `编辑分类 · ${target.value!.name}`
  const parent = props.categories.find(c => c.id === parentValue.value)
  return parent ? `新增子分类 · ${parent.name} 之下` : '新增顶级分类'
})

/** 缩进的父级选项；编辑时排除自己与子孙 */
const parentOptions = computed(() => {
  const banned = new Set<number>()
  if (target.value) {
    banned.add(target.value.id)
    const byParent = new Map<number | null, number[]>()
    for (const c of props.categories) {
      const list = byParent.get(c.parent_id) ?? []
      list.push(c.id)
      byParent.set(c.parent_id, list)
    }
    const queue = [...(byParent.get(target.value.id) ?? [])]
    while (queue.length) {
      const current = queue.pop()!
      banned.add(current)
      queue.push(...(byParent.get(current) ?? []))
    }
  }
  const options: { id: number, label: string }[] = []
  const walk = (parentId: number | null, depth: number) => {
    for (const c of props.categories.filter(x => x.parent_id === parentId)) {
      if (banned.has(c.id))
        continue
      options.push({ id: c.id, label: `${'　'.repeat(depth)}${c.name}` })
      walk(c.id, depth + 1)
    }
  }
  walk(null, 0)
  return options
})

function open(category?: Category, parentId?: number | null) {
  target.value = category ?? null
  name.value = category?.name ?? ''
  parentValue.value = (category ? category.parent_id : parentId) ?? TOP_LEVEL
  error.value = ''
  visible.value = true
}
defineExpose({ open })

async function submit() {
  const trimmedName = name.value.trim()
  if (!trimmedName) {
    error.value = '请填写分类名称。'
    return
  }
  if (trimmedName.length > 50) {
    error.value = `分类名称不能超过 50 字（当前 ${trimmedName.length} 字）。`
    return
  }
  error.value = ''
  submitting.value = true
  const parentId = parentValue.value === TOP_LEVEL ? null : parentValue.value
  try {
    if (target.value)
      await updateCategory(target.value.id, { name: trimmedName, parent_id: parentId })
    else
      await createCategory({ name: trimmedName, parent_id: parentId })
    ElMessage.success(isEdit.value ? `已更新分类「${trimmedName}」` : `已新增分类「${trimmedName}」`)
    visible.value = false
    emit('success')
  }
  catch {
    // 同级重名/成环等业务错误已由 request 拦截器统一提示，保持弹窗打开供修改
  }
  finally {
    submitting.value = false
  }
}
</script>

<template>
  <el-dialog v-model="visible" class="app-dialog" :title="title" width="480px" :close-on-click-modal="false">
    <div class="mf">
      <label><span class="req">*</span>分类名称</label>
      <input v-model="name" type="text" placeholder="例如：研发实验小组（≤50 字）" maxlength="50">
    </div>
    <div class="mf">
      <label>所属父分类</label>
      <el-select v-model="parentValue" style="width: 100%">
        <el-option :value="TOP_LEVEL" label="（顶级分类）" />
        <el-option v-for="option in parentOptions" :key="option.id" :value="option.id" :label="option.label" />
      </el-select>
      <div class="hint">
        编辑时更换父分类 = 移动节点（子树整体随迁）；不能移动到自己或自己的子孙分类下。
      </div>
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
