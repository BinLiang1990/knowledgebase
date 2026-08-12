<script setup lang="ts">
import type { CoordRow } from './coordRows'
import type { Dimension } from '@/api/dimension'
// 写/编辑答案合体弹窗：open() 新写、open(existing) 编辑（镜像 demo 共用的
// #ansMask 弹窗，设计文档 §4.2-§4.4）。
import type { Filters } from '@/utils/dimension'
import { createAnswer, editAnswer } from '@/api/answer'
import { diffCoord } from '@/utils/coord'
import { today } from '@/utils/format'
import CoordEditor from './CoordEditor.vue'
import { coordRowsFromCoord, coordRowsToCoord, hasLockedRow } from './coordRows'

export interface ExistingAnswer {
  answerId: number
  coord: Filters
  content: string
  effective_time: string
  note: string | null
}

const props = defineProps<{
  kbId: number
  kpId: number
  dimensions: Dimension[]
}>()

const emit = defineEmits<{
  /** 保存成功——父页面重载条件组与知识点统计 */
  success: []
}>()

const visible = ref(false)
const submitting = ref(false)
const existing = ref<ExistingAnswer | null>(null)
const content = ref('')
const effectiveTime = ref(today())
const note = ref('')
const rows = ref<CoordRow[]>([])
const migrationReason = ref('')
const error = ref('')

const isEdit = computed(() => existing.value !== null)

function open(target?: ExistingAnswer) {
  existing.value = target ?? null
  content.value = target?.content ?? ''
  // 编辑时生效时间从原值起步，不能默认 today()——否则只改内容/条件也会把
  // 生效日期静默推到今天（Kimi 终审，PR #24）
  effectiveTime.value = target?.effective_time ?? today()
  note.value = target?.note ?? ''
  rows.value = target ? coordRowsFromCoord(target.coord, props.dimensions) : []
  migrationReason.value = ''
  error.value = ''
  visible.value = true
}
defineExpose({ open })

// 条件是否已实际变更（决定是否显示迁移原因输入框）
const showMigrationReason = computed(() => {
  if (!existing.value)
    return false
  const result = coordRowsToCoord(rows.value, props.dimensions)
  return Boolean(result.coord) && diffCoord(existing.value.coord, result.coord!, props.dimensions)
})

async function submit() {
  const trimmedContent = content.value.trim()
  if (!trimmedContent || !effectiveTime.value) {
    error.value = '答案内容、生效时间为必填项。'
    return
  }
  const result = coordRowsToCoord(rows.value, props.dimensions)
  if (result.error || !result.coord) {
    error.value = result.error ?? '条件填写有误。'
    return
  }
  const coord = result.coord
  const trimmedNote = note.value.trim() || undefined

  if (!existing.value) {
    submitting.value = true
    try {
      await createAnswer(props.kbId, props.kpId, {
        coord,
        content: trimmedContent,
        effective_time: effectiveTime.value,
        note: trimmedNote,
      })
      ElMessage.success('已保存答案')
      visible.value = false
      emit('success')
    }
    catch {
      // 服务端错误已由 request 拦截器统一提示，保持弹窗打开供修改
    }
    finally {
      submitting.value = false
    }
    return
  }

  const changed = diffCoord(existing.value.coord, coord, props.dimensions)
  if (changed && hasLockedRow(rows.value)) {
    // §4.2/§4.4：coord 始终原样带上锁定行的原值，服务端 normalize_coord 会
    // 拒绝它（引用的维度已不再启用）——在这里用用户能理解的话拦下，而不是 400
    error.value = '该答案的条件包含已停用的维度，暂不支持迁移条件；如需修改，请只调整内容或生效时间。'
    return
  }
  if (changed && !migrationReason.value.trim()) {
    error.value = '变更适用条件需要填写迁移原因。'
    return
  }
  error.value = ''
  submitting.value = true
  try {
    await editAnswer(props.kbId, props.kpId, existing.value.answerId, {
      content: trimmedContent,
      effective_time: effectiveTime.value,
      note: trimmedNote,
      // 条件未变时整个省略 coord——「总是发」会破坏「coord 引用已停用维度的
      // 答案仍可编辑内容/时间」这条路径（设计文档 §4.4）
      ...(changed ? { coord, migration_reason: migrationReason.value.trim() } : {}),
    })
    ElMessage.success('已保存答案')
    visible.value = false
    emit('success')
  }
  catch {
    // 服务端错误已由 request 拦截器统一提示，保持弹窗打开供修改
  }
  finally {
    submitting.value = false
  }
}
</script>

<template>
  <el-dialog
    v-model="visible"
    class="app-dialog"
    :title="isEdit ? '编辑答案' : '写一条答案'"
    width="560px"
    :close-on-click-modal="false"
  >
    <div class="mf">
      <label><span class="req">*</span>答案内容</label>
      <textarea v-model="content" rows="3" placeholder="这个条件组合下的说法" />
    </div>
    <div class="mf">
      <label><span class="req">*</span>生效时间</label>
      <input v-model="effectiveTime" type="date">
    </div>
    <div class="mf">
      <label>适用条件(只写你关心的；全部移除 = 默认答案，处处适用)</label>
      <CoordEditor v-model="rows" :dimensions="dimensions" />
    </div>
    <div v-if="showMigrationReason" class="mf">
      <label><span class="req">*</span>迁移原因</label>
      <input v-model="migrationReason" type="text" placeholder="条件变化后为什么要迁移，将记录在留痕中">
    </div>
    <div class="mf">
      <label>变更说明(可选)</label>
      <input v-model="note" type="text" placeholder="例如：流程调整">
    </div>
    <p v-if="error" class="hint" style="color: var(--red)">
      {{ error }}
    </p>
    <template #footer>
      <button type="button" class="btn" @click="visible = false">
        取 消
      </button>
      <button type="button" class="btn primary" :disabled="submitting" @click="submit">
        确 定
      </button>
    </template>
  </el-dialog>
</template>
