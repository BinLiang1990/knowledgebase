/**
 * 写答案弹窗「适用条件」行的编辑模型与换算纯函数（仅详情页使用）。
 */
import type { Dimension } from '@/api/dimension'
import type { Filters, FilterValue } from '@/utils/dimension'
import { toFilterValue } from '@/utils/dimension'

/**
 * `locked` 非空表示该行的 coord key 已不在当前 `dimensions` 列表里（全局停用
 * 或本库禁用，设计文档 §4.2）：渲染为只读，重建 coord 时始终原样带上原值，
 * 不经过 toFilterValue。
 */
export interface CoordRow {
  key: string
  raw: string
  locked?: FilterValue
}

/**
 * 注意 `value` 到这里时可能已经丢过精度：迁移到 json-bigint 后超出安全范围的
 * 整数会以字符串到达（旧 React 版 fetch+JSON.parse 的已知缺陷已修复），
 * String(value) 是安全的。
 */
export function coordRowsFromCoord(coord: Record<string, FilterValue>, dimensions: Dimension[]): CoordRow[] {
  return Object.entries(coord).map(([key, value]) => {
    const dim = dimensions.find(d => d.key === key)
    if (!dim)
      return { key, raw: '', locked: value }
    return { key, raw: String(value) }
  })
}

export function hasLockedRow(rows: CoordRow[]): boolean {
  return rows.some(r => r.locked !== undefined)
}

export interface CoordRowsResult {
  coord?: Filters
  error?: string
}

/**
 * 行 → coord。沿用 issue #7 评审确立的空白拒绝纪律：选了维度但值为空/纯空白
 * 的行直接报错，而不是静默丢弃或提交 ""。
 */
export function coordRowsToCoord(rows: CoordRow[], dimensions: Dimension[]): CoordRowsResult {
  const coord: Filters = {}
  for (const row of rows) {
    if (row.locked !== undefined) {
      coord[row.key] = row.locked
      continue
    }
    const dim = dimensions.find(d => d.key === row.key)
    if (!dim)
      return { error: '请为每一行选择维度' }
    const trimmed = row.raw.trim()
    if (!trimmed)
      return { error: `「${dim.label}」不能为空` }
    coord[row.key] = toFilterValue(dim.field_type, trimmed)
  }
  return { coord }
}
