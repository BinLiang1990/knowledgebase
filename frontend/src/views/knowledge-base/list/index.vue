<script setup lang="ts">
// 知识库列表页。列表接口无关键词/分页参数，搜索与分页在前端内存中完成
// （设计文档 §5，见 api/knowledgeBase.ts 的注释）。
// 2026-08-19（issue #40）：左侧新增分类树（PRD §4.11）——点击分类节点，
// 右侧只展示该分类及其全部子孙下的知识库；分类过滤同样在前端内存中做
// （后端虽提供 ?category_id= 过滤，但列表本来就是全量拉取 + 客户端过滤，
// 保持同一套口径；对外接口的服务端过滤面向第三方）。
import type { CategoryScope } from '@/api/category'
import type { KnowledgeBase } from '@/api/knowledgeBase'
import { listKnowledgeBases } from '@/api/knowledgeBase'
import { useAsyncData } from '@/composables/useAsyncData'
import { formatDate } from '@/utils/format'
import CategoryTree from './CategoryTree.vue'
import KnowledgeBaseFormDialog from './KnowledgeBaseFormDialog.vue'
import ToggleKbStatusDialog from './ToggleKbStatusDialog.vue'

defineOptions({ name: 'KnowledgeBaseList' })

const PAGE_SIZE = 8

const kbQuery = useAsyncData(listKnowledgeBases)

const keywordInput = ref('')
const keyword = ref('')
const page = ref(1)
const scope = ref<CategoryScope>({ type: 'all' })

const scopeIds = computed(() => (scope.value.type === 'category' ? new Set(scope.value.ids) : null))
const scopeLabel = computed(() => {
  if (scope.value.type === 'none')
    return '未分类'
  return scope.value.type === 'category' ? scope.value.label : '全部知识库'
})

const filtered = computed(() => {
  const list = kbQuery.data.value ?? []
  return list.filter((kb) => {
    if (scope.value.type === 'none' && kb.category_id !== null)
      return false
    if (scopeIds.value && (kb.category_id === null || !scopeIds.value.has(kb.category_id)))
      return false
    if (!keyword.value)
      return true
    return `${kb.name} ${kb.description ?? ''}`.toLowerCase().includes(keyword.value)
  })
})

const pageCount = computed(() => Math.max(1, Math.ceil(filtered.value.length / PAGE_SIZE)))
// 变更（编辑/停用）可能把当前页从 filtered 底下抽空——比如搜索结果第 2 页
// 仅剩的一条被停用后 page 还停在 2，分页会显示无效的「第 2/1 页」。夹回
// 合法范围（Codex 结论，PR #22）。
watch(pageCount, (count) => {
  if (page.value > count)
    page.value = count
})
const pageItems = computed(() => filtered.value.slice((page.value - 1) * PAGE_SIZE, page.value * PAGE_SIZE))

function applyFilter() {
  keyword.value = keywordInput.value.trim().toLowerCase()
  page.value = 1
}
function resetFilter() {
  keywordInput.value = ''
  keyword.value = ''
  page.value = 1
}
function onScopeSelect(next: CategoryScope) {
  scope.value = next
  page.value = 1
}

// ---- 分类树的计数口径（PRD §4.11）：节点数字只统计启用中的知识库；
// 删除拦截按「占用即阻塞」统计全部状态（含已停用） ----
const totalActiveCount = computed(() => (kbQuery.data.value ?? []).filter(kb => kb.status === 'active').length)
const uncategorizedCount = computed(() =>
  (kbQuery.data.value ?? []).filter(kb => kb.status === 'active' && kb.category_id === null).length,
)
const kbCountByCategory = computed(() => {
  const counts: Record<number, number> = {}
  for (const kb of kbQuery.data.value ?? []) {
    if (kb.category_id !== null)
      counts[kb.category_id] = (counts[kb.category_id] ?? 0) + 1
  }
  return counts
})

const treeRef = ref<InstanceType<typeof CategoryTree>>()
const formDialogRef = ref<InstanceType<typeof KnowledgeBaseFormDialog>>()
const toggleDialogRef = ref<InstanceType<typeof ToggleKbStatusDialog>>()

function openCreate() {
  // 预填当前选中的分类，省去建库后再改挂
  formDialogRef.value?.open(undefined, {
    categoryId: scope.value.type === 'category' ? scope.value.id : null,
  })
}
function openEdit(kb: KnowledgeBase) {
  formDialogRef.value?.open(kb)
}
function openToggle(kb: KnowledgeBase) {
  toggleDialogRef.value?.open(kb)
}
/** 知识库变化（建/改/停启）会影响树上的节点计数，两边一起刷 */
function onKbMutated() {
  kbQuery.load()
  treeRef.value?.reload()
}
</script>

<template>
  <div class="notice">
    <b>知识库</b>是知识点的容器，不同知识库之间的知识点互不影响；左侧<b>分类树</b>把知识库按业务归属分层组织——点击分类节点，右侧只展示该分类<b>及其全部子孙分类</b>下的知识库，节点可拖拽调整排序与层级。节点数字为「直属数(子树合计)」，只统计启用中的知识库。
  </div>

  <div class="kb-layout">
    <CategoryTree
      ref="treeRef"
      :total-active-count="totalActiveCount"
      :uncategorized-count="uncategorizedCount"
      :kb-count-by-category="kbCountByCategory"
      @select="onScopeSelect"
      @changed="kbQuery.load"
    />

    <div class="card ov list-panel">
      <div class="card-head">
        <span class="tick" />
        <h3>知识库列表</h3>
        <span class="sub">{{ scopeLabel }}</span>
        <span class="spacer" />
        <span class="ops">
          <button type="button" class="btn primary" @click="openCreate">+ 新增知识库</button>
        </span>
      </div>

      <div class="form-row">
        <input
          v-model="keywordInput"
          type="text"
          placeholder="搜索知识库名称或描述"
          @keydown.enter="applyFilter"
        >
        <button type="button" class="btn primary sm" @click="applyFilter">
          查 询
        </button>
        <button type="button" class="btn sm" @click="resetFilter">
          重 置
        </button>
      </div>

      <table class="tbl">
        <thead>
          <tr>
            <th>名称</th>
            <th>描述</th>
            <th>分类</th>
            <th>知识点数</th>
            <th>状态</th>
            <th>创建时间</th>
            <th class="op-col">
              操作
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="kbQuery.loading.value">
            <td colspan="7" class="empty">
              <span class="spin" /> 加载中…
            </td>
          </tr>
          <tr v-else-if="kbQuery.error.value">
            <td colspan="7" class="empty">
              加载失败，请检查网络或后端服务后<a @click="kbQuery.load"> 重试</a>
            </td>
          </tr>
          <tr v-else-if="pageItems.length === 0">
            <td colspan="7" class="empty">
              {{ keyword || scope.type !== 'all' ? '该筛选条件下暂无知识库，试试调整分类或关键词' : '暂无知识库，点击右上角「+ 新增知识库」创建' }}
            </td>
          </tr>
          <template v-else>
            <tr v-for="kb in pageItems" :key="kb.id">
              <td>
                <RouterLink v-if="kb.status === 'active'" :to="`/knowledge-bases/${kb.id}/knowledge-points`">
                  {{ kb.name }}
                </RouterLink>
                <template v-else>
                  {{ kb.name }}
                </template>
              </td>
              <td>{{ kb.description || '—' }}</td>
              <td>
                <span v-if="kb.category_name" class="cat-tag">{{ kb.category_name }}</span>
                <span v-else class="cat-tag none">未分类</span>
              </td>
              <td class="num" style="font-weight: 400">
                {{ kb.active_knowledge_point_count }}
              </td>
              <td>
                <span v-if="kb.status === 'active'" class="status-dot ok"><i />启用中</span>
                <span v-else class="status-dot off"><i />已停用</span>
              </td>
              <td class="num" style="font-weight: 400">
                {{ formatDate(kb.created_at) }}
              </td>
              <td class="op-col ops">
                <RouterLink v-if="kb.status === 'active'" :to="`/knowledge-bases/${kb.id}/knowledge-points`">
                  进入
                </RouterLink>
                <a @click="openEdit(kb)">编辑</a>
                <a :class="{ danger: kb.status === 'active' }" @click="openToggle(kb)">
                  {{ kb.status === 'active' ? '停用' : '启用' }}
                </a>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
      <el-pagination
        v-model:current-page="page"
        class="pager"
        layout="total, prev, pager, next"
        :total="filtered.length"
        :page-size="PAGE_SIZE"
      />
    </div>
  </div>

  <KnowledgeBaseFormDialog ref="formDialogRef" @success="onKbMutated" />
  <ToggleKbStatusDialog ref="toggleDialogRef" @success="onKbMutated" />
</template>

<style scoped>
.kb-layout {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}
.kb-layout .list-panel {
  flex: 1;
  min-width: 0;
}
.cat-tag {
  display: inline-block;
  font-size: 12px;
  padding: 2px 10px;
  border-radius: 999px;
  background: var(--gray-bg, #f5f8fd);
  border: 1px solid var(--gray-bd, #dde5f1);
  color: var(--ink-3);
  max-width: 160px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: middle;
}
.cat-tag.none {
  color: var(--ink-5);
  border-style: dashed;
}
</style>
