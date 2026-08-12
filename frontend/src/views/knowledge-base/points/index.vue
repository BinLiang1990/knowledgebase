<script setup lang="ts">
import type { KnowledgePoint } from '@/api/knowledgePoint'
// 知识点列表页：统计卡 + 带条件提问（时间/维度筛选）+ 可展开知识点列表。
import type { Filters } from '@/utils/dimension'
import { listEnabledDimensions } from '@/api/dimension'
import { listKnowledgeBases } from '@/api/knowledgeBase'
import { listKnowledgePoints } from '@/api/knowledgePoint'
import { useAsyncData } from '@/composables/useAsyncData'
import { useCrumb } from '@/composables/useCrumb'
import { today } from '@/utils/format'
import ConditionPicker from '../components/ConditionPicker.vue'
import DeleteKnowledgePointDialog from '../components/DeleteKnowledgePointDialog.vue'
import KbTabs from '../components/KbTabs.vue'
import AddKnowledgePointDialog from './AddKnowledgePointDialog.vue'
import KnowledgePointRow from './KnowledgePointRow.vue'

defineOptions({ name: 'KnowledgePointList' })

const PAGE_SIZE = 6

const route = useRoute()
const kbId = computed(() => Number(route.params.kbId))
const kbIdValid = computed(() => Number.isFinite(kbId.value))

const kbQuery = useAsyncData(listKnowledgeBases)
const kb = computed(() => kbQuery.data.value?.find(k => k.id === kbId.value))
// 知识库确认有效且启用前不发库内请求——畸形 :kbId（NaN）或已停用的库反正
// 马上会被下方守卫拦下，别先打出一串可避免的 404（Kimi 终审，PR #23）
const kbReady = computed(() => kb.value?.status === 'active')

useCrumb(computed(() => (kb.value ? `${kb.value.name} / 知识点列表` : undefined)))

const keywordInput = ref('')
const keyword = ref('')
const filters = ref<Filters>({})
const qMode = ref<'now' | 'day'>('now')
const qTime = ref(today())
const page = ref(1)
const expanded = ref<Record<number, boolean>>({})

// 「最新」模式整个省略 at 而不是冻结渲染时刻的 today()：页面跨本地零点放着
// 不动，也应让后端每次用它自己的当前日期（Codex 结论，PR #23）
const at = computed(() => (qMode.value === 'day' ? qTime.value : undefined))
const hasFilter = computed(() => Boolean(keyword.value) || Object.keys(filters.value).length > 0)

const dimensionsQuery = useAsyncData(() => listEnabledDimensions(kbId.value), {
  enabled: () => kbReady.value,
  watch: [kbReady],
})
const dimensions = computed(() => dimensionsQuery.data.value ?? [])

const kpQuery = useAsyncData(
  () => listKnowledgePoints(kbId.value, { keyword: keyword.value, at: at.value, coord: filters.value }),
  {
    enabled: () => kbReady.value,
    watch: [kbReady, keyword, filters, at],
  },
)
const knowledgePoints = computed(() => kpQuery.data.value ?? [])

const pageCount = computed(() => Math.max(1, Math.ceil(knowledgePoints.value.length / PAGE_SIZE)))
watch(pageCount, (count) => {
  if (page.value > count)
    page.value = count
})
const pageItems = computed(() => knowledgePoints.value.slice((page.value - 1) * PAGE_SIZE, page.value * PAGE_SIZE))

function applyFilter() {
  keyword.value = keywordInput.value.trim().toLowerCase()
  page.value = 1
}
function resetFilter() {
  keywordInput.value = ''
  keyword.value = ''
  filters.value = {}
  qMode.value = 'now'
  qTime.value = today()
  page.value = 1
}
function handleFiltersChange(next: Filters) {
  filters.value = next
  page.value = 1
}
function handleTimeChange(mode: 'now' | 'day', time: string) {
  qMode.value = mode
  qTime.value = time
  page.value = 1
}
function toggleExpand(id: number) {
  expanded.value[id] = !expanded.value[id]
}

const addDialogRef = ref<InstanceType<typeof AddKnowledgePointDialog>>()
const deleteDialogRef = ref<InstanceType<typeof DeleteKnowledgePointDialog>>()

function requestDelete(kp: KnowledgePoint) {
  deleteDialogRef.value?.open({ kbId: kbId.value, id: kp.id, title: kp.title })
}

// 新增/删除知识点会改变知识库自身的 active_knowledge_point_count（「知识主题」
// 统计卡直接读知识库列表数据），所以两者成功后知识库列表也要一并重载
function reloadAfterKpMutation() {
  kpQuery.load()
  kbQuery.load()
}
</script>

<template>
  <template v-if="kbQuery.loading.value">
    <!-- Number.isFinite 守卫：畸形 :kbId（NaN）在加载/错误态也不能渲染出
         指向 /knowledge-bases/NaN/... 的 tab 链接（Kimi 终审，PR #29） -->
    <KbTabs v-if="kbIdValid" :kb-id="kbId" active="kp-list" />
    <div class="card">
      <div class="empty-block">
        <span class="spin" /> 加载中…
      </div>
    </div>
  </template>

  <!-- 拉取失败 ≠ 知识库不存在（Codex 结论，PR #23）：报成「不存在」既误导
       又没给用户可重试的入口 -->
  <template v-else-if="kbQuery.error.value">
    <KbTabs v-if="kbIdValid" :kb-id="kbId" active="kp-list" />
    <div class="card">
      <div class="empty-block">
        加载知识库失败，请稍后重试
        <br>
        <span style="display: inline-block; margin-top: 12px">
          <a @click="kbQuery.load">重试</a>
        </span>
      </div>
    </div>
  </template>

  <template v-else-if="!kb || kb.status !== 'active'">
    <!-- 无效/停用的知识库没有可切换的「设置」，不渲染 KbTabs（issue #13 设计 §2.1） -->
    <div class="card">
      <div class="empty-block">
        没有指定有效的知识库（可能已被停用或不存在）
        <br>
        <span style="display: inline-block; margin-top: 12px">
          <RouterLink class="btn primary" to="/knowledge-bases">‹ 返回知识库列表</RouterLink>
        </span>
      </div>
    </div>
  </template>

  <template v-else>
    <KbTabs :kb-id="kbId" active="kp-list" />
    <div class="stat-grid">
      <div class="stat">
        <div class="lbl">
          知识主题
        </div>
        <div class="val num">
          {{ kb.active_knowledge_point_count }}<small>个</small>
        </div>
        <div class="foot">
          当前生效的知识点
        </div>
      </div>
      <div class="stat c2">
        <div class="lbl">
          在用答案
        </div>
        <div class="val num">
          —
        </div>
        <div class="foot">
          统计接口开发中
        </div>
      </div>
      <div class="stat c3">
        <div class="lbl">
          启用维度
        </div>
        <div class="val num">
          {{ dimensions.length }}<small>个</small>
        </div>
        <div class="foot">
          本知识库已启用
        </div>
      </div>
      <div class="stat c4">
        <div class="lbl">
          今日变更
        </div>
        <div class="val num">
          —
        </div>
        <div class="foot">
          统计接口开发中
        </div>
      </div>
    </div>

    <div class="card ov">
      <div class="card-head">
        <span class="tick" />
        <h3>带条件提问</h3>
        <span class="sub">钉住你关心的维度条件；不钉的不参与过滤</span>
        <span class="spacer" />
        <span class="ops">
          <button type="button" class="btn primary" @click="addDialogRef?.open()">+ 新增知识点</button>
        </span>
      </div>
      <div class="form-row">
        <input
          v-model="keywordInput"
          type="text"
          placeholder="搜索知识点标题"
          @keydown.enter="applyFilter"
        >
        <!-- 维度拉取失败时如果静默回退 []，条件选择器会宣称「本知识库没有启用
             维度」，与真实的空态无法区分——把失败明示出来（Codex，PR #23） -->
        <span v-if="dimensionsQuery.error.value" class="hint" style="color: var(--red)">
          维度加载失败，条件筛选暂不可用 · <a @click="dimensionsQuery.load">重试</a>
        </span>
        <ConditionPicker
          v-else
          :dimensions="dimensions"
          :filters="filters"
          :q-mode="qMode"
          :q-time="qTime"
          :today="today()"
          @update:filters="handleFiltersChange"
          @time-change="handleTimeChange"
        />
        <button type="button" class="btn primary sm" @click="applyFilter">
          查 询
        </button>
        <button type="button" class="btn sm" @click="resetFilter">
          重 置
        </button>
      </div>
    </div>

    <div class="card ov">
      <div class="card-head">
        <span class="tick" />
        <h3>知识点</h3>
        <span class="sub">「{{ kb.name }}」· 点行展开查看全部答案</span>
      </div>
      <div v-if="kpQuery.loading.value" class="empty-block">
        <span class="spin" /> 加载中…
      </div>
      <div v-else-if="kpQuery.error.value" class="empty-block">
        加载失败
        <br>
        <a @click="kpQuery.load">重试</a>
      </div>
      <div v-else-if="pageItems.length === 0" class="empty-block">
        {{ hasFilter ? '没有知识点在这些条件下有匹配的答案：减少条件，或换个条件试试' : '暂无知识点，点击右上角「+ 新增知识点」创建' }}
      </div>
      <template v-else>
        <KnowledgePointRow
          v-for="kp in pageItems"
          :key="kp.id"
          :kp="kp"
          :kb-id="kbId"
          :at="at"
          :q-mode="qMode"
          :expanded="Boolean(expanded[kp.id])"
          :dimensions="dimensions"
          :has-filter="hasFilter"
          @toggle-expand="toggleExpand(kp.id)"
          @delete-request="requestDelete(kp)"
        />
      </template>
      <el-pagination
        v-model:current-page="page"
        class="pager"
        layout="total, prev, pager, next"
        :total="knowledgePoints.length"
        :page-size="PAGE_SIZE"
      />
    </div>

    <AddKnowledgePointDialog ref="addDialogRef" :kb-id="kbId" @success="reloadAfterKpMutation" />
    <DeleteKnowledgePointDialog ref="deleteDialogRef" @success="reloadAfterKpMutation" />
  </template>
</template>
