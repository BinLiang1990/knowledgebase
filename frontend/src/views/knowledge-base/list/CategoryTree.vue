<script setup lang="ts">
// 知识库列表页左栏的分类树（PRD §4.11，issue #40）。分类管理不设独立
// 页面——增删改、拖拽排序/改层级、名称搜索全部在这棵树上就地完成；
// 视觉与交互基准是 frontend-mock/kb-list.html。
//
// 拖拽直接用 el-tree 的 draggable：drop-type 的 before/after/inner 与
// 后端 POST /categories/{id}/move 的 before/after/inside 一一对应。
// el-tree 落子时已先行改了本地树，所以无论接口成败都 reload() 以服务端
// 为准（失败即回滚视觉）。
import type { Category, CategoryScope } from '@/api/category'
import { listCategories, moveCategory } from '@/api/category'
import CategoryFormDialog from './CategoryFormDialog.vue'
import DeleteCategoryDialog from './DeleteCategoryDialog.vue'

const props = defineProps<{
  /** 启用中知识库总数（「全部」节点的数字） */
  totalActiveCount: number
  /** category_id 为空的启用中知识库数（「未分类」节点的数字） */
  uncategorizedCount: number
  /** 各分类下**全部状态**的知识库数（删除拦截口径：含已停用，占用即阻塞） */
  kbCountByCategory: Record<number, number>
}>()

const emit = defineEmits<{
  /** 选中节点变化 / 结构变化后刷新——父页据此过滤右侧列表 */
  select: [scope: CategoryScope]
  /** 分类增删改/移动成功——父页可刷新知识库列表（分类名列可能变化） */
  changed: []
}>()

interface TreeNodeData {
  key: string
  id: number | null
  virtual?: 'all' | 'none'
  name: string
  directCount: number
  subtreeCount: number
  children: TreeNodeData[]
}

const cats = ref<Category[]>([])
const loading = ref(false)
const failed = ref(false)
const selectedKey = ref('all')
const keywordInput = ref('')
const keyword = ref('')

type TreeNodeArg = any

const treeRef = ref()

const treeData = computed<TreeNodeData[]>(() => {
  const byParent = new Map<number | null, Category[]>()
  for (const c of cats.value) {
    const list = byParent.get(c.parent_id) ?? []
    list.push(c)
    byParent.set(c.parent_id, list)
  }
  function build(parentId: number | null): TreeNodeData[] {
    return (byParent.get(parentId) ?? []).map((c) => {
      const children = build(c.id)
      return {
        key: `c${c.id}`,
        id: c.id,
        name: c.name,
        directCount: c.active_knowledge_base_count,
        subtreeCount: c.active_knowledge_base_count + children.reduce((s, k) => s + k.subtreeCount, 0),
        children,
      }
    })
  }
  return [
    { key: 'all', id: null, virtual: 'all' as const, name: '全部', directCount: props.totalActiveCount, subtreeCount: props.totalActiveCount, children: [] },
    { key: 'none', id: null, virtual: 'none' as const, name: '未分类', directCount: props.uncategorizedCount, subtreeCount: props.uncategorizedCount, children: [] },
    ...build(null),
  ]
})

const catById = computed(() => new Map(cats.value.map(c => [c.id, c])))

function descendantIds(id: number): number[] {
  const byParent = new Map<number | null, number[]>()
  for (const c of cats.value) {
    const list = byParent.get(c.parent_id) ?? []
    list.push(c.id)
    byParent.set(c.parent_id, list)
  }
  const out: number[] = []
  const queue = [...(byParent.get(id) ?? [])]
  while (queue.length) {
    const current = queue.pop()!
    out.push(current)
    queue.push(...(byParent.get(current) ?? []))
  }
  return out
}

function categoryPath(id: number): string {
  const parts: string[] = []
  let current = catById.value.get(id)
  while (current) {
    parts.unshift(current.name)
    current = current.parent_id === null ? undefined : catById.value.get(current.parent_id)
  }
  return parts.join(' / ')
}

function currentScope(): CategoryScope {
  if (selectedKey.value === 'all')
    return { type: 'all' }
  if (selectedKey.value === 'none')
    return { type: 'none' }
  const id = Number(selectedKey.value.slice(1))
  return { type: 'category', id, label: `${categoryPath(id)}（含子分类）`, ids: [id, ...descendantIds(id)] }
}

async function reload() {
  loading.value = true
  failed.value = false
  try {
    cats.value = await listCategories()
    // 选中的分类可能已被删除/移动——不存在则回落到「全部」；无论如何
    // 重发一次 select，让父页拿到基于最新结构的 scope（含子孙 id 集合）
    if (selectedKey.value.startsWith('c') && !catById.value.has(Number(selectedKey.value.slice(1))))
      selectedKey.value = 'all'
    emit('select', currentScope())
  }
  catch {
    failed.value = true
  }
  finally {
    loading.value = false
  }
}
reload()
defineExpose({ reload })

function onNodeClick(data: TreeNodeData) {
  selectedKey.value = data.key
  emit('select', currentScope())
}

// ---- 名称搜索：命中节点连同祖先展示，未命中分支隐藏；搜索态暂停拖拽 ----
watch(keywordInput, (value) => {
  keyword.value = value.trim()
  treeRef.value?.filter(keyword.value)
})
// 参数用宽松的 Record 签名——el-tree 的 FilterNodeMethodFunction 声明的是
// 它自己的索引类型，具名接口在逆变位置对不上；进函数体立刻收窄
function filterNode(value: string, rawData: Record<string, unknown>): boolean {
  const data = rawData as unknown as TreeNodeData
  if (!value)
    return true
  if (data.virtual)
    return false // 搜索态隐藏「全部/未分类」虚拟节点，与原型一致
  return data.name.toLowerCase().includes(value.toLowerCase())
}
const noMatch = computed(() =>
  keyword.value !== ''
  && !cats.value.some(c => c.name.toLowerCase().includes(keyword.value.toLowerCase())),
)

/** 关键字高亮切分：null = 未命中（原样展示） */
function kwParts(name: string): { pre: string, hit: string, post: string } | null {
  if (!keyword.value)
    return null
  const index = name.toLowerCase().indexOf(keyword.value.toLowerCase())
  if (index < 0)
    return null
  return { pre: name.slice(0, index), hit: name.slice(index, index + keyword.value.length), post: name.slice(index + keyword.value.length) }
}

// ---- 拖拽：上/下边缘 = 调同级排序，中部 = 挂为子分类（PRD §4.11） ----
function allowDrag(node: TreeNodeArg): boolean {
  return !keyword.value && !node.data.virtual
}
function allowDrop(_dragging: TreeNodeArg, drop: TreeNodeArg, _type: 'prev' | 'inner' | 'next'): boolean {
  return !drop.data.virtual
}
async function onNodeDrop(dragging: TreeNodeArg, drop: TreeNodeArg, dropType: 'before' | 'after' | 'inner') {
  const position = dropType === 'inner' ? 'inside' : dropType
  try {
    await moveCategory(dragging.data.id, { target_id: drop.data.id, position })
    ElMessage.success(
      position === 'inside'
        ? `已将「${dragging.data.name}」移动到「${drop.data.name}」之下`
        : `已调整「${dragging.data.name}」的排序`,
    )
    emit('changed')
  }
  catch {
    // 成环/落点重名等已由 request 拦截器提示；reload 会回滚 el-tree 的本地乐观移动
  }
  finally {
    await reload()
  }
}

// ---- 增删改弹窗 ----
const formDialogRef = ref<InstanceType<typeof CategoryFormDialog>>()
const deleteDialogRef = ref<InstanceType<typeof DeleteCategoryDialog>>()

function openCreate(parentId: number | null) {
  formDialogRef.value?.open(undefined, parentId)
}
function openEdit(data: TreeNodeData) {
  const category = catById.value.get(data.id!)
  if (category)
    formDialogRef.value?.open(category)
}
function openDelete(data: TreeNodeData) {
  deleteDialogRef.value?.open(
    { id: data.id!, name: data.name, path: categoryPath(data.id!) },
    { childCount: data.children.length, kbCount: props.kbCountByCategory[data.id!] ?? 0 },
  )
}
async function onMutated() {
  await reload()
  emit('changed')
}
</script>

<template>
  <div class="card tree-panel">
    <div class="tree-search">
      <input v-model="keywordInput" type="text" placeholder="按分类名称搜索">
      <button v-if="keywordInput" type="button" class="btn sm" title="清空搜索" @click="keywordInput = ''">
        ✕
      </button>
    </div>

    <div class="tree-scroll">
      <div v-if="loading" class="tree-empty">
        <span class="spin" /> 加载分类中…
      </div>
      <div v-else-if="failed" class="tree-empty">
        分类加载失败<br><a @click="reload">重试</a>
      </div>
      <div v-else-if="noMatch" class="tree-empty">
        无匹配分类<br>换个关键字，或清空搜索恢复完整树
      </div>
      <el-tree
        v-show="!loading && !failed && !noMatch"
        ref="treeRef"
        :data="treeData"
        node-key="key"
        default-expand-all
        :expand-on-click-node="false"
        :filter-node-method="filterNode"
        draggable
        :allow-drag="allowDrag"
        :allow-drop="allowDrop"
        @node-click="onNodeClick"
        @node-drop="onNodeDrop"
      >
        <template #default="{ data }">
          <div
            class="tnode"
            :class="{ sel: selectedKey === data.key, virtual: !!data.virtual }"
            :title="data.virtual ? undefined : categoryPath(data.id)"
          >
            <span class="nm">
              <template v-if="kwParts(data.name)">
                {{ kwParts(data.name)!.pre }}<mark>{{ kwParts(data.name)!.hit }}</mark>{{ kwParts(data.name)!.post }}
              </template>
              <template v-else>
                {{ data.name }}
              </template>
            </span>
            <span class="cnt num">
              ({{ data.directCount }})<template v-if="data.children.length">({{ data.subtreeCount }})</template>
            </span>
            <span v-if="!data.virtual" class="acts" @click.stop>
              <a title="编辑分类" @click="openEdit(data)">✎</a>
              <a title="新增子分类" @click="openCreate(data.id)">＋</a>
              <a class="danger" title="删除分类" @click="openDelete(data)">－</a>
            </span>
          </div>
        </template>
      </el-tree>
    </div>

    <div class="tree-foot">
      <button type="button" class="btn sm add-root" @click="openCreate(null)">
        ＋ 新增顶级分类
      </button>
      <div class="tree-hint">
        同一父分类下名称唯一（≤50 字）；仅允许删除<b>空分类</b>。拖拽节点上/下边缘调排序、拖到中部挂为子分类；不能拖到自己或子孙下，搜索时暂停拖拽。
      </div>
    </div>

    <CategoryFormDialog ref="formDialogRef" :categories="cats" @success="onMutated" />
    <DeleteCategoryDialog ref="deleteDialogRef" @success="onMutated" />
  </div>
</template>

<style scoped>
.tree-panel {
  width: 288px;
  flex: none;
  position: sticky;
  top: 82px;
  max-height: calc(100vh - 100px);
  display: flex;
  flex-direction: column;
}
.tree-search {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}
.tree-search input {
  flex: 1;
  min-width: 0;
}
.tree-scroll {
  overflow-y: auto;
  flex: 1;
  margin: 0 -8px;
  padding: 0 8px;
}
.tree-empty {
  padding: 24px 8px;
  text-align: center;
  color: var(--ink-5);
  font-size: 12.5px;
  line-height: 1.8;
}
.tnode {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  padding-right: 4px;
  font-size: 13.5px;
  color: var(--ink-2);
}
.tnode.sel {
  color: var(--brand-deep, #1a56f0);
  font-weight: 600;
}
.tnode.virtual .nm {
  font-weight: 600;
}
.tnode .nm {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.tnode .nm mark {
  background: #ffe9a8;
  color: inherit;
  border-radius: 2px;
  padding: 0 1px;
}
.tnode .cnt {
  color: var(--ink-5);
  font-size: 12px;
  flex: none;
  font-weight: 400;
}
.tnode.sel .cnt {
  color: var(--brand, #2f6bff);
}
.tnode .acts {
  margin-left: auto;
  flex: none;
  display: none;
  gap: 6px;
}
.tnode .acts a {
  font-size: 13px;
  line-height: 1;
}
:deep(.el-tree-node__content) {
  height: 30px;
  border-radius: 8px;
}
:deep(.el-tree-node__content:hover) .acts {
  display: inline-flex;
}
.tree-foot {
  border-top: 1px solid var(--line);
  margin-top: 10px;
  padding-top: 10px;
}
.tree-foot .add-root {
  width: 100%;
  justify-content: center;
}
.tree-hint {
  font-size: 11.5px;
  color: var(--ink-6);
  line-height: 1.7;
  margin-top: 8px;
}
</style>
