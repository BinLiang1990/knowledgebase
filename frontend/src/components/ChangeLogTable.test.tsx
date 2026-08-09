import { describe, expect, it } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ChangeLogTable } from './ChangeLogTable';
import { renderWithProviders } from '../test/renderWithProviders';
import { API_BASE, HttpResponse, envelope, http, makeChangeLogEntry, makeGlobalChangeLogEntry, server } from '../test/server';

describe('ChangeLogTable', () => {
  it('renders an empty state when there are no entries', () => {
    renderWithProviders(<ChangeLogTable entries={[]} kbId={1} kpId={1} />);
    expect(screen.getByText('暂无变更记录')).toBeInTheDocument();
  });

  it('renders knowledge-point-scoped entries without the location columns', () => {
    renderWithProviders(
      <ChangeLogTable entries={[makeChangeLogEntry({ action: 'edit', source: '人工编辑' })]} kbId={1} kpId={1} />,
    );
    expect(screen.getByText('改答案')).toBeInTheDocument();
    expect(screen.getByText('人工编辑')).toBeInTheDocument();
    expect(screen.queryByText('知识库')).not.toBeInTheDocument();
  });

  it('renders the location columns and a working link when showLocation is true', () => {
    renderWithProviders(
      <ChangeLogTable
        entries={[makeGlobalChangeLogEntry({ knowledge_base_id: 3, knowledge_point_id: 5, knowledge_point_title: 'kp-5', knowledge_base_name: 'kb-3' })]}
        showLocation
      />,
    );
    expect(screen.getByText('kb-3')).toBeInTheDocument();
    const link = screen.getByText('kp-5').closest('a');
    expect(link).toHaveAttribute('href', '/knowledge-bases/3/knowledge-points/5');
  });

  it('shows a "—" dash in the operations column, not a revoke link, when revocable is false', () => {
    renderWithProviders(
      <ChangeLogTable entries={[makeChangeLogEntry({ revocable: false, status: 'revoked' })]} kbId={1} kpId={1} />,
    );
    expect(screen.queryByText('撤回')).not.toBeInTheDocument();
    const opsCell = document.querySelector('td.op-col') as HTMLElement;
    expect(within(opsCell).getByText('—')).toBeInTheDocument();
  });

  it('requires a reason before submitting a revoke', async () => {
    renderWithProviders(
      <ChangeLogTable entries={[makeChangeLogEntry({ revocable: true, after_content: 'the content' })]} kbId={1} kpId={1} />,
    );
    await userEvent.click(screen.getByText('撤回'));
    const dialog = (await screen.findByText('撤回答案')).closest('.modal') as HTMLElement;
    expect(within(dialog).getByText('the content')).toBeInTheDocument();

    await userEvent.click(within(dialog).getByText('确 认 撤 回'));
    expect(await within(dialog).findByText('请填写撤回原因。')).toBeInTheDocument();
  });

  it('submits a revoke with the row\'s own kbId/kpId in the global (showLocation) mode', async () => {
    let requestedPath = '';
    server.use(
      http.post(`${API_BASE}/knowledge-bases/:kbId/knowledge-points/:kpId/answers/:answerId/revoke`, ({ request }) => {
        requestedPath = new URL(request.url).pathname;
        return HttpResponse.json(envelope(makeChangeLogEntry()));
      }),
    );
    renderWithProviders(
      <ChangeLogTable
        entries={[makeGlobalChangeLogEntry({ knowledge_base_id: 7, knowledge_point_id: 9, answer_id: 42, revocable: true })]}
        showLocation
      />,
    );
    await userEvent.click(screen.getByText('撤回'));
    const dialog = (await screen.findByText('撤回答案')).closest('.modal') as HTMLElement;
    await userEvent.type(within(dialog).getByPlaceholderText('必填，写入留痕'), '测试');
    await userEvent.click(within(dialog).getByText('确 认 撤 回'));

    await screen.findByText('已撤回该条件下的答案');
    expect(requestedPath).toBe('/knowledge-bases/7/knowledge-points/9/answers/42/revoke');
  });
});
