import { NavLink } from 'react-router-dom';

// Design doc §4.2 (issue #6): only render nav items whose page actually
// exists yet — 操作日志 still lands in issue #14. Adding it now as a dead
// link would be worse than omitting it; the spec/demo define no "disabled
// nav item" style to fall back on. 维度管理 is filled in by issue #13.
export function Sidebar() {
  return (
    <aside className="side">
      <div className="side-logo">
        <span className="h-bar" />
        <span className="name">
          知识库管理
          <small>KNOWLEDGE BASE ADMIN</small>
        </span>
      </div>
      <div className="side-group">全局</div>
      <nav className="side-menu">
        <NavLink to="/knowledge-bases" className={({ isActive }) => `side-item${isActive ? ' sel' : ''}`}>
          <span className="ic">▦</span>知识库列表
        </NavLink>
        <NavLink to="/dimensions" className={({ isActive }) => `side-item${isActive ? ' sel' : ''}`}>
          <span className="ic">▤</span>维度管理
        </NavLink>
      </nav>
      <div className="side-foot">
        v0.1 · React + 真实后端
        <br />
        接口约定见 docs/PRD.md §4.10
      </div>
    </aside>
  );
}
