import { describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { KnowledgePointRow } from './KnowledgePointRow';
import { renderWithProviders } from '../test/renderWithProviders';
import { makeKp } from '../test/server';

describe('KnowledgePointRow', () => {
  it('links the title and "查看详情" to the detail route without triggering row expansion', async () => {
    const onToggleExpand = vi.fn();
    renderWithProviders(
      <KnowledgePointRow
        kp={makeKp()}
        kbId={1}
        at={undefined}
        qMode="now"
        expanded={false}
        onToggleExpand={onToggleExpand}
        onDeleteRequest={vi.fn()}
        dimensions={[]}
        hasFilter={false}
      />,
    );

    const titleLink = screen.getByRole('link', { name: 'kp-1' });
    expect(titleLink).toHaveAttribute('href', '/knowledge-bases/1/knowledge-points/1');
    await userEvent.click(titleLink);
    expect(onToggleExpand).not.toHaveBeenCalled();

    const detailLink = screen.getByRole('link', { name: '查看详情' });
    expect(detailLink).toHaveAttribute('href', '/knowledge-bases/1/knowledge-points/1');
    await userEvent.click(detailLink);
    expect(onToggleExpand).not.toHaveBeenCalled();
  });

  it('still toggles expansion when the row body (not the title) is clicked', async () => {
    const onToggleExpand = vi.fn();
    renderWithProviders(
      <KnowledgePointRow
        kp={makeKp()}
        kbId={1}
        at={undefined}
        qMode="now"
        expanded={false}
        onToggleExpand={onToggleExpand}
        onDeleteRequest={vi.fn()}
        dimensions={[]}
        hasFilter={false}
      />,
    );

    await userEvent.click(screen.getByText('1 条答案'));
    expect(onToggleExpand).toHaveBeenCalledTimes(1);
  });
});
