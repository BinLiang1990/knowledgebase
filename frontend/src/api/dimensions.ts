import { useQuery } from '@tanstack/react-query';
import { apiClient } from './client';

// Mirrors backend/src/kb_backend/schemas/dimension.py::DimensionOut
export interface Dimension {
  key: string;
  label: string;
  field_type: 'text' | 'number' | 'date' | 'boolean';
  weight: number;
}

export function useEnabledDimensions(kbId: number) {
  return useQuery({
    queryKey: ['knowledge-bases', kbId, 'enabled-dimensions'],
    queryFn: ({ signal }) => apiClient.get<Dimension[]>(`/knowledge-bases/${kbId}/enabled-dimensions`, { signal }),
  });
}
