<script setup lang="ts">
// 「立体全景」tab（issue #16，交互对齐 frontend-mock/detail.html::tabTree）：
// 选择"行/层"两个维度轴，答案按时间列展开成等距 3D 网格；颜色 = 同一条
// 答案链的领地；悬停格子看命中答案与来源（含"继承自更泛化条件"提示）。
// 计算逻辑在 utils/cube.ts（纯函数，有单测），本组件只管轴选择与渲染。
import type { Answer } from '@/api/answer'
import type { Dimension } from '@/api/dimension'
import type { CubeCell } from '@/utils/cube'
import { listAllAnswers } from '@/api/knowledgePoint'
import { useAsyncData } from '@/composables/useAsyncData'
import { describeCoord } from '@/utils/coord'
import { buildCubeModel, DEFAULT_SLOT, usedDimensions } from '@/utils/cube'

const props = defineProps<{
  kbId: number
  kpId: number
  dimensions: Dimension[]
}>()

// 与 mock 相同的 8 色轮换：[前景, 背景]
const CUBE_PALETTE: Array<[string, string]> = [
  ['#0f9d58', '#e6f6ec'],
  ['#1a56f0', '#e8effe'],
  ['#0fa8a2', '#e5f5f4'],
  ['#7a5af8', '#f0ebfe'],
  ['#e08600', '#fdf3e0'],
  ['#e5484d', '#fdecec'],
  ['#b0399f', '#fbeaf8'],
  ['#5b6b85', '#eef1f6'],
]
const CELL = 72
const GAP = 6

const answersQuery = useAsyncData(() => listAllAnswers(props.kbId, props.kpId))
const answers = computed(() => answersQuery.data.value ?? [])

const used = computed(() => usedDimensions(answers.value, props.dimensions))

// 轴选择：用户选过且仍有效则尊重，否则回落（行=第一个可用维度；层=第二个）
const axisAChoice = ref('')
const axisBChoice = ref<string | null>(null) // null = 未初始化；'' = 不分层
const axisA = computed(() => {
  if (axisAChoice.value && used.value.some(d => d.key === axisAChoice.value))
    return axisAChoice.value
  return used.value[0]?.key ?? ''
})
const bOptions = computed(() => used.value.filter(d => d.key !== axisA.value))
const axisB = computed(() => {
  if (axisBChoice.value === '')
    return ''
  if (axisBChoice.value && bOptions.value.some(d => d.key === axisBChoice.value))
    return axisBChoice.value
  return bOptions.value[0]?.key ?? ''
})
const dimA = computed(() => used.value.find(d => d.key === axisA.value))
const dimB = computed(() => bOptions.value.find(d => d.key === axisB.value))

const expanded = ref(false)

const model = computed(() => {
  if (!axisA.value)
    return null
  return buildCubeModel(answers.value, props.dimensions, axisA.value, axisB.value || null)
})

/** 图例插入序 → 颜色（同 mock：轮换 8 色） */
const colorByGroup = computed(() => {
  const map = new Map<string, [string, string]>()
  if (model.value) {
    let i = 0
    for (const key of model.value.legend.keys())
      map.set(key, CUBE_PALETTE[i++ % CUBE_PALETTE.length])
  }
  return map
})

const stageWidth = computed(() => (model.value ? model.value.times.length * CELL + (model.value.times.length - 1) * GAP : 0))
const stageHeight = computed(() => (model.value ? model.value.rows.length * CELL + (model.value.rows.length - 1) * GAP : 0))
const zGap = computed(() => Math.min(Math.max(80, stageHeight.value * 0.3), 115))

function layerZ(layerIndex: number): number {
  if (!model.value)
    return 0
  const count = model.value.layers.length
  return ((count - 1) / 2 - layerIndex) * (expanded.value ? zGap.value * 1.55 : zGap.value)
}

function slotLabel(value: string): string {
  return value === DEFAULT_SLOT ? '(默认)' : value
}
function shortTime(t: string): string {
  return t.slice(5)
}
function cellStyle(cell: CubeCell): Record<string, string> | undefined {
  if (!cell.groupKey)
    return undefined
  const color = colorByGroup.value.get(cell.groupKey)
  return color ? { background: color[1], color: color[0] } : undefined
}
function legendColor(groupKey: string): [string, string] {
  return colorByGroup.value.get(groupKey) ?? CUBE_PALETTE[0]
}
function legendText(answer: Answer): string {
  const cond = describeCoord(answer.coord, props.dimensions)
  const content = answer.content.length > 16 ? `${answer.content.slice(0, 16)}…` : answer.content
  return `${cond}：${content}`
}

// ---- 悬停提示（mock 的 #tipCube：fixed 定位跟随鼠标） ----
interface Tip {
  where: string
  content: string | null
  origin: string | null
  inherited: boolean
}
const tip = ref<Tip | null>(null)
const tipX = ref(0)
const tipY = ref(0)

function cellWhere(rowValue: string, layerValue: string, time: string): string {
  const parts = [`${dimA.value?.label ?? ''}=${slotLabel(rowValue)}`]
  if (dimB.value)
    parts.push(`${dimB.value.label}=${slotLabel(layerValue)}`)
  parts.push(shortTime(time))
  return parts.join(' · ')
}

function showTip(event: MouseEvent, cell: CubeCell, rowValue: string, layerValue: string, time: string) {
  tip.value = cell.answer
    ? {
        where: cellWhere(rowValue, layerValue, time),
        content: cell.answer.content,
        origin: describeCoord(cell.answer.coord, props.dimensions),
        inherited: cell.inherited,
      }
    : { where: `${cellWhere(rowValue, layerValue, time)}：这一天还没有适用答案`, content: null, origin: null, inherited: false }
  moveTip(event)
}
function moveTip(event: MouseEvent) {
  tipX.value = Math.min(event.clientX + 14, window.innerWidth - 310)
  tipY.value = event.clientY + 16
}
function hideTip() {
  tip.value = null
}
</script>

<template>
  <div v-if="answersQuery.loading.value" class="empty-block">
    <span class="spin" /> 加载中…
  </div>
  <div v-else-if="answersQuery.error.value" class="empty-block">
    加载失败
    <br>
    <a @click="answersQuery.load">重试</a>
  </div>
  <div v-else-if="!model || used.length === 0" class="mini-note" style="margin-top: 12px">
    这个知识点还没有带条件的答案，谈不上立体展开；先去「当前答案」写一条带维度条件的答案。
  </div>
  <template v-else>
    <div class="form-row" style="margin-bottom: 2px">
      <span class="f-lbl">行(斜向)</span>
      <select :value="axisA" @change="axisAChoice = ($event.target as HTMLSelectElement).value">
        <option v-for="d in used" :key="d.key" :value="d.key">
          {{ d.label }}
        </option>
      </select>
      <template v-if="bOptions.length">
        <span class="f-lbl">层(纵向)</span>
        <select :value="axisB" @change="axisBChoice = ($event.target as HTMLSelectElement).value">
          <option value="">
            (不分层)
          </option>
          <option v-for="d in bOptions" :key="d.key" :value="d.key">
            {{ d.label }}
          </option>
        </select>
      </template>
      <button v-if="dimB && model.layers.length > 1" type="button" class="btn sm" @click="expanded = !expanded">
        {{ expanded ? '合 上' : '拆开看' }}
      </button>
      <span class="mini-note">列 = 时间({{ model.times.map(shortTime).join(' → ') }}) · 颜色 = 同一条答案的领地 · 悬停格子看来源</span>
    </div>

    <div class="cube-stage" :style="expanded ? { padding: '120px 0 240px' } : undefined">
      <div
        class="cube3"
        :style="{
          width: `${stageWidth}px`,
          height: `${stageHeight}px`,
          transform: expanded ? 'rotateX(58deg) rotateZ(45deg) scale(.85)' : undefined,
        }"
      >
        <div
          v-for="(lv, li) in model.layers"
          :key="lv"
          class="layer3"
          :style="{
            transform: `translateZ(${layerZ(li)}px)`,
            gridTemplateColumns: `repeat(${model.times.length}, ${CELL}px)`,
            gridAutoRows: `${CELL}px`,
          }"
        >
          <div v-if="dimB" class="layer3-lbl">
            {{ dimB.label }} = {{ slotLabel(lv) }}
          </div>
          <template v-for="(rv, ri) in model.rows" :key="rv">
            <div
              v-for="(t, ti) in model.times"
              :key="t"
              class="c3cell"
              :class="{ emptyc: !model.grid[li][ri][ti].answer }"
              :style="cellStyle(model.grid[li][ri][ti])"
              @mouseenter="showTip($event, model.grid[li][ri][ti], rv, lv, t)"
              @mousemove="moveTip"
              @mouseleave="hideTip"
            >
              {{ model.grid[li][ri][ti].answer ? model.grid[li][ri][ti].answer!.content.slice(0, 4) : '无' }}
            </div>
          </template>
        </div>
      </div>
    </div>

    <div class="cube-legend">
      <span v-for="[key, answer] in model.legend" :key="key">
        <i
          :style="{
            display: 'inline-block',
            width: '10px',
            height: '10px',
            borderRadius: '3px',
            background: legendColor(key)[1],
            border: `1.5px solid ${legendColor(key)[0]}`,
            marginRight: '6px',
            verticalAlign: '-1px',
          }"
        />{{ legendText(answer) }}
      </span>
    </div>

    <div v-if="model.offAxisCount" class="mini-note" style="text-align: center; margin-top: 12px">
      另有 {{ model.offAxisCount }} 条答案挂在其他维度上，切换上方「行 / 层」可见。
    </div>

    <Teleport to="body">
      <div v-if="tip" class="cube-tip" :style="{ left: `${tipX}px`, top: `${tipY}px` }">
        {{ tip.where }}
        <template v-if="tip.content">
          <br>「{{ tip.content }}」
          <br>来自「{{ tip.origin }}」那条<template v-if="tip.inherited">
            · <b>继承而来</b>
          </template>
        </template>
      </div>
    </Teleport>
  </template>
</template>

<style scoped>
.cube-stage {
  perspective: 1500px;
  display: flex;
  justify-content: center;
  padding: 70px 0 210px;
}
.cube3 {
  transform-style: preserve-3d;
  transform: rotateX(58deg) rotateZ(45deg);
  position: relative;
  transition: transform 0.8s cubic-bezier(0.16, 1, 0.3, 1);
}
.layer3 {
  position: absolute;
  inset: 0;
  transform-style: preserve-3d;
  display: grid;
  gap: 6px;
  transition: transform 0.8s cubic-bezier(0.16, 1, 0.3, 1);
}
.c3cell {
  border-radius: 8px;
  border: 1.5px solid rgb(255 255 255 / 85%);
  box-shadow: 0 2px 0 rgb(31 66 135 / 12%);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11.5px;
  font-weight: 600;
  cursor: default;
  user-select: none;
  white-space: nowrap;
  overflow: hidden;
}
.c3cell.emptyc {
  background: #f0f3f9;
  color: var(--ink-7, #a8b3c5);
  border-style: dashed;
  font-weight: 400;
}
.layer3-lbl {
  position: absolute;
  left: -12px;
  top: 50%;
  transform: rotateZ(-45deg) rotateX(-58deg) translate(-100%, -50%);
  font-size: 12.5px;
  font-weight: 600;
  color: var(--ink-2, #334155);
  white-space: nowrap;
}
.cube-legend {
  display: flex;
  gap: 12px 20px;
  flex-wrap: wrap;
  font-size: 12.5px;
  color: var(--ink-2, #334155);
  justify-content: center;
  margin-top: -70px;
  position: relative;
}
</style>

<style>
/* Teleport 到 body 的悬浮提示：scoped 选择器出不了组件树，这里全局定义 */
.cube-tip {
  position: fixed;
  z-index: 300;
  pointer-events: none;
  background: rgb(31 43 67 / 94%);
  color: #fff;
  font-size: 12.5px;
  line-height: 1.7;
  padding: 8px 13px;
  border-radius: 9px;
  max-width: 300px;
  box-shadow: 0 8px 24px rgb(15 23 42 / 25%);
}
.cube-tip b {
  color: #8fb5ff;
}
</style>
