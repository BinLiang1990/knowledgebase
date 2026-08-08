# kb-frontend

React 前端骨架，见 `docs/PRD.md` 与 `docs/specs/2026-08-08-react-skeleton-kb-page-design.md`（issue #6）。

## 环境准备

```bash
cd frontend
cp .env.example .env   # 默认值已指向后端本地开发端口 8000，一般不用改
npm install
```

## 启动

```bash
npm run dev       # http://localhost:5173，需要后端同时在 8000 端口运行
npm run build      # 类型检查 + 生产构建
npm run test        # Vitest + React Testing Library + MSW
npm run lint        # oxlint
```

后端启动方式见 `backend/README.md`。后端已配置 CORS 允许 `http://localhost:5173`/`http://127.0.0.1:5173`（见 `backend/src/kb_backend/config.py` 的 `cors_allowed_origins`）。

## 目录结构

```
src/
  api/         # 请求封装（{code,data,msg} 信封处理）+ 各资源的 TanStack Query hooks
  components/
    layout/    # Sidebar / TopBar / AppShell
    ui/        # Modal / Toast / Pager 等跨页面通用组件
  pages/       # 每个路由一个页面组件
  styles/      # 设计系统 CSS（移植自 `UI规范-企业信息管理平台(1).md` §9/§3）
  test/        # Vitest 测试基础设施（MSW server、渲染 helper）
```

新增页面时复用 `styles/` 里已有的类名（`.card`/`.tbl`/`.btn`/`.tag`/`.mask`...），不要新增色值或另起一套样式——设计规范原文要求"任何颜色、字号、圆角、阴影都必须取自本文档"。
