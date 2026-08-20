/**
 * 维度管理（字段镜像 backend/src/kb_backend/schemas/dimension.py）。
 * 维度定义全局共享；每个知识库单独「启用」后才能在该库的答案条件里使用。
 */
import { request } from '@/utils/request'

/** 对外（启用中）维度：DimensionOut */
export interface Dimension {
  key: string
  label: string
  field_type: 'text' | 'number' | 'date' | 'boolean'
  weight: number
}

/** 管理侧维度：DimensionAdminOut——不分状态，含对外视图刻意省略的字段 */
export interface AdminDimension extends Dimension {
  default_value: string | null
  status: 'active' | 'deprecated'
  answer_count: number
}

/**
 * 与 DimensionUpdateInput 结构上分开，镜像后端 DimensionCreate/DimensionUpdate
 * 的拆分——DimensionUpdate 根本没有 field_type 字段（设计文档 §3.2，issue #13），
 * 不是「送了会被拒」而是不存在。
 */
export interface DimensionCreateInput {
  label: string
  field_type: Dimension['field_type']
  weight: number
  default_value: string | null
}

export interface DimensionUpdateInput {
  label: string
  weight: number
  /**
   * 永远显式发送、从不省略——null 表示「清空」，非空字符串表示「设为该值」。
   * 整个省略这个 key 会被后端基于 model_fields_set 的逻辑理解为「保持不变」，
   * 用户刚清空的场景会静默不生效（设计文档 §4.2，issue #13）。
   */
  default_value: string | null
}

/** 某知识库已启用的维度（6.x /knowledge-bases/{id}/enabled-dimensions） */
export function listEnabledDimensions(kbId: number) {
  return request.get<Dimension[]>(`/knowledge-bases/${kbId}/enabled-dimensions`)
}

/**
 * 某维度在该知识库现存答案条件里出现过的全部取值（条件选择器的下拉候选，
 * 仅对 text 维度调用）。dimension_key 走 axios params 自动编码——维度 key
 * 是任意文本，裸拼 URL 的坑同 updateDimension 注释。silent：候选只是输入
 * 辅助，拉取失败不弹全局错误提示，由选择器内联降级为纯手输。
 */
export function listDimensionValues(kbId: number, dimensionKey: string) {
  return request.get<string[]>(`/knowledge-bases/${kbId}/dimension-values`, {
    params: { dimension_key: dimensionKey },
    silent: true,
  })
}

/** 管理侧维度全量列表（含已停用） */
export function listAdminDimensions() {
  return request.get<AdminDimension[]>('/admin/dimensions')
}

/** 新增全局维度 */
export function createDimension(input: DimensionCreateInput) {
  return request.post<AdminDimension>('/dimensions', input)
}

/**
 * 编辑全局维度。encodeURIComponent(key)：维度 key 是用户输入的 label 原文
 * （后端只拒绝其中的 "/"，设计文档 §4.3），"?"/"#"/"&" 都合法，裸拼进 URL
 * 会被解析成查询串/片段，静默打到错误资源（Codex 结论，PR #29）。
 */
export function updateDimension(key: string, input: DimensionUpdateInput) {
  return request.patch<AdminDimension>(`/dimensions/${encodeURIComponent(key)}`, input)
}

/** 启用/停用全局维度 */
export function setDimensionStatus(key: string, status: 'active' | 'deprecated') {
  return request.post<AdminDimension>(
    `/dimensions/${encodeURIComponent(key)}/${status === 'active' ? 'activate' : 'deactivate'}`,
  )
}

/** 整体设置某知识库启用的维度集合 */
export function setEnabledDimensions(kbId: number, dimensionKeys: string[]) {
  return request.put<Dimension[]>(`/knowledge-bases/${kbId}/enabled-dimensions`, { dimension_keys: dimensionKeys })
}
