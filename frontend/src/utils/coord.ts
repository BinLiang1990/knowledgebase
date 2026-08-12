import type { FilterValue } from './dimension'
/**
 * 维度坐标（coord）的比较与展示纯函数。
 * 迁移自 React 版 api/answers.ts——这里的每一条比较规则都对应过一次真实
 * 评审发现（PR #24/#30），改动前先读函数注释。
 */
import type { Dimension } from '@/api/dimension'

/**
 * 设计文档 §4.3：原始 coord 值（answer-groups 返回的 JSON 值）与 CoordEditor
 * 草稿值（toFilterValue 产出）是不对称的——number 一侧是 JSON 数字、另一侧是
 * 保精度字符串。按原始字符串比较会产生假「已变更」（如 "1.50" vs 1.5）。
 * 在 `dimensions` 里找不到的 key（锁定/已停用行）回退 String() 比较，锁定行
 * 总是原样回显原值，所以这里是精确的。
 */
export function coordValueEquals(fieldType: Dimension['field_type'] | undefined, a: unknown, b: unknown): boolean {
  if (fieldType === 'number')
    return numbersEqual(a, b)
  // Boolean('false') 是 true（非空字符串都为真值），所以不能靠 JS 真值化：
  // coordValueEquals('boolean', false, 'false') 曾因此误报不相等（PR #24 终审）。
  if (fieldType === 'boolean')
    return normalizeBoolean(a) === normalizeBoolean(b)
  return String(a) === String(b)
}

function normalizeBoolean(v: unknown): boolean {
  if (typeof v === 'string')
    return v === 'true'
  return Boolean(v)
}

/**
 * coord.py 接受到 uint64 范围的精确整数，远超 2^53——`Number(a) === Number(b)`
 * 会把不同的大整数折叠到同一个 double（如 9007199254740992 与
 * "9007199254740993"），导致只改了大数值条件的编辑被误判为「未变更」而整个
 * 略去 coord（设计文档 §4.4）。两侧都是纯整数时用 BigInt 精确比较；小数回退
 * Number（本应用的小数精度不超出 double 范围）。Codex 评审结论，PR #24。
 */
function numbersEqual(a: unknown, b: unknown): boolean {
  const sa = String(a)
  const sb = String(b)
  if (sa === sb)
    return true
  const isPlainInt = (s: string) => /^-?\d+$/.test(s)
  if (isPlainInt(sa) && isPlainInt(sb)) {
    try {
      return BigInt(sa) === BigInt(sb)
    }
    catch {
      // 正则已保证可解析，此分支理论不可达——兜底走下方浮点比较
    }
  }
  return Number(a) === Number(b)
}

/**
 * `current` 相对 `original` 是否发生了后端 is_migration 判定意义上的变化
 * （设计文档 §4.3/§4.4）——key 集合变了，或任一共有 key 的值按其
 * field_type 比较规则变了。
 */
export function diffCoord(
  original: Record<string, FilterValue>,
  current: Record<string, FilterValue>,
  dimensions: Dimension[],
): boolean {
  const originalKeys = Object.keys(original)
  const currentKeys = Object.keys(current)
  if (originalKeys.length !== currentKeys.length)
    return true
  for (const key of originalKeys) {
    if (!(key in current))
      return true
    const fieldType = dimensions.find(d => d.key === key)?.field_type
    if (!coordValueEquals(fieldType, original[key], current[key]))
      return true
  }
  return false
}

/** 把 coord 描述成人类可读的「适用条件：xx = yy 且 …」；空 coord 即默认答案 */
export function describeCoord(coord: Record<string, unknown>, dimensions: Dimension[]): string {
  const keys = Object.keys(coord)
  if (!keys.length)
    return '默认答案 · 处处适用'
  const parts = keys
    .sort()
    .map(k => `${dimensions.find(d => d.key === k)?.label ?? k} = ${String(coord[k])}`)
  return `适用条件：${parts.join(' 且 ')}`
}

/**
 * 条件组跨编辑稳定的身份标识（列表渲染 key 用）——latest_answer.id 每追加一版
 * 就变，会让渲染层把编辑过的行当成全新元素（丢 DOM 状态、重挂载闪烁）。
 * 注意：仅用作列表 key。需要按组归并数据时必须用服务端的 coord_hash——本编码
 * 对含 ":"/"|" 的文本值有歧义碰撞（见 utils/timeline.ts 的注释，PR #30）。
 */
export function coordGroupKey(coord: Record<string, unknown>): string {
  const keys = Object.keys(coord).sort()
  return keys.length ? keys.map(k => `${k}:${String(coord[k])}`).join('|') : '(默认)'
}
