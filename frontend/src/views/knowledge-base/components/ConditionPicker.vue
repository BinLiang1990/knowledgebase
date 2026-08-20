<script setup lang="ts">
// 「带条件提问」的查询条件选择器：时间模式（最新/回看某天）+ 维度条件 chips
// + 「加一个条件」下拉。与 CoordEditor（答案条件编辑）是两回事——这里一次
// 锁定一个 维度=取值 用于查询过滤。
import type { Dimension } from '@/api/dimension'
import type { Filters } from '@/utils/dimension'
import { listDimensionValues } from '@/api/dimension'
import { displayValue, FIELD_TYPE_LABEL, toFilterValue } from '@/utils/dimension'

const props = defineProps<{
  kbId: number
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

// text 维度的候选取值（既有答案条件里出现过的值）：undefined = 未加载/
// 加载中，[] = 确认无候选。按维度 key 缓存一次拉取的结果——选择器一次
// 打开期间反复切维度不重复请求，页面级新鲜度足够（写答案改了取值集合后
// 刷新/重进页面即可见）。
const suggestions = ref<string[]>()
const suggestionsLoading = ref(false)
const suggestionsError = ref(false)
const valueCache = new Map<string, string[]>()

async function loadSuggestions(dim: Dimension) {
  suggestions.value = valueCache.get(dim.key)
  suggestionsError.value = false
  if (suggestions.value !== undefined || dim.field_type !== 'text')
    return
  suggestionsLoading.value = true
  try {
    const values = await listDimensionValues(props.kbId, dim.key)
    valueCache.set(dim.key, values)
    // 请求返回前用户可能已切到别的维度，不要把候选塞给错的输入框
    if (activeDim.value === dim.key)
      suggestions.value = values
  }
  catch {
    // 请求已 silent（api/dimension.ts）：候选拉不到就内联提示 + 纯手输降级
    if (activeDim.value === dim.key)
      suggestionsError.value = true
  }
  finally {
    suggestionsLoading.value = false
  }
}

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
  const dim = props.dimensions.find(d => d.key === key)
  if (dim)
    loadSuggestions(dim)
  const existing = props.filters[key]
  if (existing !== undefined) {
    draft.value = String(existing)
    return
  }
  // boolean <select> 原生总会显示一个选中项（浏览器画不出「什么都没选」），
  // 视觉默认是「是」/true。不同步 draft 的话，用户不碰下拉直接点确定会因
  // `!draft` 守卫静默无操作，与界面显示的选中项矛盾（本组件测试期发现）。
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
          <ValueInput v-model="draft" :dim="activeDimension" :suggestions="suggestions" />
          <div v-if="activeDimension.field_type === 'text'" class="mini-note" style="margin-top: 6px">
            <template v-if="suggestionsLoading">
              <span class="spin" /> 正在加载既有取值…
            </template>
            <template v-else-if="suggestionsError">
              既有取值加载失败，可直接输入
            </template>
            <template v-else-if="suggestions && !suggestions.length">
              本库暂无该维度的既有取值，直接输入即可
            </template>
            <template v-else-if="suggestions">
              共 {{ suggestions.length }} 个既有取值，输入关键字可筛选
            </template>
          </div>
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
