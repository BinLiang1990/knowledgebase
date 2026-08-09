import { describe, expect, it } from 'vitest';
import { buildTimelineGroups } from './timeline';
import { makeAnswer } from '../test/server';

// Safely-distant past/future dates so these tests don't depend on the real
// "today" at run time.
const PAST_1 = '2000-01-01';
const PAST_2 = '2000-06-01';
const FUTURE = '2099-01-01';

describe('buildTimelineGroups', () => {
  it('tags a single unrevoked version as current', () => {
    const groups = buildTimelineGroups([makeAnswer({ id: 1, effective_time: PAST_1 })]);
    const entries = groups.get('(默认)')!;
    expect(entries).toHaveLength(1);
    expect(entries[0].status).toBe('current');
  });

  it('picks the version with the later effective_time as current, not the one written last', () => {
    // v1 written first with the later effective_time (PAST_2); v2 written
    // second but backfilled with an EARLIER effective_time (PAST_1). By
    // resolve.py's real rule, v1 (later effective_time) is current — the
    // demo's simpler write-order logic would get this wrong.
    const v1 = makeAnswer({ id: 1, effective_time: PAST_2, created_at: '2026-01-01T00:00:00' });
    const v2 = makeAnswer({ id: 2, effective_time: PAST_1, created_at: '2026-01-02T00:00:00' });
    const groups = buildTimelineGroups([v1, v2]);
    const entries = groups.get('(默认)')!;
    const byId = new Map(entries.map((e) => [e.answer.id, e.status]));
    expect(byId.get(1)).toBe('current');
    expect(byId.get(2)).toBe('superseded');
  });

  it('tags every row of a whole-chain revoke as revoked, not just the last-written one', () => {
    // Regression for design doc §4.1: a whole-chain revoke sets
    // revoked=true on every row (backend batch UPDATE) — this must NOT be
    // collapsed the way get_change_log's own `status` field is (which only
    // marks the chronologically-last version as "revoked").
    const v1 = makeAnswer({ id: 1, effective_time: PAST_1, created_at: '2026-01-01T00:00:00', revoked: true });
    const v2 = makeAnswer({ id: 2, effective_time: PAST_2, created_at: '2026-01-02T00:00:00', revoked: true });
    const groups = buildTimelineGroups([v1, v2]);
    const entries = groups.get('(默认)')!;
    expect(entries.every((e) => e.status === 'revoked')).toBe(true);
  });

  it('tags a future-effective version as not-yet-effective, not current', () => {
    const past = makeAnswer({ id: 1, effective_time: PAST_1, created_at: '2026-01-01T00:00:00' });
    const future = makeAnswer({ id: 2, effective_time: FUTURE, created_at: '2026-01-02T00:00:00' });
    const groups = buildTimelineGroups([past, future]);
    const entries = groups.get('(默认)')!;
    const byId = new Map(entries.map((e) => [e.answer.id, e.status]));
    expect(byId.get(1)).toBe('current');
    expect(byId.get(2)).toBe('not-yet-effective');
  });

  it('groups multiple coord groups independently', () => {
    const groups = buildTimelineGroups([
      makeAnswer({ id: 1, coord: {}, effective_time: PAST_1 }),
      makeAnswer({ id: 2, coord: { tenant: 'acme' }, effective_time: PAST_1 }),
    ]);
    expect(groups.size).toBe(2);
    expect(groups.get('(默认)')).toHaveLength(1);
    expect(groups.get('tenant:acme')).toHaveLength(1);
  });

  it('breaks a same-effective_time tie by created_at, matching resolve.py (not the demo\'s simpler comparison)', () => {
    const older = makeAnswer({ id: 1, effective_time: PAST_1, created_at: '2026-01-01T00:00:00' });
    const newer = makeAnswer({ id: 2, effective_time: PAST_1, created_at: '2026-01-02T00:00:00' });
    const groups = buildTimelineGroups([older, newer]);
    const entries = groups.get('(默认)')!;
    const byId = new Map(entries.map((e) => [e.answer.id, e.status]));
    expect(byId.get(2)).toBe('current');
    expect(byId.get(1)).toBe('superseded');
  });
});
