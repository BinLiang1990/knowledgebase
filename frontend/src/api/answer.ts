/**
 * 答案（字段镜像 backend/src/kb_backend/schemas/knowledge_point.py::AnswerOut）。
 * 参数清洗（trim、空转 undefined）由调用方页面在提交前完成后传入。
 */
import type { FilterValue } from '@/utils/dimension'
import { request } from '@/utils/request'

export interface Answer {
  id: number
  knowledge_base_id: number
  knowledge_point_id: number
  coord: Record<string, string | number | boolean>
  coord_hash: string
  content: string
  effective_time: string
  operator: string
  /** 数据来源（产生方式）：人工填报 / AI生成 / 批量导入 */
  source: string
  /** 操作系统（写入方系统编码）：tyzsk = 本系统，其他为外部系统编码 */
  source_system: string
  note: string | null
  revoked: boolean
  revoked_at: string | null
  revoked_by: string | null
  revoke_reason: string | null
  reactivated_at: string | null
  reactivated_by: string | null
  reactivate_reason: string | null
  created_at: string
}

export interface CreateAnswerInput {
  coord: Record<string, FilterValue>
  content: string
  effective_time: string
  note?: string
  /** issue #32：目标条件组合当前是撤回态时必填——写入即整链恢复 + 追加新版本 */
  reactivate_reason?: string
}

export interface EditAnswerInput {
  content: string
  effective_time: string
  note?: string
  /**
   * 设计文档 §4.4：条件没动过时整个省略（连原值都不发），让后端走
   * 「原样复用目标 coord、跳过重校验」的路径——这条路径是「答案自身 coord
   * 引用了已停用维度时仍能编辑内容/时间」得以成立的原因。
   */
  coord?: Record<string, FilterValue>
  migration_reason?: string
  /** issue #32：编辑落点的链（迁移后的新条件或原条件本身）是撤回态时必填 */
  reactivate_reason?: string
}

/** 写一条答案（4.x） */
export function createAnswer(kbId: number, kpId: number, input: CreateAnswerInput) {
  return request.post<Answer>(`/knowledge-bases/${kbId}/knowledge-points/${kpId}/answers`, input)
}

/** 编辑答案（同组追加新版本；coord 变更即迁移） */
export function editAnswer(kbId: number, kpId: number, answerId: number, input: EditAnswerInput) {
  return request.post<Answer>(`/knowledge-bases/${kbId}/knowledge-points/${kpId}/answers/${answerId}/edit`, input)
}

/** 撤回答案（逻辑删除，历史与留痕永久保留） */
export function revokeAnswer(kbId: number, kpId: number, answerId: number, revokeReason: string) {
  return request.post<Answer>(`/knowledge-bases/${kbId}/knowledge-points/${kpId}/answers/${answerId}/revoke`, {
    revoke_reason: revokeReason,
  })
}
