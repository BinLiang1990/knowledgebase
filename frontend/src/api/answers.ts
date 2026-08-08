import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from './client';
import type { Dimension } from './dimensions';
import { invalidateKnowledgePointDataQueries } from './knowledgePoints';
import type { AnswerGroup } from './knowledgePoints';
import type { FilterValue, Filters } from '../components/ui/dimensionValue';

// Mirrors backend/src/kb_backend/schemas/knowledge_point.py::AnswerOut.
// Shared across knowledgePoints.ts (list/resolve/answer-groups) and the
// knowledge-point detail page (issue #8).
export interface Answer {
  id: number;
  knowledge_base_id: number;
  knowledge_point_id: number;
  coord: Record<string, string | number | boolean>;
  coord_hash: string;
  content: string;
  effective_time: string;
  operator: string;
  source: string;
  note: string | null;
  revoked: boolean;
  revoked_at: string | null;
  revoked_by: string | null;
  revoke_reason: string | null;
  created_at: string;
}

function coordSpec(coord: Record<string, unknown>): number {
  return Object.keys(coord).length;
}

function coordWeight(coord: Record<string, unknown>, dimensions: Dimension[]): number {
  return Object.keys(coord).reduce((sum, key) => sum + (dimensions.find((d) => d.key === key)?.weight ?? 0), 0);
}

// PRD §4.6.1 rule 3, first bullet — mirrors backend's resolve.py::_coord_compatible
// exactly: every key the GROUP itself specifies must agree with the query
// wherever the query also specifies it; a key the query asks about but the
// group never wrote (or vice versa) is not checked. coord={} is therefore
// always compatible.
function coordCompatible(groupCoord: Record<string, unknown>, query: Filters): boolean {
  for (const [key, value] of Object.entries(groupCoord)) {
    if (!(key in query)) continue;
    if (String(value) !== String(query[key])) return false;
  }
  return true;
}

// Replicates resolve.py::resolve()'s real 5-key sort tuple — NOT the
// 3-key version PRD §4.6.1's prose describes. `effective_time` is
// day-granularity and ties are common; `created_at`/`id` were added
// server-side specifically to keep the winner deterministic on a tie
// ("Found by the Kimi review gate on PR #21", resolve.py:88-93). Using
// only 3 keys here would make this tab's "此条件下生效" pick disagree with
// what /resolve or the list page's `resolved` preview computes for the same
// knowledge point — see design doc §4.1.
//
// Known, accepted divergence (design doc §4.1): weight for a coord key no
// longer present in `dimensions` (globally deprecated, or disabled for this
// KB) falls back to 0 here, whereas the backend's own weight lookup doesn't
// filter by status at all. Not fixed here — would require a new backend
// endpoint exposing deprecated-dimension weights, out of this issue's scope.
export function sortLiveGroupsByPriority(
  groups: AnswerGroup[],
  filters: Filters,
  dimensions: Dimension[],
): AnswerGroup[] {
  const live = groups.filter((g) => g.live_answer !== null);
  const compatible = Object.keys(filters).length === 0 ? live : live.filter((g) => coordCompatible(g.coord, filters));
  return [...compatible].sort((a, b) => {
    const specDiff = coordSpec(b.coord) - coordSpec(a.coord);
    if (specDiff !== 0) return specDiff;
    const weightDiff = coordWeight(b.coord, dimensions) - coordWeight(a.coord, dimensions);
    if (weightDiff !== 0) return weightDiff;
    const av = a.live_answer!;
    const bv = b.live_answer!;
    if (av.effective_time !== bv.effective_time) return av.effective_time < bv.effective_time ? 1 : -1;
    if (av.created_at !== bv.created_at) return av.created_at < bv.created_at ? 1 : -1;
    return bv.id - av.id;
  });
}

// "此条件下生效" tag: only meaningful when there was a filter to disambiguate
// against, and only when the winner isn't tied with the runner-up on spec
// (a tie means the "winner" was picked by weight/time, not by genuinely
// being the only compatible candidate at that specificity).
export function hasUniqueTopMatch(sortedGroups: AnswerGroup[], hasFilter: boolean): boolean {
  if (!hasFilter || sortedGroups.length === 0) return false;
  if (sortedGroups.length === 1) return true;
  return coordSpec(sortedGroups[0].coord) > coordSpec(sortedGroups[1].coord);
}

// Design doc §4.3: original coord values (from answer-groups, server JSON)
// and CoordEditor draft values (from toFilterValue) are asymmetric — number
// is a JSON number on one side and a precision-preserving string on the
// other. Comparing them as raw strings produces false "changed" positives
// (e.g. "1.50" vs 1.5). A key not found in `dimensions` (locked/deprecated
// row) falls back to String() comparison, which is exact here since a
// locked row always echoes its original value unchanged.
export function coordValueEquals(fieldType: Dimension['field_type'] | undefined, a: unknown, b: unknown): boolean {
  if (fieldType === 'number') return Number(a) === Number(b);
  if (fieldType === 'boolean') return Boolean(a) === Boolean(b);
  return String(a) === String(b);
}

// True if `current` differs from `original` in a way that matters to the
// backend's is_migration decision (design doc §4.3/§4.4) — key set changed,
// or any shared key's value changed under its field_type's comparison rule.
export function diffCoord(original: Record<string, FilterValue>, current: Record<string, FilterValue>, dimensions: Dimension[]): boolean {
  const originalKeys = Object.keys(original);
  const currentKeys = Object.keys(current);
  if (originalKeys.length !== currentKeys.length) return true;
  for (const key of originalKeys) {
    if (!(key in current)) return true;
    const fieldType = dimensions.find((d) => d.key === key)?.field_type;
    if (!coordValueEquals(fieldType, original[key], current[key])) return true;
  }
  return false;
}

interface CreateAnswerInput {
  coord: Record<string, FilterValue>;
  content: string;
  effective_time: string;
  note?: string;
}

export function useCreateAnswer(kbId: number, kpId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateAnswerInput) =>
      apiClient.post<Answer>(`/knowledge-bases/${kbId}/knowledge-points/${kpId}/answers`, input),
    onSuccess: () => invalidateKnowledgePointDataQueries(queryClient, kbId),
  });
}

interface EditAnswerInput {
  answerId: number;
  content: string;
  effective_time: string;
  note?: string;
  // Design doc §4.4: omitted entirely (not even sent as the unchanged
  // value) when the condition wasn't actually touched, so the backend's
  // "reuse the target's coord verbatim, skip re-validation" path applies —
  // that path is what lets editing content/time succeed even when the
  // answer's own coord references a since-disabled dimension.
  coord?: Record<string, FilterValue>;
  migration_reason?: string;
}

export function useEditAnswer(kbId: number, kpId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ answerId, ...body }: EditAnswerInput) =>
      apiClient.post<Answer>(`/knowledge-bases/${kbId}/knowledge-points/${kpId}/answers/${answerId}/edit`, body),
    onSuccess: () => invalidateKnowledgePointDataQueries(queryClient, kbId),
  });
}
