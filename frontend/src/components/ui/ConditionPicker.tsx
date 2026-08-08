import { useEffect, useRef, useState } from 'react';
import type { Dimension } from '../../api/dimensions';
import { ValueInput, displayValue, toFilterValue } from './dimensionValue';
import type { FilterValue, Filters } from './dimensionValue';

export type { FilterValue, Filters };

interface ConditionPickerProps {
  dimensions: Dimension[];
  filters: Filters;
  onFiltersChange: (filters: Filters) => void;
  qMode: 'now' | 'day';
  qTime: string;
  today: string;
  onTimeChange: (mode: 'now' | 'day', time: string) => void;
}

export function ConditionPicker({
  dimensions,
  filters,
  onFiltersChange,
  qMode,
  qTime,
  today,
  onTimeChange,
}: ConditionPickerProps) {
  const [open, setOpen] = useState(false);
  const [activeDim, setActiveDim] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const rootRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
    function handleClickOutside(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
        setActiveDim(null);
      }
    }
    document.addEventListener('click', handleClickOutside);
    return () => document.removeEventListener('click', handleClickOutside);
  }, [open]);

  function removeFilter(key: string) {
    const next = { ...filters };
    delete next[key];
    onFiltersChange(next);
  }

  function openDimension(key: string) {
    setActiveDim(key);
    const existing = filters[key];
    if (existing !== undefined) {
      setDraft(String(existing));
      return;
    }
    // The boolean <select> always shows an option as selected natively
    // (browsers can't render a native select with nothing chosen) — it
    // visually defaults to "是"/true. Without this, clicking 确定 without
    // ever touching the select left `draft` as "" and commit() silently
    // no-op'd via its `!draft` guard, contradicting what the UI showed as
    // selected. Found while writing this component's own test.
    const dim = dimensions.find((d) => d.key === key);
    setDraft(dim?.field_type === 'boolean' ? 'true' : '');
  }

  function commit() {
    if (!activeDim) return;
    const dim = dimensions.find((d) => d.key === activeDim);
    if (!dim) return;
    // A whitespace-only text value is truthy, so it would otherwise commit
    // and display an active-looking filter chip — the backend then trims
    // it to "" and drops the coordinate, silently returning unfiltered
    // results. Codex outer-gate finding on PR #23.
    const trimmed = draft.trim();
    if (!trimmed) return;
    onFiltersChange({ ...filters, [activeDim]: toFilterValue(dim.field_type, trimmed) });
    setOpen(false);
    setActiveDim(null);
  }

  const chips = Object.entries(filters).map(([key, value]) => {
    const dim = dimensions.find((d) => d.key === key);
    return (
      <span
        key={key}
        className="tag blue"
        style={{ cursor: 'pointer' }}
        title="点击移除该条件"
        onClick={() => removeFilter(key)}
      >
        {dim?.label ?? key} = {displayValue(dim, value)} ✕
      </span>
    );
  });

  return (
    <>
      <span>时间</span>
      <span className="seg">
        <button type="button" className={qMode === 'now' ? 'on' : ''} onClick={() => onTimeChange('now', today)}>
          最新
        </button>
        <button type="button" className={qMode === 'day' ? 'on' : ''} onClick={() => onTimeChange('day', qTime)}>
          回看某天
        </button>
      </span>
      {qMode === 'day' && (
        <input
          type="date"
          value={qTime}
          max={today}
          onChange={(e) => {
            if (e.target.value) onTimeChange('day', e.target.value);
          }}
        />
      )}
      {chips}
      <span className={`dd${open ? ' open' : ''}`} ref={rootRef}>
        <button
          type="button"
          className="btn sm"
          onClick={(e) => {
            e.stopPropagation();
            setOpen((v) => !v);
            setActiveDim(null);
          }}
        >
          + 加一个条件
        </button>
        {open && (
          <div className="dd-menu" style={{ display: 'block' }} onClick={(e) => e.stopPropagation()}>
            {activeDim ? (
              (() => {
                const dim = dimensions.find((d) => d.key === activeDim)!;
                return (
                  <>
                    <div className="dd-group">「{dim.label}」= ?</div>
                    <div style={{ padding: '2px 12px 10px' }}>
                      <ValueInput dim={dim} value={draft} onChange={setDraft} />
                      <button type="button" className="btn primary sm" style={{ marginTop: 8 }} onClick={commit}>
                        确 定
                      </button>
                    </div>
                    <div className="dd-sep" />
                    <div className="dd-item" onClick={() => setActiveDim(null)}>
                      <span className="t" style={{ color: 'var(--ink-5)' }}>‹ 返回维度列表</span>
                    </div>
                  </>
                );
              })()
            ) : (
              <>
                <div className="dd-group">按哪个维度加条件？(本知识库已启用 {dimensions.length} 个维度)</div>
                {dimensions.length ? (
                  dimensions.map((d) => (
                    <div key={d.key} className="dd-item" onClick={() => openDimension(d.key)}>
                      <span className="t">
                        {d.label}
                        {filters[d.key] !== undefined ? ` · 已选 ${displayValue(d, filters[d.key])}` : ''}
                      </span>
                      <span className="d">
                        {{ text: '文本', number: '数值', date: '时间', boolean: '布尔' }[d.field_type]} · 权重{' '}
                        {d.weight}
                      </span>
                    </div>
                  ))
                ) : (
                  <div className="dd-item" style={{ color: 'var(--ink-6)', cursor: 'default' }}>
                    本知识库还没有启用任何维度，去「知识库设置」启用
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </span>
    </>
  );
}
