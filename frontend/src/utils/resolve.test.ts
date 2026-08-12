import { describe, expect, it } from 'vitest'
import { makeAnswer, makeAnswerGroup, makeDimension } from '@/test/factories'
import { hasUniqueTopMatch, sortLiveGroupsByPriority } from './resolve'

describe('sortLiveGroupsByPriority', () => {
  it('丢弃没有 live 答案的组', () => {
    const groups = [
      makeAnswerGroup({ coord: { tenant: 'acme' }, live_answer: null }),
      makeAnswerGroup({ coord: {}, live_answer: makeAnswer() }),
    ]
    const result = sortLiveGroupsByPriority(groups, {}, [])
    expect(result).toHaveLength(1)
    expect(result[0].coord).toEqual({})
  })

  it('有筛选条件时按 coord 兼容性过滤', () => {
    const groups = [
      makeAnswerGroup({ coord: { tenant: 'acme' }, live_answer: makeAnswer() }),
      makeAnswerGroup({ coord: { tenant: 'other' }, live_answer: makeAnswer() }),
      makeAnswerGroup({ coord: {}, live_answer: makeAnswer() }),
    ]
    const result = sortLiveGroupsByPriority(groups, { tenant: 'acme' }, [])
    const coords = result.map(g => g.coord)
    expect(coords).toContainEqual({ tenant: 'acme' })
    expect(coords).toContainEqual({})
    expect(coords).not.toContainEqual({ tenant: 'other' })
  })

  it('number 型筛选值与等价的组内值匹配，不受字符串/数字表示影响（PR #24 Codex 修复）', () => {
    const dims = [makeDimension({ key: 'priority', field_type: 'number' })]
    const groups = [makeAnswerGroup({ coord: { priority: 1 }, live_answer: makeAnswer() })]
    // 筛选值是保精度字符串（issue #7），组内值是 JSON 数字——"1.0" 与 `1`
    // 在 /resolve 眼里是同一条件，朴素 String() 比较会拒绝
    expect(sortLiveGroupsByPriority(groups, { priority: '1.0' }, dims)).toHaveLength(1)
  })

  it('按 spec 降序、再权重降序、再 effective_time 降序排序', () => {
    const dims = [makeDimension({ key: 'tenant', weight: 10 }), makeDimension({ key: 'region', weight: 90 })]
    const groups = [
      makeAnswerGroup({ coord: { tenant: 'a' }, live_answer: makeAnswer({ id: 1, effective_time: '2026-01-01' }) }),
      makeAnswerGroup({ coord: { region: 'b' }, live_answer: makeAnswer({ id: 2, effective_time: '2026-01-01' }) }),
      makeAnswerGroup({ coord: { tenant: 'a', region: 'b' }, live_answer: makeAnswer({ id: 3, effective_time: '2026-01-01' }) }),
    ]
    const result = sortLiveGroupsByPriority(groups, {}, dims)
    // spec=2 最前；spec=1 里权重高的 region(90) 先于 tenant(10)
    expect(result.map(g => g.live_answer!.id)).toEqual([3, 2, 1])
  })

  it('effective_time 平局时按 created_at、再按 id 决出', () => {
    const groups = [
      makeAnswerGroup({
        coord: {},
        live_answer: makeAnswer({ id: 1, effective_time: '2026-01-01', created_at: '2026-01-01T00:00:00' }),
      }),
      makeAnswerGroup({
        coord: {},
        live_answer: makeAnswer({ id: 2, effective_time: '2026-01-01', created_at: '2026-01-02T00:00:00' }),
      }),
    ]
    const result = sortLiveGroupsByPriority(groups, {}, [])
    expect(result.map(g => g.live_answer!.id)).toEqual([2, 1])
  })

  it('coord key 不在 dimensions 里（已停用维度）时权重按 0 回退', () => {
    const groups = [
      makeAnswerGroup({ coord: { deprecated_dim: 'x' }, live_answer: makeAnswer({ id: 1 }) }),
      makeAnswerGroup({ coord: { tenant: 'a' }, live_answer: makeAnswer({ id: 2 }) }),
    ]
    const dims = [makeDimension({ key: 'tenant', weight: 50 })]
    // deprecated_dim 不在 dims 里 → 权重 0 → 同样 spec 下 tenant(50) 胜出
    const result = sortLiveGroupsByPriority(groups, {}, dims)
    expect(result.map(g => g.live_answer!.id)).toEqual([2, 1])
  })
})

describe('hasUniqueTopMatch', () => {
  it('没有筛选条件时为 false', () => {
    const groups = [makeAnswerGroup({ coord: { tenant: 'a' } })]
    expect(hasUniqueTopMatch(groups, false)).toBe(false)
  })

  it('有筛选且仅一条结果时为 true', () => {
    const groups = [makeAnswerGroup({ coord: { tenant: 'a' } })]
    expect(hasUniqueTopMatch(groups, true)).toBe(true)
  })

  it('前两名 spec 平局时为 false', () => {
    const groups = [makeAnswerGroup({ coord: { tenant: 'a' } }), makeAnswerGroup({ coord: { region: 'b' } })]
    expect(hasUniqueTopMatch(groups, true)).toBe(false)
  })

  it('第一名 spec 严格高于第二名时为 true', () => {
    const groups = [
      makeAnswerGroup({ coord: { tenant: 'a', region: 'b' } }),
      makeAnswerGroup({ coord: { tenant: 'a' } }),
    ]
    expect(hasUniqueTopMatch(groups, true)).toBe(true)
  })
})
