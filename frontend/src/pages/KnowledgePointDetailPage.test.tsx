import { describe, expect, it } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { KnowledgePointDetailPage } from './KnowledgePointDetailPage';
import { renderWithProviders } from '../test/renderWithProviders';
import {
  API_BASE,
  HttpResponse,
  envelope,
  http,
  makeAnswer,
  makeAnswerGroup,
  makeChangeLogEntry,
  makeDimension,
  makeKb,
  makeKpDetail,
  server,
} from '../test/server';

function renderPage(initialPath = '/knowledge-bases/1/knowledge-points/1') {
  return renderWithProviders(
    <Routes>
      <Route path="/knowledge-bases/:kbId/knowledge-points/:kpId" element={<KnowledgePointDetailPage />} />
    </Routes>,
    { initialEntries: [initialPath] },
  );
}

describe('KnowledgePointDetailPage', () => {
  it('renders the header: title, id, active answer count, created info, status tag', async () => {
    server.use(
      http.get(`${API_BASE}/knowledge-bases/:kbId/knowledge-points/:id`, () =>
        HttpResponse.json(
          envelope(makeKpDetail({ title: 'refund-policy', active_answer_count: 3, operator: 'alice' })),
        ),
      ),
    );
    renderPage();
    expect(await screen.findByText('refund-policy')).toBeInTheDocument();
    expect(screen.getByText('3 条在用答案')).toBeInTheDocument();
    expect(screen.getByText(/alice/)).toBeInTheDocument();
    expect(screen.getByText('正常')).toBeInTheDocument();
  });

  it('disables write/edit actions until enabled-dimensions has loaded (Codex fix on PR #24)', async () => {
    // Never resolves — simulates enabled-dimensions still being in flight
    // while answer-groups has already returned, the race that used to
    // permanently lock every condition row as "deprecated dimension".
    server.use(http.get(`${API_BASE}/knowledge-bases/:kbId/enabled-dimensions`, () => new Promise(() => {})));
    renderPage();
    await screen.findByText('kp-1');
    await screen.findByText('answer content');

    expect(screen.getByText('+ 写一条答案')).toBeDisabled();
    await userEvent.click(screen.getByText('编辑'));
    expect(screen.queryByText('写一条答案', { selector: 'h3' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '编辑答案' })).not.toBeInTheDocument();
  });

  it('shows a guard when the knowledge base does not exist', async () => {
    server.use(http.get(`${API_BASE}/knowledge-bases`, () => HttpResponse.json(envelope([]))));
    renderPage('/knowledge-bases/999/knowledge-points/1');
    expect(await screen.findByText(/没有指定有效的知识库/)).toBeInTheDocument();
  });

  it('shows a guard when the knowledge base is deactivated', async () => {
    server.use(http.get(`${API_BASE}/knowledge-bases`, () => HttpResponse.json(envelope([makeKb({ status: 'deprecated' })]))));
    renderPage();
    expect(await screen.findByText(/没有指定有效的知识库/)).toBeInTheDocument();
  });

  it('shows a soft-deleted notice and hides write/edit-title/delete ops', async () => {
    server.use(
      http.get(`${API_BASE}/knowledge-bases/:kbId/knowledge-points/:id`, () =>
        HttpResponse.json(
          envelope(makeKpDetail({ status: 'deleted', deleted_at: '2026-08-01T00:00:00', delete_reason: 'obsolete' })),
        ),
      ),
    );
    renderPage();
    expect(await screen.findByText(/该知识点已被/)).toBeInTheDocument();
    expect(screen.getByText(/obsolete/)).toBeInTheDocument();
    expect(screen.getByText('已删除')).toBeInTheDocument();
    expect(screen.queryByText('+ 写一条答案')).not.toBeInTheDocument();
    expect(screen.queryByText('编辑标题')).not.toBeInTheDocument();
    expect(screen.queryByText('删 除')).not.toBeInTheDocument();
  });

  it('disables the per-answer "编辑" link for a soft-deleted knowledge point (Kimi fix on PR #24)', async () => {
    server.use(
      http.get(`${API_BASE}/knowledge-bases/:kbId/knowledge-points/:id`, () =>
        HttpResponse.json(envelope(makeKpDetail({ status: 'deleted', deleted_at: '2026-08-01T00:00:00', delete_reason: 'obsolete' }))),
      ),
    );
    renderPage();
    await screen.findByText(/该知识点已被/);
    const editLink = await screen.findByText('编辑');
    expect(editLink).toHaveAttribute('title', expect.stringContaining('已删除'));
    await userEvent.click(editLink);
    expect(screen.queryByRole('heading', { name: '编辑答案' })).not.toBeInTheDocument();
  });

  it('edits the title and refreshes the header in place', async () => {
    let title = 'kp-1';
    server.use(
      http.get(`${API_BASE}/knowledge-bases/:kbId/knowledge-points/:id`, () =>
        HttpResponse.json(envelope(makeKpDetail({ title }))),
      ),
    );
    server.use(
      http.patch(`${API_BASE}/knowledge-bases/:kbId/knowledge-points/:id`, async ({ request }) => {
        const body = (await request.json()) as { title: string };
        title = body.title;
        return HttpResponse.json(envelope(makeKpDetail({ title })));
      }),
    );
    renderPage();
    await screen.findByText('kp-1');

    await userEvent.click(screen.getByText('编辑标题'));
    // Ambiguous by text alone: the ops button and the modal's own <h3> both
    // read "编辑标题" once the modal is open.
    const dialog = (await screen.findByRole('heading', { name: '编辑标题' })).closest('.modal') as HTMLElement;
    const input = within(dialog).getByDisplayValue('kp-1');
    await userEvent.clear(input);
    await userEvent.type(input, 'renamed-kp');
    await userEvent.click(within(dialog).getByText('确 定'));

    // The ops button's own text is also "编辑标题" and stays in the DOM
    // after the modal closes — assert on the modal heading, not the text.
    await waitFor(() => expect(screen.queryByRole('heading', { name: '编辑标题' })).not.toBeInTheDocument());
    expect(await screen.findByText('renamed-kp')).toBeInTheDocument();
  });

  it('deletes the knowledge point and refreshes in place to the soft-deleted state (no navigation)', async () => {
    let deleted = false;
    server.use(
      http.get(`${API_BASE}/knowledge-bases/:kbId/knowledge-points/:id`, () =>
        HttpResponse.json(
          envelope(
            deleted
              ? makeKpDetail({ status: 'deleted', deleted_at: '2026-08-08T00:00:00', delete_reason: 'test reason' })
              : makeKpDetail(),
          ),
        ),
      ),
    );
    server.use(
      http.post(`${API_BASE}/knowledge-bases/:kbId/knowledge-points/:id/delete`, () => {
        deleted = true;
        return HttpResponse.json(envelope(makeKpDetail({ status: 'deleted' })));
      }),
    );
    renderPage();
    await screen.findByText('kp-1');

    await userEvent.click(screen.getByText('删 除'));
    const dialog = (await screen.findByText('删除知识点')).closest('.modal') as HTMLElement;
    await userEvent.type(within(dialog).getByPlaceholderText('请说明删除原因，将记录在留痕中'), 'test reason');
    await userEvent.click(within(dialog).getByText('确 定 删 除'));

    await waitFor(() => expect(screen.queryByText('删除知识点')).not.toBeInTheDocument());
    expect(await screen.findByText(/该知识点已被/)).toBeInTheDocument();
    // Still on the same page — no navigation — and the URL never changed.
    expect(screen.getByText('kp-1')).toBeInTheDocument();
  });

  it('当前答案 tab: shows all live groups with no filter', async () => {
    server.use(
      http.get(`${API_BASE}/knowledge-bases/:kbId/knowledge-points/:id/answer-groups`, () =>
        HttpResponse.json(
          envelope([
            makeAnswerGroup({ coord: {}, latest_answer: makeAnswer({ content: 'default content' }), live_answer: makeAnswer({ content: 'default content' }) }),
            makeAnswerGroup({
              coord: { tenant: 'acme' },
              latest_answer: makeAnswer({ content: 'acme content' }),
              live_answer: makeAnswer({ content: 'acme content' }),
            }),
          ]),
        ),
      ),
    );
    renderPage();
    await screen.findByText('kp-1');
    expect(await screen.findByText('default content')).toBeInTheDocument();
    expect(screen.getByText('acme content')).toBeInTheDocument();
    expect(screen.getByText(/全部答案 2 条/)).toBeInTheDocument();
  });

  it('当前答案 tab: filters by condition, sorts by priority, and tags the unique top match', async () => {
    server.use(
      http.get(`${API_BASE}/knowledge-bases/:kbId/enabled-dimensions`, () =>
        HttpResponse.json(envelope([makeDimension({ key: 'tenant', label: '租户' })])),
      ),
    );
    server.use(
      http.get(`${API_BASE}/knowledge-bases/:kbId/knowledge-points/:id/answer-groups`, () =>
        HttpResponse.json(
          envelope([
            makeAnswerGroup({ coord: {}, latest_answer: makeAnswer({ content: 'default content' }), live_answer: makeAnswer({ content: 'default content' }) }),
            makeAnswerGroup({
              coord: { tenant: 'acme' },
              latest_answer: makeAnswer({ content: 'acme content' }),
              live_answer: makeAnswer({ content: 'acme content' }),
            }),
          ]),
        ),
      ),
    );
    renderPage();
    await screen.findByText('kp-1');
    await screen.findByText('default content');

    await userEvent.click(screen.getByText('+ 加一个条件'));
    await userEvent.click(await screen.findByText('租户'));
    const input = document.querySelector('.dd-menu input[type="text"]') as HTMLInputElement;
    await userEvent.type(input, 'acme');
    await userEvent.click(screen.getByText('确 定'));

    // The default group (coord={}) is always coord-compatible (§4.6.1) —
    // it stays in the list as a lower-priority fallback, it just doesn't
    // outrank the exact match. Both rows are expected here.
    await waitFor(() => expect(screen.getByText(/满足条件的答案 2 条/)).toBeInTheDocument());
    const rows = document.querySelectorAll('.ans-item');
    expect(rows).toHaveLength(2);
    expect(within(rows[0] as HTMLElement).getByText('acme content')).toBeInTheDocument();
    expect(within(rows[0] as HTMLElement).getByText('此条件下生效')).toBeInTheDocument();
    expect(within(rows[1] as HTMLElement).getByText('default content')).toBeInTheDocument();
    expect(within(rows[1] as HTMLElement).queryByText('此条件下生效')).not.toBeInTheDocument();
  });

  it('当前答案 tab: shows an empty-result hint when nothing matches', async () => {
    server.use(
      http.get(`${API_BASE}/knowledge-bases/:kbId/knowledge-points/:id/answer-groups`, () =>
        HttpResponse.json(envelope([])),
      ),
    );
    renderPage();
    await screen.findByText('kp-1');
    expect(await screen.findByText(/这个条件、这个时间点还没有答案/)).toBeInTheDocument();
  });

  it('omits the `at` query param in "最新" mode and includes it in "回看某天" mode', async () => {
    const seenAtParams: Array<string | null> = [];
    server.use(
      http.get(`${API_BASE}/knowledge-bases/:kbId/knowledge-points/:id/answer-groups`, ({ request }) => {
        seenAtParams.push(new URL(request.url).searchParams.get('at'));
        return HttpResponse.json(envelope([]));
      }),
    );
    renderPage();
    await screen.findByText('kp-1');
    await waitFor(() => expect(seenAtParams.length).toBeGreaterThan(0));
    expect(seenAtParams.every((p) => p === null)).toBe(true);

    await userEvent.click(screen.getByText('回看某天'));
    await waitFor(() => expect(seenAtParams.some((p) => p !== null)).toBe(true));
  });

  it('renders the still-unbuilt tab as an in-development placeholder', async () => {
    renderPage();
    await screen.findByText('kp-1');

    await userEvent.click(screen.getByText('立体全景'));
    expect(await screen.findByText(/立体全景开发中/)).toBeInTheDocument();
  });

  it('renders real content (not a placeholder) for the timeline and logs tabs (issue #14)', async () => {
    renderPage();
    await screen.findByText('kp-1');

    await userEvent.click(screen.getByText('版本历史'));
    expect(await screen.findByText('answer content')).toBeInTheDocument();
    expect(screen.queryByText(/版本历史开发中/)).not.toBeInTheDocument();

    await userEvent.click(screen.getByText('变更留痕'));
    expect(await screen.findByText('写答案')).toBeInTheDocument();
    expect(screen.queryByText(/变更留痕开发中/)).not.toBeInTheDocument();
  });

  it('lets the timeline tab switch between coord groups, and shows a status tag per version (issue #14)', async () => {
    server.use(
      http.get(`${API_BASE}/knowledge-bases/:kbId/knowledge-points/:kpId/answers`, () =>
        HttpResponse.json(
          envelope([
            makeAnswer({ id: 1, coord: {}, coord_hash: 'hash-default', content: 'default version', effective_time: '2000-01-01' }),
            makeAnswer({
              id: 2,
              coord: { tenant: 'acme' },
              coord_hash: 'hash-acme',
              content: 'acme version',
              effective_time: '2000-01-01',
              revoked: true,
            }),
          ]),
        ),
      ),
    );
    renderPage();
    await screen.findByText('kp-1');
    await userEvent.click(screen.getByText('版本历史'));

    expect(await screen.findByText('default version')).toBeInTheDocument();
    expect(screen.getByText('当前')).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByRole('combobox'), '适用条件：租户 = acme');
    expect(await screen.findByText('acme version')).toBeInTheDocument();
    expect(screen.getByText('已撤回')).toBeInTheDocument();
  });

  it('lists timeline coord-group options in a stable, sorted order regardless of backend row order (Kimi 终审 fix on PR #30)', async () => {
    // Backend row order for an unfiltered SELECT isn't a guaranteed
    // contract — deliberately return the groups in the OPPOSITE order
    // from what a sorted-by-label render should produce, so this test
    // would fail if the page just used Map insertion order verbatim.
    server.use(
      http.get(`${API_BASE}/knowledge-bases/:kbId/knowledge-points/:kpId/answers`, () =>
        HttpResponse.json(
          envelope([
            makeAnswer({ id: 1, coord: { tenant: 'zzz' }, coord_hash: 'hash-z', effective_time: '2000-01-01' }),
            makeAnswer({ id: 2, coord: { tenant: 'aaa' }, coord_hash: 'hash-a', effective_time: '2000-01-01' }),
          ]),
        ),
      ),
    );
    renderPage();
    await screen.findByText('kp-1');
    await userEvent.click(screen.getByText('版本历史'));

    const options = await screen.findAllByRole('option');
    const labels = options.map((o) => o.textContent);
    expect(labels).toEqual([...labels].sort((a, b) => (a ?? '').localeCompare(b ?? '')));
  });

  it('can revoke a revocable answer from the change-log tab', async () => {
    server.use(
      http.get(`${API_BASE}/knowledge-bases/:kbId/knowledge-points/:kpId/change-log`, () =>
        HttpResponse.json(envelope([makeChangeLogEntry({ answer_id: 77, revocable: true, after_content: 'revocable content' })])),
      ),
    );
    let requestedPath = '';
    server.use(
      http.post(`${API_BASE}/knowledge-bases/:kbId/knowledge-points/:kpId/answers/:answerId/revoke`, ({ request }) => {
        requestedPath = new URL(request.url).pathname;
        return HttpResponse.json(envelope(makeAnswer({ id: 77, revoked: true })));
      }),
    );
    renderPage();
    await screen.findByText('kp-1');
    await userEvent.click(screen.getByText('变更留痕'));
    await userEvent.click(await screen.findByText('撤回'));

    const dialog = (await screen.findByText('撤回答案')).closest('.modal') as HTMLElement;
    await userEvent.type(within(dialog).getByPlaceholderText('必填，写入留痕'), '测试撤回');
    await userEvent.click(within(dialog).getByText('确 认 撤 回'));

    await screen.findByText('已撤回该条件下的答案');
    expect(requestedPath).toBe('/knowledge-bases/1/knowledge-points/1/answers/77/revoke');
  });

  it('refreshes active_answer_count after creating an answer (invalidation reaches the single-KP fetch)', async () => {
    let count = 1;
    server.use(
      http.get(`${API_BASE}/knowledge-bases/:kbId/knowledge-points/:id`, () =>
        HttpResponse.json(envelope(makeKpDetail({ active_answer_count: count }))),
      ),
    );
    server.use(
      http.post(`${API_BASE}/knowledge-bases/:kbId/knowledge-points/:kpId/answers`, () => {
        count = 2;
        return HttpResponse.json(envelope(makeAnswer({ id: 50 })));
      }),
    );
    renderPage();
    await screen.findByText('1 条在用答案');

    await userEvent.click(screen.getByText('+ 写一条答案'));
    const dialog = (await screen.findByText('写一条答案')).closest('.modal') as HTMLElement;
    await userEvent.type(within(dialog).getByPlaceholderText('这个条件组合下的说法'), 'brand new answer');
    await userEvent.click(within(dialog).getByText('确 定'));

    await waitFor(() => expect(screen.queryByText('写一条答案')).not.toBeInTheDocument());
    expect(await screen.findByText('2 条在用答案')).toBeInTheDocument();
  });
});
