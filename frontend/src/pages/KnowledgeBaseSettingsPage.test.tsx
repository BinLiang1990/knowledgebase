import { describe, expect, it } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { KnowledgeBaseSettingsPage } from './KnowledgeBaseSettingsPage';
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
