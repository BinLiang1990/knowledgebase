import { setupServer } from 'msw/node';
import { http, HttpResponse } from 'msw';
import type { KnowledgeBase } from '../api/knowledgeBases';
import type { Dimension } from '../api/dimensions';
import type { Answer } from '../api/answers';
import type { AnswerGroup, KnowledgePoint, Resolved } from '../api/knowledgePoints';

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

export function makeDimension(overrides: Partial<Dimension> = {}): Dimension {
  return { key: 'tenant', label: '租户', field_type: 'text', weight: 50, ...overrides };
}

export function makeAnswer(overrides: Partial<Answer> = {}): Answer {
  return {
    id: 1,
    knowledge_base_id: 1,
    knowledge_point_id: 1,
    coord: {},
    coord_hash: 'hash-1',
    content: 'answer content',
    effective_time: '2026-08-08',
    operator: 'admin',
    source: '人工填报',
    note: null,
    revoked: false,
    revoked_at: null,
    revoked_by: null,
    revoke_reason: null,
    created_at: '2026-08-08T00:00:00',
    ...overrides,
  };
}

export function makeResolved(overrides: Partial<Resolved> = {}): Resolved {
  return { status: 'default', answer: makeAnswer(), ...overrides };
}

export function makeKp(overrides: Partial<KnowledgePoint> = {}): KnowledgePoint {
  return {
    id: 1,
    knowledge_base_id: 1,
    title: 'kp-1',
    status: 'active',
    operator: 'admin',
    active_answer_count: 1,
    created_at: '2026-08-08T00:00:00',
    updated_at: '2026-08-08T00:00:00',
    deleted_at: null,
    delete_reason: null,
    resolved: makeResolved(),
    ...overrides,
  };
}

export function makeAnswerGroup(overrides: Partial<AnswerGroup> = {}): AnswerGroup {
  return {
    coord: {},
    revoked: false,
    version_count: 1,
    latest_answer: makeAnswer(),
    live_answer: makeAnswer(),
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
  http.get(`${API_BASE}/knowledge-bases/:kbId/enabled-dimensions`, () => HttpResponse.json(envelope([makeDimension()]))),
  http.get(`${API_BASE}/knowledge-bases/:kbId/knowledge-points`, () => HttpResponse.json(envelope([makeKp()]))),
  http.post(`${API_BASE}/knowledge-bases/:kbId/knowledge-points`, () =>
    HttpResponse.json(envelope(makeKp({ id: 2, title: 'new-kp' }))),
  ),
  http.post(`${API_BASE}/knowledge-bases/:kbId/knowledge-points/:id/delete`, () =>
    HttpResponse.json(envelope(makeKp({ status: 'deleted' }))),
  ),
  http.get(`${API_BASE}/knowledge-bases/:kbId/knowledge-points/:id/answer-groups`, () =>
    HttpResponse.json(envelope([makeAnswerGroup()])),
  ),
];

export { HttpResponse, envelope, errorEnvelope, http };
export const server = setupServer(...handlers);
