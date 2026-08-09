import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from './client';

// Mirrors backend/src/kb_backend/schemas/dimension.py::DimensionOut
export interface Dimension {
  key: string;
  label: string;
  field_type: 'text' | 'number' | 'date' | 'boolean';
  weight: number;
}

export function useEnabledDimensions(kbId: number, enabled = true) {
  return useQuery({
    queryKey: ['knowledge-bases', kbId, 'enabled-dimensions'],
    queryFn: ({ signal }) => apiClient.get<Dimension[]>(`/knowledge-bases/${kbId}/enabled-dimensions`, { signal }),
    enabled,
  });
}

// Mirrors backend/src/kb_backend/schemas/dimension.py::DimensionAdminOut —
// every dimension regardless of status, plus the fields the external,
// active-only DimensionOut above deliberately omits.
export interface AdminDimension extends Dimension {
  default_value: string | null;
  status: 'active' | 'deprecated';
  answer_count: number;
}

// Structurally separate from DimensionUpdateInput, mirroring the backend's
// own DimensionCreate/DimensionUpdate split — DimensionUpdate has no
// field_type field at all (design doc §3.2, issue #13), not merely one
// that's rejected if sent.
export interface DimensionCreateInput {
  label: string;
  field_type: Dimension['field_type'];
  weight: number;
  default_value: string | null;
}

export interface DimensionUpdateInput {
  label: string;
  weight: number;
  // Always sent explicitly, never omitted — null means "clear it", a
  // non-empty string means "set it to this". Omitting this key entirely
  // would be interpreted by the backend's model_fields_set-based logic as
  // "leave unchanged", which is wrong both when the user just cleared the
  // field (the clear would silently not take effect) and, if a caller
  // instead reached for something like `value || undefined` to "play it
  // safe", would still risk collapsing "clear" and "untouched" into the
  // same wire representation. Sending the field's real current value on
  // every edit — never guessing whether the user "touched" it — is what
  // is actually being changed. Design doc §4.2, issue #13.
  default_value: string | null;
}

export const ADMIN_DIMENSIONS_KEY = ['admin-dimensions'] as const;

// No single, fixed query key to invalidate here — useEnabledDimensions is
// cached per knowledge base, under ['knowledge-bases', kbId,
// 'enabled-dimensions'], and a global dimension change (rename,
// reactivate/deactivate, weight) can affect any knowledge base that has it
// enabled, not just whichever one the admin happens to be looking at right
// now. An earlier version of this invalidated a literal ['dimensions'] key
// instead — nothing in this codebase ever queries under that key, so it
// was a complete no-op, silently leaving every already-cached
// enabled-dimensions list stale after a create/update/activate/deactivate.
// Codex outer-gate finding on PR #29 (fifth round).
function invalidateAllEnabledDimensionsQueries(queryClient: ReturnType<typeof useQueryClient>) {
  queryClient.invalidateQueries({
    predicate: (query) => query.queryKey[0] === 'knowledge-bases' && query.queryKey[2] === 'enabled-dimensions',
  });
}

export function useAdminDimensions() {
  return useQuery({
    queryKey: ADMIN_DIMENSIONS_KEY,
    queryFn: ({ signal }) => apiClient.get<AdminDimension[]>('/admin/dimensions', { signal }),
  });
}

export function useCreateDimension() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: DimensionCreateInput) => apiClient.post<AdminDimension>('/dimensions', input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ADMIN_DIMENSIONS_KEY });
      invalidateAllEnabledDimensionsQueries(queryClient);
    },
  });
}

export function useUpdateDimension() {
  const queryClient = useQueryClient();
  return useMutation({
    // encodeURIComponent(key) — a dimension's key is a client-typed label
    // verbatim (backend only rejects "/" in it, design doc §4.3), so
    // characters like "?"/"#"/"&" are otherwise valid and would otherwise
    // get interpreted as the start of a query string/fragment when
    // interpolated raw into a URL path, silently targeting the wrong (or
    // no) resource. Codex outer-gate finding on PR #29.
    mutationFn: ({ key, ...input }: DimensionUpdateInput & { key: string }) =>
      apiClient.patch<AdminDimension>(`/dimensions/${encodeURIComponent(key)}`, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ADMIN_DIMENSIONS_KEY });
      invalidateAllEnabledDimensionsQueries(queryClient);
    },
  });
}

export function useSetDimensionStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ key, status }: { key: string; status: 'active' | 'deprecated' }) =>
      apiClient.post<AdminDimension>(
        `/dimensions/${encodeURIComponent(key)}/${status === 'active' ? 'activate' : 'deactivate'}`,
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ADMIN_DIMENSIONS_KEY });
      invalidateAllEnabledDimensionsQueries(queryClient);
    },
  });
}

export function useSetEnabledDimensions(kbId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (dimensionKeys: string[]) =>
      apiClient.put<Dimension[]>(`/knowledge-bases/${kbId}/enabled-dimensions`, { dimension_keys: dimensionKeys }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['knowledge-bases', kbId, 'enabled-dimensions'] });
    },
  });
}
