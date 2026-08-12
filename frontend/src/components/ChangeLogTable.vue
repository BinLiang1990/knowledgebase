<script setup lang="ts">
// 变更留痕表格。知识点详情页（不带定位列）与全局操作日志页（showLocation，
// 每行内联知识库/知识点两列）共用。行级撤回入口只对 revocable 的行开放。
import type { ChangeLogEntry, GlobalChangeLogEntry } from '@/api/changeLog'
import { ACTION_LABEL, CHANGE_LOG_STATUS_LABEL } from '@/api/changeLog'
import { listAdminDimensions } from '@/api/dimension'
import { useAsyncData } from '@/composables/useAsyncData'
import { describeCoord } from '@/utils/coord'
import { formatDateTime } from '@/utils/format'
import RevokeAnswerDialog from './RevokeAnswerDialog.vue'

const props = withDefaults(defineProps<{
  entries: ChangeLogEntry[] | GlobalChangeLogEntry[]
  /** true 时 entries 是全局留痕（每行携带自己的 knowledge_base_id 等定位字段） */
  showLocation?: boolean
  /** 非全局用法必传：该页所有行同属这一个知识库/知识点 */
  kbId?: number
  kpId?: number
}>(), { showLocation: false })

const emit = defineEmits<{
  /** 行内撤回成功——父页面重载自己的留痕数据 */
  refresh: []
}>()

// 用管理侧（而非仅启用中）维度列表：留痕是永久历史记录，可能引用已全局停用
// 的维度；describeCoord 找不到时会回退原 key，但只要维度还存在（无论状态）
// 就应显示真实 label。
const dimensionsQuery = useAsyncData(listAdminDimensions)
const dimensions = computed(() => dimensionsQuery.data.value ?? [])

const STATUS_TAG_CLASS: Record<ChangeLogEntry['status'], string> = {
  live: 'green',
  superseded: 'gray',
  revoked: 'red',
  reactivated: 'blue',
}

interface RowView {
  entry: ChangeLogEntry
  kbId: number
  kpId: number
  location: { kbName: string, kpTitle: string } | null
}

// 在 computed 里一次性把两种入参形状归一成行视图，模板不再需要类型断言：
// 全局行用自己携带的定位字段，普通行用父级传入的 kbId/kpId
const rows = computed<RowView[]>(() => props.entries.map((entry) => {
  if (props.showLocation) {
    const g = entry as GlobalChangeLogEntry
    return {
      entry,
      kbId: g.knowledge_base_id,
      kpId: g.knowledge_point_id,
      location: { kbName: g.knowledge_base_name, kpTitle: g.knowledge_point_title },
    }
  }
  return { entry, kbId: props.kbId!, kpId: props.kpId!, location: null }
}))

const colCount = computed(() => (props.showLocation ? 11 : 9))

const revokeDialogRef = ref<InstanceType<typeof RevokeAnswerDialog>>()

function requestRevoke(row: RowView) {
  revokeDialogRef.value?.open({
    kbId: row.kbId,
    kpId: row.kpId,
    answerId: row.entry.answer_id,
    content: row.entry.after_content ?? row.entry.before_content ?? '',
  })
}
</script>

<template>
  <div class="table-wrap">
    <table class="tbl">
      <thead>
        <tr>
          <th>时间</th>
          <th v-if="showLocation">
            知识库
          </th>
          <th v-if="showLocation">
            知识点
          </th>
          <th>操作人</th>
          <th>动作</th>
          <th>条件</th>
          <th>变更前</th>
          <th>变更后</th>
          <th>来源</th>
          <th>状态</th>
          <th class="op-col">
            操作
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="rows.length === 0">
          <td :colspan="colCount" class="empty">
            暂无变更记录
          </td>
        </tr>
        <tr v-for="row in rows" :key="`${row.entry.answer_id}-${row.entry.action}-${row.entry.time}`">
          <td class="num" style="font-weight: 400">
            {{ formatDateTime(row.entry.time) }}
          </td>
          <template v-if="row.location">
            <td>{{ row.location.kbName }}</td>
            <td>
              <RouterLink :to="`/knowledge-bases/${row.kbId}/knowledge-points/${row.kpId}`">
                {{ row.location.kpTitle }}
              </RouterLink>
            </td>
          </template>
          <td>{{ row.entry.operator }}</td>
          <td>{{ ACTION_LABEL[row.entry.action] }}</td>
          <td style="color: var(--ink-4)">
            {{ describeCoord(row.entry.coord, dimensions) }}
          </td>
          <td style="max-width: 200px; color: var(--ink-4)">
            {{ row.entry.before_content ?? '—' }}
          </td>
          <td style="max-width: 200px">
            {{ row.entry.after_content ?? '—' }}
          </td>
          <td><span class="tag purple">{{ row.entry.source }}</span></td>
          <td>
            <span class="tag" :class="STATUS_TAG_CLASS[row.entry.status]">
              {{ CHANGE_LOG_STATUS_LABEL[row.entry.status] }}
            </span>
          </td>
          <td class="op-col ops">
            <a v-if="row.entry.revocable" class="danger" @click="requestRevoke(row)">撤回</a>
            <span v-else style="color: var(--ink-7)">—</span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
  <RevokeAnswerDialog ref="revokeDialogRef" @success="emit('refresh')" />
</template>
