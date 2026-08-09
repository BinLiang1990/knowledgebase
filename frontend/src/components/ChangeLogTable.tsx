import { useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ACTION_LABEL, CHANGE_LOG_STATUS_LABEL, type ChangeLogEntry, type GlobalChangeLogEntry } from '../api/changeLog';
import { useAdminDimensions } from '../api/dimensions';
import { describeCoord } from '../api/answers';
import type { Dimension } from '../api/dimensions';
import { RevokeAnswerModal } from './RevokeAnswerModal';

// Discriminated union, not `entries: ChangeLogEntry[] | GlobalChangeLogEntry[]`
// (design doc §4.3, issue #14) — `showLocation: true` narrows `entries` to
// GlobalChangeLogEntry[] so the extra columns' fields (knowledge_base_name
// etc.) are accessible without a cast; the non-global variant instead
// carries kbId/kpId (every row shares the same one, unlike the global
// variant where each row's own knowledge_base_id/knowledge_point_id may
// differ — see RevokeAnswerModal's own comment for why that distinction
// matters for who instantiates useRevokeAnswer with what).
type ChangeLogTableProps =
  | { entries: ChangeLogEntry[]; showLocation?: false; kbId: number; kpId: number }
  | { entries: GlobalChangeLogEntry[]; showLocation: true };

const STATUS_TAG_CLASS: Record<ChangeLogEntry['status'], string> = {
  live: 'green',
  superseded: 'gray',
  revoked: 'red',
};

interface RevokeTarget {
  kbId: number;
  kpId: number;
  answerId: number;
  content: string;
}

export function ChangeLogTable(props: ChangeLogTableProps) {
  const [revokeTarget, setRevokeTarget] = useState<RevokeTarget | null>(null);
  // Admin (not enabled-only) dimensions — a change-log row is a permanent
  // historical record and may reference a dimension that has since been
  // globally deactivated; describeCoord falls back to the raw key when a
  // dimension isn't found, but this table would rather show its real
  // label whenever the dimension still exists at all, active or not.
  const dimensionsQuery = useAdminDimensions();
  const dimensions = dimensionsQuery.data ?? [];
  const colCount = props.showLocation ? 11 : 9;

  // Branching here (not inside a shared .map over a union-typed array) is
  // what lets TypeScript narrow props.entries to a concrete array type in
  // each branch — a single `.map` over `props.entries` at the top level
  // keeps its element type as `ChangeLogEntry | GlobalChangeLogEntry`
  // regardless of any earlier `props.showLocation` check, since narrowing
  // a discriminated union property doesn't propagate into a value already
  // extracted from it.
  const rows = props.showLocation
    ? props.entries.map((entry) => (
        <ChangeLogRow
          key={`${entry.answer_id}-${entry.action}-${entry.time}`}
          entry={entry}
          kbId={entry.knowledge_base_id}
          kpId={entry.knowledge_point_id}
          dimensions={dimensions}
          locationCells={
            <>
              <td>{entry.knowledge_base_name}</td>
              <td>
                <Link to={`/knowledge-bases/${entry.knowledge_base_id}/knowledge-points/${entry.knowledge_point_id}`}>
                  {entry.knowledge_point_title}
                </Link>
              </td>
            </>
          }
          onRevoke={setRevokeTarget}
        />
      ))
    : props.entries.map((entry) => (
        <ChangeLogRow
          key={`${entry.answer_id}-${entry.action}-${entry.time}`}
          entry={entry}
          kbId={props.kbId}
          kpId={props.kpId}
          dimensions={dimensions}
          locationCells={null}
          onRevoke={setRevokeTarget}
        />
      ));

  return (
    <>
      <div className="table-wrap">
        <table className="tbl">
          <thead>
            <tr>
              <th>时间</th>
              {props.showLocation && <th>知识库</th>}
              {props.showLocation && <th>知识点</th>}
              <th>操作人</th>
              <th>动作</th>
              <th>条件</th>
              <th>变更前</th>
              <th>变更后</th>
              <th>来源</th>
              <th>状态</th>
              <th className="op-col">操作</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={colCount} className="empty">
                  暂无变更记录
                </td>
              </tr>
            )}
            {rows}
          </tbody>
        </table>
      </div>
      {revokeTarget && (
        <RevokeAnswerModal
          kbId={revokeTarget.kbId}
          kpId={revokeTarget.kpId}
          answerId={revokeTarget.answerId}
          content={revokeTarget.content}
          onClose={() => setRevokeTarget(null)}
        />
      )}
    </>
  );
}

function ChangeLogRow({
  entry,
  kbId,
  kpId,
  dimensions,
  locationCells,
  onRevoke,
}: {
  entry: ChangeLogEntry;
  kbId: number;
  kpId: number;
  dimensions: Dimension[];
  locationCells: ReactNode;
  onRevoke: (target: RevokeTarget) => void;
}) {
  return (
    <tr>
      <td className="num" style={{ fontWeight: 400 }}>
        {entry.time.replace('T', ' ').slice(0, 19)}
      </td>
      {locationCells}
      <td>{entry.operator}</td>
      <td>{ACTION_LABEL[entry.action]}</td>
      <td style={{ color: 'var(--ink-4)' }}>{describeCoord(entry.coord, dimensions)}</td>
      <td style={{ maxWidth: 200, color: 'var(--ink-4)' }}>{entry.before_content ?? '—'}</td>
      <td style={{ maxWidth: 200 }}>{entry.after_content ?? '—'}</td>
      <td>
        <span className="tag purple">{entry.source}</span>
      </td>
      <td>
        <span className={`tag ${STATUS_TAG_CLASS[entry.status]}`}>{CHANGE_LOG_STATUS_LABEL[entry.status]}</span>
      </td>
      <td className="op-col ops">
        {entry.revocable ? (
          <a
            className="danger"
            onClick={() =>
              onRevoke({ kbId, kpId, answerId: entry.answer_id, content: entry.after_content ?? entry.before_content ?? '' })
            }
          >
            撤回
          </a>
        ) : (
          <span style={{ color: 'var(--ink-7)' }}>—</span>
        )}
      </td>
    </tr>
  );
}
