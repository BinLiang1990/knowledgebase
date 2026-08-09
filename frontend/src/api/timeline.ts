import type { Answer } from './answers';
import { coordGroupKey } from './answers';
import { today } from '../lib/today';

export type TimelineStatus = 'current' | 'superseded' | 'not-yet-effective' | 'revoked';

export interface TimelineEntry {
  answer: Answer;
  status: TimelineStatus;
}

// Groups by coordGroupKey and tags each version within its group. Not the
// same computation as get_change_log's own `status` field — see design doc
// §4.1 (issue #14): a whole-chain revoke marks EVERY row here as "revoked"
// (matching demo's tabTimeline), not just the chronologically-last one the
// way change-log's write-order-based status does; and "current" here is
// resolve.py's effective_time-based rule, not change-log's created_at
// write-order rule. These genuinely answer different questions, so this
// is a dedicated function, not a reinterpretation of change-log's output.
export function buildTimelineGroups(answers: Answer[]): Map<string, TimelineEntry[]> {
  const byGroup = new Map<string, Answer[]>();
  for (const a of answers) {
    const key = coordGroupKey(a.coord);
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
