import { describe, expect, it } from 'vitest'
import { makeAnswer } from '@/test/factories'
import { buildTimelineGroups } from './timeline'

// 用足够久远的过去/未来日期，避免测试依赖运行时的真实「今天」。
// effective_time 在这里只作为排序/平局元组（compareForCurrency）的首键——
// 自 PR #30 终审第 2 轮起，「当前」本身来自 currentAnswerIdByHash（服务端
// live_answer 的替身），从不与客户端 today() 比较。
const PAST_1 = '2000-01-01'
const PAST_2 = '2000-06-01'
const FUTURE = '2099-01-01'

// makeAnswer() 默认的 coord_hash 是固定占位值，与 coord 无关——需要多个
// 不同组的测试必须显式设置 coord_hash：buildTimelineGroups 按 coord_hash
// 分组（不从 coord 自行推导，原因见该函数注释）。
const HASH_A = 'hash-a'
const HASH_B = 'hash-b'

function currentMap(entries: Array<[string, number | null]>): Map<string, number | null> {
  return new Map(entries)
}

describe('buildTimelineGroups', () => {
  it('把服务端报告的 live 答案标为当前', () => {
    const groups = buildTimelineGroups(
      [makeAnswer({ id: 1, effective_time: PAST_1, coord_hash: HASH_A })],
      currentMap([[HASH_A, 1]]),
    )
    const entries = groups.get(HASH_A)!
    expect(entries).toHaveLength(1)
    expect(entries[0].status).toBe('current')
  })

  it('以 effective_time 更晚者为当前，而不是写入更晚者', () => {
    // v1 先写但 effective_time 更晚（PAST_2）；v2 后写但回填了更早的
    // effective_time（PAST_1）。按 resolve.py 的真实规则 v1 是当前——demo
    // 更简单的写入顺序逻辑会算错。服务端（经 currentMap 替身）认定 v1 live。
    const v1 = makeAnswer({ id: 1, effective_time: PAST_2, created_at: '2026-01-01T00:00:00', coord_hash: HASH_A })
    const v2 = makeAnswer({ id: 2, effective_time: PAST_1, created_at: '2026-01-02T00:00:00', coord_hash: HASH_A })
    const groups = buildTimelineGroups([v1, v2], currentMap([[HASH_A, 1]]))
    const byId = new Map(groups.get(HASH_A)!.map(e => [e.answer.id, e.status]))
    expect(byId.get(1)).toBe('current')
    expect(byId.get(2)).toBe('superseded')
  })

  it('整链撤回时每一行都标撤回，而不是只标最后写入的那行', () => {
    // 回归（设计文档 §4.1）：整链撤回会把每一行的 revoked 都置 true（后端
    // 批量 UPDATE）——不能像 get_change_log 的 status 字段那样只把时间上
    // 最后的版本标成 revoked。整链撤回的组没有 live_answer，服务端报 null。
    const v1 = makeAnswer({ id: 1, effective_time: PAST_1, created_at: '2026-01-01T00:00:00', revoked: true, coord_hash: HASH_A })
    const v2 = makeAnswer({ id: 2, effective_time: PAST_2, created_at: '2026-01-02T00:00:00', revoked: true, coord_hash: HASH_A })
    const groups = buildTimelineGroups([v1, v2], currentMap([[HASH_A, null]]))
    expect(groups.get(HASH_A)!.every(e => e.status === 'revoked')).toBe(true)
  })

  it('服务端没选为 live 的未来版本标尚未生效，而不是当前', () => {
    const past = makeAnswer({ id: 1, effective_time: PAST_1, created_at: '2026-01-01T00:00:00', coord_hash: HASH_A })
    const future = makeAnswer({ id: 2, effective_time: FUTURE, created_at: '2026-01-02T00:00:00', coord_hash: HASH_A })
    const groups = buildTimelineGroups([past, future], currentMap([[HASH_A, 1]]))
    const byId = new Map(groups.get(HASH_A)!.map(e => [e.answer.id, e.status]))
    expect(byId.get(1)).toBe('current')
    expect(byId.get(2)).toBe('not-yet-effective')
  })

  it('服务端报本组无 live 答案时，所有未撤回行都标尚未生效', () => {
    // 回归（PR #30 终审第 2 轮）：currentAnswerIdByHash 没有本组的 live id
    // （站在服务端视角所有版本都在未来）时，不能有任何行被误报为
    // superseded——从来没有过「当前」可供替代
    const v1 = makeAnswer({ id: 1, effective_time: PAST_1, created_at: '2026-01-01T00:00:00', coord_hash: HASH_A })
    const v2 = makeAnswer({ id: 2, effective_time: FUTURE, created_at: '2026-01-02T00:00:00', coord_hash: HASH_A })
    const groups = buildTimelineGroups([v1, v2], currentMap([[HASH_A, null]]))
    expect(groups.get(HASH_A)!.every(e => e.status === 'not-yet-effective')).toBe(true)
  })

  it('多个条件组按 coord_hash 独立分组', () => {
    const groups = buildTimelineGroups(
      [
        makeAnswer({ id: 1, coord: {}, effective_time: PAST_1, coord_hash: HASH_A }),
        makeAnswer({ id: 2, coord: { tenant: 'acme' }, effective_time: PAST_1, coord_hash: HASH_B }),
      ],
      currentMap([[HASH_A, 1], [HASH_B, 2]]),
    )
    expect(groups.size).toBe(2)
    expect(groups.get(HASH_A)).toHaveLength(1)
    expect(groups.get(HASH_B)).toHaveLength(1)
  })

  it('字符串编码会碰撞的两个不同 coord 不会被拼进同一条链（PR #30 Codex 修复）', () => {
    // {a: "x|b:y"} 与 {a: "x", b: "y"} 在 coordGroupKey 的 `key:value` + "|"
    // 编码下序列化出同一个串——按那个串分组（本函数的早期版本）会把两条
    // 真正不同的版本链并成一条坏时间线。按服务端 coord_hash 分组则无论
    // 文本值里有什么字符都能分开。
    const a = makeAnswer({ id: 1, coord: { a: 'x|b:y' }, effective_time: PAST_1, coord_hash: HASH_A })
    const b = makeAnswer({ id: 2, coord: { a: 'x', b: 'y' }, effective_time: PAST_1, coord_hash: HASH_B })
    const groups = buildTimelineGroups([a, b], currentMap([[HASH_A, 1], [HASH_B, 2]]))
    expect(groups.size).toBe(2)
    expect(groups.get(HASH_A)).toHaveLength(1)
    expect(groups.get(HASH_B)).toHaveLength(1)
  })

  it('effective_time 相同的平局按 created_at 决出，与 resolve.py 一致（而非 demo 的简化比较）', () => {
    const older = makeAnswer({ id: 1, effective_time: PAST_1, created_at: '2026-01-01T00:00:00', coord_hash: HASH_A })
    const newer = makeAnswer({ id: 2, effective_time: PAST_1, created_at: '2026-01-02T00:00:00', coord_hash: HASH_A })
    const groups = buildTimelineGroups([older, newer], currentMap([[HASH_A, 2]]))
    const byId = new Map(groups.get(HASH_A)!.map(e => [e.answer.id, e.status]))
    expect(byId.get(2)).toBe('current')
    expect(byId.get(1)).toBe('superseded')
  })
})
