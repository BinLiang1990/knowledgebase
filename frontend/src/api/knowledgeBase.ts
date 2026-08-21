/**
 * 知识库管理（对接契约见 docs/PRD.md §4.10；字段镜像
 * backend/src/kb_backend/schemas/knowledge_base.py::KnowledgeBaseOut）。
 */
import { request } from '@/utils/request'

export interface KnowledgeBase {
  id: number
  name: string
  description: string | null
  status: 'active' | 'deprecated'
  active_knowledge_point_count: number
  /** 所属分类（PRD §4.11）：两者皆 null = 未分类 */
  category_id: number | null
  category_name: string | null
  created_at: string
  updated_at: string
}

/** 回收站条目：在 KnowledgeBase 之上补删除留痕（status 恒为 deprecated） */
export interface KnowledgeBaseRecycleItem extends KnowledgeBase {
  deleted_at: string
  deleted_by: string | null
}

export interface KnowledgeBaseInput {
  name: string
  description?: string
  /** 所属分类：null = 未分类。编辑时始终显式传（后端区分「未传」与「传 null」） */
  category_id?: number | null
}

export interface KnowledgeBaseCreateInput extends KnowledgeBaseInput {
  /** 创建时直接启用的维度 key（可选）——省去建库后再去「知识库设置」勾选 */
  enabled_dimension_keys?: string[]
}

/**
 * 知识库全量列表（不分页，data 为数组）。供「按 id 找库名」「选择启用中
 * 的库」这类需要全集的场景（详情页/设置页/加关联弹窗）；列表页的过滤与
 * 分页改走下面的 pageKnowledgeBases（2026-08-21 从前端内存过滤改为服务端）。
 */
export function listKnowledgeBases() {
  return request.get<KnowledgeBase[]>('/knowledge-bases')
}

export interface KnowledgeBasePageQuery {
  page: number
  page_size: number
  /** 名称或描述包含（服务端大小写不敏感） */
  keyword?: string
  /** 按分类过滤，语义固定为「该分类及其全部子孙」；与 uncategorized 互斥 */
  category_id?: number
  /** 仅未分类 */
  uncategorized?: boolean
  status?: 'active' | 'deprecated'
}

export interface KnowledgeBasePage {
  list: KnowledgeBase[]
  total: number
  page: number
  page_size: number
  /** 分类树虚拟节点的全局计数（与过滤条件无关），随分页响应带回省一次请求 */
  summary: {
    /** 启用中知识库总数（「全部」节点） */
    active_total: number
    /** 未分类的启用中知识库数（「未分类」节点） */
    active_uncategorized: number
  }
}

/** 知识库分页列表：分类/关键词/状态过滤与分页全部在服务端完成 */
export function pageKnowledgeBases(query: KnowledgeBasePageQuery) {
  return request.get<KnowledgeBasePage>('/knowledge-bases', { params: query })
}

/** 新增知识库（可同时启用维度，与建库同一事务） */
export function createKnowledgeBase(input: KnowledgeBaseCreateInput) {
  return request.post<KnowledgeBase>('/knowledge-bases', input)
}

/** 编辑知识库名称/描述 */
export function updateKnowledgeBase(id: number, input: KnowledgeBaseInput) {
  return request.patch<KnowledgeBase>(`/knowledge-bases/${id}`, input)
}

/** 启用/停用知识库 */
export function setKnowledgeBaseStatus(id: number, status: 'active' | 'deprecated') {
  return request.post<KnowledgeBase>(`/knowledge-bases/${id}/${status === 'active' ? 'activate' : 'deactivate'}`)
}

/** 删除知识库（进回收站）——仅允许已停用的库，后端强校验 */
export function deleteKnowledgeBase(id: number) {
  return request.post<KnowledgeBaseRecycleItem>(`/knowledge-bases/${id}/delete`)
}

/** 回收站列表（最近删除的在前） */
export function listRecycleBin() {
  return request.get<KnowledgeBaseRecycleItem[]>('/knowledge-bases/recycle-bin')
}

/** 从回收站还原（回到「已停用」状态） */
export function restoreKnowledgeBase(id: number) {
  return request.post<KnowledgeBase>(`/knowledge-bases/${id}/restore`)
}

/** 回收站内彻底删除——后端实现仍为软删（数据保留），但界面上不可再还原 */
export function purgeKnowledgeBase(id: number) {
  return request.post(`/knowledge-bases/${id}/purge`)
}
