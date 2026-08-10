import { NavLink } from 'react-router-dom';
import logo from '../../assets/logo.png';

// Design doc §4.2 (issue #6): only render nav items whose page actually
// exists yet. 维度管理 (issue #13) and 操作日志 (issue #14) are both filled
// in now — every item PRD/demo's global nav lists is present.
export function Sidebar() {
  return (
    <aside className="side">
      <div className="side-logo">
        <img src={logo} alt="" className="side-logo-mark" />
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
        <NavLink to="/change-log" className={({ isActive }) => `side-item${isActive ? ' sel' : ''}`}>
          <span className="ic">⟲</span>操作日志
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
