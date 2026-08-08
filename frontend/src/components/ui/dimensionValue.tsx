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
}: {
  dim: Dimension;
  value: string;
  onChange: (v: string) => void;
}) {
  if (dim.field_type === 'number') {
    return <input type="number" value={value} onChange={(e) => onChange(e.target.value)} autoFocus />;
  }
  if (dim.field_type === 'date') {
    return <input type="date" value={value} onChange={(e) => onChange(e.target.value)} autoFocus />;
  }
  if (dim.field_type === 'boolean') {
    return (
      <select value={value || 'true'} onChange={(e) => onChange(e.target.value)} autoFocus>
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
