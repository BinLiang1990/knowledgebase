<script setup lang="ts">
// 「带条件提问」的查询条件选择器：时间模式（最新/回看某天）+ 维度条件 chips
// + 「加一个条件」下拉。与 CoordEditor（答案条件编辑）是两回事——这里一次
// 锁定一个 维度=取值 用于查询过滤。
import type { Dimension } from '@/api/dimension'
import type { Filters } from '@/utils/dimension'
import { displayValue, FIELD_TYPE_LABEL, toFilterValue } from '@/utils/dimension'

const props = defineProps<{
  dimensions: Dimension[]
  filters: Filters
  qMode: 'now' | 'day'
  qTime: string
  today: string
}>()

const emit = defineEmits<{
  'update:filters': [filters: Filters]
  /** 时间模式/日期变化（父级借此重置分页并重查） */
  'timeChange': [mode: 'now' | 'day', time: string]
}>()

const open = ref(false)
const activeDim = ref<string | null>(null)
const draft = ref('')
const rootRef = ref<HTMLElement>()

// 点击浮层外部关闭（规范 §1 工具库：@vueuse/core）
onClickOutside(rootRef, () => {
  open.value = false
  activeDim.value = null
})

const activeDimension = computed(() => props.dimensions.find(d => d.key === activeDim.value))

function removeFilter(key: string) {
  const next = { ...props.filters }
  delete next[key]
  emit('update:filters', next)
}

function toggleMenu() {
  open.value = !open.value
  activeDim.value = null
}

function openDimension(key: string) {
  activeDim.value = key
  const existing = props.filters[key]
  if (existing !== undefined) {
    draft.value = String(existing)
    return
  }
  // boolean <select> 原生总会显示一个选中项（浏览器画不出「什么都没选」），
  // 视觉默认是「是」/true。不同步 draft 的话，用户不碰下拉直接点确定会因
  // `!draft` 守卫静默无操作，与界面显示的选中项矛盾（本组件测试期发现）。
  const dim = props.dimensions.find(d => d.key === key)
  draft.value = dim?.field_type === 'boolean' ? 'true' : ''
}

function commit() {
  const dim = activeDimension.value
  if (!dim)
    return
  // 纯空白文本是真值，会提交出一个看似生效的条件 chip——后端 trim 成 ""
  // 后丢弃该坐标，静默返回未过滤结果（Codex 结论，PR #23）
  const trimmed = draft.value.trim()
  if (!trimmed)
    return
  emit('update:filters', { ...props.filters, [dim.key]: toFilterValue(dim.field_type, trimmed) })
  open.value = false
  activeDim.value = null
}

function onDayInput(event: Event) {
  const value = (event.target as HTMLInputElement).value
  if (value)
    emit('timeChange', 'day', value)
}
</script>

<template>
  <span>时间</span>
  <span class="seg">
    <button type="button" :class="{ on: qMode === 'now' }" @click="emit('timeChange', 'now', today)">
      最新
    </button>
    <button type="button" :class="{ on: qMode === 'day' }" @click="emit('timeChange', 'day', qTime)">
      回看某天
    </button>
  </span>
  <input v-if="qMode === 'day'" type="date" :value="qTime" :max="today" @change="onDayInput">
  <span
    v-for="(value, key) in filters"
    :key="key"
    class="tag blue"
    style="cursor: pointer"
    title="点击移除该条件"
    @click="removeFilter(String(key))"
  >
    {{ dimensions.find(d => d.key === key)?.label ?? key }} = {{ displayValue(dimensions.find(d => d.key === key), value) }} ✕
  </span>
  <span ref="rootRef" class="dd" :class="{ open }">
    <button type="button" class="btn sm" @click.stop="toggleMenu">
      + 加一个条件
    </button>
    <div v-if="open" class="dd-menu" style="display: block" @click.stop>
      <template v-if="activeDimension">
        <div class="dd-group">「{{ activeDimension.label }}」= ?</div>
        <div style="padding: 2px 12px 10px">
          <ValueInput v-model="draft" :dim="activeDimension" />
          <button type="button" class="btn primary sm" style="margin-top: 8px" @click="commit">
            确 定
          </button>
        </div>
        <div class="dd-sep" />
        <div class="dd-item" @click="activeDim = null">
          <span class="t" style="color: var(--ink-5)">‹ 返回维度列表</span>
        </div>
      </template>
      <template v-else>
        <div class="dd-group">按哪个维度加条件？(本知识库已启用 {{ dimensions.length }} 个维度)</div>
        <template v-if="dimensions.length">
          <div v-for="d in dimensions" :key="d.key" class="dd-item" @click="openDimension(d.key)">
            <span class="t">
              {{ d.label }}{{ filters[d.key] !== undefined ? ` · 已选 ${displayValue(d, filters[d.key])}` : '' }}
            </span>
            <span class="d">{{ FIELD_TYPE_LABEL[d.field_type] }} · 权重 {{ d.weight }}</span>
          </div>
        </template>
        <div v-else class="dd-item" style="color: var(--ink-6); cursor: default">
          本知识库还没有启用任何维度，去「知识库设置」启用
        </div>
      </template>
    </div>
  </span>
</template>
