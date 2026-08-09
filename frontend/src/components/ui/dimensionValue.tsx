import type { Dimension } from '../../api/dimensions';

// Shared by ConditionPicker (query filters) and CoordEditor (answer
// conditions) — both need the exact same dimension-value type-conversion
// rule. Extracted after issue #7's Codex round caught a trim bug that only
// existed in ConditionPicker's own copy of this logic; duplicating it again
// for CoordEditor would reopen the same drift risk (issue #8 design doc §4.2).
export type FilterValue = string | number | boolean;
export type Filters = Record<string, FilterValue>;

export function displayValue(dim: Dimension | undefined, value: FilterValue): string {
  if (dim?.field_type === 'boolean') return value ? '是' : '否';
  return String(value);
}

// Value input per field_type — native input types do the heavy lifting for
// number/date validity; boolean is a fixed select (see design docs for why
// the *committed* value still needs type conversion beyond this).
export function ValueInput({
  dim,
  value,
  onChange,
  allowUnset = false,
}: {
  dim: Dimension;
  value: string;
  onChange: (v: string) => void;
  // Every existing caller (ConditionPicker's filters, CoordEditor's coord
  // values) only ever renders this for a field that's already been added
  // to the filter/coord — there is no "unset" state to represent there, so
  // the boolean branch has always been able to default an empty value to
  // "是"/true. issue #13's "默认取值提示" is optional and genuinely can be
  // unset — silently defaulting the *displayed* selection to "是" while the
  // underlying state (and what actually gets submitted) stays empty/null
  // would show the user one value and save a different one. allowUnset
  // adds a real "未设置" option and stops coercing an empty value to
  // "true" for display, without changing behavior for any existing caller
  // that omits it. Codex outer-gate finding on PR #29.
  allowUnset?: boolean;
}) {
  if (dim.field_type === 'number') {
    return <input type="number" value={value} onChange={(e) => onChange(e.target.value)} autoFocus />;
  }
  if (dim.field_type === 'date') {
    return <input type="date" value={value} onChange={(e) => onChange(e.target.value)} autoFocus />;
  }
  if (dim.field_type === 'boolean') {
    return (
      <select value={allowUnset ? value : value || 'true'} onChange={(e) => onChange(e.target.value)} autoFocus>
        {allowUnset && <option value="">未设置</option>}
        <option value="true">是</option>
        <option value="false">否</option>
      </select>
    );
  }
  return (
    <input type="text" value={value} placeholder="输入取值" onChange={(e) => onChange(e.target.value)} autoFocus />
  );
}

// coord.py's field_type-specific parsing: boolean must become a real JSON
// boolean, not the string the <select> gives us; number stays a string so
// the backend's Decimal-based parser gets the exact digits instead of a
// JS-Number round-trip.
export function toFilterValue(fieldType: Dimension['field_type'], raw: string): FilterValue {
  if (fieldType === 'boolean') return raw === 'true';
  return raw;
}
