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
 * 知识库全量列表——该接口没有关键词/分页参数，搜索与分页在前端内存中做
 * （设计文档 §5）：数据量撑不起服务端过滤，且与 demo 的客户端做法对齐。
 */
export function listKnowledgeBases() {
  return request.get<KnowledgeBase[]>('/knowledge-bases')
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
