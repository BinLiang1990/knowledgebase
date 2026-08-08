// Mirrors backend/src/kb_backend/schemas/knowledge_point.py::AnswerOut.
// Shared across knowledgePoints.ts (list/resolve/answer-groups) and the
// future knowledge-point detail page (issue #8), which will add the
// write/edit mutations this type doesn't need yet.
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
