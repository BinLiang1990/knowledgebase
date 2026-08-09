import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from './client';
import type { Answer } from './answers';
import { KNOWLEDGE_BASES_KEY } from './knowledgeBases';

export type ResolveStatus = 'exact' | 'weighted' | 'default' | 'fallback-latest' | 'none';

export interface Resolved {
  status: ResolveStatus;
  answer: Answer | null;
}

// Mirrors backend/src/kb_backend/schemas/knowledge_point.py::KnowledgePointOut
// exactly — this is also what the single-fetch GET /{kp_id} returns (issue
// #8), unlike the list endpoint below which additively attaches `resolved`.
export interface KnowledgePointDetail {
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
}

// The list endpoint's per-row shape: the plain KnowledgePointDetail plus the
// additive `resolved` field (docs/specs/2026-08-08-resolve-engine-design.md
// §4.2).
export interface KnowledgePoint extends KnowledgePointDetail {
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

export function useKnowledgePoints(kbId: number, filters: KnowledgePointFilters, enabled = true) {
  return useQuery({
    queryKey: knowledgePointsKey(kbId, filters),
    queryFn: ({ signal }) =>
      apiClient.get<KnowledgePoint[]>(
        `/knowledge-bases/${kbId}/knowledge-points${buildKnowledgePointsQuery(filters)}`,
        { signal },
      ),
    enabled,
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
// Every query this module exports nests under this same prefix
// (['knowledge-bases', kbId, 'knowledge-points', ...]) on purpose — see
// design doc §4.5 — so a single invalidation here reaches useKnowledgePoints,
// useKnowledgePoint, and useAnswerGroups regardless of their differing
// filters/kpId/at suffixes.
// Exported so api/changeLog.ts and api/knowledgePoints.ts's own
// useAllAnswers (issue #14) can nest their query keys under this same
// prefix — a single invalidateKnowledgePointDataQueries call then covers
// change-log/all-answers/answer-groups alike, with no separate
// invalidation logic needed for the new hooks.
export function knowledgePointDataKeyPrefix(kbId: number) {
  return ['knowledge-bases', kbId, 'knowledge-points'] as const;
}

// Defined here (not in api/changeLog.ts, despite belonging conceptually to
// the global change-log feature) so both changeLog.ts and this module can
// import it without a runtime circular dependency — changeLog.ts already
// imports knowledgePointDataKeyPrefix from here, so the reverse import
// would form a genuine cycle (unlike the existing type-only Answer import
// from answers.ts, which TypeScript fully erases). This module is the
// single source of truth for both shared keys.
export const GLOBAL_CHANGE_LOG_KEY = ['change-log'] as const;

// For mutations that only change a knowledge point's own data (writing/
// editing an answer, renaming) — NOT the knowledge base's aggregate
// active_knowledge_point_count, so KNOWLEDGE_BASES_KEY is deliberately left
// alone (unlike invalidateAfterKpMutation below).
export function invalidateKnowledgePointDataQueries(queryClient: ReturnType<typeof useQueryClient>, kbId: number) {
  queryClient.invalidateQueries({ queryKey: knowledgePointDataKeyPrefix(kbId) });
}

// Any knowledge-point mutation that can affect what the global change-log
// page shows (a new default answer on create, a renamed knowledge point
// changing every one of its rows' knowledge_point_title) must also
// invalidate GLOBAL_CHANGE_LOG_KEY, or a cached global log page keeps
// showing stale entries/titles. Kimi 终审 finding on PR #30 — this was
// previously only done for useRevokeAnswer in api/answers.ts.
function invalidateKnowledgePointDataAndGlobalLog(queryClient: ReturnType<typeof useQueryClient>, kbId: number) {
  invalidateKnowledgePointDataQueries(queryClient, kbId);
  queryClient.invalidateQueries({ queryKey: GLOBAL_CHANGE_LOG_KEY });
}

// Creating/deleting a knowledge point changes the knowledge base's own
// active_knowledge_point_count (the "知识主题" stat card reads it straight
// off useKnowledgeBases()'s cache) — both mutations must invalidate that
// query too, not just the knowledge-points list. Codex outer-gate finding
// on PR #23.
function invalidateAfterKpMutation(queryClient: ReturnType<typeof useQueryClient>, kbId: number) {
  invalidateKnowledgePointDataAndGlobalLog(queryClient, kbId);
  queryClient.invalidateQueries({ queryKey: KNOWLEDGE_BASES_KEY });
}

export function useKnowledgePoint(kbId: number, kpId: number, enabled = true) {
  return useQuery({
    queryKey: [...knowledgePointDataKeyPrefix(kbId), kpId] as const,
    queryFn: ({ signal }) =>
      apiClient.get<KnowledgePointDetail>(`/knowledge-bases/${kbId}/knowledge-points/${kpId}`, { signal }),
    enabled,
  });
}

// Every version, every coord group, unfiltered (issue #14 design doc §1) —
// the "版本历史" tab's data source. Deliberately NOT the same query
// useAnswerGroups uses (that one is grouped/summarized server-side); see
// design doc §4.1 for why the timeline needs raw per-version rows instead.
export function useAllAnswers(kbId: number, kpId: number, enabled: boolean) {
  return useQuery({
    queryKey: [...knowledgePointDataKeyPrefix(kbId), kpId, 'answers'] as const,
    queryFn: ({ signal }) =>
      apiClient.get<Answer[]>(`/knowledge-bases/${kbId}/knowledge-points/${kpId}/answers`, { signal }),
    enabled,
  });
}

export function useUpdateKnowledgePointTitle(kbId: number, kpId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (title: string) =>
      apiClient.patch<KnowledgePointDetail>(`/knowledge-bases/${kbId}/knowledge-points/${kpId}`, { title }),
    // The global change-log page inlines this KP's title on every one of
    // its rows (knowledge_point_title) — a rename must invalidate that
    // cache too, not just this KP's own data. Kimi 终审 finding on PR #30.
    onSuccess: () => invalidateKnowledgePointDataAndGlobalLog(queryClient, kbId),
  });
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
