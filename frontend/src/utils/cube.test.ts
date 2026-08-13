import { describe, expect, it } from 'vitest'
import { makeAnswer, makeDimension } from '@/test/factories'
import { buildCubeModel, DEFAULT_SLOT, usedDimensions } from './cube'

const dims = [
  makeDimension({ key: 'tenant', label: '租户', weight: 50 }),
  makeDimension({ key: 'region', label: '地区', weight: 30 }),
  makeDimension({ key: 'channel', label: '渠道', weight: 10 }),
]

describe('usedDimensions', () => {
  it('只保留答案里实际写了值、且在启用维度里的维度', () => {
    const answers = [
      makeAnswer({ id: 1, coord: { tenant: 'A' } }),
      makeAnswer({ id: 2, coord: { unknown_dim: 'x' } }), // 不在启用维度里
      makeAnswer({ id: 3, coord: { region: '' } }), // 空值不算用到
    ]
    expect(usedDimensions(answers, dims).map(d => d.key)).toEqual(['tenant'])
  })
})

describe('buildCubeModel', () => {
  it('默认行取默认答案，具体行优先取本行条件的答案', () => {
    const answers = [
      makeAnswer({ id: 1, coord: {}, content: '默认答案', effective_time: '2026-08-01' }),
      makeAnswer({ id: 2, coord: { tenant: 'A' }, content: 'A 专属', effective_time: '2026-08-02' }),
    ]
    const model = buildCubeModel(answers, dims, 'tenant', null)
    expect(model.rows).toEqual([DEFAULT_SLOT, 'A'])
    expect(model.layers).toEqual([DEFAULT_SLOT])
    expect(model.times).toEqual(['2026-08-01', '2026-08-02'])

    const [layer] = model.grid
    // 默认行：两天都是默认答案
    expect(layer[0][0].answer?.content).toBe('默认答案')
    expect(layer[0][1].answer?.content).toBe('默认答案')
    // A 行第 1 天：A 专属还没生效 → 继承默认
    expect(layer[1][0].answer?.content).toBe('默认答案')
    expect(layer[1][0].inherited).toBe(true)
    // A 行第 2 天：命中 A 专属，非继承
    expect(layer[1][1].answer?.content).toBe('A 专属')
    expect(layer[1][1].inherited).toBe(false)
  })

  it('没有任何答案命中时格子为空', () => {
    const answers = [
      makeAnswer({ id: 1, coord: { tenant: 'A' }, effective_time: '2026-08-02' }),
    ]
    const model = buildCubeModel(answers, dims, 'tenant', null)
    // 默认行没有默认答案可继承 → 空
    expect(model.grid[0][0][0].answer).toBeNull()
  })

  it('撤回的链不参与命中', () => {
    const answers = [
      makeAnswer({ id: 1, coord: {}, content: '默认', effective_time: '2026-08-01' }),
      makeAnswer({ id: 2, coord: { tenant: 'A' }, content: 'A 已撤回', effective_time: '2026-08-02', revoked: true }),
    ]
    const model = buildCubeModel(answers, dims, 'tenant', null)
    const cell = model.grid[0][1][1] // A 行最后一天
    expect(cell.answer?.content).toBe('默认')
    expect(cell.inherited).toBe(true)
  })

  it('链内取时间列之前的最新版本（同链多版本）', () => {
    const answers = [
      makeAnswer({ id: 1, coord: { tenant: 'A' }, content: '旧版', effective_time: '2026-08-01', created_at: '2026-08-01T00:00:00' }),
      makeAnswer({ id: 2, coord: { tenant: 'A' }, content: '新版', effective_time: '2026-08-03', created_at: '2026-08-03T00:00:00' }),
    ]
    const model = buildCubeModel(answers, dims, 'tenant', null)
    const row = model.grid[0][1]
    expect(row[0].answer?.content).toBe('旧版') // 2026-08-01 列
    expect(row[1].answer?.content).toBe('新版') // 2026-08-03 列
  })

  it('双轴分层：层维度取值各自成层，跨层不互相命中', () => {
    const answers = [
      makeAnswer({ id: 1, coord: {}, content: '默认', effective_time: '2026-08-01' }),
      makeAnswer({ id: 2, coord: { tenant: 'A', region: '北' }, content: 'A北', effective_time: '2026-08-01' }),
    ]
    const model = buildCubeModel(answers, dims, 'tenant', 'region')
    expect(model.layers).toEqual([DEFAULT_SLOT, '北'])
    // 默认层 A 行：A北 挂着 region 条件，不该命中 → 继承默认
    expect(model.grid[0][1][0].answer?.content).toBe('默认')
    // 北层 A 行：命中 A北
    expect(model.grid[1][1][0].answer?.content).toBe('A北')
    expect(model.grid[1][1][0].inherited).toBe(false)
    // 北层默认行：默认答案继承而来
    expect(model.grid[1][0][0].answer?.content).toBe('默认')
    expect(model.grid[1][0][0].inherited).toBe(true)
  })

  it('更具体(条件多)的链赢过泛化链，与 resolve 同序', () => {
    const answers = [
      makeAnswer({ id: 1, coord: { tenant: 'A' }, content: '只有租户', effective_time: '2026-08-01' }),
      makeAnswer({ id: 2, coord: { tenant: 'A', region: '北' }, content: '租户+地区', effective_time: '2026-08-01' }),
    ]
    const model = buildCubeModel(answers, dims, 'tenant', 'region')
    // 北层 A 行：两条链都兼容，spec 高者(租户+地区)赢
    expect(model.grid[1][1][0].answer?.content).toBe('租户+地区')
  })

  it('挂在其他维度上的答案计入 offAxisCount 且不进格子', () => {
    const answers = [
      makeAnswer({ id: 1, coord: { channel: '电话' }, content: '渠道答案', effective_time: '2026-08-01' }),
      makeAnswer({ id: 2, coord: { tenant: 'A' }, content: 'A', effective_time: '2026-08-01' }),
    ]
    const model = buildCubeModel(answers, dims, 'tenant', null)
    expect(model.offAxisCount).toBe(1)
    expect(model.grid[0][1][0].answer?.content).toBe('A')
  })

  it('时间列超过 5 个只保留最近 5 个', () => {
    const answers = ['01', '02', '03', '04', '05', '06'].map((d, i) =>
      makeAnswer({ id: i + 1, coord: {}, effective_time: `2026-08-${d}`, created_at: `2026-08-${d}T00:00:00` }),
    )
    const model = buildCubeModel(answers, dims, 'tenant', null)
    expect(model.times).toEqual(['2026-08-02', '2026-08-03', '2026-08-04', '2026-08-05', '2026-08-06'])
  })

  it('图例按链去重收集', () => {
    const answers = [
      makeAnswer({ id: 1, coord: {}, content: '默认', effective_time: '2026-08-01' }),
      makeAnswer({ id: 2, coord: { tenant: 'A' }, content: 'A', effective_time: '2026-08-01' }),
    ]
    const model = buildCubeModel(answers, dims, 'tenant', null)
    expect(model.legend.size).toBe(2)
  })
})
