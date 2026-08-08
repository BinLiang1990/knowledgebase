import type { ReactNode } from 'react';
import type { Dimension } from '../api/dimensions';
import type { AnswerGroup } from '../api/knowledgePoints';

interface AnswerGroupTreeProps {
  groups: AnswerGroup[];
  dimensions: Dimension[];
}

function labelFor(dimensions: Dimension[], key: string): string {
  // A coord key that's no longer in the enabled-dimensions list (globally
  // deprecated, or since disabled for this KB) still gets shown by its raw
  // key — historical data staying visible after dimension deactivation is
  // expected behavior (PRD §6 rule #7), not an error state.
  return dimensions.find((d) => d.key === key)?.label ?? key;
}

function CoordChips({ coord, dimensions }: { coord: AnswerGroup['coord']; dimensions: Dimension[] }) {
  return (
    <>
      {Object.entries(coord).map(([key, value]) => (
        <span key={key} className="tag blue">
          {labelFor(dimensions, key)} = {String(value)}
        </span>
      ))}
    </>
  );
}

function Leaf({ group, labelNode }: { group: AnswerGroup; labelNode?: ReactNode }) {
  const arrow = labelNode ? (
    <>
      {labelNode} <span style={{ color: 'var(--ink-6)' }}>→</span>{' '}
    </>
  ) : (
    '· '
  );

  if (group.revoked) {
    return (
      <div className="tnode" style={{ cursor: 'default', color: 'var(--ink-6)' }}>
        {arrow}
        <s>{group.latest_answer.content}</s> <span className="cnt">已撤回，留痕保存</span>
      </div>
    );
  }
  if (!group.live_answer) {
    // Not yet effective at the selected time — distinct from revoked (see
    // design doc §2): the demo conflates the two, this is a deliberate
    // correction, not an oversight.
    return (
      <div className="tnode" style={{ cursor: 'default', color: 'var(--ink-6)' }}>
        {arrow}
        {group.latest_answer.content}{' '}
        <span className="cnt">
          <span className="num" style={{ fontWeight: 400 }}>
            {group.latest_answer.effective_time}
          </span>{' '}
          起生效 · 尚未生效
        </span>
      </div>
    );
  }
  return (
    <div className="tnode" style={{ cursor: 'default' }}>
      {arrow}
      {group.live_answer.content}{' '}
      <span className="cnt">
        <span className="num" style={{ fontWeight: 400 }}>
          {group.live_answer.effective_time}
        </span>{' '}
        起 · 共 {group.version_count} 版
      </span>
    </div>
  );
}

export function AnswerGroupTree({ groups, dimensions }: AnswerGroupTreeProps) {
  if (!groups.length) {
    return (
      <div className="kids">
        <div className="mini-note" style={{ padding: '8px 0' }}>
          还没有任何答案
        </div>
      </div>
    );
  }

  const defaultGroups = groups.filter((g) => Object.keys(g.coord).length === 0);
  const singleByKey = new Map<string, AnswerGroup[]>();
  const multiGroups: AnswerGroup[] = [];
  for (const g of groups) {
    const keys = Object.keys(g.coord);
    if (keys.length === 1) {
      const key = keys[0];
      singleByKey.set(key, [...(singleByKey.get(key) ?? []), g]);
    } else if (keys.length >= 2) {
      multiGroups.push(g);
    }
  }

  return (
    <div className="kids">
      {defaultGroups.length > 0 && (
        <>
          <div className="tnode" style={{ cursor: 'default' }}>
            ▾ <span className="tag gray">默认答案</span>
          </div>
          <div className="kids">
            {defaultGroups.map((g) => (
              <Leaf key={g.latest_answer.id} group={g} />
            ))}
          </div>
        </>
      )}
      {[...singleByKey.entries()].map(([key, groupsForKey]) => (
        <div key={key}>
          <div className="tnode" style={{ cursor: 'default' }}>
            ▾ <span className="tag purple">{labelFor(dimensions, key)}</span>{' '}
            <span className="cnt">{groupsForKey.length} 个取值</span>
          </div>
          <div className="kids">
            {groupsForKey.map((g) => (
              <Leaf
                key={g.latest_answer.id}
                group={g}
                labelNode={<span className="tag blue">{String(g.coord[key])}</span>}
              />
            ))}
          </div>
        </div>
      ))}
      {multiGroups.length > 0 && (
        <>
          <div className="tnode" style={{ cursor: 'default' }}>
            ▾ <span className="tag purple">组合条件</span> <span className="cnt">{multiGroups.length} 条</span>
          </div>
          <div className="kids">
            {multiGroups.map((g) => (
              <Leaf
                key={g.latest_answer.id}
                group={g}
                labelNode={<CoordChips coord={g.coord} dimensions={dimensions} />}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
