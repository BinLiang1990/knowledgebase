/**
 * 知识点（字段镜像 backend/src/kb_backend/schemas/knowledge_point.py）。
 * React 版本里围绕 TanStack Query 缓存失效的整套逻辑（失效前缀、全局留痕
 * 联动失效等）随迁移移除：Vue 版页面挂载即取数、变更后由页面显式 reload，
 * 不存在跨页缓存可失效。
 */
import type { Answer } from './answer'
import type { FilterValue } from '@/utils/dimension'
import { request } from '@/utils/request'

export type ResolveStatus = 'exact' | 'weighted' | 'default' | 'fallback-latest' | 'none'

export interface Resolved {
  status: ResolveStatus
  answer: Answer | null
}

/** 单查 GET /{kp_id} 返回的形状（issue #8），列表行在其上加 resolved */
export interface KnowledgePointDetail {
  id: number
  knowledge_base_id: number
  title: string
  status: 'active' | 'deleted'
  operator: string
  active_answer_count: number
  created_at: string
  updated_at: string
  deleted_at: string | null
  delete_reason: string | null
}

/** 列表行：加上 resolve 引擎附加的 resolved（resolve-engine 设计文档 §4.2） */
export interface KnowledgePoint extends KnowledgePointDetail {
  resolved: Resolved
}

/** 条件组（AnswerGroupOut） */
export interface AnswerGroup {
  coord: Record<string, string | number | boolean>
  revoked: boolean
  version_count: number
  latest_answer: Answer
  live_answer: Answer | null
}

export interface KnowledgePointFilters {
  keyword?: string
  at?: string
  coord?: Record<string, FilterValue>
}

export interface CreateKnowledgePointInput {
  title: string
  default_answer?: { content: string, effective_time: string }
}

/** 知识点列表（带关键词/时间/坐标过滤，含每行的 resolved 预览） */
export function listKnowledgePoints(kbId: number, filters: KnowledgePointFilters) {
  const params: Record<string, string> = {}
  if (filters.keyword)
    params.keyword = filters.keyword
  if (filters.at)
    params.at = filters.at
  if (filters.coord && Object.keys(filters.coord).length > 0)
    params.coord = JSON.stringify(filters.coord)
  return request.get<KnowledgePoint[]>(`/knowledge-bases/${kbId}/knowledge-points`, { params })
}

/**
 * 条件组列表。`at` 省略（而不是传前端算的今天）即「最新」模式——让后端每次
 * 用它自己的当前日期，页面跨本地零点放着不动也不会一直查昨天（PR #23）。
 */
export function listAnswerGroups(kbId: number, kpId: number, at?: string) {
  return request.get<AnswerGroup[]>(
    `/knowledge-bases/${kbId}/knowledge-points/${kpId}/answer-groups`,
    { params: at ? { at } : undefined },
  )
}

/** 知识点单查（issue #8） */
export function getKnowledgePoint(kbId: number, kpId: number) {
  return request.get<KnowledgePointDetail>(`/knowledge-bases/${kbId}/knowledge-points/${kpId}`)
}

/**
 * 每个版本、每个条件组、不过滤（issue #14 设计文档 §1）——「版本历史」tab 的
 * 数据源。刻意不用 answer-groups（那是服务端分组汇总过的）：时间线需要
 * 逐版本原始行，见设计文档 §4.1。
 */
export function listAllAnswers(kbId: number, kpId: number) {
  return request.get<Answer[]>(`/knowledge-bases/${kbId}/knowledge-points/${kpId}/answers`)
}

/** 新增知识点（可携带默认答案） */
export function createKnowledgePoint(kbId: number, input: CreateKnowledgePointInput) {
  return request.post<KnowledgePoint>(`/knowledge-bases/${kbId}/knowledge-points`, input)
}

/** 改标题 */
export function updateKnowledgePointTitle(kbId: number, kpId: number, title: string) {
  return request.patch<KnowledgePointDetail>(`/knowledge-bases/${kbId}/knowledge-points/${kpId}`, { title })
}

/** 软删除知识点（原因必填，写入留痕） */
export function deleteKnowledgePoint(kbId: number, kpId: number, deleteReason: string) {
  return request.post<KnowledgePoint>(`/knowledge-bases/${kbId}/knowledge-points/${kpId}/delete`, {
    delete_reason: deleteReason,
  })
}
