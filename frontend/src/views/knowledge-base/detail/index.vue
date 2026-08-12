<script setup lang="ts">
import type { ExistingAnswer } from './WriteAnswerDialog.vue'
// 知识点详情页：头部（标题/元信息/操作）+ 四个 tab（当前答案 / 立体全景 /
// 版本历史 / 变更留痕）。立体全景仍是 P2（issue #16），按 IA 对齐 demo 保留
// tab 位、内容为占位——与 issue #7 对未建统计卡的处理一致。
import type { AnswerGroup } from '@/api/knowledgePoint'
import type { Filters } from '@/utils/dimension'
import { listChangeLog } from '@/api/changeLog'
import { listEnabledDimensions } from '@/api/dimension'
import { listKnowledgeBases } from '@/api/knowledgeBase'
import { getKnowledgePoint, listAnswerGroups } from '@/api/knowledgePoint'
import RevokeAnswerDialog from '@/components/RevokeAnswerDialog.vue'
import { useAsyncData } from '@/composables/useAsyncData'
import { useCrumb } from '@/composables/useCrumb'
import { coordGroupKey, describeCoord } from '@/utils/coord'
import { formatDate, today } from '@/utils/format'
import { hasUniqueTopMatch, sortLiveGroupsByPriority } from '@/utils/resolve'
import ConditionPicker from '../components/ConditionPicker.vue'
import DeleteKnowledgePointDialog from '../components/DeleteKnowledgePointDialog.vue'
import EditTitleDialog from './EditTitleDialog.vue'
import TimelinePane from './TimelinePane.vue'
import WriteAnswerDialog from './WriteAnswerDialog.vue'

defineOptions({ name: 'KnowledgePointDetail' })

type TabKey = 'now' | 'tree' | 'timeline' | 'logs'

const TABS: Array<[TabKey, string]> = [
  ['now', '当前答案'],
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

const tab = ref<TabKey>('now')
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

// 答案变更（写/编辑/撤回）会改变条件组、知识点的在用答案数与留痕
function reloadAfterAnswerMutation() {
  groupsQuery.load()
  kpQuery.load()
  changeLogQuery.load()
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

        <div v-if="tab === 'tree'" class="empty-block">
          立体全景开发中，见 Issue #16
        </div>

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
        @success="reloadAfterAnswerMutation"
      />
      <EditTitleDialog ref="editTitleDialogRef" :kb-id="kbId" :kp-id="kpId" @success="kpQuery.load" />
      <DeleteKnowledgePointDialog ref="deleteDialogRef" @success="reloadAfterKpMutation" />
      <RevokeAnswerDialog ref="revokeDialogRef" @success="reloadAfterAnswerMutation" />
    </template>
  </template>
</template>
