import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CoordEditor, coordRowsFromCoord, coordRowsToCoord, hasLockedRow } from './CoordEditor';
import type { CoordRow } from './CoordEditor';
import { makeDimension } from '../test/server';

const DIMS = [
  makeDimension({ key: 'tenant', label: '租户', field_type: 'text' }),
  makeDimension({ key: 'is_vip', label: '是否VIP', field_type: 'boolean' }),
];

describe('coordRowsFromCoord', () => {
  it('builds an editable row for a key present in dimensions', () => {
    const rows = coordRowsFromCoord({ tenant: 'acme' }, DIMS);
    expect(rows).toEqual([{ key: 'tenant', raw: 'acme' }]);
  });

  it('builds a locked row for a key not present in dimensions', () => {
    const rows = coordRowsFromCoord({ deprecated_dim: 'x' }, DIMS);
    expect(rows).toEqual([{ key: 'deprecated_dim', raw: '', locked: 'x' }]);
  });
});

describe('hasLockedRow', () => {
  it('detects a locked row', () => {
    expect(hasLockedRow([{ key: 'tenant', raw: 'acme' }])).toBe(false);
    expect(hasLockedRow([{ key: 'old', raw: '', locked: 'x' }])).toBe(true);
  });
});

describe('coordRowsToCoord', () => {
  it('converts editable rows through toFilterValue', () => {
    const rows: CoordRow[] = [{ key: 'tenant', raw: 'acme' }, { key: 'is_vip', raw: 'true' }];
    const result = coordRowsToCoord(rows, DIMS);
    expect(result.coord).toEqual({ tenant: 'acme', is_vip: true });
    expect(result.error).toBeUndefined();
  });

  it('passes a locked row through verbatim', () => {
    const rows: CoordRow[] = [{ key: 'old', raw: '', locked: 42 }];
    const result = coordRowsToCoord(rows, DIMS);
    expect(result.coord).toEqual({ old: 42 });
  });

  it('rejects a row with no dimension selected', () => {
    const rows: CoordRow[] = [{ key: '', raw: 'x' }];
    expect(coordRowsToCoord(rows, DIMS).error).toBeTruthy();
  });

  it('rejects a whitespace-only value', () => {
    const rows: CoordRow[] = [{ key: 'tenant', raw: '   ' }];
    const result = coordRowsToCoord(rows, DIMS);
    expect(result.error).toContain('租户');
    expect(result.coord).toBeUndefined();
  });

  it('returns an empty coord for zero rows (default answer)', () => {
    expect(coordRowsToCoord([], DIMS)).toEqual({ coord: {} });
  });
});

describe('CoordEditor', () => {
  it('adds and removes rows', async () => {
    let rows: CoordRow[] = [];
    const onChange = vi.fn((next: CoordRow[]) => {
      rows = next;
    });
    const { rerender } = render(<CoordEditor dimensions={DIMS} rows={rows} onChange={onChange} />);

    await userEvent.click(screen.getByText('+ 加一个条件'));
    expect(rows).toEqual([{ key: '', raw: '' }]);
    rerender(<CoordEditor dimensions={DIMS} rows={rows} onChange={onChange} />);

    await userEvent.click(screen.getByText('移除'));
    expect(rows).toEqual([]);
  });

  it('excludes an already-used dimension from other rows dropdowns', () => {
    const rows: CoordRow[] = [{ key: 'tenant', raw: 'acme' }, { key: '', raw: '' }];
    render(<CoordEditor dimensions={DIMS} rows={rows} onChange={vi.fn()} />);

    const selects = document.querySelectorAll('select');
    const secondRowOptions = Array.from(selects[1].querySelectorAll('option')).map((o) => o.textContent);
    expect(secondRowOptions).not.toContain('租户');
    expect(secondRowOptions).toContain('是否VIP');
  });

  it('renders a locked row as read-only with no select or remove link', () => {
    const rows: CoordRow[] = [{ key: 'deprecated_dim', raw: '', locked: 'x' }];
    render(<CoordEditor dimensions={DIMS} rows={rows} onChange={vi.fn()} />);

    expect(screen.getByText('deprecated_dim（已停用）')).toBeInTheDocument();
    expect(screen.queryByText('移除')).not.toBeInTheDocument();
  });

  it('defaults a newly-picked boolean dimension row to "true", matching the select\'s own visual default', async () => {
    let rows: CoordRow[] = [{ key: '', raw: '' }];
    const onChange = vi.fn((next: CoordRow[]) => {
      rows = next;
    });
    render(<CoordEditor dimensions={DIMS} rows={rows} onChange={onChange} />);

    const select = document.querySelector('select') as HTMLSelectElement;
    await userEvent.selectOptions(select, '是否VIP');

    expect(rows).toEqual([{ key: 'is_vip', raw: 'true' }]);
  });
});
