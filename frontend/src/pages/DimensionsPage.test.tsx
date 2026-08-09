import { describe, expect, it } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DimensionsPage } from './DimensionsPage';
import { renderWithProviders } from '../test/renderWithProviders';
import { API_BASE, HttpResponse, envelope, errorEnvelope, http, makeAdminDimension, server } from '../test/server';

function renderPage() {
  return renderWithProviders(<DimensionsPage />);
}

describe('DimensionsPage', () => {
  it('renders the loaded dimension list', async () => {
    renderPage();
    expect(await screen.findByText('租户')).toBeInTheDocument();
    expect(screen.getByText('tenant')).toBeInTheDocument();
    expect(screen.getByText('文本')).toBeInTheDocument();
    expect(screen.getByText('启用中')).toBeInTheDocument();
  });

  it('renders an empty state when there are no dimensions', async () => {
    server.use(http.get(`${API_BASE}/admin/dimensions`, () => HttpResponse.json(envelope([]))));
    renderPage();
    expect(await screen.findByText(/暂无维度定义/)).toBeInTheDocument();
  });

  it('renders a failure state with a retry link on error', async () => {
    server.use(
      http.get(`${API_BASE}/admin/dimensions`, () => HttpResponse.json(errorEnvelope('数据库异常'), { status: 500 })),
    );
    renderPage();
    expect(await screen.findByText(/加载失败/)).toBeInTheDocument();
  });

  it('shows an inline validation hint when submitting a blank name', async () => {
    renderPage();
    await screen.findByText('租户');

    await userEvent.click(screen.getByText('+ 新增维度'));
    const modal = await screen.findByText('新增维度');
    const dialog = modal.closest('.modal') as HTMLElement;
    await userEvent.click(within(dialog).getByText('确 定'));

    expect(await within(dialog).findByText('请填写维度名称。')).toBeInTheDocument();
  });

  it('rejects a name containing a slash on create', async () => {
    renderPage();
    await screen.findByText('租户');

    await userEvent.click(screen.getByText('+ 新增维度'));
    const dialog = (await screen.findByText('新增维度')).closest('.modal') as HTMLElement;
    await userEvent.type(within(dialog).getByPlaceholderText('例如：部门 / 标签 / 复核周期'), 'a/b');
    await userEvent.click(within(dialog).getByText('确 定'));

    expect(await within(dialog).findByText('名称不能包含斜杠(/)')).toBeInTheDocument();
  });

  it('rejects a name containing a slash on edit too (stricter than the backend on purpose)', async () => {
    renderPage();
    await screen.findByText('租户');

    await userEvent.click(screen.getByText('编辑'));
    const dialog = (await screen.findByText('编辑维度 · 租户')).closest('.modal') as HTMLElement;
    const nameInput = within(dialog).getByDisplayValue('租户');
    await userEvent.clear(nameInput);
    await userEvent.type(nameInput, 'a/b');
    await userEvent.click(within(dialog).getByText('确 定'));

    expect(await within(dialog).findByText('名称不能包含斜杠(/)')).toBeInTheDocument();
  });

  it('creates a dimension and refreshes the list', async () => {
    renderPage();
    await screen.findByText('租户');

    await userEvent.click(screen.getByText('+ 新增维度'));
    const dialog = (await screen.findByText('新增维度')).closest('.modal') as HTMLElement;
    await userEvent.type(within(dialog).getByPlaceholderText('例如：部门 / 标签 / 复核周期'), '部门');
    await userEvent.click(within(dialog).getByText('确 定'));

    expect(await screen.findByText(/已新增维度/)).toBeInTheDocument();
  });

  it('disables the field type select when editing, but still shows the current value', async () => {
    renderPage();
    await screen.findByText('租户');

    await userEvent.click(screen.getByText('编辑'));
    const dialog = (await screen.findByText('编辑维度 · 租户')).closest('.modal') as HTMLElement;
    const select = within(dialog).getByDisplayValue('文本') as HTMLSelectElement;
    expect(select).toBeDisabled();
  });

  it('editing without touching the default value hint leaves it unchanged', async () => {
    server.use(
      http.get(`${API_BASE}/admin/dimensions`, () =>
        HttpResponse.json(envelope([makeAdminDimension({ default_value: 'HQ' })])),
      ),
    );
    let receivedBody: unknown;
    server.use(
      http.patch(`${API_BASE}/dimensions/:key`, async ({ request }) => {
        receivedBody = await request.json();
        return HttpResponse.json(envelope(makeAdminDimension({ default_value: 'HQ' })));
      }),
    );
    renderPage();
    await screen.findByText('租户');

    await userEvent.click(screen.getByText('编辑'));
    const dialog = (await screen.findByText('编辑维度 · 租户')).closest('.modal') as HTMLElement;
    await userEvent.click(within(dialog).getByText('确 定'));

    await screen.findByText(/已更新维度/);
    expect(receivedBody).toMatchObject({ default_value: 'HQ' });
  });

  it('clearing the default value hint submits null, not the old value', async () => {
    server.use(
      http.get(`${API_BASE}/admin/dimensions`, () =>
        HttpResponse.json(envelope([makeAdminDimension({ default_value: 'HQ' })])),
      ),
    );
    let receivedBody: unknown;
    server.use(
      http.patch(`${API_BASE}/dimensions/:key`, async ({ request }) => {
        receivedBody = await request.json();
        return HttpResponse.json(envelope(makeAdminDimension({ default_value: null })));
      }),
    );
    renderPage();
    await screen.findByText('租户');

    await userEvent.click(screen.getByText('编辑'));
    const dialog = (await screen.findByText('编辑维度 · 租户')).closest('.modal') as HTMLElement;
    const defaultValueInput = within(dialog).getByDisplayValue('HQ');
    await userEvent.clear(defaultValueInput);
    await userEvent.click(within(dialog).getByText('确 定'));

    await screen.findByText(/已更新维度/);
    expect(receivedBody).toMatchObject({ default_value: null });
  });

  it('deactivating an in-use dimension shows the impact warning', async () => {
    server.use(
      http.get(`${API_BASE}/admin/dimensions`, () =>
        HttpResponse.json(envelope([makeAdminDimension({ answer_count: 7 })])),
      ),
    );
    renderPage();
    await screen.findByText('租户');

    await userEvent.click(screen.getByText('停用'));
    const dialog = (await screen.findByText('停用维度')).closest('.modal') as HTMLElement;
    expect(within(dialog).getByText(/7 条答案/)).toBeInTheDocument();
  });

  it('surfaces a business error from the backend on create instead of a generic message', async () => {
    server.use(http.post(`${API_BASE}/dimensions`, () => HttpResponse.json(errorEnvelope('维度已存在，请使用其他名称'), { status: 400 })));
    renderPage();
    await screen.findByText('租户');

    await userEvent.click(screen.getByText('+ 新增维度'));
    const dialog = (await screen.findByText('新增维度')).closest('.modal') as HTMLElement;
    await userEvent.type(within(dialog).getByPlaceholderText('例如：部门 / 标签 / 复核周期'), '租户');
    await userEvent.click(within(dialog).getByText('确 定'));

    expect(await within(dialog).findByText('维度已存在，请使用其他名称')).toBeInTheDocument();
  });
});
