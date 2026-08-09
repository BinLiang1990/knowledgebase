import { Link } from 'react-router-dom';

type KbTabKey = 'kp-list' | 'settings';

const TABS: Array<[KbTabKey, string]> = [
  ['kp-list', '知识点列表'],
  ['settings', '知识库设置'],
];

// Only the two tabs that actually have a page behind them — demo's
// kb-tabs also has a "回收站" tab, but that page has never been built in
// this project and no tracked issue owns it; adding a tab that 404s would
// be worse than omitting it (design doc §1, issue #13).
export function KbTabs({ kbId, active }: { kbId: number; active: KbTabKey }) {
  return (
    <div className="tabs kb-tabs">
      {TABS.map(([key, label]) => (
        <Link
          key={key}
          to={key === 'kp-list' ? `/knowledge-bases/${kbId}/knowledge-points` : `/knowledge-bases/${kbId}/settings`}
          className={`tab${key === active ? ' active' : ''}`}
        >
          {label}
        </Link>
      ))}
    </div>
  );
}
