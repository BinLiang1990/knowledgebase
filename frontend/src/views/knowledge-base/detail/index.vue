<script setup lang="ts">
import type { ExistingAnswer } from './WriteAnswerDialog.vue'
// 知识点详情页：头部（标题/元信息/操作）+ 五个 tab（当前答案 / 答案关联 /
// 立体全景 / 版本历史 / 变更留痕）。
import type { AnswerGroup } from '@/api/knowledgePoint'
import type { AnswerRelation } from '@/api/relation'
import type { Filters } from '@/utils/dimension'
import { listChangeLog } from '@/api/changeLog'
import { listEnabledDimensions } from '@/api/dimension'
import { listKnowledgeBases } from '@/api/knowledgeBase'
import { getKnowledgePoint, listAnswerGroups } from '@/api/knowledgePoint'
import { analyzeRelations, listRelations } from '@/api/relation'
import RevokeAnswerDialog from '@/components/RevokeAnswerDialog.vue'
import { useAsyncData } from '@/composables/useAsyncData'
import { useCrumb } from '@/composables/useCrumb'
import { coordGroupKey, describeCoord } from '@/utils/coord'
import { formatDate, today } from '@/utils/format'
import { hasUniqueTopMatch, sortLiveGroupsByPriority } from '@/utils/resolve'
import ConditionPicker from '../components/ConditionPicker.vue'
import DeleteKnowledgePointDialog from '../components/DeleteKnowledgePointDialog.vue'
import AddRelationDialog from './AddRelationDialog.vue'
import EditRelationDialog from './EditRelationDialog.vue'
import EditTitleDialog from './EditTitleDialog.vue'
import RelationsPane from './RelationsPane.vue'
import TimelinePane from './TimelinePane.vue'
import TreePane from './TreePane.vue'
import WriteAnswerDialog from './WriteAnswerDialog.vue'

defineOptions({ name: 'KnowledgePointDetail' })

type TabKey = 'now' | 'relations' | 'tree' | 'timeline' | 'logs'

const TABS: Array<[TabKey, string]> = [
  ['now', '当前答案'],
  ['relations', '答案关联'],
  ['tree', '立体全景'],
  ['timeline', '版本历史'],
  ['logs', '变更留痕'],
]

const route = useRoute()
const kbId = computed(() => Number(route.params.kbId))
const kpId = computed(() => Number(route.params.kpId))

const kbQuery = useAsyncData(listKnowledgeBases)
const kb = computed(() => kbQuery.data.value?.find(k => k.id === kbId.value))
const kbReady = computed(() => kb.value?.status === 'active' && Number.isFinite(kpId.value))

useCrumb(computed(() => (kb.value ? `${kb.value.name} / 知识点列表 / 详情` : undefined)))

// ?tab= 深链（对齐 frontend-mock 的 detail.html?tab=）：非法值回落默认 tab
const initialTab = String(route.query.tab ?? '')
const tab = ref<TabKey>(TABS.some(([key]) => key === initialTab) ? initialTab as TabKey : 'now')
const filters = ref<Filters>({})
const qMode = ref<'now' | 'day'>('now')
const qTime = ref(today())

const at = computed(() => (qMode.value === 'day' ? qTime.value : undefined))
const hasFilter = computed(() => Object.keys(filters.value).length > 0)

const dimensionsQuery = useAsyncData(() => listEnabledDimensions(kbId.value), {
  enabled: () => kbReady.value,
  watch: [kbReady],
})
const dimensions = computed(() => dimensionsQuery.data.value ?? [])
// 写答案弹窗打开时会用当下的 dimensions 一次性构建条件行——维度还没就绪就
// 打开，已有条件行会被整个误判为引用已停用维度，且贯穿弹窗整个生命周期。
// 就绪前禁用写/编辑入口，而不是让竞态决定结果（Codex 结论，PR #24）
const dimensionsReady = computed(() => !dimensionsQuery.loading.value && !dimensionsQuery.error.value)

const kpQuery = useAsyncData(() => getKnowledgePoint(kbId.value, kpId.value), {
  enabled: () => kbReady.value,
  watch: [kbReady],
})
const kp = computed(() => kpQuery.data.value)

const groupsQuery = useAsyncData(() => listAnswerGroups(kbId.value, kpId.value, at.value), {
  enabled: () => kbReady.value,
  watch: [kbReady, at],
})
const groups = computed(() => groupsQuery.data.value ?? [])

const changeLogQuery = useAsyncData(() => listChangeLog(kbId.value, kpId.value), {
  enabled: () => kbReady.value,
  watch: [kbReady],
})

// 答案关联（docs/PRD-答案关联.md §5）：查询归页面持有——「当前答案」卡片的
// 关联角标和「答案关联」tab 复用同一份数据。分析进行中每 5s 静默轮询，
// 完成后停（PRD §5.4）。
let relationsPolling = false
let relationsTimer: number | undefined
const relationsQuery = useAsyncData(
  () => listRelations(kbId.value, kpId.value, { silent: relationsPolling }),
  { enabled: () => kbReady.value, watch: [kbReady] },
)
const relationStatus = computed(() => relationsQuery.data.value?.generation_status)
const relationAnalysisDisabled = computed(() => relationStatus.value === 'disabled')
watch(relationStatus, (status) => {
  const shouldPoll = status === 'pending' || status === 'generating'
  if (shouldPoll && relationsTimer === undefined) {
    relationsTimer = window.setInterval(() => {
      relationsPolling = true
      relationsQuery.load()
    }, 5000)
  }
  else if (!shouldPoll && relationsTimer !== undefined) {
    window.clearInterval(relationsTimer)
    relationsTimer = undefined
    relationsPolling = false
  }
}, { immediate: true })
onBeforeUnmount(() => {
  if (relationsTimer !== undefined)
    window.clearInterval(relationsTimer)
})

/** 该条件组现有关联数（角标）；按链的 coord_hash 匹配任一端 */
function relationCount(g: AnswerGroup): number {
  const hash = g.latest_answer.coord_hash
  const rels = relationsQuery.data.value?.relations ?? []
  return rels.filter(r =>
    (r.a.kp_id === kpId.value && r.a.coord_hash === hash)
    || (r.b.kp_id === kpId.value && r.b.coord_hash === hash),
  ).length
}

const analyzeSubmitting = ref(false)

/** 发起分析：coordHash 省略 = 知识点级自动关联（PRD §3.1） */
async function startAnalyze(coordHash?: string) {
  if (analyzeSubmitting.value)
    return
  analyzeSubmitting.value = true
  try {
    await analyzeRelations(kbId.value, kpId.value, coordHash)
    ElMessage.success('已发起关联分析，完成后自动刷新')
    tab.value = 'relations'
    relationsPolling = false
    relationsQuery.load()
  }
  catch {
    // request 拦截器已提示（未配置网关/没有生效答案等）
  }
  finally {
    analyzeSubmitting.value = false
  }
}

const isDeleted = computed(() => kp.value?.status === 'deleted')
const sorted = computed(() => sortLiveGroupsByPriority(groups.value, filters.value, dimensions.value))
const uniqueTop = computed(() => hasUniqueTopMatch(sorted.value, hasFilter.value))

// 已删除知识点除删除/恢复外全只读——头部已隐藏「写一条答案/编辑标题/删除」，
// 行内「编辑」也必须禁用，否则会撞上 edit_answer 自己的 400 守卫（PR #24 终审）。
// 撤回刻意不禁：后端 revoke_answer 不检查知识点删除状态，PRD §6 规则 8 把
// 软删与撤回视为独立操作（不同于会拒绝的 edit）。
const editDisabledReason = computed(() =>
  isDeleted.value
    ? '该知识点已删除，不能编辑答案'
    : !dimensionsReady.value
        ? '维度加载完成后才能编辑'
        : null,
)

function handleFiltersChange(next: Filters) {
  filters.value = next
}
function handleTimeChange(mode: 'now' | 'day', time: string) {
  qMode.value = mode
  qTime.value = time
}

const writeDialogRef = ref<InstanceType<typeof WriteAnswerDialog>>()
const editTitleDialogRef = ref<InstanceType<typeof EditTitleDialog>>()
const deleteDialogRef = ref<InstanceType<typeof DeleteKnowledgePointDialog>>()
const revokeDialogRef = ref<InstanceType<typeof RevokeAnswerDialog>>()
const addRelationDialogRef = ref<InstanceType<typeof AddRelationDialog>>()
const editRelationDialogRef = ref<InstanceType<typeof EditRelationDialog>>()

function openEditRelation(rel: AnswerRelation) {
  editRelationDialogRef.value?.open(rel)
}

function openWrite() {
  writeDialogRef.value?.open()
}
function openEdit(g: AnswerGroup) {
  const live = g.live_answer!
  const existing: ExistingAnswer = {
    answerId: live.id,
    coord: g.coord,
    content: live.content,
    effective_time: live.effective_time,
    note: live.note,
  }
  writeDialogRef.value?.open(existing)
}
function openRevoke(g: AnswerGroup) {
  const live = g.live_answer!
  revokeDialogRef.value?.open({ kbId: kbId.value, kpId: kpId.value, answerId: live.id, content: live.content })
}
function openDelete() {
  if (kp.value)
    deleteDialogRef.value?.open({ kbId: kbId.value, id: kp.value.id, title: kp.value.title })
}

// 答案变更（写/编辑/撤回）会改变条件组、知识点的在用答案数与留痕；
// 关联的 stale/对端撤回态也由答案内容推导，一并重载
function reloadAfterAnswerMutation() {
  groupsQuery.load()
  kpQuery.load()
  changeLogQuery.load()
  relationsQuery.load()
}
// 删除（软删）后知识点仍可查看，重载详情让页面切到已删除态；统计卡同步
function reloadAfterKpMutation() {
  kpQuery.load()
  kbQuery.load()
  changeLogQuery.load()
}
</script>

<template>
  <template v-if="kbQuery.loading.value">
    <div class="card">
      <div class="empty-block">
        <span class="spin" /> 加载中…
      </div>
    </div>
  </template>

  <template v-else-if="kbQuery.error.value">
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
    <RouterLink class="back-link" :to="`/knowledge-bases/${kbId}/knowledge-points`">
      ‹ 返回列表
    </RouterLink>

    <template v-if="kpQuery.loading.value">
      <div class="card">
        <div class="empty-block">
          <span class="spin" /> 加载中…
        </div>
      </div>
    </template>

    <template v-else-if="kpQuery.error.value || !kp">
      <div class="card">
        <div class="empty-block">
          找不到这个知识点
        </div>
      </div>
    </template>

    <template v-else>
      <div class="card">
        <div class="detail-head">
          <div>
            <h2>{{ kp.title }}</h2>
            <div class="meta">
              <span>ID <b class="num">{{ kp.id }}</b></span>
              <span>{{ kp.active_answer_count }} 条在用答案</span>
              <span>创建 <b class="num">{{ formatDate(kp.created_at) }}</b> · {{ kp.operator }}</span>
              <span v-if="isDeleted" class="tag gray">已删除</span>
              <span v-else class="tag green">正常</span>
            </div>
          </div>
          <div class="ops">
            <template v-if="!isDeleted">
              <button
                type="button"
                class="btn primary"
                :disabled="!dimensionsReady"
                :title="dimensionsReady ? undefined : '维度加载完成后才能写答案'"
                @click="openWrite"
              >
                + 写一条答案
              </button>
              <button type="button" class="btn" @click="editTitleDialogRef?.open(kp.title)">
                编辑标题
              </button>
              <button type="button" class="btn danger" @click="openDelete">
                删 除
              </button>
            </template>
          </div>
        </div>
      </div>

      <div v-if="isDeleted" class="notice">
        该知识点已被<b>软删除</b>（删除时间 <b>{{ kp.deleted_at ? formatDate(kp.deleted_at) : '—' }}</b>，原因：{{ kp.delete_reason || '—' }}）。以下仍可查看其全部历史答案。
      </div>

      <div class="card ov">
        <div class="tabs">
          <div
            v-for="[key, label] in TABS"
            :key="key"
            class="tab"
            :class="{ active: tab === key }"
            @click="tab = key"
          >
            {{ label }}
          </div>
        </div>

        <RelationsPane
          v-if="tab === 'relations'"
          :kb-id="kbId"
          :kp-id="kpId"
          :dimensions="dimensions"
          :data="relationsQuery.data.value"
          :loading="relationsQuery.loading.value"
          :error="relationsQuery.error.value"
          :readonly="isDeleted"
          @refresh="relationsQuery.load"
          @add-relation="addRelationDialogRef?.open()"
          @edit-relation="openEditRelation"
          @auto-relate="startAnalyze()"
        />

        <TreePane v-else-if="tab === 'tree'" :kb-id="kbId" :kp-id="kpId" :dimensions="dimensions" />

        <TimelinePane v-else-if="tab === 'timeline'" :kb-id="kbId" :kp-id="kpId" :dimensions="dimensions" />

        <template v-else-if="tab === 'logs'">
          <div v-if="changeLogQuery.loading.value" class="empty-block">
            <span class="spin" /> 加载中…
          </div>
          <div v-else-if="changeLogQuery.error.value" class="empty-block">
            加载失败
            <br>
            <a @click="changeLogQuery.load">重试</a>
          </div>
          <ChangeLogTable
            v-else
            :entries="changeLogQuery.data.value ?? []"
            :kb-id="kbId"
            :kp-id="kpId"
            @refresh="reloadAfterAnswerMutation"
          />
        </template>

        <template v-else>
          <div class="form-row">
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
            <button v-if="hasFilter" type="button" class="btn sm" @click="filters = {}">
              清空条件
            </button>
          </div>
          <div class="mini-note" style="margin: 12px 2px 2px">
            {{ hasFilter ? `满足条件的答案 ${sorted.length} 条` : `全部答案 ${sorted.length} 条 · 一个知识点本来就可以有多种答案，各管各的条件` }}
          </div>
          <div v-if="groupsQuery.loading.value" class="empty-block">
            <span class="spin" /> 加载中…
          </div>
          <div v-else-if="groupsQuery.error.value" class="empty-block">
            加载失败
            <br>
            <a @click="groupsQuery.load">重试</a>
          </div>
          <div v-else-if="sorted.length === 0" class="empty-block">
            这个条件、这个时间点还没有答案：换个时间，或放宽条件
          </div>
          <template v-else>
            <div v-for="(g, i) in sorted" :key="coordGroupKey(g.coord)" class="ans-item">
              <div style="display: flex; align-items: flex-start; gap: 16px">
                <div class="ai-content" style="flex: 1">
                  {{ g.live_answer!.content }}
                </div>
                <span class="ops" style="font-size: 12.5px; white-space: nowrap; padding-top: 3px">
                  <a
                    :style="relationAnalysisDisabled || isDeleted ? 'color: var(--ink-6); cursor: not-allowed' : undefined"
                    :title="relationAnalysisDisabled ? '关联分析未启用（服务端未配置模型网关）' : isDeleted ? '该知识点已删除' : '在所有知识库中检索与这条答案相关的答案'"
                    @click="relationAnalysisDisabled || isDeleted ? undefined : startAnalyze(g.latest_answer.coord_hash)"
                  >
                    分析关联
                  </a>
                  <a
                    :style="editDisabledReason ? 'color: var(--ink-6); cursor: not-allowed' : undefined"
                    :title="editDisabledReason ?? undefined"
                    @click="editDisabledReason ? undefined : openEdit(g)"
                  >
                    编辑
                  </a>
                  <a class="danger" @click="openRevoke(g)">撤回</a>
                </span>
              </div>
              <div class="ai-cond">
                <span v-if="uniqueTop && i === 0" class="live"><i /> 此条件下生效</span>
                <span>{{ describeCoord(g.coord, dimensions) }}</span>
                <span><span class="num">{{ g.live_answer!.effective_time }}</span> 起 · 共 {{ g.version_count }} 版</span>
                <span>{{ g.live_answer!.operator }} 录入</span>
                <span
                  v-if="relationCount(g) > 0"
                  class="tag purple"
                  style="cursor: pointer"
                  title="查看该答案的关联"
                  @click="tab = 'relations'"
                >关联 {{ relationCount(g) }}</span>
              </div>
            </div>
          </template>
        </template>
      </div>

      <WriteAnswerDialog
        ref="writeDialogRef"
        :kb-id="kbId"
        :kp-id="kpId"
        :dimensions="dimensions"
        :groups="groups"
        @success="reloadAfterAnswerMutation"
      />
      <EditTitleDialog ref="editTitleDialogRef" :kb-id="kbId" :kp-id="kpId" @success="kpQuery.load" />
      <DeleteKnowledgePointDialog ref="deleteDialogRef" @success="reloadAfterKpMutation" />
      <RevokeAnswerDialog ref="revokeDialogRef" @success="reloadAfterAnswerMutation" />
      <AddRelationDialog
        ref="addRelationDialogRef"
        :kb-id="kbId"
        :kp-id="kpId"
        :self-groups="groups"
        :dimensions="dimensions"
        :analysis-disabled="relationAnalysisDisabled"
        @success="relationsQuery.load"
      />
      <EditRelationDialog ref="editRelationDialogRef" @success="relationsQuery.load" />
    </template>
  </template>
</template>
