import { describe, expect, it } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { WriteAnswerModal } from './WriteAnswerModal';
import { renderWithProviders } from '../test/renderWithProviders';
import { API_BASE, HttpResponse, envelope, http, makeAnswer, makeDimension, server } from '../test/server';

const DIMS = [
  makeDimension({ key: 'tenant', label: '租户', field_type: 'text' }),
  makeDimension({ key: 'is_vip', label: '是否VIP', field_type: 'boolean' }),
];

describe('WriteAnswerModal', () => {
  it('creates a new answer without a migration_reason', async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(`${API_BASE}/knowledge-bases/:kbId/knowledge-points/:kpId/answers`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(envelope(makeAnswer({ id: 99 })));
      }),
    );
    renderWithProviders(<WriteAnswerModal kbId={1} kpId={1} dimensions={DIMS} onClose={() => {}} />);

    await userEvent.type(screen.getByPlaceholderText('这个条件组合下的说法'), 'new answer');
    await userEvent.click(screen.getByText('确 定'));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({ content: 'new answer', coord: {} });
    expect(body).not.toHaveProperty('migration_reason');
  });

  it('editing without touching the condition sends no coord and requires no migration reason', async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(`${API_BASE}/knowledge-bases/:kbId/knowledge-points/:kpId/answers/:answerId/edit`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(envelope(makeAnswer({ id: 100 })));
      }),
    );
    renderWithProviders(
      <WriteAnswerModal
        kbId={1}
        kpId={1}
        dimensions={DIMS}
        existing={{ answerId: 5, coord: { tenant: 'acme' }, content: 'old content' }}
        onClose={() => {}}
      />,
    );

    const textarea = screen.getByPlaceholderText('这个条件组合下的说法');
    await userEvent.clear(textarea);
    await userEvent.type(textarea, 'edited content');
    await userEvent.click(screen.getByText('确 定'));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).not.toHaveProperty('coord');
    expect(body).not.toHaveProperty('migration_reason');
    expect(body!.content).toBe('edited content');
  });

  it('requires a migration reason when the condition changes, and rejects a blank one', async () => {
    renderWithProviders(
      <WriteAnswerModal
        kbId={1}
        kpId={1}
        dimensions={DIMS}
        existing={{ answerId: 5, coord: { tenant: 'acme' }, content: 'old content' }}
        onClose={() => {}}
      />,
    );

    const valueInput = document.querySelector('.mf input[type="text"]') as HTMLInputElement;
    await userEvent.clear(valueInput);
    await userEvent.type(valueInput, 'other-tenant');

    // The label is "<span>*</span>迁移原因" — no single element's full text
    // equals just "迁移原因" (same pitfall as issue #7's hit-mode tags).
    expect(await screen.findByText(/迁移原因/)).toBeInTheDocument();
    await userEvent.click(screen.getByText('确 定'));
    expect(await screen.findByText('变更适用条件需要填写迁移原因。')).toBeInTheDocument();
  });

  it('sends coord and migration_reason when the condition actually changed', async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(`${API_BASE}/knowledge-bases/:kbId/knowledge-points/:kpId/answers/:answerId/edit`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(envelope(makeAnswer({ id: 101 })));
      }),
    );
    renderWithProviders(
      <WriteAnswerModal
        kbId={1}
        kpId={1}
        dimensions={DIMS}
        existing={{ answerId: 5, coord: { tenant: 'acme' }, content: 'old content' }}
        onClose={() => {}}
      />,
    );

    const valueInput = document.querySelector('.mf input[type="text"]') as HTMLInputElement;
    await userEvent.clear(valueInput);
    await userEvent.type(valueInput, 'other-tenant');
    await userEvent.type(await screen.findByPlaceholderText('条件变化后为什么要迁移，将记录在留痕中'), 'moved tenant');
    await userEvent.click(screen.getByText('确 定'));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({ coord: { tenant: 'other-tenant' }, migration_reason: 'moved tenant' });
  });

  it('does not treat a number-only formatting difference as a condition change', async () => {
    renderWithProviders(
      <WriteAnswerModal
        kbId={1}
        kpId={1}
        dimensions={[makeDimension({ key: 'priority', label: '优先级', field_type: 'number' })]}
        existing={{ answerId: 5, coord: { priority: 1.5 }, content: 'old content' }}
        onClose={() => {}}
      />,
    );
    // Untouched draft mirrors the original value as a string ("1.5") — no
    // migration-reason field should appear since nothing actually changed.
    expect(screen.queryByText(/迁移原因/)).not.toBeInTheDocument();
  });

  it('blocks submission when a locked (deprecated-dimension) row is present and the condition changed', async () => {
    renderWithProviders(
      <WriteAnswerModal
        kbId={1}
        kpId={1}
        dimensions={DIMS}
        existing={{ answerId: 5, coord: { tenant: 'acme', old_dim: 'x' }, content: 'old content' }}
        onClose={() => {}}
      />,
    );

    expect(screen.getByText('old_dim（已停用）')).toBeInTheDocument();
    const valueInput = document.querySelector('.mf input[type="text"]') as HTMLInputElement;
    await userEvent.clear(valueInput);
    await userEvent.type(valueInput, 'other-tenant');
    await userEvent.click(screen.getByText('确 定'));

    expect(await screen.findByText(/暂不支持迁移条件/)).toBeInTheDocument();
  });

  it('shows a required-field hint when content or effective time is missing', async () => {
    renderWithProviders(<WriteAnswerModal kbId={1} kpId={1} dimensions={DIMS} onClose={() => {}} />);
    await userEvent.click(screen.getByText('确 定'));
    expect(await screen.findByText('答案内容、生效时间为必填项。')).toBeInTheDocument();
  });
});
