import { describe, expect, it } from 'vitest'
import { makeDimension } from '@/test/factories'
import { coordGroupKey, coordValueEquals, describeCoord, diffCoord } from './coord'

describe('coordGroupKey', () => {
  it('只改答案 id 的编辑前后保持不变（PR #24 终审修复）', () => {
    // 用 latest_answer.id 当列表 key 会把每次编辑都当成全新行——追加新版本
    // 意味着新的 answer id
    expect(coordGroupKey({ tenant: 'acme' })).toBe(coordGroupKey({ tenant: 'acme' }))
  })

  it('对真正不同的 coord 产生不同 key', () => {
    expect(coordGroupKey({ tenant: 'acme' })).not.toBe(coordGroupKey({ tenant: 'other' }))
    expect(coordGroupKey({})).not.toBe(coordGroupKey({ tenant: 'acme' }))
  })

  it('与键的插入顺序无关', () => {
    expect(coordGroupKey({ a: '1', b: '2' })).toBe(coordGroupKey({ b: '2', a: '1' }))
  })
})

describe('describeCoord', () => {
  it('描述默认（空）coord', () => {
    expect(describeCoord({}, [])).toBe('默认答案 · 处处适用')
  })

  it('单条件用维度 label 描述', () => {
    const dims = [makeDimension({ key: 'tenant', label: '租户' })]
    expect(describeCoord({ tenant: 'acme' }, dims)).toBe('适用条件：租户 = acme')
  })

  it('未知维度（如已停用）回退原 key', () => {
    expect(describeCoord({ ghost: 'x' }, [])).toBe('适用条件：ghost = x')
  })
})

describe('coordValueEquals', () => {
  it('number 型按数值比较，与字符串格式无关', () => {
    expect(coordValueEquals('number', 5, '5')).toBe(true)
    expect(coordValueEquals('number', 1.5, '1.50')).toBe(true)
    expect(coordValueEquals('number', 1, '2')).toBe(false)
  })

  it('boolean 型按布尔值比较', () => {
    expect(coordValueEquals('boolean', true, true)).toBe(true)
    expect(coordValueEquals('boolean', true, false)).toBe(false)
  })

  it('字符串 "false" 按 false 处理而非真值化（PR #24 终审修复）', () => {
    // Boolean('false') 是 true——非空字符串都是真值——朴素的
    // Boolean(a) === Boolean(b) 会把语义相同的值误报为不同
    expect(coordValueEquals('boolean', false, 'false')).toBe(true)
    expect(coordValueEquals('boolean', true, 'true')).toBe(true)
    expect(coordValueEquals('boolean', false, 'true')).toBe(false)
  })

  it('text/date 与未知 field_type 按字符串比较', () => {
    expect(coordValueEquals('text', 'acme', 'acme')).toBe(true)
    expect(coordValueEquals('date', '2026-01-01', '2026-01-01')).toBe(true)
    expect(coordValueEquals(undefined, 'x', 'x')).toBe(true)
    expect(coordValueEquals(undefined, 'x', 'y')).toBe(false)
  })

  it('区分超出 Number 精度的大整数而不是折叠它们（PR #24 Codex 修复）', () => {
    // Number(a) === Number(b) 会把这两个不同的、后端支持的整数折叠到同一个
    // double（9007199254740992）——2**53 本身可被精确表示，所以这不是被测试
    // 自己的 JS 字面量先揉坏的值
    expect(coordValueEquals('number', 9007199254740992, '9007199254740993')).toBe(false)
    expect(coordValueEquals('number', 9007199254740992, '9007199254740992')).toBe(true)
    // 两侧都是精确数字串（经 toFilterValue 提交时的形态）时任意远超 2**53 仍精确
    expect(coordValueEquals('number', '18446744073709551615', '18446744073709551615')).toBe(true)
    expect(coordValueEquals('number', '18446744073709551615', '18446744073709551614')).toBe(false)
  })
})

describe('diffCoord', () => {
  const dims = [
    makeDimension({ key: 'priority', field_type: 'number' }),
    makeDimension({ key: 'tenant', field_type: 'text' }),
  ]

  it('完全相同的 coord 为 false', () => {
    expect(diffCoord({ tenant: 'acme' }, { tenant: 'acme' }, dims)).toBe(false)
  })

  it('number 值仅字符串格式不同为 false', () => {
    expect(diffCoord({ priority: 5 }, { priority: '5' }, dims)).toBe(false)
  })

  it('值真的变了为 true', () => {
    expect(diffCoord({ tenant: 'acme' }, { tenant: 'other' }, dims)).toBe(true)
  })

  it('键集合变了为 true', () => {
    expect(diffCoord({ tenant: 'acme' }, { tenant: 'acme', priority: '1' }, dims)).toBe(true)
    expect(diffCoord({ tenant: 'acme', priority: '1' }, { tenant: 'acme' }, dims)).toBe(true)
  })
})
