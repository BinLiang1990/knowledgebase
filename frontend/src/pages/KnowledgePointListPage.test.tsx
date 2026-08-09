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
  errorEnvelope,
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

  it('omits the `at` query param in "最新" mode instead of freezing a client-computed date (issue #7 Codex fix)', async () => {
    let sawAtParam = false;
    server.use(
      http.get(`${API_BASE}/knowledge-bases/:kbId/knowledge-points`, ({ request }) => {
        if (new URL(request.url).searchParams.has('at')) sawAtParam = true;
        return HttpResponse.json(envelope([makeKp()]));
      }),
    );
    renderPage();
    await screen.findByText('kp-1');
    expect(sawAtParam).toBe(false);
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

  it('does not fetch dimensions or knowledge points for a deactivated knowledge base (issue #7 Kimi fix)', async () => {
    let dimensionsRequested = false;
    let kpsRequested = false;
    server.use(http.get(`${API_BASE}/knowledge-bases`, () => HttpResponse.json(envelope([makeKb({ status: 'deprecated' })]))));
    server.use(
      http.get(`${API_BASE}/knowledge-bases/:kbId/enabled-dimensions`, () => {
        dimensionsRequested = true;
        return HttpResponse.json(envelope([]));
      }),
    );
    server.use(
      http.get(`${API_BASE}/knowledge-bases/:kbId/knowledge-points`, () => {
        kpsRequested = true;
        return HttpResponse.json(envelope([]));
      }),
    );
    renderPage();
    await screen.findByText(/没有指定有效的知识库/);
    expect(dimensionsRequested).toBe(false);
    expect(kpsRequested).toBe(false);
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

  it('shows a distinct fallback message for "回看某天" mode with no other filter (issue #7 Kimi fix)', async () => {
    server.use(
      http.get(`${API_BASE}/knowledge-bases/:kbId/knowledge-points`, () =>
        HttpResponse.json(envelope([makeKp({ resolved: { status: 'none', answer: null } })])),
      ),
    );
    renderPage();
    await screen.findByText('还没有写过任何答案');

    await userEvent.click(screen.getByText('回看某天'));
    expect(await screen.findByText('这个时间点还没有匹配的答案')).toBeInTheDocument();
    expect(screen.queryByText('还没有写过任何答案')).not.toBeInTheDocument();
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

  it('rejects a whitespace-only text condition instead of committing an empty filter (issue #7 Codex fix)', async () => {
    renderPage();
    await screen.findByText('kp-1');
    await userEvent.click(screen.getByText('+ 加一个条件'));
    await userEvent.click(await screen.findByText('租户'));
    const input = document.querySelector('.dd-menu input[type="text"]') as HTMLInputElement;
    await userEvent.type(input, '   ');
    await userEvent.click(screen.getByText('确 定'));

    // A committed filter would close the dropdown and render a "租户 = ..."
    // chip; whitespace-only input must do neither.
    expect(input).toBeInTheDocument();
    expect(screen.queryByText(/租户 =/)).not.toBeInTheDocument();
  });

  it('links the title and the "查看详情" op to the detail page (issue #8)', async () => {
    renderPage();
    await screen.findByText('kp-1');

    const titleLink = screen.getByRole('link', { name: 'kp-1' });
    expect(titleLink).toHaveAttribute('href', '/knowledge-bases/1/knowledge-points/1');
    const detailLink = screen.getByRole('link', { name: '查看详情' });
    expect(detailLink).toHaveAttribute('href', '/knowledge-bases/1/knowledge-points/1');
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
    // The title itself is now a Link to the detail page (issue #8) and
    // stops click propagation, so expansion must be triggered elsewhere on
    // the row.
    await userEvent.click(screen.getByText('1 条答案'));
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
    // The title itself is now a Link to the detail page (issue #8) and
    // stops click propagation, so expansion must be triggered elsewhere on
    // the row.
    await userEvent.click(screen.getByText('1 条答案'));

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

  it('refreshes the 知识主题 stat after creating a knowledge point (issue #7 Codex fix)', async () => {
    let count = 3;
    server.use(
      http.get(`${API_BASE}/knowledge-bases`, () => HttpResponse.json(envelope([makeKb({ active_knowledge_point_count: count })]))),
    );
    server.use(
      http.post(`${API_BASE}/knowledge-bases/:kbId/knowledge-points`, () => {
        count = 4;
        return HttpResponse.json(envelope(makeKp({ id: 2, title: 'new-kp' })));
      }),
    );
    renderPage();
    await screen.findByText('kp-1');
    const statGrid = document.querySelector('.stat-grid') as HTMLElement;
    const subjectCard = statGrid.querySelectorAll('.stat')[0] as HTMLElement;
    expect(within(subjectCard).getByText('3')).toBeInTheDocument();

    await userEvent.click(screen.getByText('+ 新增知识点'));
    const dialog = (await screen.findByText('新增知识点')).closest('.modal') as HTMLElement;
    await userEvent.type(within(dialog).getByPlaceholderText('知识点标题，例如：退款政策'), 'brand-new-kp');
    await userEvent.click(within(dialog).getByText('确 定'));
    await waitFor(() => expect(screen.queryByText('新增知识点')).not.toBeInTheDocument());

    await waitFor(() => expect(within(subjectCard).getByText('4')).toBeInTheDocument());
  });

  it('surfaces an enabled-dimensions load failure instead of claiming zero dimensions', async () => {
    server.use(
      http.get(`${API_BASE}/knowledge-bases/:kbId/enabled-dimensions`, () =>
        HttpResponse.json(errorEnvelope('数据库异常'), { status: 500 }),
      ),
    );
    renderPage();
    await screen.findByText('kp-1');
    expect(await screen.findByText(/维度加载失败/)).toBeInTheDocument();
    expect(screen.queryByText('+ 加一个条件')).not.toBeInTheDocument();
  });

  it('distinguishes a knowledge-base load failure from "no such knowledge base"', async () => {
    server.use(http.get(`${API_BASE}/knowledge-bases`, () => HttpResponse.json(errorEnvelope('数据库异常'), { status: 500 })));
    renderPage();
    expect(await screen.findByText(/加载知识库失败/)).toBeInTheDocument();
    expect(screen.queryByText(/没有指定有效的知识库/)).not.toBeInTheDocument();
  });

  it('renders KbTabs with the kp-list tab active on a normal load (issue #13)', async () => {
    const { container } = renderPage();
    await screen.findByText('kp-1');
    const tabs = container.querySelector('.kb-tabs') as HTMLElement;
    expect(within(tabs).getByText('知识点列表')).toHaveClass('active');
    expect(within(tabs).getByText('知识库设置')).not.toHaveClass('active');
  });

  it('still renders KbTabs when the knowledge-base fetch fails (design doc §2.1: no reason to hide it)', async () => {
    server.use(http.get(`${API_BASE}/knowledge-bases`, () => HttpResponse.json(errorEnvelope('数据库异常'), { status: 500 })));
    const { container } = renderPage();
    await screen.findByText(/加载知识库失败/);
    expect(container.querySelector('.kb-tabs')).not.toBeNull();
  });

  it('does not render KbTabs for an invalid knowledge base, mirroring the demo (design doc §2.1)', async () => {
    server.use(http.get(`${API_BASE}/knowledge-bases`, () => HttpResponse.json(envelope([]))));
    const { container } = renderPage('/knowledge-bases/999/knowledge-points');
    await screen.findByText(/没有指定有效的知识库/);
    expect(container.querySelector('.kb-tabs')).toBeNull();
  });
});
