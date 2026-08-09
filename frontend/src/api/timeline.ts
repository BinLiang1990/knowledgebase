import type { Answer } from './answers';
import { today } from '../lib/today';

export type TimelineStatus = 'current' | 'superseded' | 'not-yet-effective' | 'revoked';

export interface TimelineEntry {
  answer: Answer;
  status: TimelineStatus;
}

// Groups by the server-computed coord_hash, NOT coordGroupKey(a.coord) —
// coordGroupKey's `key:value` + `|`-joined string encoding is ambiguous for
// any legal text value that itself contains ":" or "|": {a: "x|b:y"} and
// {a: "x", b: "y"} both serialize to the identical string "a:x|b:y". That
// collision would silently splice two unrelated coordinate chains'
// versions into one timeline, corrupting both the displayed history and
// the "current version" computation. coord_hash is the real SHA-256-based
// hash the backend already computes and returns on every Answer — reusing
// it sidesteps the whole class of encoding-collision bugs coordGroupKey is
// exposed to. (coordGroupKey itself is left as-is for its existing use as
// a React list key elsewhere — a wrong key there is a display glitch, not
// data corruption — this fix is scoped to the one place a collision
// actually corrupts data.) Codex outer-gate finding on PR #30.
export function buildTimelineGroups(answers: Answer[]): Map<string, TimelineEntry[]> {
  const byGroup = new Map<string, Answer[]>();
  for (const a of answers) {
    const key = a.coord_hash;
    const list = byGroup.get(key);
    if (list) list.push(a);
    else byGroup.set(key, [a]);
  }
  const result = new Map<string, TimelineEntry[]>();
  for (const [key, chain] of byGroup) {
    result.set(key, tagChain(chain));
  }
  return result;
}

// Descending: newest first, mirrors resolve.py::compute_live_groups' real
// tie-break tuple (effective_time, created_at, id) — not the simpler,
// two-key comparison the demo's own tabTimeline uses. A backfilled
// effective_time (legal — edit_answer never rejects it) can make the
// chronologically-last-WRITTEN version different from the version that is
// actually current by effective_time, so this has to match the real
// algorithm exactly, not the demo's simplification, or this tab would
// disagree with "当前答案" (which already mirrors the real algorithm via
// sortLiveGroupsByPriority) about which version is current.
function compareForCurrency(a: Answer, b: Answer): number {
  if (a.effective_time !== b.effective_time) return a.effective_time < b.effective_time ? 1 : -1;
  if (a.created_at !== b.created_at) return a.created_at < b.created_at ? 1 : -1;
  return b.id - a.id;
}

// `sortedDesc` is already ordered by the exact tie-break tuple above, so
// the first non-revoked, already-effective entry in iteration order IS the
// maximum among all such entries — one pass suffices.
function findCurrentId(sortedDesc: Answer[], atTime: string): number | undefined {
  return sortedDesc.find((a) => !a.revoked && a.effective_time <= atTime)?.id;
}

// Deliberately no `atTime` parameter — this always reads today(). If a
// future feature needs "what was current as of some other date", that
// requires explicitly adding the parameter here (and to callers), not
// quietly wiring in the existing qMode/qTime state from the "当前答案" tab.
// Design doc §4.2, issue #14.
function tagChain(chain: Answer[]): TimelineEntry[] {
  const sorted = [...chain].sort(compareForCurrency);
  const atTime = today();
  const currentId = findCurrentId(sorted, atTime);
  return sorted.map((answer) => ({
    answer,
    status: answer.revoked
      ? 'revoked'
      : answer.id === currentId
        ? 'current'
        : answer.effective_time > atTime
          ? 'not-yet-effective'
          : 'superseded',
  }));
}
