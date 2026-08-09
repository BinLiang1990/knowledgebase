import { describe, expect, it } from 'vitest';
import { buildTimelineGroups } from './timeline';
import { makeAnswer } from '../test/server';

// Safely-distant past/future dates so these tests don't depend on the real
// "today" at run time.
const PAST_1 = '2000-01-01';
const PAST_2 = '2000-06-01';
const FUTURE = '2099-01-01';

// makeAnswer()'s default coord_hash is a fixed placeholder regardless of
// `coord` — tests that need multiple distinct groups must set coord_hash
// explicitly, since buildTimelineGroups groups by coord_hash (not by
// re-deriving anything from `coord` itself — see the function's own
// comment for why coord_hash is used).
const HASH_A = 'hash-a';
const HASH_B = 'hash-b';

describe('buildTimelineGroups', () => {
  it('tags a single unrevoked version as current', () => {
    const groups = buildTimelineGroups([makeAnswer({ id: 1, effective_time: PAST_1, coord_hash: HASH_A })]);
    const entries = groups.get(HASH_A)!;
    expect(entries).toHaveLength(1);
    expect(entries[0].status).toBe('current');
  });

  it('picks the version with the later effective_time as current, not the one written last', () => {
    // v1 written first with the later effective_time (PAST_2); v2 written
    // second but backfilled with an EARLIER effective_time (PAST_1). By
    // resolve.py's real rule, v1 (later effective_time) is current — the
    // demo's simpler write-order logic would get this wrong.
    const v1 = makeAnswer({ id: 1, effective_time: PAST_2, created_at: '2026-01-01T00:00:00', coord_hash: HASH_A });
    const v2 = makeAnswer({ id: 2, effective_time: PAST_1, created_at: '2026-01-02T00:00:00', coord_hash: HASH_A });
    const groups = buildTimelineGroups([v1, v2]);
    const entries = groups.get(HASH_A)!;
    const byId = new Map(entries.map((e) => [e.answer.id, e.status]));
    expect(byId.get(1)).toBe('current');
    expect(byId.get(2)).toBe('superseded');
  });

  it('tags every row of a whole-chain revoke as revoked, not just the last-written one', () => {
    // Regression for design doc §4.1: a whole-chain revoke sets
    // revoked=true on every row (backend batch UPDATE) — this must NOT be
    // collapsed the way get_change_log's own `status` field is (which only
    // marks the chronologically-last version as "revoked").
    const v1 = makeAnswer({ id: 1, effective_time: PAST_1, created_at: '2026-01-01T00:00:00', revoked: true, coord_hash: HASH_A });
    const v2 = makeAnswer({ id: 2, effective_time: PAST_2, created_at: '2026-01-02T00:00:00', revoked: true, coord_hash: HASH_A });
    const groups = buildTimelineGroups([v1, v2]);
    const entries = groups.get(HASH_A)!;
    expect(entries.every((e) => e.status === 'revoked')).toBe(true);
  });

  it('tags a future-effective version as not-yet-effective, not current', () => {
    const past = makeAnswer({ id: 1, effective_time: PAST_1, created_at: '2026-01-01T00:00:00', coord_hash: HASH_A });
    const future = makeAnswer({ id: 2, effective_time: FUTURE, created_at: '2026-01-02T00:00:00', coord_hash: HASH_A });
    const groups = buildTimelineGroups([past, future]);
    const entries = groups.get(HASH_A)!;
    const byId = new Map(entries.map((e) => [e.answer.id, e.status]));
    expect(byId.get(1)).toBe('current');
    expect(byId.get(2)).toBe('not-yet-effective');
  });

  it('groups multiple coord groups independently, keyed by coord_hash', () => {
    const groups = buildTimelineGroups([
      makeAnswer({ id: 1, coord: {}, effective_time: PAST_1, coord_hash: HASH_A }),
      makeAnswer({ id: 2, coord: { tenant: 'acme' }, effective_time: PAST_1, coord_hash: HASH_B }),
    ]);
    expect(groups.size).toBe(2);
    expect(groups.get(HASH_A)).toHaveLength(1);
    expect(groups.get(HASH_B)).toHaveLength(1);
  });

  it('does not splice two distinct coords into one chain when their string encodings would collide (Codex outer-gate fix on PR #30)', () => {
    // {a: "x|b:y"} and {a: "x", b: "y"} both serialize to the identical
    // string "a:x|b:y" under coordGroupKey's `key:value` + "|"-joined
    // encoding — grouping by that string (an earlier version of this
    // function did) would merge these two genuinely different coords'
    // versions into a single, corrupted timeline. Grouping by the real,
    // server-computed coord_hash keeps them apart regardless of what
    // characters the coord's own text values contain.
    const a = makeAnswer({ id: 1, coord: { a: 'x|b:y' }, effective_time: PAST_1, coord_hash: HASH_A });
    const b = makeAnswer({ id: 2, coord: { a: 'x', b: 'y' }, effective_time: PAST_1, coord_hash: HASH_B });
    const groups = buildTimelineGroups([a, b]);
    expect(groups.size).toBe(2);
    expect(groups.get(HASH_A)).toHaveLength(1);
    expect(groups.get(HASH_B)).toHaveLength(1);
  });

  it('breaks a same-effective_time tie by created_at, matching resolve.py (not the demo\'s simpler comparison)', () => {
    const older = makeAnswer({ id: 1, effective_time: PAST_1, created_at: '2026-01-01T00:00:00', coord_hash: HASH_A });
    const newer = makeAnswer({ id: 2, effective_time: PAST_1, created_at: '2026-01-02T00:00:00', coord_hash: HASH_A });
    const groups = buildTimelineGroups([older, newer]);
    const entries = groups.get(HASH_A)!;
    const byId = new Map(entries.map((e) => [e.answer.id, e.status]));
    expect(byId.get(2)).toBe('current');
    expect(byId.get(1)).toBe('superseded');
  });
});
