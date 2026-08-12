/**
 * 答案关联（字段镜像 backend/src/kb_backend/schemas/relation.py）。
 * 关联本身跨知识库：查询/发起分析挂在知识点下，增删改与任务进度是全局路由
 * （docs/PRD-答案关联.md §3.3/§3.4）。
 */
import { request } from '@/utils/request'

export type RelationEndpointState = 'ok' | 'revoked' | 'kp-deleted' | 'missing'

export interface RelationEndpoint {
  kb_id: number
  kp_id: number
  coord_hash: string
  coord: Record<string, string | number | boolean>
  kb_name: string | null
  kp_title: string | null
  state: RelationEndpointState
  current_content_preview: string | null
}

export interface AnswerRelation {
  id: number
  a: RelationEndpoint
  b: RelationEndpoint
  description: string
  source: 'ai' | 'manual'
  similarity: number | null
  model: string | null
  operator: string
  /** 任一端当前生效内容与生成时不一致（服务端动态推导） */
  stale: boolean
  /** 手动添加时选择 AI 生成、描述尚未产出 */
  generating: boolean
  created_at: string
  updated_at: string
}

export type GenerationStatus = 'disabled' | 'generating' | 'pending' | 'idle'

export interface RelationsData {
  generation_status: GenerationStatus
  relations: AnswerRelation[]
}

export interface RelationTask {
  id: number
  kind: 'analyze' | 'generate_pair'
  status: 'pending' | 'generating' | 'done' | 'failed'
  phase: string | null
  progress_done: number
  progress_total: number
  retry_count: number
  last_error: string | null
}

export interface EndpointRefInput {
  kb_id: number
  kp_id: number
  coord_hash: string
}

export interface CreateRelationInput {
  a: EndpointRefInput
  b: EndpointRefInput
  /** 留空 + generate=true：由 AI 异步生成描述 */
  description?: string
  generate?: boolean
}

/** 该知识点的全部关联（任一端属于该知识点即返回，两端对称可见） */
export function listRelations(kbId: number, kpId: number, options?: { coordHash?: string, silent?: boolean }) {
  return request.get<RelationsData>(
    `/knowledge-bases/${kbId}/knowledge-points/${kpId}/answer-relations`,
    {
      params: options?.coordHash ? { coord_hash: options.coordHash } : undefined,
      // 轮询走静默：分析进行中每几秒刷一次，失败不该连环弹错误提示
      silent: options?.silent,
    },
  )
}

/**
 * 发起分析：coordHash 给定 = 单条答案；省略 = 知识点级自动关联
 * （全部有效链逐条在所有知识库中召回，PRD §3.1）。
 */
export function analyzeRelations(kbId: number, kpId: number, coordHash?: string) {
  return request.post<{ task_id: number, status: string }>(
    `/knowledge-bases/${kbId}/knowledge-points/${kpId}/answer-relations/analyze`,
    { coord_hash: coordHash ?? null },
  )
}

/** 手动添加关联（描述留空 + generate=true 时返回 task_id） */
export function createRelation(input: CreateRelationInput) {
  return request.post<{ relation_id: number, task_id: number | null }>('/answer-relations', input)
}

/** 人工改写描述——改写后 source 转 manual，后续 AI 分析不再覆盖 */
export function updateRelationDescription(relationId: number, description: string) {
  return request.patch<{ relation_id: number }>(`/answer-relations/${relationId}`, { description })
}

/** 单对重新生成（重新生成即接受 AI 内容，source 转回 ai） */
export function regenerateRelation(relationId: number) {
  return request.post<{ task_id: number, status: string }>(`/answer-relations/${relationId}/regenerate`)
}

export function deleteRelation(relationId: number) {
  return request.delete<Record<string, never>>(`/answer-relations/${relationId}`)
}

export function getRelationTask(taskId: number) {
  return request.get<RelationTask>(`/answer-relations/tasks/${taskId}`, { silent: true })
}
