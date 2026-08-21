/**
 * 变更留痕（字段镜像 backend/src/kb_backend/schemas/change_log.py）。
 */
import { request } from '@/utils/request'

export interface ChangeLogEntry {
  time: string
  knowledge_point_id: number
  answer_id: number
  operator: string
  action: 'create' | 'edit' | 'revoke' | 'reactivate'
  coord: Record<string, string | number | boolean>
  before_content: string | null
  after_content: string | null
  /** 数据来源（产生方式）：人工填报 / AI生成 / 批量导入 */
  source: string
  /** 操作系统（写入方系统编码）：tyzsk = 本系统，其他为外部系统编码 */
  source_system: string
  revoke_reason: string | null
  /** reactivated 只出现在撤回条目上：这次撤回后来被恢复、已不再生效（issue #32） */
  status: 'live' | 'superseded' | 'revoked' | 'reactivated'
  revocable: boolean
  reactivate_reason: string | null
}

/** 全局端点在同样字段之上内联的三个定位列（issue #14 设计文档 §4.4） */
export interface GlobalChangeLogEntry extends ChangeLogEntry {
  knowledge_base_id: number
  knowledge_base_name: string
  knowledge_point_title: string
}

export const ACTION_LABEL: Record<ChangeLogEntry['action'], string> = {
  create: '写答案',
  edit: '改答案',
  revoke: '撤回答案',
  reactivate: '恢复答案',
}

export const CHANGE_LOG_STATUS_LABEL: Record<ChangeLogEntry['status'], string> = {
  live: '生效',
  superseded: '已被新版替代',
  revoked: '已撤回',
  reactivated: '已恢复',
}

/** 单个知识点的变更留痕 */
export function listChangeLog(kbId: number, kpId: number) {
  return request.get<ChangeLogEntry[]>(`/knowledge-bases/${kbId}/knowledge-points/${kpId}/change-log`)
}

/** 跨全部知识库的全量变更留痕 */
export function listGlobalChangeLog() {
  return request.get<GlobalChangeLogEntry[]>('/change-log')
}
