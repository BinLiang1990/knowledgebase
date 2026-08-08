import { describe, expect, it } from 'vitest';
import { coordValueEquals, diffCoord, hasUniqueTopMatch, sortLiveGroupsByPriority } from './answers';
import { makeAnswer, makeAnswerGroup, makeDimension } from '../test/server';

describe('sortLiveGroupsByPriority', () => {
  it('drops groups with no live answer', () => {
    const groups = [
      makeAnswerGroup({ coord: { tenant: 'acme' }, live_answer: null }),
      makeAnswerGroup({ coord: {}, live_answer: makeAnswer() }),
    ];
    const result = sortLiveGroupsByPriority(groups, {}, []);
    expect(result).toHaveLength(1);
    expect(result[0].coord).toEqual({});
  });

  it('filters by coord compatibility when a filter is set', () => {
    const groups = [
      makeAnswerGroup({ coord: { tenant: 'acme' }, live_answer: makeAnswer() }),
      makeAnswerGroup({ coord: { tenant: 'other' }, live_answer: makeAnswer() }),
      makeAnswerGroup({ coord: {}, live_answer: makeAnswer() }),
    ];
    const result = sortLiveGroupsByPriority(groups, { tenant: 'acme' }, []);
    const coords = result.map((g) => g.coord);
    expect(coords).toContainEqual({ tenant: 'acme' });
    expect(coords).toContainEqual({});
    expect(coords).not.toContainEqual({ tenant: 'other' });
  });

  it('matches a number-typed filter against an equivalent group value regardless of string/number formatting (Codex fix on PR #24)', () => {
    const dims = [makeDimension({ key: 'priority', field_type: 'number' })];
    const groups = [makeAnswerGroup({ coord: { priority: 1 }, live_answer: makeAnswer() })];
    // The filter value arrives as a precision-preserving string (issue #7),
    // the group's own coord value is a JSON number — a naive String()
    // comparison would already treat "1" === "1" fine, but "1.0" would not
    // naively match the group's bare `1`, even though /resolve considers
    // them the same condition.
    expect(sortLiveGroupsByPriority(groups, { priority: '1.0' }, dims)).toHaveLength(1);
  });

  it('sorts by spec desc, then weight desc, then effective_time desc', () => {
    const dims = [makeDimension({ key: 'tenant', weight: 10 }), makeDimension({ key: 'region', weight: 90 })];
    const groups = [
      makeAnswerGroup({ coord: { tenant: 'a' }, live_answer: makeAnswer({ id: 1, effective_time: '2026-01-01' }) }),
      makeAnswerGroup({ coord: { region: 'b' }, live_answer: makeAnswer({ id: 2, effective_time: '2026-01-01' }) }),
      makeAnswerGroup({ coord: { tenant: 'a', region: 'b' }, live_answer: makeAnswer({ id: 3, effective_time: '2026-01-01' }) }),
    ];
    const result = sortLiveGroupsByPriority(groups, {}, dims);
    // spec=2 first, then spec=1 with higher weight (region=90) before tenant (weight=10)
    expect(result.map((g) => g.live_answer!.id)).toEqual([3, 2, 1]);
  });

  it('breaks an effective_time tie by created_at, then by id', () => {
    const groups = [
      makeAnswerGroup({
        coord: {},
        live_answer: makeAnswer({ id: 1, effective_time: '2026-01-01', created_at: '2026-01-01T00:00:00' }),
      }),
      makeAnswerGroup({
        coord: {},
        live_answer: makeAnswer({ id: 2, effective_time: '2026-01-01', created_at: '2026-01-02T00:00:00' }),
      }),
    ];
    // Both have coord={} (same coord_hash in reality), but as independent
    // groups here this just exercises the tie-break chain directly.
    const result = sortLiveGroupsByPriority(groups, {}, []);
    expect(result.map((g) => g.live_answer!.id)).toEqual([2, 1]);
  });

  it('falls back to weight 0 for a coord key not present in dimensions (deprecated dimension)', () => {
    const groups = [
      makeAnswerGroup({ coord: { deprecated_dim: 'x' }, live_answer: makeAnswer({ id: 1 }) }),
      makeAnswerGroup({ coord: { tenant: 'a' }, live_answer: makeAnswer({ id: 2 }) }),
    ];
    const dims = [makeDimension({ key: 'tenant', weight: 50 })];
    // deprecated_dim isn't in `dims` -> weight 0 -> tenant (weight 50) wins despite equal spec
    const result = sortLiveGroupsByPriority(groups, {}, dims);
    expect(result.map((g) => g.live_answer!.id)).toEqual([2, 1]);
  });
});

describe('hasUniqueTopMatch', () => {
  it('is false when there is no filter', () => {
    const groups = [makeAnswerGroup({ coord: { tenant: 'a' } })];
    expect(hasUniqueTopMatch(groups, false)).toBe(false);
  });

  it('is true for a single result with a filter', () => {
    const groups = [makeAnswerGroup({ coord: { tenant: 'a' } })];
    expect(hasUniqueTopMatch(groups, true)).toBe(true);
  });

  it('is false when the top two results tie on spec', () => {
    const groups = [makeAnswerGroup({ coord: { tenant: 'a' } }), makeAnswerGroup({ coord: { region: 'b' } })];
    expect(hasUniqueTopMatch(groups, true)).toBe(false);
  });

  it('is true when the top result has strictly higher spec than the runner-up', () => {
    const groups = [makeAnswerGroup({ coord: { tenant: 'a', region: 'b' } }), makeAnswerGroup({ coord: { tenant: 'a' } })];
    expect(hasUniqueTopMatch(groups, true)).toBe(true);
  });
});

describe('coordValueEquals', () => {
  it('compares number-typed values numerically regardless of string formatting', () => {
    expect(coordValueEquals('number', 5, '5')).toBe(true);
    expect(coordValueEquals('number', 1.5, '1.50')).toBe(true);
    expect(coordValueEquals('number', 1, '2')).toBe(false);
  });

  it('compares boolean-typed values as booleans', () => {
    expect(coordValueEquals('boolean', true, true)).toBe(true);
    expect(coordValueEquals('boolean', true, false)).toBe(false);
  });

  it('compares text/date-typed and unknown-field-type values as strings', () => {
    expect(coordValueEquals('text', 'acme', 'acme')).toBe(true);
    expect(coordValueEquals('date', '2026-01-01', '2026-01-01')).toBe(true);
    expect(coordValueEquals(undefined, 'x', 'x')).toBe(true);
    expect(coordValueEquals(undefined, 'x', 'y')).toBe(false);
  });

  it('distinguishes large integers beyond Number precision instead of collapsing them (Codex fix on PR #24)', () => {
    // Number(a) === Number(b) would collapse both of these onto the same
    // double (9007199254740992) even though they're distinct, backend-
    // supported integers — 2**53 is exactly representable as `a`, so this
    // isn't testing a value already mangled by the test's own JS literal.
    expect(coordValueEquals('number', 9007199254740992, '9007199254740993')).toBe(false);
    expect(coordValueEquals('number', 9007199254740992, '9007199254740992')).toBe(true);
    // Both sides as exact digit strings (as they'd arrive via toFilterValue
    // on both ends) stays exact arbitrarily far past 2**53.
    expect(coordValueEquals('number', '18446744073709551615', '18446744073709551615')).toBe(true);
    expect(coordValueEquals('number', '18446744073709551615', '18446744073709551614')).toBe(false);
  });
});

describe('diffCoord', () => {
  const dims = [makeDimension({ key: 'priority', field_type: 'number' }), makeDimension({ key: 'tenant', field_type: 'text' })];

  it('is false for identical coords', () => {
    expect(diffCoord({ tenant: 'acme' }, { tenant: 'acme' }, dims)).toBe(false);
  });

  it('is false when a number value only differs in string formatting', () => {
    expect(diffCoord({ priority: 5 }, { priority: '5' }, dims)).toBe(false);
  });

  it('is true when a value actually changed', () => {
    expect(diffCoord({ tenant: 'acme' }, { tenant: 'other' }, dims)).toBe(true);
  });

  it('is true when the key set changed', () => {
    expect(diffCoord({ tenant: 'acme' }, { tenant: 'acme', priority: '1' }, dims)).toBe(true);
    expect(diffCoord({ tenant: 'acme', priority: '1' }, { tenant: 'acme' }, dims)).toBe(true);
  });
});
