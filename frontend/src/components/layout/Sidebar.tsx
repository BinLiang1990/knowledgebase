import { NavLink } from 'react-router-dom';

// Design doc §4.2: only render nav items whose page actually exists yet —
// 维度管理/操作日志 land in later issues (#13/#14). Adding them now as
// dead links would be worse than omitting them; the spec/demo define no
// "disabled nav item" style to fall back on.
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
      </nav>
      <div className="side-foot">
        v0.1 · React + 真实后端
        <br />
        接口约定见 docs/PRD.md §4.10
      </div>
    </aside>
  );
}
