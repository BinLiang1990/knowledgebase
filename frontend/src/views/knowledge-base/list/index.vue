<script setup lang="ts">
// 知识库列表页。2026-08-21 起分类切换、关键词搜索、分页全部走服务端参数
// （GET /knowledge-bases?category_id/uncategorized/keyword/page）——最初是
// 全量拉取 + 前端内存过滤（设计文档 §5 的旧口径），数据量增长后不成立。
// 左侧分类树（PRD §4.11，issue #40）：点击分类节点，右侧只展示该分类及其
// 全部子孙下的知识库（含子孙语义由服务端实现，前端只传选中分类 id）。
import type { CategoryScope } from '@/api/category'
import type { KnowledgeBase } from '@/api/knowledgeBase'
import { pageKnowledgeBases } from '@/api/knowledgeBase'
import { useAsyncData } from '@/composables/useAsyncData'
import { formatDate } from '@/utils/format'
import CategoryTree from './CategoryTree.vue'
import DeleteKbDialog from './DeleteKbDialog.vue'
import KnowledgeBaseFormDialog from './KnowledgeBaseFormDialog.vue'
import ToggleKbStatusDialog from './ToggleKbStatusDialog.vue'

defineOptions({ name: 'KnowledgeBaseList' })

const PAGE_SIZE = 8

const keywordInput = ref('')
const keyword = ref('')
const page = ref(1)
const scope = ref<CategoryScope>({ type: 'all' })

const kbQuery = useAsyncData(
  () =>
    pageKnowledgeBases({
      page: page.value,
      page_size: PAGE_SIZE,
      keyword: keyword.value || undefined,
      category_id: scope.value.type === 'category' ? scope.value.id : undefined,
      uncategorized: scope.value.type === 'none' || undefined,
    }),
  // 同一次交互里 keyword/page/scope 可能一起变（如查询时重置回第 1 页），
  // watch 在同一 tick 内合并触发，只发一次请求；竞态由 useAsyncData 兜底
  { watch: [keyword, page, scope] },
)

const scopeLabel = computed(() => {
  if (scope.value.type === 'none')
    return '未分类'
  return scope.value.type === 'category' ? scope.value.label : '全部知识库'
})

const pageItems = computed(() => kbQuery.data.value?.list ?? [])
const total = computed(() => kbQuery.data.value?.total ?? 0)

// 变更（删除/停用后重载）可能把当前页抽空——总数缩到当前页码之前时夹回
// 合法范围（Codex 结论，PR #22 的服务端分页版），watch 触发重新取数
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))
watch(pageCount, (count) => {
  if (page.value > count)
    page.value = count
})

function applyFilter() {
  keyword.value = keywordInput.value.trim()
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

// ---- 分类树虚拟节点（全部/未分类）的启用中计数：来自分页响应的全局
// summary（PRD §4.11 计数口径）；各分类节点的数字由树自己的 /categories
// 接口提供 ----
const totalActiveCount = computed(() => kbQuery.data.value?.summary.active_total ?? 0)
const uncategorizedCount = computed(() => kbQuery.data.value?.summary.active_uncategorized ?? 0)

const treeRef = ref<InstanceType<typeof CategoryTree>>()
const formDialogRef = ref<InstanceType<typeof KnowledgeBaseFormDialog>>()
const toggleDialogRef = ref<InstanceType<typeof ToggleKbStatusDialog>>()
const deleteDialogRef = ref<InstanceType<typeof DeleteKbDialog>>()

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
function openDelete(kb: KnowledgeBase) {
  deleteDialogRef.value?.open(kb)
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
          <RouterLink to="/knowledge-bases/recycle-bin" class="btn">
            回收站
          </RouterLink>
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
                <!-- 仅已停用的库可删（后端强校验），删除 = 进回收站 -->
                <a v-if="kb.status === 'deprecated'" class="danger" @click="openDelete(kb)">删除</a>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
      <el-pagination
        v-model:current-page="page"
        class="pager"
        layout="total, prev, pager, next"
        :total="total"
        :page-size="PAGE_SIZE"
      />
    </div>
  </div>

  <KnowledgeBaseFormDialog ref="formDialogRef" @success="onKbMutated" />
  <ToggleKbStatusDialog ref="toggleDialogRef" @success="onKbMutated" />
  <DeleteKbDialog ref="deleteDialogRef" @success="onKbMutated" />
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
