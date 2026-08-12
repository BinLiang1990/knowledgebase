<script setup lang="ts">
// 「版本历史」tab：按条件组选择一条版本链，纵向时间线展示每个版本。
// 刻意独立于「当前答案」tab 的 qMode/qTime（设计文档 §4.2：本 tab 不时间
// 旅行）——answer-groups 始终 at=undefined，让后端按它自己的今天 resolve；
// 其 live_answer 是 buildTimelineGroups 判定「当前」的服务端权威来源
// （替代客户端 today() 比较的原因见 utils/timeline.ts，PR #30 终审第 2 轮）。
import type { Dimension } from '@/api/dimension'
import type { TimelineStatus } from '@/utils/timeline'
import { listAllAnswers, listAnswerGroups } from '@/api/knowledgePoint'
import { useAsyncData } from '@/composables/useAsyncData'
import { describeCoord } from '@/utils/coord'
import { buildTimelineGroups } from '@/utils/timeline'

const props = defineProps<{
  kbId: number
  kpId: number
  dimensions: Dimension[]
}>()

const TIMELINE_STATUS_TAG: Record<TimelineStatus, { label: string, cls: string }> = {
  'current': { label: '当前', cls: 'blue' },
  'superseded': { label: '已被新版替代', cls: 'gray' },
  'not-yet-effective': { label: '晚于查询时间，暂不生效', cls: 'orange' },
  'revoked': { label: '已撤回', cls: 'gray' },
}

const answersQuery = useAsyncData(() => listAllAnswers(props.kbId, props.kpId))
const currentGroupsQuery = useAsyncData(() => listAnswerGroups(props.kbId, props.kpId))

const selectedGroup = ref<string | null>(null)

const loading = computed(() => answersQuery.loading.value || currentGroupsQuery.loading.value)
const isError = computed(() => answersQuery.error.value || currentGroupsQuery.error.value)

const groups = computed(() => {
  const currentAnswerIdByHash = new Map(
    (currentGroupsQuery.data.value ?? []).map(g => [g.latest_answer.coord_hash, g.live_answer?.id ?? null]),
  )
  return buildTimelineGroups(answersQuery.data.value ?? [], currentAnswerIdByHash)
})

// 按描述文案排序，不保留 Map 插入序——插入序跟着后端 SELECT 的偶然行序走，
// 跨请求不稳定；选择器顺序与默认选中组一抖一抖的体验很差（Kimi 终审，PR #30）
const keys = computed(() => [...groups.value.keys()].sort((a, b) =>
  describeCoord(groups.value.get(a)![0].answer.coord, props.dimensions)
    .localeCompare(describeCoord(groups.value.get(b)![0].answer.coord, props.dimensions)),
))

const activeKey = computed(() =>
  selectedGroup.value && keys.value.includes(selectedGroup.value) ? selectedGroup.value : keys.value[0],
)
const entries = computed(() => groups.value.get(activeKey.value) ?? [])

function retry() {
  answersQuery.load()
  currentGroupsQuery.load()
}

function onSelectGroup(event: Event) {
  selectedGroup.value = (event.target as HTMLSelectElement).value
}
</script>

<template>
  <div v-if="loading" class="empty-block">
    <span class="spin" /> 加载中…
  </div>
  <div v-else-if="isError" class="empty-block">
    加载失败
    <br>
    <a @click="retry">重试</a>
  </div>
  <div v-else-if="(answersQuery.data.value ?? []).length === 0" class="empty-block">
    还没有任何答案
  </div>
  <template v-else>
    <div class="form-row" style="margin-bottom: 14px">
      <span class="f-lbl">选择条件组合(每组条件一条独立版本链)</span>
      <select :value="activeKey" @change="onSelectGroup">
        <option v-for="k in keys" :key="k" :value="k">
          {{ describeCoord(groups.get(k)![0].answer.coord, dimensions) }}
        </option>
      </select>
    </div>
    <div class="timeline">
      <div v-for="(entry, i) in entries" :key="entry.answer.id" class="tl-item">
        <div class="tl-dot-col">
          <div class="tl-dot" :class="{ cur: entry.status === 'current' }" />
          <div v-if="i < entries.length - 1" class="tl-line" />
        </div>
        <div class="tl-body">
          <div class="tl-head">
            <span class="time num" style="font-weight: 400">{{ entry.answer.effective_time }}</span>
            <span class="tag" :class="TIMELINE_STATUS_TAG[entry.status].cls">
              {{ TIMELINE_STATUS_TAG[entry.status].label }}
            </span>
            <span class="field-hint">操作人：{{ entry.answer.operator }}</span>
          </div>
          <div class="tl-content">
            {{ entry.answer.content }}
          </div>
          <div v-if="entry.answer.note" class="field-hint" style="margin-top: 4px">
            说明：{{ entry.answer.note }}
          </div>
        </div>
      </div>
    </div>
    <div class="mini-note" style="margin-top: 8px">
      旧版本与撤回版永不删除。"当前"版本与"当前答案"tab 保持一致，以服务器当前时间为准。
    </div>
  </template>
</template>
