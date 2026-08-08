// toISOString() reports the UTC calendar date, which lags the local date by
// up to a day in timezones ahead of UTC (e.g. UTC+8 China, for the first 8
// hours after local midnight) — Codex outer-gate finding on PR #23. Format
// from the local Date fields instead. Extracted to a shared module once a
// second caller (issue #8's WriteAnswerModal) needed it, so the fix can't
// silently regress by being re-typed differently in a new file.
export function today(): string {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}
