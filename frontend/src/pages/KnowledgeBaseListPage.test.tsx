import { describe, expect, it } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { KnowledgeBaseListPage } from './KnowledgeBaseListPage';
import { renderWithProviders } from '../test/renderWithProviders';
import { API_BASE, HttpResponse, envelope, errorEnvelope, http, makeKb, server } from '../test/server';

describe('KnowledgeBaseListPage', () => {
  it('renders the loaded list', async () => {
    renderWithProviders(<KnowledgeBaseListPage />);
    expect(await screen.findByText('kb-1')).toBeInTheDocument();
    expect(screen.getByText('启用中')).toBeInTheDocument();
  });

  it('renders an empty state when there are no knowledge bases', async () => {
    server.use(http.get(`${API_BASE}/knowledge-bases`, () => HttpResponse.json(envelope([]))));
    renderWithProviders(<KnowledgeBaseListPage />);
    expect(await screen.findByText(/暂无知识库/)).toBeInTheDocument();
  });

  it('renders a failure state with a retry link on error', async () => {
    server.use(http.get(`${API_BASE}/knowledge-bases`, () => HttpResponse.json(errorEnvelope('数据库异常'), { status: 500 })));
    renderWithProviders(<KnowledgeBaseListPage />);
    expect(await screen.findByText(/加载失败/)).toBeInTheDocument();
  });

  it('filters by keyword on Enter', async () => {
    server.use(
      http.get(`${API_BASE}/knowledge-bases`, () =>
        HttpResponse.json(envelope([makeKb({ id: 1, name: 'refund-policy' }), makeKb({ id: 2, name: 'invoice-process' })])),
      ),
    );
    renderWithProviders(<KnowledgeBaseListPage />);
    await screen.findByText('refund-policy');

    const input = screen.getByPlaceholderText('搜索知识库名称或描述');
    await userEvent.type(input, 'refund{Enter}');

    expect(screen.getByText('refund-policy')).toBeInTheDocument();
    expect(screen.queryByText('invoice-process')).not.toBeInTheDocument();
  });

  it('shows an inline validation hint when submitting a blank name', async () => {
    renderWithProviders(<KnowledgeBaseListPage />);
    await screen.findByText('kb-1');

    await userEvent.click(screen.getByText('+ 新增知识库'));
    const modal = await screen.findByText('新增知识库');
    const dialog = modal.closest('.modal') as HTMLElement;
    await userEvent.click(within(dialog).getByText('确 定'));

    expect(await within(dialog).findByText('请填写知识库名称。')).toBeInTheDocument();
  });

  it('creates a knowledge base and refreshes the list', async () => {
    renderWithProviders(<KnowledgeBaseListPage />);
    await screen.findByText('kb-1');

    await userEvent.click(screen.getByText('+ 新增知识库'));
    const dialog = (await screen.findByText('新增知识库')).closest('.modal') as HTMLElement;
    await userEvent.type(within(dialog).getByPlaceholderText('例如：产品知识库'), 'new-kb');
    await userEvent.click(within(dialog).getByText('确 定'));

    await waitFor(() => expect(screen.queryByText('新增知识库')).not.toBeInTheDocument());
    expect(await screen.findByText(/已创建知识库/)).toBeInTheDocument();
  });

  it('shows the backend error inline on duplicate name instead of closing the modal', async () => {
    server.use(http.post(`${API_BASE}/knowledge-bases`, () => HttpResponse.json(errorEnvelope('知识库名称已存在，请使用其他名称'), { status: 400 })));
    renderWithProviders(<KnowledgeBaseListPage />);
    await screen.findByText('kb-1');

    await userEvent.click(screen.getByText('+ 新增知识库'));
    const dialog = (await screen.findByText('新增知识库')).closest('.modal') as HTMLElement;
    await userEvent.type(within(dialog).getByPlaceholderText('例如：产品知识库'), 'kb-1');
    await userEvent.click(within(dialog).getByText('确 定'));

    expect(await within(dialog).findByText('知识库名称已存在，请使用其他名称')).toBeInTheDocument();
    expect(screen.getByText('新增知识库')).toBeInTheDocument();
  });

  it('opens the edit modal pre-filled with existing values', async () => {
    server.use(
      http.get(`${API_BASE}/knowledge-bases`, () =>
        HttpResponse.json(envelope([makeKb({ name: 'edit-me', description: 'old desc' })])),
      ),
    );
    renderWithProviders(<KnowledgeBaseListPage />);
    await screen.findByText('edit-me');

    await userEvent.click(screen.getByText('编辑'));
    const dialog = (await screen.findByText('编辑知识库 · edit-me')).closest('.modal') as HTMLElement;
    expect(within(dialog).getByDisplayValue('edit-me')).toBeInTheDocument();
    expect(within(dialog).getByDisplayValue('old desc')).toBeInTheDocument();
  });

  it('shows the risk block only when deactivating, not when activating', async () => {
    server.use(
      http.get(`${API_BASE}/knowledge-bases`, () =>
        HttpResponse.json(
          envelope([
            makeKb({ id: 1, name: 'active-kb', status: 'active' }),
            makeKb({ id: 2, name: 'deprecated-kb', status: 'deprecated' }),
          ]),
        ),
      ),
    );
    renderWithProviders(<KnowledgeBaseListPage />);
    await screen.findByText('active-kb');

    await userEvent.click(screen.getAllByText('停用')[0]);
    let dialog = (await screen.findByText('停用知识库')).closest('.modal') as HTMLElement;
    expect(within(dialog).getByText(/停用后知识库列表不再显示/)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByText('取 消'));

    await userEvent.click(screen.getByText('启用'));
    dialog = (await screen.findByText('启用知识库')).closest('.modal') as HTMLElement;
    expect(within(dialog).queryByText(/停用后知识库列表不再显示/)).not.toBeInTheDocument();
  });

  it('confirming deactivate calls the deactivate endpoint and refreshes', async () => {
    let calledDeactivate = false;
    server.use(
      http.post(`${API_BASE}/knowledge-bases/:id/deactivate`, () => {
        calledDeactivate = true;
        return HttpResponse.json(envelope(makeKb({ status: 'deprecated' })));
      }),
    );
    renderWithProviders(<KnowledgeBaseListPage />);
    await screen.findByText('kb-1');

    await userEvent.click(screen.getByText('停用'));
    const dialog = (await screen.findByText('停用知识库')).closest('.modal') as HTMLElement;
    await userEvent.click(within(dialog).getByText('确 定'));

    await waitFor(() => expect(calledDeactivate).toBe(true));
  });
});
