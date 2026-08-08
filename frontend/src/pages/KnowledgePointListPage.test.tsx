import { describe, expect, it } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { KnowledgePointListPage } from './KnowledgePointListPage';
import { renderWithProviders } from '../test/renderWithProviders';
import {
  API_BASE,
  HttpResponse,
  envelope,
  http,
  makeAnswer,
  makeAnswerGroup,
  makeDimension,
  makeKb,
  makeKp,
  makeResolved,
  server,
} from '../test/server';

function renderPage(initialPath = '/knowledge-bases/1/knowledge-points') {
  return renderWithProviders(
    <Routes>
      <Route path="/knowledge-bases/:kbId/knowledge-points" element={<KnowledgePointListPage />} />
    </Routes>,
    { initialEntries: [initialPath] },
  );
}

describe('KnowledgePointListPage', () => {
  it('renders the loaded list with its resolved preview', async () => {
    renderPage();
    expect(await screen.findByText('kp-1')).toBeInTheDocument();
  });

  it('shows a guard when the knowledge base does not exist', async () => {
    server.use(http.get(`${API_BASE}/knowledge-bases`, () => HttpResponse.json(envelope([]))));
    renderPage('/knowledge-bases/999/knowledge-points');
    expect(await screen.findByText(/没有指定有效的知识库/)).toBeInTheDocument();
  });

  it('shows a guard when the knowledge base is deactivated', async () => {
    server.use(http.get(`${API_BASE}/knowledge-bases`, () => HttpResponse.json(envelope([makeKb({ status: 'deprecated' })]))));
    renderPage();
    expect(await screen.findByText(/没有指定有效的知识库/)).toBeInTheDocument();
  });

  it.each([
    ['exact', '精确命中'],
    ['weighted', '未精确命中 · 按权重回退'],
    ['default', '默认'],
    ['fallback-latest', '无默认 · 取最新'],
  ] as const)('renders the %s hit-mode tag', async (status, tagText) => {
    server.use(
      http.get(`${API_BASE}/knowledge-bases/:kbId/knowledge-points`, () =>
        HttpResponse.json(envelope([makeKp({ resolved: makeResolved({ status, answer: makeAnswer({ content: 'preview text' }) }) })])),
      ),
    );
    renderPage();
    // answer.content is a bare text node mixed with sibling elements
    // (coord chips, hit-mode tag) inside .trow-ans, not wrapped in its own
    // element — exact-string matching finds no element whose full text
    // equals just "preview text", even though it's genuinely present.
    await screen.findByText(/preview text/);
    expect(screen.getByText(tagText)).toBeInTheDocument();
  });

  it('renders the none-status fallback text when a knowledge point has no answers', async () => {
    server.use(
      http.get(`${API_BASE}/knowledge-bases/:kbId/knowledge-points`, () =>
        HttpResponse.json(envelope([makeKp({ resolved: { status: 'none', answer: null } })])),
      ),
    );
    renderPage();
    expect(await screen.findByText('还没有写过任何答案')).toBeInTheDocument();
  });

  it('the condition picker only lists this KB\'s enabled dimensions', async () => {
    renderPage();
    await screen.findByText('kp-1');
    await userEvent.click(screen.getByText('+ 加一个条件'));
    expect(await screen.findByText('租户')).toBeInTheDocument();
  });

  it('submits a boolean filter as a real JSON boolean, not a string', async () => {
    server.use(
      http.get(`${API_BASE}/knowledge-bases/:kbId/enabled-dimensions`, () =>
        HttpResponse.json(envelope([makeDimension({ key: 'is_vip', label: '是否VIP', field_type: 'boolean' })])),
      ),
    );
    let receivedCoordParam: string | null = null;
    server.use(
      http.get(`${API_BASE}/knowledge-bases/:kbId/knowledge-points`, ({ request }) => {
        const url = new URL(request.url);
        if (url.searchParams.has('coord')) receivedCoordParam = url.searchParams.get('coord');
        return HttpResponse.json(envelope([makeKp()]));
      }),
    );

    renderPage();
    await screen.findByText('kp-1');
    await userEvent.click(screen.getByText('+ 加一个条件'));
    await userEvent.click(await screen.findByText('是否VIP'));
    await userEvent.click(screen.getByText('确 定'));

    await waitFor(() => expect(receivedCoordParam).not.toBeNull());
    expect(JSON.parse(receivedCoordParam!)).toEqual({ is_vip: true });
  });

  it('submits a number filter as a string, not a JS Number', async () => {
    server.use(
      http.get(`${API_BASE}/knowledge-bases/:kbId/enabled-dimensions`, () =>
        HttpResponse.json(envelope([makeDimension({ key: 'priority', label: '优先级', field_type: 'number' })])),
      ),
    );
    let receivedCoordParam: string | null = null;
    server.use(
      http.get(`${API_BASE}/knowledge-bases/:kbId/knowledge-points`, ({ request }) => {
        const url = new URL(request.url);
        if (url.searchParams.has('coord')) receivedCoordParam = url.searchParams.get('coord');
        return HttpResponse.json(envelope([makeKp()]));
      }),
    );

    renderPage();
    await screen.findByText('kp-1');
    await userEvent.click(screen.getByText('+ 加一个条件'));
    await userEvent.click(await screen.findByText('优先级'));
    const input = document.querySelector('.dd-menu input[type="number"]') as HTMLInputElement;
    await userEvent.type(input, '5');
    await userEvent.click(screen.getByText('确 定'));

    await waitFor(() => expect(receivedCoordParam).not.toBeNull());
    const parsed = JSON.parse(receivedCoordParam!);
    expect(parsed).toEqual({ priority: '5' });
    expect(typeof parsed.priority).toBe('string');
  });

  it('does not fetch answer-groups for a collapsed row', async () => {
    let groupsRequested = false;
    server.use(
      http.get(`${API_BASE}/knowledge-bases/:kbId/knowledge-points/:id/answer-groups`, () => {
        groupsRequested = true;
        return HttpResponse.json(envelope([]));
      }),
    );
    renderPage();
    await screen.findByText('kp-1');
    expect(groupsRequested).toBe(false);
  });

  it('expanding a row fetches and renders its answer-group tree', async () => {
    const treeAnswer = makeAnswer({ content: 'tree content' });
    server.use(
      http.get(`${API_BASE}/knowledge-bases/:kbId/knowledge-points/:id/answer-groups`, () =>
        HttpResponse.json(envelope([makeAnswerGroup({ latest_answer: treeAnswer, live_answer: treeAnswer })])),
      ),
    );
    renderPage();
    await screen.findByText('kp-1');
    await userEvent.click(screen.getByText('kp-1'));
    expect(await screen.findByText(/tree content/)).toBeInTheDocument();
  });

  it('renders a revoked answer group struck through, distinct from a not-yet-effective one', async () => {
    server.use(
      http.get(`${API_BASE}/knowledge-bases/:kbId/knowledge-points/:id/answer-groups`, () =>
        HttpResponse.json(
          envelope([
            makeAnswerGroup({
              coord: { tenant: 'acme' },
              revoked: true,
              live_answer: null,
              latest_answer: makeAnswer({ content: 'revoked content' }),
            }),
            makeAnswerGroup({
              coord: { tenant: 'other' },
              revoked: false,
              live_answer: null,
              latest_answer: makeAnswer({ content: 'future content' }),
            }),
          ]),
        ),
      ),
    );
    renderPage();
    await screen.findByText('kp-1');
    await userEvent.click(screen.getByText('kp-1'));

    expect(await screen.findByText('已撤回，留痕保存')).toBeInTheDocument();
    expect(screen.getByText(/尚未生效/)).toBeInTheDocument();
  });

  it('creates a knowledge point and refreshes the list', async () => {
    renderPage();
    await screen.findByText('kp-1');
    await userEvent.click(screen.getByText('+ 新增知识点'));
    const dialog = (await screen.findByText('新增知识点')).closest('.modal') as HTMLElement;
    await userEvent.type(within(dialog).getByPlaceholderText('知识点标题，例如：退款政策'), 'brand-new-kp');
    await userEvent.click(within(dialog).getByText('确 定'));
    await waitFor(() => expect(screen.queryByText('新增知识点')).not.toBeInTheDocument());
    expect(await screen.findByText(/已创建知识点/)).toBeInTheDocument();
  });

  it('requires a delete reason and shows a risk block', async () => {
    renderPage();
    await screen.findByText('kp-1');
    await userEvent.click(screen.getByText('删除'));
    const dialog = (await screen.findByText('删除知识点')).closest('.modal') as HTMLElement;
    expect(within(dialog).getByText(/采用软删除/)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByText('确 定 删 除'));
    expect(await within(dialog).findByText('请填写删除原因。')).toBeInTheDocument();
  });

  it('deletes a knowledge point after confirming with a reason', async () => {
    renderPage();
    await screen.findByText('kp-1');
    await userEvent.click(screen.getByText('删除'));
    const dialog = (await screen.findByText('删除知识点')).closest('.modal') as HTMLElement;
    await userEvent.type(within(dialog).getByPlaceholderText('请说明删除原因，将记录在留痕中'), 'test reason');
    await userEvent.click(within(dialog).getByText('确 定 删 除'));
    expect(await screen.findByText(/已删除/)).toBeInTheDocument();
  });

  it('stat cards show real numbers for 知识主题/启用维度 and placeholders for the rest', async () => {
    server.use(http.get(`${API_BASE}/knowledge-bases`, () => HttpResponse.json(envelope([makeKb({ active_knowledge_point_count: 7 })]))));
    renderPage();
    await screen.findByText('kp-1');

    const statGrid = document.querySelector('.stat-grid') as HTMLElement;
    const [subjectCard, , dimensionCard] = statGrid.querySelectorAll('.stat');
    expect(within(subjectCard as HTMLElement).getByText('7')).toBeInTheDocument();
    expect(within(dimensionCard as HTMLElement).getByText('1')).toBeInTheDocument();
    expect(screen.getAllByText('统计接口开发中')).toHaveLength(2);
  });
});
