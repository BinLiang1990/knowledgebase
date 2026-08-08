import type { Dimension } from '../api/dimensions';
import { useAnswerGroups, type KnowledgePoint } from '../api/knowledgePoints';
import { AnswerGroupTree } from './AnswerGroupTree';

interface KnowledgePointRowProps {
  kp: KnowledgePoint;
  kbId: number;
  at: string | undefined;
  qMode: 'now' | 'day';
  expanded: boolean;
  onToggleExpand: () => void;
  onDeleteRequest: () => void;
  dimensions: Dimension[];
  hasFilter: boolean;
}

function CoordTags({ coord, dimensions }: { coord: Record<string, unknown>; dimensions: Dimension[] }) {
  return (
    <>
      {Object.entries(coord).map(([key, value]) => (
        <span key={key} className="tag blue">
          {dimensions.find((d) => d.key === key)?.label ?? key} = {String(value)}
        </span>
      ))}
    </>
  );
}

export function KnowledgePointRow({
  kp,
  kbId,
  at,
  qMode,
  expanded,
  onToggleExpand,
  onDeleteRequest,
  dimensions,
  hasFilter,
}: KnowledgePointRowProps) {
  const groupsQuery = useAnswerGroups(kbId, kp.id, at, expanded);
  const { status, answer } = kp.resolved;

  return (
    <div className="trow">
      <div className="trow-main" onClick={onToggleExpand}>
        <span className="arrow">{expanded ? '▾' : '▸'}</span>
        <span style={{ fontWeight: 600, fontSize: '14.5px' }}>{kp.title}</span>
        <span className="trm-meta">{kp.active_answer_count} 条答案</span>
        <span style={{ flex: 1 }} />
        <span className="ops" onClick={(e) => e.stopPropagation()}>
          <a className="danger" onClick={onDeleteRequest}>
            删除
          </a>
        </span>
      </div>
      <div className="trow-ans">
        {qMode === 'day' ? (
          <>
            回看 <span className="num">{at}</span>
          </>
        ) : (
          '当前'
        )}
        ：
        {status === 'none' || !answer ? (
          <span style={{ color: 'var(--ink-7)' }}>
            {hasFilter ? '这个条件、这个时间点还没有匹配的答案' : '还没有写过任何答案'}
          </span>
        ) : status === 'default' || status === 'fallback-latest' ? (
          <>
            {status === 'default' ? (
              <span className="tag gray">默认</span>
            ) : (
              <span className="tag orange">无默认 · 取最新</span>
            )}{' '}
            {answer.content}
          </>
        ) : (
          <>
            {answer.content} <CoordTags coord={answer.coord} dimensions={dimensions} />
            {status === 'exact' ? (
              <span className="tag green" style={{ marginLeft: 4 }}>
                精确命中
              </span>
            ) : (
              <span className="tag orange" style={{ marginLeft: 4 }}>
                未精确命中 · 按权重回退
              </span>
            )}
          </>
        )}
      </div>
      {expanded && (
        <>
          {groupsQuery.isLoading && <div className="mini-note" style={{ padding: '8px 0' }}>加载中…</div>}
          {groupsQuery.isError && <div className="mini-note" style={{ padding: '8px 0' }}>加载失败</div>}
          {groupsQuery.data && <AnswerGroupTree groups={groupsQuery.data} dimensions={dimensions} />}
        </>
      )}
    </div>
  );
}
