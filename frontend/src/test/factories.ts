/**
 * 单元测试的数据工厂（迁移自 React 版 test/server.ts，仅保留纯逻辑测试
 * 需要的部分——组件测试与 msw mock 随框架迁移移除，见 README「测试」一节）。
 */
import type { Answer } from '@/api/answer'
import type { Dimension } from '@/api/dimension'
import type { AnswerGroup } from '@/api/knowledgePoint'

export function makeDimension(overrides: Partial<Dimension> = {}): Dimension {
  return { key: 'tenant', label: '租户', field_type: 'text', weight: 50, ...overrides }
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
    source_system: 'tyzsk',
    note: null,
    revoked: false,
    revoked_at: null,
    revoked_by: null,
    revoke_reason: null,
    reactivated_at: null,
    reactivated_by: null,
    reactivate_reason: null,
    created_at: '2026-08-08T00:00:00',
    ...overrides,
  }
}

export function makeAnswerGroup(overrides: Partial<AnswerGroup> = {}): AnswerGroup {
  return {
    coord: {},
    revoked: false,
    version_count: 1,
    latest_answer: makeAnswer(),
    live_answer: makeAnswer(),
    ...overrides,
  }
}
