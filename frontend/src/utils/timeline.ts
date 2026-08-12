/**
 * 「版本历史」tab 的分组与状态标注纯函数。迁移自 React 版 api/timeline.ts，
 * 分组键与「当前版本」的判定都以服务端为准——两处各有一个真实 bug 的教训，
 * 见下方注释（PR #30）。
 */
import type { Answer } from '@/api/answer'

export type TimelineStatus = 'current' | 'superseded' | 'not-yet-effective' | 'revoked'

export interface TimelineEntry {
  answer: Answer
  status: TimelineStatus
}

/**
 * 按服务端算好的 coord_hash 分组，而不是 coordGroupKey(a.coord)——后者的
 * `key:value` + `|` 拼接编码对含 ":"/"|" 的合法文本值有歧义：{a: "x|b:y"} 与
 * {a: "x", b: "y"} 序列化出同一个串，会把两条无关版本链拼接进一条时间线，
 * 同时污染展示与「当前版本」计算（Codex 结论，PR #30）。
 *
 * `currentAnswerIdByHash`：每个 coord_hash 下服务端当前认定 live 的答案 id
 * （没有则 null）——即「当前答案」tab useAnswerGroups(at=undefined) 已经拿到的
 * live_answer。用它而不是客户端 today() 复算「当前」，是因为浏览器与 API
 * 服务器可能处于不同时区（或短暂时钟偏移），在日期边界附近会对同一组选出
 * 不同的「当前」版本（Kimi 终审第 2 轮，PR #30）。
 */
export function buildTimelineGroups(
  answers: Answer[],
  currentAnswerIdByHash: Map<string, number | null>,
): Map<string, TimelineEntry[]> {
  const byGroup = new Map<string, Answer[]>()
  for (const a of answers) {
    const key = a.coord_hash
    const list = byGroup.get(key)
    if (list)
      list.push(a)
    else
      byGroup.set(key, [a])
  }
  const result = new Map<string, TimelineEntry[]>()
  for (const [key, chain] of byGroup)
    result.set(key, tagChain(chain, currentAnswerIdByHash.get(key) ?? null))

  return result
}

/**
 * 降序（最新在前），镜像 resolve.py::compute_live_groups 真实的平局元组
 * (effective_time, created_at, id)——不是 demo 用的两键简化版。edit_answer
 * 允许回填 effective_time，写入顺序最后的版本未必是按生效时间最新的版本，
 * 这里不与真实算法一致，本 tab 就会与「当前答案」tab 对哪一版是当前产生分歧。
 */
function compareForCurrency(a: Answer, b: Answer): number {
  if (a.effective_time !== b.effective_time)
    return a.effective_time < b.effective_time ? 1 : -1
  if (a.created_at !== b.created_at)
    return a.created_at < b.created_at ? 1 : -1
  return b.id - a.id
}

/**
 * `currentId` 是服务端给出的本组 live 答案 id（服务端认为都不 live 则 null），
 * 其余状态由该 id 在排序中的位置推出：compute_live_groups 在已生效、未撤回的
 * 行里取 (effective_time, created_at, id) 最大者，所以排在当前版之前的未撤回
 * 行必然 effective_time 晚于「现在」（否则服务端会选它）→ 尚未生效；排在其后
 * 的行生效时间不晚于当前版 → 已被替代。currentId 为 null（整链撤回，或所有
 * 版本都在未来）时，所有未撤回行都落进「排在缺席的当前版之前」→ 尚未生效。
 */
function tagChain(chain: Answer[], currentId: number | null): TimelineEntry[] {
  const sorted = [...chain].sort(compareForCurrency)
  const currentIndex = currentId === null ? -1 : sorted.findIndex(a => a.id === currentId)
  return sorted.map((answer, index) => ({
    answer,
    status: answer.revoked
      ? 'revoked'
      : index === currentIndex
        ? 'current'
        : currentIndex === -1 || index < currentIndex
          ? 'not-yet-effective'
          : 'superseded',
  }))
}
