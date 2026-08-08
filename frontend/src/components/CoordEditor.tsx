import type { Dimension } from '../api/dimensions';
import { ValueInput, toFilterValue } from './ui/dimensionValue';
import type { FilterValue, Filters } from './ui/dimensionValue';

// A row with `locked` set carries a coord key that isn't in the current
// `dimensions` list (globally deprecated, or disabled for this KB) — design
// doc §4.2. It's rendered read-only and always contributes its original
// value verbatim to the reconstructed coord, never through toFilterValue.
export interface CoordRow {
  key: string;
  raw: string;
  locked?: FilterValue;
}

export function coordRowsFromCoord(coord: Record<string, FilterValue>, dimensions: Dimension[]): CoordRow[] {
  return Object.entries(coord).map(([key, value]) => {
    const dim = dimensions.find((d) => d.key === key);
    if (!dim) return { key, raw: '', locked: value };
    return { key, raw: String(value) };
  });
}

export function hasLockedRow(rows: CoordRow[]): boolean {
  return rows.some((r) => r.locked !== undefined);
}

export interface CoordRowsResult {
  coord?: Filters;
  error?: string;
}

// Mirrors the demo's readCondRows, plus the whitespace-reject discipline
// issue #7's Codex round established for ConditionPicker: a row with a
// dimension picked but a blank/whitespace-only value is rejected outright
// rather than silently dropped or sent as "".
export function coordRowsToCoord(rows: CoordRow[], dimensions: Dimension[]): CoordRowsResult {
  const coord: Filters = {};
  for (const row of rows) {
    if (row.locked !== undefined) {
      coord[row.key] = row.locked;
      continue;
    }
    const dim = dimensions.find((d) => d.key === row.key);
    if (!dim) return { error: '请为每一行选择维度' };
    const trimmed = row.raw.trim();
    if (!trimmed) return { error: `「${dim.label}」不能为空` };
    coord[row.key] = toFilterValue(dim.field_type, trimmed);
  }
  return { coord };
}

interface CoordEditorProps {
  dimensions: Dimension[];
  rows: CoordRow[];
  onChange: (rows: CoordRow[]) => void;
}

// The "适用条件" multi-row editor for the write/edit-answer form — distinct
// from ConditionPicker (issue #7), which locks one dimension=value at a time
// for querying. This edits the full set of 0~N conditions an answer is
// pinned to. Design doc §4.2.
export function CoordEditor({ dimensions, rows, onChange }: CoordEditorProps) {
  function addRow() {
    onChange([...rows, { key: '', raw: '' }]);
  }
  function removeRow(index: number) {
    onChange(rows.filter((_, i) => i !== index));
  }
  function updateRow(index: number, patch: Partial<CoordRow>) {
    onChange(rows.map((r, i) => (i === index ? { ...r, ...patch } : r)));
  }

  return (
    <div>
      {rows.map((row, i) => {
        if (row.locked !== undefined) {
          return (
            <div className="form-row" key={`locked-${row.key}`} style={{ marginBottom: 8 }}>
              <span className="tag gray">{row.key}（已停用）</span>
              <span className="hint">{String(row.locked)}</span>
            </div>
          );
        }
        // A dimension already picked by another row is excluded here — the
        // demo lets the same dimension appear twice and silently keeps only
        // the last row's value; design doc §4.2 treats that as an ambiguity
        // worth preventing rather than reproducing.
        const usedByOtherRows = rows.filter((_, j) => j !== i).map((r) => r.key);
        const availableDims = dimensions.filter((d) => d.key === row.key || !usedByOtherRows.includes(d.key));
        const dim = dimensions.find((d) => d.key === row.key);
        return (
          <div className="form-row" key={`row-${i}`} style={{ marginBottom: 8 }}>
            <select
              value={row.key}
              onChange={(e) => {
                const nextDim = dimensions.find((d) => d.key === e.target.value);
                // Matches ConditionPicker's own fix for the same bug: a
                // boolean <select> always shows an option as selected
                // (browsers can't render "nothing chosen"), so the backing
                // state must start in sync with what's visually shown.
                updateRow(i, { key: e.target.value, raw: nextDim?.field_type === 'boolean' ? 'true' : '' });
              }}
              style={{ minWidth: 120 }}
            >
              <option value="">选择维度…</option>
              {availableDims.map((d) => (
                <option key={d.key} value={d.key}>
                  {d.label}
                </option>
              ))}
            </select>
            <span className="f-val-wrap">
              {dim ? (
                <ValueInput dim={dim} value={row.raw} onChange={(v) => updateRow(i, { raw: v })} />
              ) : (
                <input type="text" disabled placeholder="先选维度" />
              )}
            </span>
            <a className="danger" style={{ fontSize: 13 }} onClick={() => removeRow(i)}>
              移除
            </a>
          </div>
        );
      })}
      <button type="button" className="btn sm" style={{ marginTop: 8 }} onClick={addRow}>
        + 加一个条件
      </button>
      <div className="hint">
        维度只能从本知识库已启用的维度中选择；条件不变 = 同组追加新版本，条件改了 = 迁移到新条件组
      </div>
    </div>
  );
}
