/**
 * 维度取值的类型转换与展示规则。ConditionPicker（查询条件）、CoordEditor
 * （答案条件）、维度管理页共用——issue #7 的评审曾抓到过只存在于其中一份
 * 拷贝里的 trim bug，此后这套规则必须唯一（issue #8 设计文档 §4.2）。
 */
import type { Dimension } from '@/api/dimension'

/** 维度坐标/筛选值：number 型条件在提交侧是保精度字符串（issue #7） */
export type FilterValue = string | number | boolean
export type Filters = Record<string, FilterValue>

/** 字段类型的中文标签（维度管理页、知识库设置页、条件选择器共用） */
export const FIELD_TYPE_LABEL: Record<Dimension['field_type'], string> = {
  text: '文本',
  number: '数值',
  date: '时间',
  boolean: '布尔',
}

/** 按维度字段类型展示取值（boolean 显示 是/否） */
export function displayValue(dim: Dimension | undefined, value: FilterValue): string {
  if (dim?.field_type === 'boolean')
    return value ? '是' : '否'
  return String(value)
}

/**
 * coord.py 的 field_type 解析约定：boolean 必须提交真正的 JSON 布尔值，
 * 而不是 <select> 给出的字符串；number 保持字符串原样，让后端基于 Decimal
 * 的解析器拿到精确数字，而不是经 JS Number 往返丢过精度的值。
 */
export function toFilterValue(fieldType: Dimension['field_type'], raw: string): FilterValue {
  if (fieldType === 'boolean')
    return raw === 'true'
  return raw
}
