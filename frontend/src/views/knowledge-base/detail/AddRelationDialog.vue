<script setup lang="ts">
// 手动添加关联（docs/PRD-答案关联.md §5.3）：级联选择对端（知识库 → 知识点
// → 条件组合），描述人工填写或留空交给 AI 异步生成。本侧固定为当前知识点，
// 只选哪条链。
import type { Dimension } from '@/api/dimension'
import type { KnowledgeBase } from '@/api/knowledgeBase'
import type { AnswerGroup, KnowledgePoint } from '@/api/knowledgePoint'
import { listKnowledgeBases } from '@/api/knowledgeBase'
import { listAnswerGroups, listKnowledgePoints } from '@/api/knowledgePoint'
import { createRelation } from '@/api/relation'
import { describeCoord } from '@/utils/coord'

const props = defineProps<{
  kbId: number
  kpId: number
  /** 当前知识点的条件组（本侧链选项）；父级已加载好 */
  selfGroups: AnswerGroup[]
  dimensions: Dimension[]
  /** AI 生成不可用（服务端未配置网关）时只允许人工描述 */
  analysisDisabled: boolean
}>()

const emit = defineEmits<{
  success: []
}>()

const visible = ref(false)
const submitting = ref(false)
const error = ref('')

const selfHash = ref('')
const otherKbId = ref<number | null>(null)
const otherKpId = ref<number | null>(null)
const otherHash = ref('')
const description = ref('')
const useAi = ref(false)

const kbs = ref<KnowledgeBase[]>([])
const kps = ref<KnowledgePoint[]>([])
const otherGroups = ref<AnswerGroup[]>([])
const loadingKps = ref(false)
const loadingGroups = ref(false)

/** 有当前生效版本的链才可选（撤回/未生效的没有可关联内容） */
function liveOnly(groups: AnswerGroup[]): AnswerGroup[] {
  return groups.filter(g => !g.revoked && g.live_answer)
}

const selfOptions = computed(() => liveOnly(props.selfGroups))

function chainLabel(g: AnswerGroup): string {
  const cond = Object.keys(g.coord).length === 0
    ? '默认答案'
    : describeCoord(g.coord, props.dimensions).replace(/^适用条件：/, '')
  const content = g.live_answer!.content
  return `${cond} · ${content.length > 20 ? `${content.slice(0, 20)}…` : content}`
}

async function open() {
  error.value = ''
  description.value = ''
  useAi.value = false
  selfHash.value = selfOptions.value[0]?.live_answer?.coord_hash ?? ''
  otherKbId.value = null
  otherKpId.value = null
  otherHash.value = ''
  kps.value = []
  otherGroups.value = []
  visible.value = true
  try {
    kbs.value = (await listKnowledgeBases()).filter(b => b.status === 'active')
  }
  catch {
    // request 拦截器已提示；弹窗保持打开可重试（重新选择知识库）
  }
}
defineExpose({ open })

watch(otherKbId, async (kbId) => {
  otherKpId.value = null
  otherHash.value = ''
  kps.value = []
  otherGroups.value = []
  if (kbId == null)
    return
  loadingKps.value = true
  try {
    kps.value = await listKnowledgePoints(kbId, {})
  }
  catch {
    // request 拦截器已提示
  }
  finally {
    loadingKps.value = false
  }
})

watch(otherKpId, async (kpId) => {
  otherHash.value = ''
  otherGroups.value = []
  if (otherKbId.value == null || kpId == null)
    return
  loadingGroups.value = true
  try {
    otherGroups.value = liveOnly(await listAnswerGroups(otherKbId.value, kpId))
  }
  catch {
    // request 拦截器已提示
  }
  finally {
    loadingGroups.value = false
  }
})

async function submit() {
  const trimmed = description.value.trim()
  if (!selfHash.value) {
    error.value = '请选择本知识点侧的答案。'
    return
  }
  if (otherKbId.value == null || otherKpId.value == null || !otherHash.value) {
    error.value = '请完整选择对端答案。'
    return
  }
  if (!trimmed && !useAi.value) {
    error.value = '请填写关联描述，或勾选「由 AI 生成描述」。'
    return
  }
  error.value = ''
  submitting.value = true
  try {
    const result = await createRelation({
      a: { kb_id: props.kbId, kp_id: props.kpId, coord_hash: selfHash.value },
      b: { kb_id: otherKbId.value, kp_id: otherKpId.value, coord_hash: otherHash.value },
      description: trimmed || undefined,
      generate: !trimmed && useAi.value,
    })
    ElMessage.success(result.task_id != null ? '已添加关联，描述生成中' : '已添加关联')
    visible.value = false
    emit('success')
  }
  catch {
    // request 拦截器已提示（重复关联/端点不可用等），保持弹窗供修正
  }
  finally {
    submitting.value = false
  }
}
</script>

<template>
  <el-dialog v-model="visible" class="app-dialog" title="手动添加关联" width="640px" :close-on-click-modal="false">
    <div class="mf">
      <label><span class="req">*</span>本知识点侧答案</label>
      <select v-model="selfHash">
        <option v-for="g in selfOptions" :key="g.live_answer!.coord_hash" :value="g.live_answer!.coord_hash">
          {{ chainLabel(g) }}
        </option>
      </select>
    </div>
    <div class="mf">
      <label><span class="req">*</span>对端知识库</label>
      <select v-model="otherKbId">
        <option :value="null" disabled>选择知识库…</option>
        <option v-for="b in kbs" :key="b.id" :value="b.id">{{ b.name }}</option>
      </select>
    </div>
    <div class="mf">
      <label><span class="req">*</span>对端知识点</label>
      <select v-model="otherKpId" :disabled="loadingKps || otherKbId == null">
        <option :value="null" disabled>{{ loadingKps ? '加载中…' : '选择知识点…' }}</option>
        <option v-for="k in kps" :key="k.id" :value="k.id">{{ k.title }}</option>
      </select>
    </div>
    <div class="mf">
      <label><span class="req">*</span>对端答案（条件组合）</label>
      <select v-model="otherHash" :disabled="loadingGroups || otherKpId == null">
        <option value="" disabled>{{ loadingGroups ? '加载中…' : '选择条件组合…' }}</option>
        <option v-for="g in otherGroups" :key="g.live_answer!.coord_hash" :value="g.live_answer!.coord_hash">
          {{ chainLabel(g) }}
        </option>
      </select>
    </div>
    <div class="mf">
      <label>关联描述</label>
      <textarea
        v-model="description"
        rows="4"
        placeholder="说明两条答案之间的关系；留空并勾选下方选项可由 AI 生成"
        maxlength="2000"
      />
      <label style="display: flex; align-items: center; gap: 6px; margin-top: 8px; font-size: 13px; cursor: pointer">
        <input v-model="useAi" type="checkbox" :disabled="analysisDisabled">
        描述留空，由 AI 生成（异步，完成前显示"生成中"）
        <span v-if="analysisDisabled" class="hint">（未配置模型网关，暂不可用）</span>
      </label>
    </div>
    <p v-if="error" class="hint" style="color: var(--red)">
      {{ error }}
    </p>
    <template #footer>
      <button type="button" class="btn" @click="visible = false">
        取 消
      </button>
      <button type="button" class="btn primary" :disabled="submitting" @click="submit">
        保 存
      </button>
    </template>
  </el-dialog>
</template>
