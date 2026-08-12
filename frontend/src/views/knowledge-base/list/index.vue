<script setup lang="ts">
// 知识库列表页。列表接口无关键词/分页参数，搜索与分页在前端内存中完成
// （设计文档 §5，见 api/knowledgeBase.ts 的注释）。
import type { KnowledgeBase } from '@/api/knowledgeBase'
import { listKnowledgeBases } from '@/api/knowledgeBase'
import { useAsyncData } from '@/composables/useAsyncData'
import { formatDate } from '@/utils/format'
import KnowledgeBaseFormDialog from './KnowledgeBaseFormDialog.vue'
import ToggleKbStatusDialog from './ToggleKbStatusDialog.vue'

defineOptions({ name: 'KnowledgeBaseList' })

const PAGE_SIZE = 8

const kbQuery = useAsyncData(listKnowledgeBases)

const keywordInput = ref('')
const keyword = ref('')
const page = ref(1)

const filtered = computed(() => {
  const list = kbQuery.data.value ?? []
  if (!keyword.value)
    return list
  const needle = keyword.value.toLowerCase()
  return list.filter(kb => `${kb.name} ${kb.description ?? ''}`.toLowerCase().includes(needle))
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

const formDialogRef = ref<InstanceType<typeof KnowledgeBaseFormDialog>>()
const toggleDialogRef = ref<InstanceType<typeof ToggleKbStatusDialog>>()

function openCreate() {
  formDialogRef.value?.open()
}
function openEdit(kb: KnowledgeBase) {
  formDialogRef.value?.open(kb)
}
function openToggle(kb: KnowledgeBase) {
  toggleDialogRef.value?.open(kb)
}
</script>

<template>
  <div class="notice">
    <b>知识库</b>是知识点的容器，不同知识库之间的知识点互不影响；<b>维度定义</b>是全局的，所有知识库共享同一套维度。
  </div>

  <div class="card ov">
    <div class="card-head">
      <span class="tick" />
      <h3>知识库列表</h3>
      <span class="sub">全部知识库</span>
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
          <td colspan="6" class="empty">
            <span class="spin" /> 加载中…
          </td>
        </tr>
        <tr v-else-if="kbQuery.error.value">
          <td colspan="6" class="empty">
            加载失败，请检查网络或后端服务后<a @click="kbQuery.load"> 重试</a>
          </td>
        </tr>
        <tr v-else-if="pageItems.length === 0">
          <td colspan="6" class="empty">
            {{ keyword ? '暂无符合条件的知识库，试试调整搜索关键词' : '暂无知识库，点击右上角「+ 新增知识库」创建' }}
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

  <KnowledgeBaseFormDialog ref="formDialogRef" @success="kbQuery.load" />
  <ToggleKbStatusDialog ref="toggleDialogRef" @success="kbQuery.load" />
</template>
