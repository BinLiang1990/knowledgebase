import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useKnowledgeBases } from '../api/knowledgeBases';
import { useEnabledDimensions } from '../api/dimensions';
import { useAllAnswers, useAnswerGroups, useKnowledgePoint } from '../api/knowledgePoints';
import { coordGroupKey, describeCoord, hasUniqueTopMatch, sortLiveGroupsByPriority } from '../api/answers';
import { useChangeLog } from '../api/changeLog';
import { buildTimelineGroups, type TimelineStatus } from '../api/timeline';
import type { AnswerGroup } from '../api/knowledgePoints';
import type { Dimension } from '../api/dimensions';
import { ApiError } from '../api/client';
import { AppShell } from '../components/layout/AppShell';
import { ChangeLogTable } from '../components/ChangeLogTable';
import { ConditionPicker, type Filters } from '../components/ui/ConditionPicker';
import { WriteAnswerModal, type ExistingAnswer } from '../components/WriteAnswerModal';
import { EditTitleModal } from '../components/EditTitleModal';
import { DeleteKnowledgePointModal } from '../components/DeleteKnowledgePointModal';
import { today } from '../lib/today';

type TabKey = 'now' | 'tree' | 'timeline' | 'logs';

const TABS: Array<[TabKey, string]> = [
  ['now', '当前答案'],
  ['tree', '立体全景'],
  ['timeline', '版本历史'],
  ['logs', '变更留痕'],
];

// 立体全景 is still P2 (issue #16) — rendered as a tab (IA parity with the
// demo) but with a placeholder, not hidden. Same treatment issue #7 gave
// unbuilt stat cards. timeline/logs are filled in by this issue (#14).
const TAB_PLACEHOLDER: Record<'tree', string> = {
  tree: '立体全景开发中，见 Issue #16',
};

const TIMELINE_STATUS_TAG: Record<TimelineStatus, { label: string; cls: string }> = {
  current: { label: '当前', cls: 'blue' },
  superseded: { label: '已被新版替代', cls: 'gray' },
  'not-yet-effective': { label: '晚于查询时间，暂不生效', cls: 'orange' },
  revoked: { label: '已撤回', cls: 'gray' },
};

function TimelineTab({
  kbId,
  kpId,
  kbReady,
  dimensions,
}: {
  kbId: number;
  kpId: number;
  kbReady: boolean;
  dimensions: Dimension[];
}) {
  const answersQuery = useAllAnswers(kbId, kpId, kbReady);
  const [selectedGroup, setSelectedGroup] = useState<string | null>(null);

  if (answersQuery.isLoading) {
    return (
      <div className="empty-block">
        <span className="spin" /> 加载中…
      </div>
    );
  }
  if (answersQuery.isError) {
    return (
      <div className="empty-block">
        加载失败
        <br />
        <a onClick={() => answersQuery.refetch()}>重试</a>
      </div>
    );
  }
  const answers = answersQuery.data ?? [];
  if (answers.length === 0) {
    return <div className="empty-block">还没有任何答案</div>;
  }

  const groups = buildTimelineGroups(answers);
  const keys = [...groups.keys()];
  const activeKey = selectedGroup && keys.includes(selectedGroup) ? selectedGroup : keys[0];
  const entries = groups.get(activeKey) ?? [];

  return (
    <>
      <div className="form-row" style={{ marginBottom: 14 }}>
        <span className="f-lbl">选择条件组合(每组条件一条独立版本链)</span>
        <select value={activeKey} onChange={(e) => setSelectedGroup(e.target.value)}>
          {keys.map((k) => (
            <option key={k} value={k}>
              {describeCoord(groups.get(k)![0].answer.coord, dimensions)}
            </option>
          ))}
        </select>
      </div>
      <div className="timeline">
        {entries.map((entry, i) => {
          const tag = TIMELINE_STATUS_TAG[entry.status];
          return (
            <div className="tl-item" key={entry.answer.id}>
              <div className="tl-dot-col">
                <div className={`tl-dot ${entry.status === 'current' ? 'cur' : ''}`} />
                {i < entries.length - 1 && <div className="tl-line" />}
              </div>
              <div className="tl-body">
                <div className="tl-head">
                  <span className="time num" style={{ fontWeight: 400 }}>
                    {entry.answer.effective_time}
                  </span>
                  <span className={`tag ${tag.cls}`}>{tag.label}</span>
                  <span className="field-hint">操作人：{entry.answer.operator}</span>
                </div>
                <div className="tl-content">{entry.answer.content}</div>
                {entry.answer.note && (
                  <div className="field-hint" style={{ marginTop: 4 }}>
                    说明：{entry.answer.note}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
      <div className="mini-note" style={{ marginTop: 8 }}>
        旧版本与撤回版永不删除。当前查询时间为 <span className="num">{today()}</span>。
      </div>
    </>
  );
}

function LogsTab({ kbId, kpId, kbReady }: { kbId: number; kpId: number; kbReady: boolean }) {
  const changeLogQuery = useChangeLog(kbId, kpId, kbReady);

  if (changeLogQuery.isLoading) {
    return (
      <div className="empty-block">
        <span className="spin" /> 加载中…
      </div>
    );
  }
  if (changeLogQuery.isError) {
    return (
      <div className="empty-block">
        加载失败
        <br />
        <a onClick={() => changeLogQuery.refetch()}>重试</a>
      </div>
    );
  }
  return <ChangeLogTable entries={changeLogQuery.data ?? []} kbId={kbId} kpId={kpId} />;
}

function AnswerRow({
  group,
  dimensions,
  isTop,
  editDisabledReason,
  onEdit,
}: {
  group: AnswerGroup;
  dimensions: Dimension[];
  isTop: boolean;
  editDisabledReason: string | null;
  onEdit: () => void;
}) {
  const live = group.live_answer!;
  return (
    <div className="ans-item">
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 16 }}>
        <div className="ai-content" style={{ flex: 1 }}>
          {live.content}
        </div>
        <span className="ops" style={{ fontSize: '12.5px', whiteSpace: 'nowrap', paddingTop: 3 }}>
          <a
            onClick={editDisabledReason ? undefined : onEdit}
            style={editDisabledReason ? { color: 'var(--ink-6)', cursor: 'not-allowed' } : undefined}
            title={editDisabledReason ?? undefined}
          >
            编辑
          </a>
        </span>
      </div>
      <div className="ai-cond">
        {isTop && (
          <span className="live">
            <i /> 此条件下生效
          </span>
        )}
        <span>{describeCoord(group.coord, dimensions)}</span>
        <span>
          <span className="num">{live.effective_time}</span> 起 · 共 {group.version_count} 版
        </span>
        <span>{live.operator} 录入</span>
      </div>
    </div>
  );
}

export function KnowledgePointDetailPage() {
  const { kbId: kbIdParam, kpId: kpIdParam } = useParams<{ kbId: string; kpId: string }>();
  const kbId = Number(kbIdParam);
  const kpId = Number(kpIdParam);

  const { data: knowledgeBases, isLoading: kbLoading, isError: kbIsError, refetch: kbRefetch } = useKnowledgeBases();
  const kb = knowledgeBases?.find((k) => k.id === kbId);
  const kbReady = kb?.status === 'active' && Number.isFinite(kpId);

  const [tab, setTab] = useState<TabKey>('now');
  const [filters, setFilters] = useState<Filters>({});
  const [qMode, setQMode] = useState<'now' | 'day'>('now');
  const [qTime, setQTime] = useState(today());
  const [writeTarget, setWriteTarget] = useState<'create' | ExistingAnswer | null>(null);
  const [editTitleOpen, setEditTitleOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  const at = qMode === 'day' ? qTime : undefined;
  const hasFilter = Object.keys(filters).length > 0;

  const dimensionsQuery = useEnabledDimensions(kbId, kbReady);
  const dimensions = dimensionsQuery.data ?? [];
  // WriteAnswerModal builds its CoordEditor rows from `dimensions` exactly
  // once, on mount — if it opens before this query has settled, every
  // existing condition row would be permanently misclassified as
  // referencing a deprecated dimension (dimensions=[] at that instant), for
  // the modal's whole lifetime. Block write/edit until it's actually ready
  // rather than let that race decide the outcome. Codex outer-gate finding
  // on PR #24.
  const dimensionsReady = !dimensionsQuery.isLoading && !dimensionsQuery.isError;

  const kpQuery = useKnowledgePoint(kbId, kpId, kbReady);
  const kp = kpQuery.data;

  const groupsQuery = useAnswerGroups(kbId, kpId, at, kbReady);
  const groups = groupsQuery.data ?? [];

  function handleFiltersChange(next: Filters) {
    setFilters(next);
  }
  function handleTimeChange(mode: 'now' | 'day', time: string) {
    setQMode(mode);
    setQTime(time);
  }

  if (kbLoading) {
    return (
      <AppShell title="知识点详情" crumb="知识库列表 / 知识点列表 / 详情">
        <div className="card">
          <div className="empty-block">
            <span className="spin" /> 加载中…
          </div>
        </div>
      </AppShell>
    );
  }

  if (kbIsError) {
    return (
      <AppShell title="知识点详情" crumb="知识库列表 / 知识点列表 / 详情">
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
    return (
      <AppShell title="知识点详情" crumb="知识库列表 / 知识点列表 / 详情">
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

  const backLink = (
    <Link className="back-link" to={`/knowledge-bases/${kbId}/knowledge-points`}>
      ‹ 返回列表
    </Link>
  );

  if (kpQuery.isLoading) {
    return (
      <AppShell title="知识点详情" crumb={`${kb.name} / 知识点列表 / 详情`}>
        {backLink}
        <div className="card">
          <div className="empty-block">
            <span className="spin" /> 加载中…
          </div>
        </div>
      </AppShell>
    );
  }

  if (kpQuery.isError || !kp) {
    return (
      <AppShell title="知识点详情" crumb={`${kb.name} / 知识点列表 / 详情`}>
        {backLink}
        <div className="card">
          <div className="empty-block">
            {kpQuery.error instanceof ApiError ? kpQuery.error.message : '找不到这个知识点'}
          </div>
        </div>
      </AppShell>
    );
  }

  const isDeleted = kp.status === 'deleted';
  const sorted = sortLiveGroupsByPriority(groups, filters, dimensions);
  const uniqueTop = hasUniqueTopMatch(sorted, hasFilter);
  // A deleted KP is read-only everywhere except delete/restore — the
  // header already hides "写一条答案"/"编辑标题"/"删除" for this state
  // (backend rejects them too), but each row's own "编辑" link was still
  // wired up and would 400 against edit_answer's own guard. Kimi 终审
  // finding on PR #24.
  const editDisabledReason = isDeleted
    ? '该知识点已删除，不能编辑答案'
    : !dimensionsReady
      ? '维度加载完成后才能编辑'
      : null;

  return (
    <AppShell title="知识点详情" crumb={`${kb.name} / 知识点列表 / 详情`}>
      {backLink}
      <div className="card">
        <div className="detail-head">
          <div>
            <h2>{kp.title}</h2>
            <div className="meta">
              <span>
                ID <b className="num">{kp.id}</b>
              </span>
              <span>{kp.active_answer_count} 条在用答案</span>
              <span>
                创建 <b className="num">{kp.created_at.slice(0, 10)}</b> · {kp.operator}
              </span>
              {isDeleted ? <span className="tag gray">已删除</span> : <span className="tag green">正常</span>}
            </div>
          </div>
          <div className="ops">
            {!isDeleted && (
              <>
                <button
                  type="button"
                  className="btn primary"
                  disabled={!dimensionsReady}
                  title={dimensionsReady ? undefined : '维度加载完成后才能写答案'}
                  onClick={() => setWriteTarget('create')}
                >
                  + 写一条答案
                </button>
                <button type="button" className="btn" onClick={() => setEditTitleOpen(true)}>
                  编辑标题
                </button>
                <button type="button" className="btn danger" onClick={() => setDeleteOpen(true)}>
                  删 除
                </button>
              </>
            )}
          </div>
        </div>
      </div>

      {isDeleted && (
        <div className="notice">
          该知识点已被<b>软删除</b>（删除时间 <b>{kp.deleted_at?.slice(0, 10) ?? '—'}</b>，原因：
          {kp.delete_reason || '—'}）。以下仍可查看其全部历史答案。
        </div>
      )}

      <div className="card ov">
        <div className="tabs">
          {TABS.map(([key, label]) => (
            <div key={key} className={`tab ${tab === key ? 'active' : ''}`} onClick={() => setTab(key)}>
              {label}
            </div>
          ))}
        </div>

        {tab === 'tree' && <div className="empty-block">{TAB_PLACEHOLDER.tree}</div>}
        {tab === 'timeline' && (
          <TimelineTab kbId={kbId} kpId={kpId} kbReady={kbReady} dimensions={dimensions} />
        )}
        {tab === 'logs' && <LogsTab kbId={kbId} kpId={kpId} kbReady={kbReady} />}
        {tab === 'now' && (
          <>
            <div className="form-row">
              {dimensionsQuery.isError ? (
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
              {hasFilter && (
                <button type="button" className="btn sm" onClick={() => setFilters({})}>
                  清空条件
                </button>
              )}
            </div>
            <div className="mini-note" style={{ margin: '12px 2px 2px' }}>
              {hasFilter
                ? `满足条件的答案 ${sorted.length} 条`
                : `全部答案 ${sorted.length} 条 · 一个知识点本来就可以有多种答案，各管各的条件`}
            </div>
            {groupsQuery.isLoading && (
              <div className="empty-block">
                <span className="spin" /> 加载中…
              </div>
            )}
            {groupsQuery.isError && (
              <div className="empty-block">
                加载失败
                <br />
                <a onClick={() => groupsQuery.refetch()}>重试</a>
              </div>
            )}
            {!groupsQuery.isLoading && !groupsQuery.isError && sorted.length === 0 && (
              <div className="empty-block">这个条件、这个时间点还没有答案：换个时间，或放宽条件</div>
            )}
            {!groupsQuery.isLoading &&
              !groupsQuery.isError &&
              sorted.map((g, i) => (
                <AnswerRow
                  key={coordGroupKey(g.coord)}
                  group={g}
                  dimensions={dimensions}
                  isTop={uniqueTop && i === 0}
                  editDisabledReason={editDisabledReason}
                  onEdit={() =>
                    setWriteTarget({
                      answerId: g.live_answer!.id,
                      coord: g.coord,
                      content: g.live_answer!.content,
                      effective_time: g.live_answer!.effective_time,
                      note: g.live_answer!.note,
                    })
                  }
                />
              ))}
          </>
        )}
      </div>

      {writeTarget && (
        <WriteAnswerModal
          kbId={kbId}
          kpId={kpId}
          dimensions={dimensions}
          existing={writeTarget === 'create' ? undefined : writeTarget}
          onClose={() => setWriteTarget(null)}
        />
      )}
      {editTitleOpen && (
        <EditTitleModal kbId={kbId} kpId={kpId} currentTitle={kp.title} onClose={() => setEditTitleOpen(false)} />
      )}
      {deleteOpen && <DeleteKnowledgePointModal kbId={kbId} target={kp} onClose={() => setDeleteOpen(false)} />}
    </AppShell>
  );
}
