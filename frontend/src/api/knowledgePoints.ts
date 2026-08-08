import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from './client';
import type { Answer } from './answers';
import { KNOWLEDGE_BASES_KEY } from './knowledgeBases';

export type ResolveStatus = 'exact' | 'weighted' | 'default' | 'fallback-latest' | 'none';

export interface Resolved {
  status: ResolveStatus;
  answer: Answer | null;
}

// Mirrors backend/src/kb_backend/schemas/knowledge_point.py::KnowledgePointOut,
// plus the additive `resolved` field the list endpoint attaches per row
// (docs/specs/2026-08-08-resolve-engine-design.md §4.2).
export interface KnowledgePoint {
  id: number;
  knowledge_base_id: number;
  title: string;
  status: 'active' | 'deleted';
  operator: string;
  active_answer_count: number;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
  delete_reason: string | null;
  resolved: Resolved;
}

// Mirrors backend/src/kb_backend/schemas/knowledge_point.py::AnswerGroupOut.
export interface AnswerGroup {
  coord: Record<string, string | number | boolean>;
  revoked: boolean;
  version_count: number;
  latest_answer: Answer;
  live_answer: Answer | null;
}

export interface KnowledgePointFilters {
  keyword?: string;
  at?: string;
  coord?: Record<string, string | number | boolean>;
}

function buildKnowledgePointsQuery(filters: KnowledgePointFilters): string {
  const params = new URLSearchParams();
  if (filters.keyword) params.set('keyword', filters.keyword);
  if (filters.at) params.set('at', filters.at);
  if (filters.coord && Object.keys(filters.coord).length > 0) {
    params.set('coord', JSON.stringify(filters.coord));
  }
  const query = params.toString();
  return query ? `?${query}` : '';
}

function knowledgePointsKey(kbId: number, filters: KnowledgePointFilters) {
  return ['knowledge-bases', kbId, 'knowledge-points', filters] as const;
}

export function useKnowledgePoints(kbId: number, filters: KnowledgePointFilters) {
  return useQuery({
    queryKey: knowledgePointsKey(kbId, filters),
    queryFn: ({ signal }) =>
      apiClient.get<KnowledgePoint[]>(
        `/knowledge-bases/${kbId}/knowledge-points${buildKnowledgePointsQuery(filters)}`,
        { signal },
      ),
  });
}

export function useAnswerGroups(kbId: number, kpId: number, at: string | undefined, enabled: boolean) {
  return useQuery({
    // `at` is part of the key on purpose: an already-expanded row must
    // refetch when the time-travel selector changes, not silently keep
    // showing the previous `at`'s cached tree. Found during design review.
    // `at` is undefined for "最新" mode (see KnowledgePointListPage) so the
    // backend's own current date is used on every request rather than a
    // date frozen at render time — the 'now' key literal keeps that case
    // distinct from any real calendar date.
    queryKey: ['knowledge-bases', kbId, 'knowledge-points', kpId, 'answer-groups', at ?? 'now'],
    queryFn: ({ signal }) =>
      apiClient.get<AnswerGroup[]>(
        `/knowledge-bases/${kbId}/knowledge-points/${kpId}/answer-groups${at ? `?at=${at}` : ''}`,
        { signal },
      ),
    enabled,
  });
}

interface CreateKnowledgePointInput {
  title: string;
  default_answer?: { content: string; effective_time: string };
}

// Creating/deleting a knowledge point changes the knowledge base's own
// active_knowledge_point_count (the "知识主题" stat card reads it straight
// off useKnowledgeBases()'s cache) — both mutations must invalidate that
// query too, not just the knowledge-points list. Codex outer-gate finding
// on PR #23.
function invalidateAfterKpMutation(queryClient: ReturnType<typeof useQueryClient>, kbId: number) {
  queryClient.invalidateQueries({ queryKey: ['knowledge-bases', kbId, 'knowledge-points'] });
  queryClient.invalidateQueries({ queryKey: KNOWLEDGE_BASES_KEY });
}

export function useCreateKnowledgePoint(kbId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateKnowledgePointInput) =>
      apiClient.post<KnowledgePoint>(`/knowledge-bases/${kbId}/knowledge-points`, input),
    onSuccess: () => invalidateAfterKpMutation(queryClient, kbId),
  });
}

export function useDeleteKnowledgePoint(kbId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, deleteReason }: { id: number; deleteReason: string }) =>
      apiClient.post<KnowledgePoint>(`/knowledge-bases/${kbId}/knowledge-points/${id}/delete`, {
        delete_reason: deleteReason,
      }),
    onSuccess: () => invalidateAfterKpMutation(queryClient, kbId),
  });
}
