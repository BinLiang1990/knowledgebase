/**
 * 「立体全景」的纯计算逻辑（issue #16，参照 frontend-mock/detail.html::tabTree）。
 *
 * 把一个知识点的全部答案版本，按「行维度 × 层维度 × 时间列」展开成等距
 * 网格：每个格子回答"这一行/层的条件、在这一天，生效的是哪条答案"。
 * 格子的选择逻辑刻意镜像 utils/resolve.ts（后端 resolve.py）的 5 键排序，
 * 保证与「当前答案」tab 的"此条件下生效"判定同源。
 */
import type { Answer } from '@/api/answer'
import type { Dimension } from '@/api/dimension'
import { coordGroupKey } from './coord'

/** 行/层上的"默认"槽位：答案没写该维度条件 */
export const DEFAULT_SLOT = '__default__'

export interface CubeCell {
  answer: Answer | null
  /** 命中的答案并没有写行/层维度的条件——由更泛化的条件继承而来 */
  inherited: boolean
  /** 图例/配色分组键（同一条链一个颜色的"领地"） */
  groupKey: string | null
}

export interface CubeModel {
  /** 行槽位：DEFAULT_SLOT + 行维度的去重取值（出现序） */
  rows: string[]
  /** 层槽位：有层维度时 DEFAULT_SLOT + 取值；无层维度时单层 [DEFAULT_SLOT] */
  layers: string[]
  /** 时间列（升序，最多取最近 5 个生效日期） */
  times: string[]
  /** grid[layerIdx][rowIdx][timeIdx] */
  grid: CubeCell[][][]
  /** 图例：groupKey → 代表答案（着色顺序 = Map 插入序） */
  legend: Map<string, Answer>
  /** 挂在其他维度上的答案条数（当前行/层轴看不到） */
  offAxisCount: number
}

function isSet(value: unknown): boolean {
  return value !== undefined && value !== null && value !== ''
}

/** 答案里实际用到、且在本库启用维度里的维度（轴的候选） */
export function usedDimensions(answers: Answer[], dimensions: Dimension[]): Dimension[] {
  const usedKeys = new Set(
    answers.flatMap(a => Object.keys(a.coord).filter(k => isSet(a.coord[k]))),
  )
  return dimensions.filter(d => usedKeys.has(d.key))
}

/** 槽位显示值：coord 值统一转字符串参与去重/比较（布尔/数字同显示文案） */
function slotOf(value: unknown): string {
  return String(value)
}

function uniqueValues(answers: Answer[], key: string): string[] {
  const seen: string[] = []
  for (const a of answers) {
    if (!isSet(a.coord[key]))
      continue
    const v = slotOf(a.coord[key])
    if (!seen.includes(v))
      seen.push(v)
  }
  return seen
}

function coordSpec(coord: Record<string, unknown>): number {
  return Object.keys(coord).filter(k => isSet(coord[k])).length
}

function coordWeight(coord: Record<string, unknown>, dimensions: Dimension[]): number {
  return Object.keys(coord)
    .filter(k => isSet(coord[k]))
    .reduce((sum, key) => sum + (dimensions.find(d => d.key === key)?.weight ?? 0), 0)
}

/** 链内版本序 / 链间平局裁决共用的 3 键（镜像 resolve.py 的时间元组） */
function newerThan(a: Answer, b: Answer): boolean {
  if (a.effective_time !== b.effective_time)
    return a.effective_time > b.effective_time
  if (a.created_at !== b.created_at)
    return a.created_at > b.created_at
  return a.id > b.id
}

/**
 * 单元格命中：行/层槽位 + 时间列 → 生效答案。
 * 候选 = 所有"写了的条件不与槽位冲突"的链（没写行/层条件的链也算——那就是
 * 继承）；每条链取 effective_time ≤ t 的最新未撤回版本；链间按
 * spec > weight > 时间 3 键选最具体的赢家（镜像 sortLiveGroupsByPriority）。
 */
function cellBest(
  answers: Answer[],
  dimensions: Dimension[],
  axisA: string,
  rowValue: string,
  axisB: string | null,
  layerValue: string | null,
  time: string,
): Answer | null {
  /** 答案写了的每个条件都不与当前行/层槽位冲突才算候选 */
  function fitsSlot(a: Answer): boolean {
    for (const k of Object.keys(a.coord)) {
      if (!isSet(a.coord[k]))
        continue
      if (k === axisA) {
        if (rowValue === DEFAULT_SLOT || slotOf(a.coord[k]) !== rowValue)
          return false
      }
      else if (axisB !== null && k === axisB) {
        if (layerValue === DEFAULT_SLOT || layerValue === null || slotOf(a.coord[k]) !== layerValue)
          return false
      }
      else {
        return false // 挂在其他维度上，当前轴不展示
      }
    }
    return true
  }

  const chains = new Map<string, Answer[]>()
  for (const a of answers) {
    if (a.effective_time > time || a.revoked || !fitsSlot(a))
      continue
    const key = coordGroupKey(a.coord)
    const chain = chains.get(key)
    if (chain)
      chain.push(a)
    else
      chains.set(key, [a])
  }

  let best: Answer | null = null
  for (const chain of chains.values()) {
    let live: Answer | null = null
    for (const version of chain) {
      if (live === null || newerThan(version, live))
        live = version
    }
    if (live === null)
      continue
    if (best === null) {
      best = live
      continue
    }
    const specDiff = coordSpec(live.coord) - coordSpec(best.coord)
    const weightDiff = coordWeight(live.coord, dimensions) - coordWeight(best.coord, dimensions)
    if (specDiff > 0 || (specDiff === 0 && weightDiff > 0) || (specDiff === 0 && weightDiff === 0 && newerThan(live, best)))
      best = live
  }
  return best
}

export function buildCubeModel(
  answers: Answer[],
  dimensions: Dimension[],
  axisA: string,
  axisB: string | null,
  maxTimes = 5,
): CubeModel {
  const rows = [DEFAULT_SLOT, ...uniqueValues(answers, axisA)]
  const layers = axisB ? [DEFAULT_SLOT, ...uniqueValues(answers, axisB)] : [DEFAULT_SLOT]
  let times = [...new Set(answers.map(a => a.effective_time))].sort()
  if (times.length > maxTimes)
    times = times.slice(-maxTimes)

  const offAxisCount = answers.filter(a =>
    Object.keys(a.coord).some(k => isSet(a.coord[k]) && k !== axisA && k !== (axisB ?? '')),
  ).length

  const legend = new Map<string, Answer>()
  const grid = layers.map(lv =>
    rows.map(rv =>
      times.map((t): CubeCell => {
        const best = cellBest(answers, dimensions, axisA, rv, axisB, axisB ? lv : null, t)
        if (!best)
          return { answer: null, inherited: false, groupKey: null }
        const groupKey = coordGroupKey(best.coord)
        if (!legend.has(groupKey))
          legend.set(groupKey, best)
        const inherited
          = (rv !== DEFAULT_SLOT && !isSet(best.coord[axisA]))
            || (axisB !== null && lv !== DEFAULT_SLOT && !isSet(best.coord[axisB]))
        return { answer: best, inherited, groupKey }
      }),
    ),
  )

  return { rows, layers, times, grid, legend, offAxisCount }
}
