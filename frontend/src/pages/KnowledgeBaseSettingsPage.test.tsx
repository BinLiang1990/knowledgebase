import { describe, expect, it } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient } from '@tanstack/react-query';
import { Route, Routes, useNavigate } from 'react-router-dom';
import { KnowledgeBaseSettingsPage } from './KnowledgeBaseSettingsPage';
import { ADMIN_DIMENSIONS_KEY } from '../api/dimensions';
import { renderWithProviders } from '../test/renderWithProviders';
import {
  API_BASE,
  HttpResponse,
  envelope,
  errorEnvelope,
  http,
  makeAdminDimension,
  makeDimension,
  makeKb,
  server,
} from '../test/server';

function renderPage(initialPath = '/knowledge-bases/1/settings') {
  return renderWithProviders(
    <Routes>
      <Route path="/knowledge-bases/:kbId/settings" element={<KnowledgeBaseSettingsPage />} />
    </Routes>,
    { initialEntries: [initialPath] },
  );
}

// Simulates a client-side navigation between two knowledge bases' settings
// pages that stays on the same matched route (only :kbId changes) — the
// scenario React Router does NOT unmount/remount the page for, unlike
// navigating away through a different route entirely.
function NavigateTo({ path }: { path: string }) {
  const navigate = useNavigate();
  return (
    <button type="button" onClick={() => navigate(path)}>
      go
    </button>
  );
}

function renderPageWithNav(targetPath: string, initialPath = '/knowledge-bases/1/settings') {
  return renderWithProviders(
    <>
      <NavigateTo path={targetPath} />
      <Routes>
        <Route path="/knowledge-bases/:kbId/settings" element={<KnowledgeBaseSettingsPage />} />
      </Routes>
    </>,
    { initialEntries: [initialPath] },
  );
}

describe('KnowledgeBaseSettingsPage', () => {
  it('renders the active-dimension checklist with the currently enabled ones checked', async () => {
    server.use(
      http.get(`${API_BASE}/admin/dimensions`, () =>
        HttpResponse.json(
          envelope([
            makeAdminDimension({ key: 'tenant', label: '租户', status: 'active', answer_count: 12 }),
            makeAdminDimension({ key: 'region', label: '地区', status: 'active', answer_count: 0 }),
            makeAdminDimension({ key: 'old-dim', label: '旧维度', status: 'deprecated' }),
          ]),
        ),
      ),
      http.get(`${API_BASE}/knowledge-bases/:kbId/enabled-dimensions`, () =>
        HttpResponse.json(envelope([makeDimension({ key: 'tenant', label: '租户' })])),
      ),
    );
    renderPage();

    expect(await screen.findByText('租户')).toBeInTheDocument();
    expect(screen.getByText('地区')).toBeInTheDocument();
    expect(screen.queryByText('旧维度')).not.toBeInTheDocument();

    const tenantCheckbox = screen.getByRole('checkbox', { name: /租户/ });
    const regionCheckbox = screen.getByRole('checkbox', { name: /地区/ });
    expect(tenantCheckbox).toBeChecked();
    expect(regionCheckbox).not.toBeChecked();

    expect(screen.getByText('全局共 12 条答案在用')).toBeInTheDocument();
  });

  it('shows an empty state with a link to dimension management when there are no active dimensions', async () => {
    server.use(http.get(`${API_BASE}/admin/dimensions`, () => HttpResponse.json(envelope([]))));
    renderPage();
    expect(await screen.findByText(/还没有任何启用中的全局维度/)).toBeInTheDocument();
  });

  it('does not render KbTabs for a malformed (non-numeric) :kbId while the knowledge-base fetch is still loading/failing (Kimi 终审 fix on PR #29)', async () => {
    server.use(http.get(`${API_BASE}/knowledge-bases`, () => HttpResponse.json(errorEnvelope('数据库异常'), { status: 500 })));
    const { container } = renderPage('/knowledge-bases/abc/settings');
    await screen.findByText(/加载知识库失败/);
    expect(container.querySelector('.kb-tabs')).toBeNull();
  });

  it('seeds from the fresh refetch, not a stale cached snapshot, on remount (Codex outer-gate fix on PR #29, round 4)', async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    // Simulate "visited this page earlier in the session, left, and the
    // enabled set changed elsewhere (e.g. the dimension got deactivated)
    // before coming back" — TanStack Query still holds this stale entry
    // and returns it instantly on the next render, before the background
    // refetch this same render triggers has resolved.
    queryClient.setQueryData(
      ['knowledge-bases', 1, 'enabled-dimensions'],
      [makeDimension({ key: 'tenant', label: '租户' })],
    );

    server.use(
      http.get(`${API_BASE}/admin/dimensions`, () =>
        HttpResponse.json(envelope([makeAdminDimension({ key: 'tenant', label: '租户' })])),
      ),
      http.get(`${API_BASE}/knowledge-bases/:kbId/enabled-dimensions`, async () => {
        await new Promise((resolve) => setTimeout(resolve, 20));
        return HttpResponse.json(envelope([])); // fresh: no longer enabled
      }),
    );

    renderWithProviders(
      <Routes>
        <Route path="/knowledge-bases/:kbId/settings" element={<KnowledgeBaseSettingsPage />} />
      </Routes>,
      { initialEntries: ['/knowledge-bases/1/settings'], queryClient },
    );

    await screen.findByText('租户');
    // Must end up unchecked once the fresh (empty) response lands, not
    // stuck on the stale cached "checked" snapshot forever.
    await waitFor(() => expect(screen.getByRole('checkbox', { name: /租户/ })).not.toBeChecked());
  });

  it('filters out a checked key that got globally deactivated while this page was open, before submitting (Codex outer-gate fix on PR #29, round 6)', async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    let tenantActive = true;
    server.use(
      http.get(`${API_BASE}/admin/dimensions`, () =>
        HttpResponse.json(
          envelope([makeAdminDimension({ key: 'tenant', label: '租户', status: tenantActive ? 'active' : 'deprecated' })]),
        ),
      ),
      http.get(`${API_BASE}/knowledge-bases/:kbId/enabled-dimensions`, () =>
        HttpResponse.json(envelope([makeDimension({ key: 'tenant', label: '租户' })])),
      ),
    );
    let receivedBody: unknown;
    server.use(
      http.put(`${API_BASE}/knowledge-bases/:kbId/enabled-dimensions`, async ({ request }) => {
        receivedBody = await request.json();
        return HttpResponse.json(envelope([]));
      }),
    );

    renderWithProviders(
      <Routes>
        <Route path="/knowledge-bases/:kbId/settings" element={<KnowledgeBaseSettingsPage />} />
      </Routes>,
      { initialEntries: ['/knowledge-bases/1/settings'], queryClient },
    );

    await screen.findByText('租户');
    expect(screen.getByRole('checkbox', { name: /租户/ })).toBeChecked();

    // Simulate "tenant" being deactivated elsewhere while this page stays
    // open — the same cache invalidation useSetDimensionStatus performs
    // for a real deactivation from the dimensions page.
    tenantActive = false;
    await queryClient.invalidateQueries({ queryKey: ADMIN_DIMENSIONS_KEY });
    await waitFor(() => expect(screen.queryByText('租户')).not.toBeInTheDocument());

    await userEvent.click(screen.getByText('保 存'));

    // checkedKeys still (invisibly) holds "tenant", but it must be
    // filtered out before submitting — otherwise every save would fail
    // with "已停用，无法启用" and there'd be no checkbox left to uncheck.
    await waitFor(() => expect(receivedBody).toEqual({ dimension_keys: [] }));
  });

  it('re-seeds the checklist for a different knowledge base after an in-place :kbId route change (Codex outer-gate fix on PR #29, round 3)', async () => {
    server.use(
      http.get(`${API_BASE}/knowledge-bases`, () =>
        HttpResponse.json(envelope([makeKb({ id: 1 }), makeKb({ id: 2, name: 'kb-2' })])),
      ),
      http.get(`${API_BASE}/admin/dimensions`, () =>
        HttpResponse.json(envelope([makeAdminDimension({ key: 'tenant', label: '租户' })])),
      ),
      http.get(`${API_BASE}/knowledge-bases/:kbId/enabled-dimensions`, ({ params }) =>
        HttpResponse.json(envelope(params.kbId === '1' ? [makeDimension({ key: 'tenant', label: '租户' })] : [])),
      ),
    );
    renderPageWithNav('/knowledge-bases/2/settings');

    await screen.findByText('租户');
    expect(screen.getByRole('checkbox', { name: /租户/ })).toBeChecked();

    await userEvent.click(screen.getByText('go'));

    // Same dimension, now for kb 2 (which has nothing enabled) — must show
    // unchecked, not still-checked state carried over from kb 1.
    await screen.findByText('租户');
    expect(screen.getByRole('checkbox', { name: /租户/ })).not.toBeChecked();
  });

  it('shows a retryable failure state, not a permanent spinner, when the enabled-dimensions fetch fails (Codex outer-gate fix on PR #29)', async () => {
    server.use(
      http.get(`${API_BASE}/admin/dimensions`, () => HttpResponse.json(envelope([makeAdminDimension()]))),
      http.get(`${API_BASE}/knowledge-bases/:kbId/enabled-dimensions`, () =>
        HttpResponse.json(errorEnvelope('数据库异常'), { status: 500 }),
      ),
    );
    renderPage();
    expect(await screen.findByText(/加载失败/)).toBeInTheDocument();
    expect(screen.queryByText(/加载中/)).not.toBeInTheDocument();
  });

  it('keeps the save button disabled on a load failure, so it cannot submit an empty set and wipe enabled dimensions (Codex outer-gate fix on PR #29, round 2)', async () => {
    server.use(
      http.get(`${API_BASE}/admin/dimensions`, () => HttpResponse.json(envelope([makeAdminDimension()]))),
      http.get(`${API_BASE}/knowledge-bases/:kbId/enabled-dimensions`, () =>
        HttpResponse.json(errorEnvelope('数据库异常'), { status: 500 }),
      ),
    );
    renderPage();
    await screen.findByText(/加载失败/);
    expect(screen.getByText('保 存')).toBeDisabled();
  });

  it('saves the exact snapshot of checked keys at save time', async () => {
    server.use(
      http.get(`${API_BASE}/admin/dimensions`, () =>
        HttpResponse.json(
          envelope([
            makeAdminDimension({ key: 'tenant', label: '租户' }),
            makeAdminDimension({ key: 'region', label: '地区' }),
          ]),
        ),
      ),
      http.get(`${API_BASE}/knowledge-bases/:kbId/enabled-dimensions`, () =>
        HttpResponse.json(envelope([makeDimension({ key: 'tenant', label: '租户' })])),
      ),
    );
    let receivedBody: unknown;
    server.use(
      http.put(`${API_BASE}/knowledge-bases/:kbId/enabled-dimensions`, async ({ request }) => {
        receivedBody = await request.json();
        return HttpResponse.json(envelope([]));
      }),
    );
    renderPage();
    await screen.findByText('租户');

    await userEvent.click(screen.getByRole('checkbox', { name: /租户/ })); // uncheck
    await userEvent.click(screen.getByRole('checkbox', { name: /地区/ })); // check
    await userEvent.click(screen.getByText('保 存'));

    expect(await screen.findByText('已保存本知识库启用的维度')).toBeInTheDocument();
    expect(receivedBody).toEqual({ dimension_keys: ['region'] });
  });

  it('shows an inline error, not a toast, when save fails', async () => {
    server.use(
      http.get(`${API_BASE}/admin/dimensions`, () => HttpResponse.json(envelope([makeAdminDimension()]))),
      http.put(`${API_BASE}/knowledge-bases/:kbId/enabled-dimensions`, () =>
        HttpResponse.json(errorEnvelope('维度「tenant」已停用，无法启用'), { status: 400 }),
      ),
    );
    renderPage();
    await screen.findByText('租户');

    await userEvent.click(screen.getByText('保 存'));

    expect(await screen.findByText('维度「tenant」已停用，无法启用')).toBeInTheDocument();
  });

  it('renders the guided empty state for an invalid knowledge base without KbTabs', async () => {
    server.use(http.get(`${API_BASE}/knowledge-bases`, () => HttpResponse.json(envelope([]))));
    renderPage('/knowledge-bases/999/settings');
    expect(await screen.findByText(/没有指定有效的知识库/)).toBeInTheDocument();
    expect(screen.queryByText('知识点列表')).not.toBeInTheDocument();
  });

  it('renders KbTabs with the settings tab active', async () => {
    server.use(http.get(`${API_BASE}/knowledge-bases`, () => HttpResponse.json(envelope([makeKb({ id: 1 })]))));
    const { container } = renderPage();
    await screen.findByText('租户');
    const tabs = container.querySelector('.kb-tabs') as HTMLElement;
    expect(within(tabs).getByText('知识库设置')).toHaveClass('active');
    expect(within(tabs).getByText('知识点列表')).not.toHaveClass('active');
  });
});
