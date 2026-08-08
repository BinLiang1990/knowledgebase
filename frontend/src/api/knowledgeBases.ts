import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from './client';

// Mirrors backend/src/kb_backend/schemas/knowledge_base.py::KnowledgeBaseOut
export interface KnowledgeBase {
  id: number;
  name: string;
  description: string | null;
  status: 'active' | 'deprecated';
  active_knowledge_point_count: number;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeBaseInput {
  name: string;
  description?: string;
}

const KNOWLEDGE_BASES_KEY = ['knowledge-bases'] as const;

// The list endpoint has no keyword-search param and no pagination — fetch
// every knowledge base (issue #2's default already includes deprecated
// ones) and do search/paging in memory (design doc §5): the volume here
// doesn't warrant a server-side filter, and demo parity calls for the same
// client-side approach frontend-mock/kb-list.html already uses.
function listKnowledgeBases() {
  return apiClient.get<KnowledgeBase[]>('/knowledge-bases');
}

export function useKnowledgeBases() {
  return useQuery({ queryKey: KNOWLEDGE_BASES_KEY, queryFn: listKnowledgeBases });
}

export function useCreateKnowledgeBase() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: KnowledgeBaseInput) => apiClient.post<KnowledgeBase>('/knowledge-bases', input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: KNOWLEDGE_BASES_KEY }),
  });
}

export function useUpdateKnowledgeBase() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...input }: KnowledgeBaseInput & { id: number }) =>
      apiClient.patch<KnowledgeBase>(`/knowledge-bases/${id}`, input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: KNOWLEDGE_BASES_KEY }),
  });
}

export function useSetKnowledgeBaseStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status }: { id: number; status: 'active' | 'deprecated' }) =>
      apiClient.post<KnowledgeBase>(
        `/knowledge-bases/${id}/${status === 'active' ? 'activate' : 'deactivate'}`,
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: KNOWLEDGE_BASES_KEY }),
  });
}
