<script setup lang="ts">
// 知识点列表的可展开行：主行（标题/答案数/操作）+ resolve 预览行 + 展开后的
// 答案树。答案树数据在首次展开时才拉取；「回看某天」的日期变化时，已展开的
// 行必须重取而不是继续显示上一个 at 的树（设计评审结论）。
import type { Dimension } from '@/api/dimension'
import type { KnowledgePoint } from '@/api/knowledgePoint'
import { listAnswerGroups } from '@/api/knowledgePoint'
import { useAsyncData } from '@/composables/useAsyncData'
import AnswerGroupTree from './AnswerGroupTree.vue'

const props = defineProps<{
  kp: KnowledgePoint
  kbId: number
  /** undefined 即「最新」模式——让后端用它自己的当前日期（PR #23） */
  at?: string
  qMode: 'now' | 'day'
  expanded: boolean
  dimensions: Dimension[]
  hasFilter: boolean
}>()

const emit = defineEmits<{
  toggleExpand: []
  deleteRequest: []
}>()

const groupsQuery = useAsyncData(
  () => listAnswerGroups(props.kbId, props.kp.id, props.at),
  { immediate: false },
)

watch(
  [() => props.expanded, () => props.at],
  ([expanded]) => {
    if (expanded)
      groupsQuery.load()
  },
  { immediate: true },
)
</script>

<template>
  <div class="trow">
    <div class="trow-main" @click="emit('toggleExpand')">
      <span class="arrow">{{ expanded ? '▾' : '▸' }}</span>
      <RouterLink
        :to="`/knowledge-bases/${kbId}/knowledge-points/${kp.id}`"
        style="font-weight: 600; font-size: 14.5px"
        @click.stop
      >
        {{ kp.title }}
      </RouterLink>
      <span class="trm-meta">{{ kp.active_answer_count }} 条答案</span>
      <span style="flex: 1" />
      <span class="ops" @click.stop>
        <RouterLink :to="`/knowledge-bases/${kbId}/knowledge-points/${kp.id}`">查看详情</RouterLink>
        <a class="danger" @click="emit('deleteRequest')">删除</a>
      </span>
    </div>
    <div class="trow-ans">
      <template v-if="qMode === 'day'">
        回看 <span class="num">{{ at }}</span>
      </template>
      <template v-else>
        当前
      </template>
      ：
      <template v-if="kp.resolved.status === 'none' || !kp.resolved.answer">
        <!-- 「回看某天」本身就是时间约束——知识点可能有答案只是所选日期还未生效，
             与「从没写过答案」混为一谈会误导（Kimi 终审，PR #23） -->
        <span style="color: var(--ink-7)">
          {{ hasFilter ? '这个条件、这个时间点还没有匹配的答案' : qMode === 'day' ? '这个时间点还没有匹配的答案' : '还没有写过任何答案' }}
        </span>
      </template>
      <template v-else-if="kp.resolved.status === 'default' || kp.resolved.status === 'fallback-latest'">
        <span v-if="kp.resolved.status === 'default'" class="tag gray">默认</span>
        <span v-else class="tag orange">无默认 · 取最新</span>
        {{ kp.resolved.answer.content }}
      </template>
      <template v-else>
        {{ kp.resolved.answer.content }}
        <span v-for="(value, key) in kp.resolved.answer.coord" :key="key" class="tag blue">
          {{ dimensions.find(d => d.key === key)?.label ?? key }} = {{ String(value) }}
        </span>
        <span v-if="kp.resolved.status === 'exact'" class="tag green" style="margin-left: 4px">精确命中</span>
        <span v-else class="tag orange" style="margin-left: 4px">未精确命中 · 按权重回退</span>
      </template>
    </div>
    <template v-if="expanded">
      <div v-if="groupsQuery.loading.value" class="mini-note" style="padding: 8px 0">
        加载中…
      </div>
      <div v-else-if="groupsQuery.error.value" class="mini-note" style="padding: 8px 0">
        加载失败
      </div>
      <AnswerGroupTree v-else-if="groupsQuery.data.value" :groups="groupsQuery.data.value" :dimensions="dimensions" />
    </template>
  </div>
</template>
