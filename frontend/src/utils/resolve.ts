import type { Filters } from './dimension'
import type { Dimension } from '@/api/dimension'
/**
 * 「当前答案」tab 的前端复算逻辑——必须与后端 resolve.py 逐字段一致，
 * 否则该 tab 的「此条件下生效」标记会与 /resolve、列表页 resolved 预览
 * 对同一知识点给出不同答案。迁移自 React 版 api/answers.ts。
 */
import type { AnswerGroup } from '@/api/knowledgePoint'
import { coordValueEquals } from './coord'

function coordSpec(coord: Record<string, unknown>): number {
  return Object.keys(coord).length
}

function coordWeight(coord: Record<string, unknown>, dimensions: Dimension[]): number {
  return Object.keys(coord).reduce((sum, key) => sum + (dimensions.find(d => d.key === key)?.weight ?? 0), 0)
}

/**
 * PRD §4.6.1 规则 3 第一条——精确镜像后端 resolve.py::_coord_compatible：
 * 组自身写了的每个 key，凡查询也指定了的，取值必须一致；查询问了而组没写
 * （或反之）的 key 不参与检查，因此 coord={} 永远兼容。
 * 比较必须走 coordValueEquals 而非裸 String()/==（Codex 结论，PR #24）：
 * number 型筛选值是保精度字符串而组内值是 JSON 数字，朴素比较会拒绝
 * 组 `1` vs 筛选 `"1.0"` 这类等价值，静默藏掉 /resolve 本会命中的答案。
 */
function coordCompatible(groupCoord: Record<string, unknown>, query: Filters, dimensions: Dimension[]): boolean {
  for (const [key, value] of Object.entries(groupCoord)) {
    if (!(key in query))
      continue
    const fieldType = dimensions.find(d => d.key === key)?.field_type
    if (!coordValueEquals(fieldType, value, query[key]))
      return false
  }
  return true
}

/**
 * 复刻 resolve.py::resolve() 真实的 5 键排序元组——不是 PRD §4.6.1 文字描述的
 * 3 键版本。effective_time 是天粒度、平局常见；created_at/id 是服务端为保证
 * 平局裁决确定性专门加的（resolve.py:88-93，PR #21 评审）。只用 3 键会让这里
 * 的排序与服务端对同一知识点算出的结果不一致（设计文档 §4.1）。
 *
 * 已知且接受的偏差（设计文档 §4.1）：coord key 已不在 `dimensions` 里（全局
 * 停用或本库禁用）时权重按 0 计，而后端自己的权重查询不过滤状态。修复需要
 * 新的后端接口暴露停用维度权重，超出范围，不在此处处理。
 */
export function sortLiveGroupsByPriority(
  groups: AnswerGroup[],
  filters: Filters,
  dimensions: Dimension[],
): AnswerGroup[] {
  const live = groups.filter(g => g.live_answer !== null)
  const compatible
    = Object.keys(filters).length === 0 ? live : live.filter(g => coordCompatible(g.coord, filters, dimensions))
  return [...compatible].sort((a, b) => {
    const specDiff = coordSpec(b.coord) - coordSpec(a.coord)
    if (specDiff !== 0)
      return specDiff
    const weightDiff = coordWeight(b.coord, dimensions) - coordWeight(a.coord, dimensions)
    if (weightDiff !== 0)
      return weightDiff
    const av = a.live_answer!
    const bv = b.live_answer!
    if (av.effective_time !== bv.effective_time)
      return av.effective_time < bv.effective_time ? 1 : -1
    if (av.created_at !== bv.created_at)
      return av.created_at < bv.created_at ? 1 : -1
    return bv.id - av.id
  })
}

/**
 * 「此条件下生效」标记：只有存在筛选条件可供消歧时才有意义，且第一名不能与
 * 第二名在 spec（条件个数）上平局——平局说明「赢家」是靠权重/时间选出来的，
 * 不是该具体度下唯一兼容的候选。
 */
export function hasUniqueTopMatch(sortedGroups: AnswerGroup[], hasFilter: boolean): boolean {
  if (!hasFilter || sortedGroups.length === 0)
    return false
  if (sortedGroups.length === 1)
    return true
  return coordSpec(sortedGroups[0].coord) > coordSpec(sortedGroups[1].coord)
}
