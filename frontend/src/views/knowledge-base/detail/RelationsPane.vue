<script setup lang="ts">
// 「答案关联」tab（docs/PRD-答案关联.md §5.2）：按"本知识点侧的链"分组展示
// 关联卡片。数据由父级 index.vue 的 relationsQuery 持有并轮询（「当前答案」
// 卡片上的角标要复用同一份数据），本组件只负责渲染与单条操作。
import type { AnswerRelation, RelationEndpoint, RelationsData } from '@/api/relation'
import type { Dimension } from '@/api/dimension'
import { deleteRelation, regenerateRelation } from '@/api/relation'
import { describeCoord } from '@/utils/coord'
import { formatDateTime } from '@/utils/format'

const props = defineProps<{
  kbId: number
  kpId: number
  dimensions: Dimension[]
  data?: RelationsData
  loading: boolean
  error: boolean
  /** 已删除知识点只读：隐藏自动关联/手动添加/重新生成入口 */
  readonly: boolean
}>()

const emit = defineEmits<{
  /** 数据需要重载（删除/发起生成后） */
  refresh: []
  /** 打开手动添加弹窗（弹窗归父级持有，与 WriteAnswerDialog 同模式） */
  addRelation: []
  /** 打开编辑描述弹窗 */
  editRelation: [relation: AnswerRelation]
  /** 发起知识点级自动关联（父级统一处理，与「分析关联」共用逻辑） */
  autoRelate: []
}>()

const relations = computed(() => props.data?.relations ?? [])
const status = computed(() => props.data?.generation_status ?? 'idle')
const analysisDisabled = computed(() => status.value === 'disabled')
const analysisRunning = computed(() => status.value === 'pending' || status.value === 'generating')

interface SelfOther {
  rel: AnswerRelation
  self: RelationEndpoint
  other: RelationEndpoint
  samePoint: boolean
}

/** 确定关联里哪端属于当前知识点（同知识点关联取 a 端） */
function splitSelfOther(rel: AnswerRelation): SelfOther {
  const isSelfA = rel.a.kp_id === props.kpId
  return {
    rel,
    self: isSelfA ? rel.a : rel.b,
    other: isSelfA ? rel.b : rel.a,
    samePoint: rel.a.kp_id === props.kpId && rel.b.kp_id === props.kpId,
  }
}

/** 按本侧链分组，默认答案组置顶、其余按 coord_hash 序（与 demo 一致） */
const groups = computed(() => {
  const byHash = new Map<string, { coord: RelationEndpoint['coord'], items: SelfOther[] }>()
  for (const rel of relations.value) {
    const item = splitSelfOther(rel)
    const entry = byHash.get(item.self.coord_hash)
    if (entry)
      entry.items.push(item)
    else
      byHash.set(item.self.coord_hash, { coord: item.self.coord, items: [item] })
  }
  return [...byHash.entries()]
    .sort(([ha, a], [hb, b]) => {
      const defA = Object.keys(a.coord).length === 0 ? 0 : 1
      const defB = Object.keys(b.coord).length === 0 ? 0 : 1
      return defA - defB || ha.localeCompare(hb)
    })
    .map(([hash, entry]) => ({ hash, ...entry }))
})

function selfLabel(coord: RelationEndpoint['coord']): string {
  return Object.keys(coord).length === 0 ? '默认答案' : describeCoord(coord, props.dimensions).replace(/^适用条件：/, '')
}

function otherLabel(item: SelfOther): string {
  const cond = Object.keys(item.other.coord).length === 0
    ? '默认答案'
    : describeCoord(item.other.coord, props.dimensions).replace(/^适用条件：/, '')
  if (item.samePoint)
    return `本知识点 / ${cond}`
  return `${item.other.kb_name ?? '未知知识库'} / ${item.other.kp_title ?? '未知知识点'} / ${cond}`
}

function otherStateTag(item: SelfOther): string | null {
  if (item.other.state === 'revoked')
    return '对端已撤回'
  if (item.other.state === 'kp-deleted' || item.other.state === 'missing')
    return '对端知识点已删除'
  return null
}

function canRegenerate(item: SelfOther): boolean {
  return !props.readonly && !analysisDisabled.value && item.other.state === 'ok' && item.self.state === 'ok'
}

const actingId = ref<number | null>(null)

async function handleRegenerate(rel: AnswerRelation) {
  actingId.value = rel.id
  try {
    await regenerateRelation(rel.id)
    ElMessage.success('已登记重新生成任务')
    emit('refresh')
  }
  catch {
    // request 拦截器已提示
  }
  finally {
    actingId.value = null
  }
}

async function handleDelete(rel: AnswerRelation) {
  try {
    await ElMessageBox.confirm('确定删除这条关联？此操作不可恢复。', '删除关联', {
      type: 'warning',
      confirmButtonText: '删 除',
      cancelButtonText: '取 消',
    })
  }
  catch {
    return // 用户取消
  }
  actingId.value = rel.id
  try {
    await deleteRelation(rel.id)
    ElMessage.success('已删除关联')
    emit('refresh')
  }
  catch {
    // request 拦截器已提示
  }
  finally {
    actingId.value = null
  }
}
</script>

<template>
  <div class="form-row" style="display: flex; align-items: center; justify-content: space-between">
    <span style="font-size: 13px; color: var(--ink-4)">
      答案关联 <b class="num">{{ relations.length }}</b> 条 · 由「自动关联 / 分析关联」生成或手动添加；关联在两端知识点的详情页对称可见
      <span v-if="analysisRunning" style="color: var(--blue, #1a56f0); margin-left: 8px">
        <span class="spin" /> 分析进行中，自动刷新…
      </span>
    </span>
    <span v-if="!readonly" style="display: flex; gap: 8px">
      <button
        type="button"
        class="btn sm"
        :disabled="analysisDisabled || analysisRunning"
        :title="analysisDisabled ? '关联分析未启用（服务端未配置模型网关）' : analysisRunning ? '已有分析进行中' : undefined"
        @click="emit('autoRelate')"
      >
        ✦ 自动关联
      </button>
      <button type="button" class="btn primary sm" @click="emit('addRelation')">
        + 手动添加关联
      </button>
    </span>
  </div>

  <div v-if="analysisDisabled" class="mini-note" style="margin: 10px 2px 0">
    关联分析未启用（服务端未配置模型网关）——「自动关联 / 分析关联」不可用，手动添加（人工填写描述）仍然可用。
  </div>

  <div v-if="loading && !data" class="empty-block">
    <span class="spin" /> 加载中…
  </div>
  <div v-else-if="error && !data" class="empty-block">
    加载失败
    <br>
    <a @click="emit('refresh')">重试</a>
  </div>
  <div v-else-if="relations.length === 0" class="empty-block">
    暂无关联。<br>在「当前答案」里对某条答案点击「分析关联」，或点右上角「自动关联 / 手动添加关联」。
  </div>

  <template v-else>
    <div v-for="group in groups" :key="group.hash" style="margin-top: 18px">
      <div style="font-size: 13px; font-weight: 600; color: var(--ink-2); margin-bottom: 4px">
        本知识点 · {{ selfLabel(group.coord) }}（{{ group.items.length }} 条关联）
      </div>

      <div v-for="item in group.items" :key="item.rel.id" class="ans-item">
        <div style="display: flex; align-items: flex-start; gap: 16px">
          <div style="flex: 1">
            <div style="font-size: 13.5px; margin-bottom: 6px">
              ↔
              <RouterLink
                v-if="!item.samePoint && item.other.kp_title"
                :to="`/knowledge-bases/${item.other.kb_id}/knowledge-points/${item.other.kp_id}`"
                style="font-weight: 600"
              >
                {{ otherLabel(item) }}
              </RouterLink>
              <b v-else>{{ otherLabel(item) }}</b>
              <span v-if="item.rel.source === 'ai'" class="tag blue">AI</span>
              <span v-else class="tag purple">手动</span>
              <span v-if="item.rel.generating" class="tag orange"><span class="spin" /> 生成中</span>
              <span v-else-if="item.rel.stale" class="tag orange">内容已更新</span>
              <span v-if="otherStateTag(item)" class="tag gray">{{ otherStateTag(item) }}</span>
            </div>

            <div v-if="item.rel.generating" class="ai-content" style="font-size: 13.5px; color: var(--ink-5)">
              描述生成中，稍后自动刷新…
            </div>
            <div v-else class="ai-content" style="font-size: 13.5px; color: var(--ink-2)">
              {{ item.rel.description }}
            </div>

            <div
              v-if="item.other.current_content_preview"
              style="font-size: 12.5px; color: var(--ink-6); margin-top: 6px"
            >
              对端当前内容：{{ item.other.current_content_preview }}
            </div>
          </div>

          <span class="ops" style="font-size: 12.5px; white-space: nowrap; padding-top: 3px">
            <a v-if="item.rel.source === 'manual' && !readonly" @click="emit('editRelation', item.rel)">编辑描述</a>
            <a
              v-if="canRegenerate(item)"
              :style="actingId === item.rel.id ? 'color: var(--ink-6); cursor: wait' : undefined"
              @click="actingId === item.rel.id ? undefined : handleRegenerate(item.rel)"
            >重新生成</a>
            <a
              class="danger"
              :style="actingId === item.rel.id ? 'color: var(--ink-6); cursor: wait' : undefined"
              @click="actingId === item.rel.id ? undefined : handleDelete(item.rel)"
            >删除</a>
          </span>
        </div>

        <div class="ai-cond">
          <span>
            {{ item.rel.source === 'ai' ? `由 ${item.rel.model ?? 'AI'} 生成` : `${item.rel.operator} 手动添加` }}
            · <span class="num">{{ formatDateTime(item.rel.updated_at) }}</span>
            <template v-if="item.rel.similarity != null">
              · 相似度 <span class="num">{{ Math.round(item.rel.similarity * 100) }}%</span>
            </template>
          </span>
        </div>
      </div>
    </div>
  </template>
</template>
