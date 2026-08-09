import type { Answer } from './answers';

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
//
// `currentAnswerIdByHash` supplies, per coord_hash, the id of the answer
// the SERVER currently considers live (or null if none is) — the same
// live_answer the "当前答案" tab's own useAnswerGroups(at=undefined) query
// already computes. Threading that through instead of recomputing
// "current" from a client-side today() closes a real disagreement window:
// a browser and the API server can be in different timezones (or just
// briefly clock-skewed), so a client-local date comparison can pick a
// different "current" version than the server did for the very same
// group, right around a day boundary. Kimi 终审 round 2 finding on PR #30.
export function buildTimelineGroups(
  answers: Answer[],
  currentAnswerIdByHash: Map<string, number | null>,
): Map<string, TimelineEntry[]> {
  const byGroup = new Map<string, Answer[]>();
  for (const a of answers) {
    const key = a.coord_hash;
    const list = byGroup.get(key);
    if (list) list.push(a);
    else byGroup.set(key, [a]);
  }
  const result = new Map<string, TimelineEntry[]>();
  for (const [key, chain] of byGroup) {
    result.set(key, tagChain(chain, currentAnswerIdByHash.get(key) ?? null));
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

// `currentId` is the server's own live_answer id for this group (or null
// if the server considers none of them live) — never derived from a
// client-side "now". Everything else follows from where that id lands in
// `sorted`, which is ordered by the exact same tie-break tuple resolve.py
// uses: compute_live_groups picks the max of (effective_time, created_at,
// id) among already-effective, non-revoked rows, so any non-revoked row
// sorting BEFORE the current one must have an effective_time later than
// "now" (otherwise the server would have preferred it instead) — i.e.
// not-yet-effective — and any row sorting AFTER it must have an
// effective_time no later than the current row's, i.e. already effective
// in the past — i.e. superseded. When currentId is null (no live answer
// for this group at all — wholly revoked, or every version is still in
// the future) every non-revoked row falls under "sorts before an absent
// current", so they're all correctly tagged not-yet-effective.
function tagChain(chain: Answer[], currentId: number | null): TimelineEntry[] {
  const sorted = [...chain].sort(compareForCurrency);
  const currentIndex = currentId === null ? -1 : sorted.findIndex((a) => a.id === currentId);
  return sorted.map((answer, index) => ({
    answer,
    status: answer.revoked
      ? 'revoked'
      : index === currentIndex
        ? 'current'
        : currentIndex === -1 || index < currentIndex
          ? 'not-yet-effective'
          : 'superseded',
  }));
}
