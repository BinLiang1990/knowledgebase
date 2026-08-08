import { setupServer } from 'msw/node';
import { http, HttpResponse } from 'msw';
import type { KnowledgeBase } from '../api/knowledgeBases';

export const API_BASE = 'http://127.0.0.1:8000';

function envelope<T>(data: T, msg = '操作成功') {
  return { code: 200, data, msg };
}
function errorEnvelope(msg: string) {
  return { code: 444, data: {}, msg };
}

export function makeKb(overrides: Partial<KnowledgeBase> = {}): KnowledgeBase {
  return {
    id: 1,
    name: 'kb-1',
    description: null,
    status: 'active',
    active_knowledge_point_count: 0,
    created_at: '2026-08-08T00:00:00',
    updated_at: '2026-08-08T00:00:00',
    ...overrides,
  };
}

export const handlers = [
  http.get(`${API_BASE}/knowledge-bases`, () => HttpResponse.json(envelope([makeKb()]))),
  http.post(`${API_BASE}/knowledge-bases`, () => HttpResponse.json(envelope(makeKb({ id: 2, name: 'new-kb' })))),
  http.patch(`${API_BASE}/knowledge-bases/:id`, () => HttpResponse.json(envelope(makeKb()))),
  http.post(`${API_BASE}/knowledge-bases/:id/activate`, () =>
    HttpResponse.json(envelope(makeKb({ status: 'active' }))),
  ),
  http.post(`${API_BASE}/knowledge-bases/:id/deactivate`, () =>
    HttpResponse.json(envelope(makeKb({ status: 'deprecated' }))),
  ),
];

export { HttpResponse, envelope, errorEnvelope, http };
export const server = setupServer(...handlers);
