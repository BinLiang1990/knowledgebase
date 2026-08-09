import { useQuery } from '@tanstack/react-query';
import { apiClient } from './client';
import { knowledgePointDataKeyPrefix } from './knowledgePoints';

// Mirrors backend/src/kb_backend/schemas/change_log.py::ChangeLogEntryOut.
export interface ChangeLogEntry {
  time: string;
  knowledge_point_id: number;
  answer_id: number;
  operator: string;
  action: 'create' | 'edit' | 'revoke';
  coord: Record<string, string | number | boolean>;
  before_content: string | null;
  after_content: string | null;
  source: string;
  revoke_reason: string | null;
  status: 'live' | 'superseded' | 'revoked';
  revocable: boolean;
}

// Mirrors GlobalChangeLogEntryOut — the same fields plus the three
// location columns only the global endpoint inlines (design doc §4.4).
export interface GlobalChangeLogEntry extends ChangeLogEntry {
  knowledge_base_id: number;
  knowledge_base_name: string;
  knowledge_point_title: string;
}

export const ACTION_LABEL: Record<ChangeLogEntry['action'], string> = {
  create: '写答案',
  edit: '改答案',
  revoke: '撤回答案',
};

export const CHANGE_LOG_STATUS_LABEL: Record<ChangeLogEntry['status'], string> = {
  live: '生效',
  superseded: '已被新版替代',
  revoked: '已撤回',
};

export function useChangeLog(kbId: number, kpId: number, enabled: boolean) {
  return useQuery({
    queryKey: [...knowledgePointDataKeyPrefix(kbId), kpId, 'change-log'] as const,
    queryFn: ({ signal }) =>
      apiClient.get<ChangeLogEntry[]>(`/knowledge-bases/${kbId}/knowledge-points/${kpId}/change-log`, { signal }),
    enabled,
  });
}

export const GLOBAL_CHANGE_LOG_KEY = ['change-log'] as const;

export function useGlobalChangeLog() {
  return useQuery({
    queryKey: GLOBAL_CHANGE_LOG_KEY,
    queryFn: ({ signal }) => apiClient.get<GlobalChangeLogEntry[]>('/change-log', { signal }),
  });
}
