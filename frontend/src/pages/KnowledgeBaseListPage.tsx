import { useEffect, useMemo, useState } from 'react';
import {
  useCreateKnowledgeBase,
  useKnowledgeBases,
  useSetKnowledgeBaseStatus,
  useUpdateKnowledgeBase,
  type KnowledgeBase,
} from '../api/knowledgeBases';
import { ApiError } from '../api/client';
import { AppShell } from '../components/layout/AppShell';
import { Modal } from '../components/ui/Modal';
import { Pager } from '../components/ui/Pager';
import { useToast } from '../components/ui/Toast';

const PAGE_SIZE = 8;

function formatDate(iso: string): string {
  return iso.slice(0, 10);
}

export function KnowledgeBaseListPage() {
  const { data: knowledgeBases, isLoading, isError, refetch } = useKnowledgeBases();
  const [keywordInput, setKeywordInput] = useState('');
  const [keyword, setKeyword] = useState('');
  const [page, setPage] = useState(1);
  const [formTarget, setFormTarget] = useState<KnowledgeBase | 'create' | null>(null);
  const [toggleTarget, setToggleTarget] = useState<KnowledgeBase | null>(null);

  const filtered = useMemo(() => {
    if (!knowledgeBases) return [];
    if (!keyword) return knowledgeBases;
    const needle = keyword.toLowerCase();
    return knowledgeBases.filter((kb) =>
      `${kb.name} ${kb.description ?? ''}`.toLowerCase().includes(needle),
    );
  }, [knowledgeBases, keyword]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  // A mutation (edit/toggle) can shrink `filtered` out from under the page
  // the user is currently viewing — e.g. deactivating the only match on
  // page 2 of a search leaves page 2 empty while `page` is still 2, so the
  // pager would show an invalid "第 2/1 页". Clamp back into range instead
  // of leaving that stale. Found by the Codex outer-gate review on PR #22.
  useEffect(() => {
    if (page > pageCount) setPage(pageCount);
  }, [page, pageCount]);
  const pageItems = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  function applyFilter() {
    setKeyword(keywordInput.trim().toLowerCase());
    setPage(1);
  }
  function resetFilter() {
    setKeywordInput('');
    setKeyword('');
    setPage(1);
  }

  return (
    <AppShell title="知识库列表" crumb="知识库管理 / 知识库列表">
      <div className="notice">
        <b>知识库</b>是知识点的容器，不同知识库之间的知识点互不影响；<b>维度定义</b>
        是全局的，所有知识库共享同一套维度。
      </div>

      <div className="card ov">
        <div className="card-head">
          <span className="tick" />
          <h3>知识库列表</h3>
          <span className="sub">全部知识库</span>
          <span className="spacer" />
          <span className="ops">
            <button type="button" className="btn primary" onClick={() => setFormTarget('create')}>
              + 新增知识库
            </button>
          </span>
        </div>

        <div className="form-row">
          <input
            type="text"
            placeholder="搜索知识库名称或描述"
            value={keywordInput}
            onChange={(e) => setKeywordInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') applyFilter();
            }}
          />
          <button type="button" className="btn primary sm" onClick={applyFilter}>
            查 询
          </button>
          <button type="button" className="btn sm" onClick={resetFilter}>
            重 置
          </button>
        </div>

        <table className="tbl">
          <thead>
            <tr>
              <th>名称</th>
              <th>描述</th>
              <th>知识点数</th>
              <th>状态</th>
              <th>创建时间</th>
              <th className="op-col">操作</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td colSpan={6} className="empty">
                  <span className="spin" /> 加载中…
                </td>
              </tr>
            )}
            {isError && !isLoading && (
              <tr>
                <td colSpan={6} className="empty">
                  加载失败，请检查网络或后端服务后
                  <a onClick={() => refetch()}> 重试</a>
                </td>
              </tr>
            )}
            {!isLoading && !isError && pageItems.length === 0 && (
              <tr>
                <td colSpan={6} className="empty">
                  {keyword ? '暂无符合条件的知识库，试试调整搜索关键词' : '暂无知识库，点击右上角「+ 新增知识库」创建'}
                </td>
              </tr>
            )}
            {!isLoading &&
              !isError &&
              pageItems.map((kb) => (
                <tr key={kb.id}>
                  <td>{kb.name}</td>
                  <td>{kb.description || '—'}</td>
                  <td className="num" style={{ fontWeight: 400 }}>
                    {kb.active_knowledge_point_count}
                  </td>
                  <td>
                    {kb.status === 'active' ? (
                      <span className="status-dot ok">
                        <i />
                        启用中
                      </span>
                    ) : (
                      <span className="status-dot off">
                        <i />
                        已停用
                      </span>
                    )}
                  </td>
                  <td className="num" style={{ fontWeight: 400 }}>
                    {formatDate(kb.created_at)}
                  </td>
                  <td className="op-col ops">
                    <a onClick={() => setFormTarget(kb)}>编辑</a>
                    <a
                      className={kb.status === 'active' ? 'danger' : ''}
                      onClick={() => setToggleTarget(kb)}
                    >
                      {kb.status === 'active' ? '停用' : '启用'}
                    </a>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
        <Pager total={filtered.length} page={page} pageSize={PAGE_SIZE} onChange={setPage} />
      </div>

      {formTarget !== null && (
        <KnowledgeBaseFormModal target={formTarget} onClose={() => setFormTarget(null)} />
      )}
      {toggleTarget !== null && (
        <ToggleStatusModal target={toggleTarget} onClose={() => setToggleTarget(null)} />
      )}
    </AppShell>
  );
}

function KnowledgeBaseFormModal({
  target,
  onClose,
}: {
  target: KnowledgeBase | 'create';
  onClose: () => void;
}) {
  const isEdit = target !== 'create';
  const [name, setName] = useState(isEdit ? target.name : '');
  const [description, setDescription] = useState(isEdit ? target.description ?? '' : '');
  const [error, setError] = useState('');
  const createMutation = useCreateKnowledgeBase();
  const updateMutation = useUpdateKnowledgeBase();
  const toast = useToast();
  const pending = createMutation.isPending || updateMutation.isPending;

  function submit() {
    const trimmedName = name.trim();
    if (!trimmedName) {
      setError('请填写知识库名称。');
      return;
    }
    setError('');
    const input = { name: trimmedName, description: description.trim() };
    const mutation = isEdit
      ? updateMutation.mutateAsync({ id: target.id, ...input })
      : createMutation.mutateAsync(input);
    mutation
      .then(() => {
        toast.ok(isEdit ? `已更新知识库「${trimmedName}」` : `已创建知识库「${trimmedName}」`);
        onClose();
      })
      .catch((err: unknown) => {
        // Business (444) and validation (422) errors both land here as
        // ApiError and are shown inline — this is a form, not a
        // confirmation dialog, so it has somewhere to show them (design
        // doc §4.5).
        setError(err instanceof ApiError ? err.message : '操作失败，请稍后重试');
      });
  }

  return (
    <Modal
      title={isEdit ? `编辑知识库 · ${target.name}` : '新增知识库'}
      open
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn" onClick={onClose}>
            取 消
          </button>
          <button type="button" className="btn primary" disabled={pending} onClick={submit}>
            确 定
          </button>
        </>
      }
    >
      <div className="mf">
        <label>
          <span className="req">*</span>名称
        </label>
        <input
          type="text"
          placeholder="例如：产品知识库"
          value={name}
          // Mirrors the backend's own KnowledgeBaseCreate/Update constraint
          // (schemas/knowledge_base.py: max_length=255) — design doc §4.5
          // says client-side limits should make a real 422 round-trip rare,
          // since the backend's 422 message is a fixed generic string with
          // no per-field detail. Found by the Codex outer-gate review on
          // PR #22 (this was designed but not actually wired up).
          maxLength={255}
          onChange={(e) => setName(e.target.value)}
        />
      </div>
      <div className="mf">
        <label>描述(可选)</label>
        <textarea
          rows={2}
          placeholder="这个知识库用来存放什么类型的知识点"
          value={description}
          maxLength={2000}
          onChange={(e) => setDescription(e.target.value)}
        />
      </div>
      {error && <p className="hint" style={{ color: 'var(--red)' }}>{error}</p>}
    </Modal>
  );
}

function ToggleStatusModal({ target, onClose }: { target: KnowledgeBase; onClose: () => void }) {
  const willDeactivate = target.status === 'active';
  const mutation = useSetKnowledgeBaseStatus();
  const toast = useToast();

  function confirm() {
    mutation
      .mutateAsync({ id: target.id, status: willDeactivate ? 'deprecated' : 'active' })
      .then(() => {
        toast.ok('已更新知识库状态');
        onClose();
      })
      .catch((err: unknown) => {
        // A confirmation dialog has no form field to attach an inline
        // error to, so this path uses a toast instead (design doc §4.5).
        toast.err(err instanceof ApiError ? err.message : '操作失败，请稍后重试');
        onClose();
      });
  }

  return (
    <Modal
      title={willDeactivate ? '停用知识库' : '启用知识库'}
      open
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn" onClick={onClose}>
            取 消
          </button>
          <button
            type="button"
            className={willDeactivate ? 'btn danger' : 'btn primary'}
            disabled={mutation.isPending}
            onClick={confirm}
          >
            确 定
          </button>
        </>
      }
    >
      <p style={{ fontSize: '13.5px', color: 'var(--ink-2)', lineHeight: 1.8 }}>
        即将{willDeactivate ? '停用' : '启用'}知识库 <b style={{ color: 'var(--ink-1)' }}>{target.name}</b>。
      </p>
      {willDeactivate && (
        <div className="risk">
          该知识库下有 {target.active_knowledge_point_count} 个知识点，停用后知识库列表不再显示、无法进入；知识点数据不会被删除，重新启用后可继续访问。
        </div>
      )}
    </Modal>
  );
}
