<script setup lang="ts">
// 新增/编辑知识库合体弹窗：open() 新增、open(kb) 编辑（规范 §8.2 非受控模式）。
// 新增模式下可直接勾选启用维度（与建库同一事务）——省去"建完还要去
// 知识库设置勾维度"的二段式操作；编辑模式刻意不出现维度区（调整已建库的
// 维度是设置页的职责，那里有"使用中"的保留链路语义）。
import type { Category } from '@/api/category'
import type { Dimension } from '@/api/dimension'
import type { KnowledgeBase } from '@/api/knowledgeBase'
import { listCategories } from '@/api/category'
import { listAdminDimensions } from '@/api/dimension'
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

const dimensions = ref<Dimension[]>([])
const dimensionsLoading = ref(false)
const dimensionsFailed = ref(false)
const selectedDimensionKeys = ref<string[]>([])

// 所属分类（PRD §4.11，issue #40）：新增/编辑都可挂分类；el-tree-select
// 清空时值为 undefined，提交时统一转 null（后端 null = 未分类）
const categories = ref<Category[]>([])
const categoryId = ref<number | undefined>(undefined)

interface CategoryTreeOption {
  value: number
  label: string
  children: CategoryTreeOption[]
}
const categoryOptions = computed<CategoryTreeOption[]>(() => {
  const build = (parentId: number | null): CategoryTreeOption[] =>
    categories.value
      .filter(c => c.parent_id === parentId)
      .map(c => ({ value: c.id, label: c.name, children: build(c.id) }))
  return build(null)
})

async function loadCategories() {
  try {
    categories.value = await listCategories()
  }
  catch {
    // 分类加载失败不阻塞建库/编辑（下拉为空 = 只能选未分类），错误已由拦截器提示
  }
}

const isEdit = computed(() => target.value !== null)
const title = computed(() => (isEdit.value ? `编辑知识库 · ${target.value!.name}` : '新增知识库'))

async function loadDimensions() {
  dimensionsLoading.value = true
  dimensionsFailed.value = false
  try {
    dimensions.value = (await listAdminDimensions()).filter(d => d.status === 'active')
  }
  catch {
    // 维度加载失败不阻塞建库（勾选区显示重试入口），错误已由拦截器提示
    dimensionsFailed.value = true
  }
  finally {
    dimensionsLoading.value = false
  }
}

function open(kb?: KnowledgeBase, defaults?: { categoryId?: number | null }) {
  target.value = kb ?? null
  name.value = kb?.name ?? ''
  description.value = kb?.description ?? ''
  // 编辑回填当前分类；新增预填父页当前选中的分类（可清空 = 未分类）
  categoryId.value = (kb ? kb.category_id : defaults?.categoryId) ?? undefined
  error.value = ''
  selectedDimensionKeys.value = []
  visible.value = true
  loadCategories()
  if (!kb)
    loadDimensions()
}
defineExpose({ open })

async function submit() {
  const trimmedName = name.value.trim()
  if (!trimmedName) {
    error.value = '请填写知识库名称。'
    return
  }
  error.value = ''
  submitting.value = true
  try {
    if (target.value) {
      await updateKnowledgeBase(target.value.id, {
        name: trimmedName,
        description: description.value.trim(),
        category_id: categoryId.value ?? null,
      })
    }
    else {
      await createKnowledgeBase({
        name: trimmedName,
        description: description.value.trim(),
        category_id: categoryId.value ?? null,
        enabled_dimension_keys: selectedDimensionKeys.value.length ? selectedDimensionKeys.value : undefined,
      })
    }
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
    <div class="mf">
      <label>所属分类</label>
      <el-tree-select
        v-model="categoryId"
        :data="categoryOptions"
        check-strictly
        default-expand-all
        clearable
        placeholder="未分类（可选）"
        style="width: 100%"
      />
      <div class="hint">
        不选 = 未分类；可随时在「编辑」里改挂分类，左侧分类树上按分类（含子分类）筛选。
      </div>
    </div>
    <div v-if="!isEdit" class="mf">
      <label>启用维度(可选)</label>
      <div v-if="dimensionsLoading" class="hint">
        <span class="spin" /> 加载维度中…
      </div>
      <div v-else-if="dimensionsFailed" class="hint">
        维度加载失败 · <a @click="loadDimensions">重试</a>（也可以先建库，稍后到「知识库设置」启用）
      </div>
      <div v-else-if="dimensions.length === 0" class="hint">
        还没有可用的全局维度——先到「维度管理」新增，或建库后再到「知识库设置」启用
      </div>
      <template v-else>
        <div style="display: flex; flex-wrap: wrap; gap: 8px 18px; padding: 4px 0">
          <label
            v-for="d in dimensions"
            :key="d.key"
            style="display: flex; align-items: center; gap: 6px; font-size: 13px; cursor: pointer"
          >
            <input v-model="selectedDimensionKeys" type="checkbox" :value="d.key">
            {{ d.label }}<span style="color: var(--ink-6)">（权重 {{ d.weight }}）</span>
          </label>
        </div>
        <div class="hint">
          只有启用的维度才能在本知识库的答案里用作适用条件；创建后可随时到「知识库设置」调整
        </div>
      </template>
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
