import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useKnowledgeBases } from '../api/knowledgeBases';
import { useEnabledDimensions } from '../api/dimensions';
import { useAnswerGroups, useKnowledgePoint } from '../api/knowledgePoints';
import { hasUniqueTopMatch, sortLiveGroupsByPriority } from '../api/answers';
import type { AnswerGroup } from '../api/knowledgePoints';
import type { Dimension } from '../api/dimensions';
import { ApiError } from '../api/client';
import { AppShell } from '../components/layout/AppShell';
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

// The other three tabs are P1/P2 (Issue #14/#16) — rendered as tabs (IA
// parity with the demo, so those issues just fill in a body) but with a
// placeholder, not hidden. Same treatment issue #7 gave unbuilt stat cards.
const TAB_PLACEHOLDER: Record<Exclude<TabKey, 'now'>, string> = {
  tree: '立体全景开发中，见 Issue #16',
  timeline: '版本历史开发中，见 Issue #14',
  logs: '变更留痕开发中，见 Issue #14',
};

function describeCoord(coord: Record<string, unknown>, dimensions: Dimension[]): string {
  const keys = Object.keys(coord);
  if (!keys.length) return '默认答案 · 处处适用';
  const parts = keys
    .sort()
    .map((k) => `${dimensions.find((d) => d.key === k)?.label ?? k} = ${String(coord[k])}`);
  return `适用条件：${parts.join(' 且 ')}`;
}

function AnswerRow({
  group,
  dimensions,
  isTop,
  onEdit,
}: {
  group: AnswerGroup;
  dimensions: Dimension[];
  isTop: boolean;
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
          <a onClick={onEdit}>编辑</a>
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
                <button type="button" className="btn primary" onClick={() => setWriteTarget('create')}>
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

        {tab !== 'now' ? (
          <div className="empty-block">{TAB_PLACEHOLDER[tab]}</div>
        ) : (
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
                  key={g.latest_answer.id}
                  group={g}
                  dimensions={dimensions}
                  isTop={uniqueTop && i === 0}
                  onEdit={() => setWriteTarget({ answerId: g.live_answer!.id, coord: g.coord, content: g.live_answer!.content })}
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
