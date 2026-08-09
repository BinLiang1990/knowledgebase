import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useKnowledgeBases } from '../api/knowledgeBases';
import { useEnabledDimensions } from '../api/dimensions';
import { useCreateKnowledgePoint, useKnowledgePoints, type KnowledgePoint } from '../api/knowledgePoints';
import { ApiError } from '../api/client';
import { AppShell } from '../components/layout/AppShell';
import { KbTabs } from '../components/layout/KbTabs';
import { Modal } from '../components/ui/Modal';
import { Pager } from '../components/ui/Pager';
import { ConditionPicker, type Filters } from '../components/ui/ConditionPicker';
import { KnowledgePointRow } from '../components/KnowledgePointRow';
import { DeleteKnowledgePointModal } from '../components/DeleteKnowledgePointModal';
import { useToast } from '../components/ui/Toast';
import { today } from '../lib/today';

const PAGE_SIZE = 6;

export function KnowledgePointListPage() {
  const { kbId: kbIdParam } = useParams<{ kbId: string }>();
  const kbId = Number(kbIdParam);

  const { data: knowledgeBases, isLoading: kbLoading, isError: kbIsError, refetch: kbRefetch } = useKnowledgeBases();
  const kb = knowledgeBases?.find((k) => k.id === kbId);

  const [keywordInput, setKeywordInput] = useState('');
  const [keyword, setKeyword] = useState('');
  const [filters, setFilters] = useState<Filters>({});
  const [qMode, setQMode] = useState<'now' | 'day'>('now');
  const [qTime, setQTime] = useState(today());
  const [page, setPage] = useState(1);
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<KnowledgePoint | null>(null);

  // In "最新" mode, omit `at` entirely rather than freezing today()'s value
  // at render time: a page left open across local midnight would otherwise
  // keep querying yesterday's date until some unrelated state change forced
  // a rerender. Omitting it lets the backend use its own current date on
  // every request. Codex outer-gate finding on PR #23.
  const at = qMode === 'day' ? qTime : undefined;
  const hasFilter = Boolean(keyword) || Object.keys(filters).length > 0;

  // Don't fire these until the knowledge base itself is confirmed valid and
  // active — otherwise a malformed :kbId (NaN) or a missing/deprecated KB
  // still triggers avoidable 404s while the guard below is about to reject
  // the page anyway. Kimi 终审 finding on PR #23.
  const kbReady = kb?.status === 'active';

  const dimensionsQuery = useEnabledDimensions(kbId, kbReady);
  const dimensions = dimensionsQuery.data ?? [];

  const kpQuery = useKnowledgePoints(kbId, { keyword, at, coord: filters }, kbReady);
  const knowledgePoints = kpQuery.data ?? [];
  const pageCount = Math.max(1, Math.ceil(knowledgePoints.length / PAGE_SIZE));
  useEffect(() => {
    if (page > pageCount) setPage(pageCount);
  }, [page, pageCount]);
  const pageItems = knowledgePoints.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  function applyFilter() {
    setKeyword(keywordInput.trim().toLowerCase());
    setPage(1);
  }
  function resetFilter() {
    setKeywordInput('');
    setKeyword('');
    setFilters({});
    setQMode('now');
    setQTime(today());
    setPage(1);
  }
  function handleFiltersChange(next: Filters) {
    setFilters(next);
    setPage(1);
  }
  function handleTimeChange(mode: 'now' | 'day', time: string) {
    setQMode(mode);
    setQTime(time);
    setPage(1);
  }
  function toggleExpand(id: number) {
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));
  }

  if (kbLoading) {
    return (
      <AppShell title="知识点列表" crumb="知识库列表 / 知识点列表">
        {/* Number.isFinite guard — a malformed :kbId (e.g. non-numeric,
            NaN) must not render tab links pointing at
            /knowledge-bases/NaN/... while still in a loading/error state.
            Kimi 终审 finding on PR #29. */}
        {Number.isFinite(kbId) && <KbTabs kbId={kbId} active="kp-list" />}
        <div className="card">
          <div className="empty-block">
            <span className="spin" /> 加载中…
          </div>
        </div>
      </AppShell>
    );
  }

  if (kbIsError) {
    // Distinct from the "no such knowledge base" guard below (Codex
    // outer-gate finding on PR #23): a failed fetch must not be reported as
    // "this knowledge base doesn't exist" — that's misleading and gives the
    // user nothing to retry.
    return (
      <AppShell title="知识点列表" crumb="知识库列表 / 知识点列表">
        {Number.isFinite(kbId) && <KbTabs kbId={kbId} active="kp-list" />}
        <div className="card">
          <div className="empty-block">
            加载知识库失败，请稍后重试
            <br />
            <span style={{ display: 'inline-block', marginTop: 12 }}>
              <a onClick={() => kbRefetch()}>重试</a>
            </span>
          </div>
        </div>
      </AppShell>
    );
  }

  if (!kb || kb.status !== 'active') {
    // No KbTabs here — mirrors frontend-mock/kb-settings.html's own
    // "!kb || kb.status !== 'active'" guard, which likewise skips
    // renderKbTabs: an invalid/deactivated knowledge base has no
    // "settings" to switch to (design doc §2.1, issue #13).
    return (
      <AppShell title="知识点列表" crumb="知识库列表 / 知识点列表">
        <div className="card">
          <div className="empty-block">
            没有指定有效的知识库（可能已被停用或不存在）
            <br />
            <span style={{ display: 'inline-block', marginTop: 12 }}>
              <Link className="btn primary" to="/knowledge-bases">
                ‹ 返回知识库列表
              </Link>
            </span>
          </div>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell title="知识点列表" crumb={`${kb.name} / 知识点列表`}>
      <KbTabs kbId={kbId} active="kp-list" />
      <div className="stat-grid">
        <div className="stat">
          <div className="lbl">知识主题</div>
          <div className="val num">
            {kb.active_knowledge_point_count}
            <small>个</small>
          </div>
          <div className="foot">当前生效的知识点</div>
        </div>
        <div className="stat c2">
          <div className="lbl">在用答案</div>
          <div className="val num">—</div>
          <div className="foot">统计接口开发中</div>
        </div>
        <div className="stat c3">
          <div className="lbl">启用维度</div>
          <div className="val num">
            {dimensions.length}
            <small>个</small>
          </div>
          <div className="foot">本知识库已启用</div>
        </div>
        <div className="stat c4">
          <div className="lbl">今日变更</div>
          <div className="val num">—</div>
          <div className="foot">统计接口开发中</div>
        </div>
      </div>

      <div className="card ov">
        <div className="card-head">
          <span className="tick" />
          <h3>带条件提问</h3>
          <span className="sub">钉住你关心的维度条件；不钉的不参与过滤</span>
          <span className="spacer" />
          <span className="ops">
            <button type="button" className="btn primary" onClick={() => setAddModalOpen(true)}>
              + 新增知识点
            </button>
          </span>
        </div>
        <div className="form-row">
          <input
            type="text"
            placeholder="搜索知识点标题"
            value={keywordInput}
            onChange={(e) => setKeywordInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') applyFilter();
            }}
          />
          {dimensionsQuery.isError ? (
            // Codex outer-gate finding on PR #23: silently falling back to
            // `[]` on a failed fetch made the picker claim "this knowledge
            // base has no enabled dimensions," indistinguishable from the
            // genuine empty case. Surface the failure instead.
            <span className="hint" style={{ color: 'var(--red)' }}>
              维度加载失败，条件筛选暂不可用 · <a onClick={() => dimensionsQuery.refetch()}>重试</a>
            </span>
          ) : (
            <ConditionPicker
              dimensions={dimensions}
              filters={filters}
              onFiltersChange={handleFiltersChange}
              qMode={qMode}
              qTime={qTime}
              today={today()}
              onTimeChange={handleTimeChange}
            />
          )}
          <button type="button" className="btn primary sm" onClick={applyFilter}>
            查 询
          </button>
          <button type="button" className="btn sm" onClick={resetFilter}>
            重 置
          </button>
        </div>
      </div>

      <div className="card ov">
        <div className="card-head">
          <span className="tick" />
          <h3>知识点</h3>
          <span className="sub">「{kb.name}」· 点行展开查看全部答案</span>
        </div>
        {kpQuery.isLoading && (
          <div className="empty-block">
            <span className="spin" /> 加载中…
          </div>
        )}
        {kpQuery.isError && (
          <div className="empty-block">
            {kpQuery.error instanceof ApiError ? kpQuery.error.message : '网络异常，请稍后重试'}
            <br />
            <a onClick={() => kpQuery.refetch()}>重试</a>
          </div>
        )}
        {!kpQuery.isLoading && !kpQuery.isError && pageItems.length === 0 && (
          <div className="empty-block">
            {hasFilter ? '没有知识点在这些条件下有匹配的答案：减少条件，或换个条件试试' : '暂无知识点，点击右上角「+ 新增知识点」创建'}
          </div>
        )}
        {!kpQuery.isLoading &&
          !kpQuery.isError &&
          pageItems.map((kp) => (
            <KnowledgePointRow
              key={kp.id}
              kp={kp}
              kbId={kbId}
              at={at}
              qMode={qMode}
              expanded={Boolean(expanded[kp.id])}
              onToggleExpand={() => toggleExpand(kp.id)}
              onDeleteRequest={() => setDeleteTarget(kp)}
              dimensions={dimensions}
              hasFilter={hasFilter}
            />
          ))}
        <Pager total={knowledgePoints.length} page={page} pageSize={PAGE_SIZE} onChange={setPage} />
      </div>

      {addModalOpen && <AddKnowledgePointModal kbId={kbId} onClose={() => setAddModalOpen(false)} />}
      {deleteTarget && (
        <DeleteKnowledgePointModal kbId={kbId} target={deleteTarget} onClose={() => setDeleteTarget(null)} />
      )}
    </AppShell>
  );
}

function AddKnowledgePointModal({ kbId, onClose }: { kbId: number; onClose: () => void }) {
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [effectiveTime, setEffectiveTime] = useState(today());
  const [error, setError] = useState('');
  const createMutation = useCreateKnowledgePoint(kbId);
  const toast = useToast();

  function submit() {
    const trimmedTitle = title.trim();
    if (!trimmedTitle || !effectiveTime) {
      setError('标题、生效时间为必填项。');
      return;
    }
    setError('');
    const trimmedContent = content.trim();
    createMutation
      .mutateAsync({
        title: trimmedTitle,
        default_answer: trimmedContent
          ? { content: trimmedContent, effective_time: effectiveTime }
          : undefined,
      })
      .then(() => {
        toast.ok(`已创建知识点「${trimmedTitle}」`);
        onClose();
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.message : '操作失败，请稍后重试');
      });
  }

  return (
    <Modal
      title="新增知识点"
      open
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn" onClick={onClose}>
            取 消
          </button>
          <button type="button" className="btn primary" disabled={createMutation.isPending} onClick={submit}>
            确 定
          </button>
        </>
      }
    >
      <div className="mf">
        <label>
          <span className="req">*</span>标题
        </label>
        <input
          type="text"
          placeholder="知识点标题，例如：退款政策"
          value={title}
          maxLength={255}
          onChange={(e) => setTitle(e.target.value)}
        />
      </div>
      <div className="mf">
        <label>默认答案内容(可选)</label>
        <textarea
          rows={3}
          placeholder="不填条件、处处适用的默认说法；也可以先留空，之后再到详情页写答案"
          value={content}
          onChange={(e) => setContent(e.target.value)}
        />
      </div>
      <div className="mf">
        <label>
          <span className="req">*</span>生效时间
        </label>
        <input type="date" value={effectiveTime} onChange={(e) => setEffectiveTime(e.target.value)} />
      </div>
      {error && <p className="hint" style={{ color: 'var(--red)' }}>{error}</p>}
    </Modal>
  );
}

