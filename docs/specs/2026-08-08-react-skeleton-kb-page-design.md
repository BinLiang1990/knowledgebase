# React 项目骨架 + 知识库管理页面（issue #6）

## 1. 范围

按 issue #6：搭建 React 项目骨架（路由、API 请求封装、UI 规范对应的样式基座），实现知识库列表页（搜索/新增/编辑/停用启用），对接 issue #2 已有的知识库 CRUD API。不含知识点列表/详情、维度管理、知识库设置、操作日志——这些页面各自有自己的 issue(#7/#8/#13/#14)。

参考物：`frontend-mock/kb-list.html` + `frontend-mock/assets/{app.js,style.css}`(交互与视觉已验证过的静态原型)、`UI规范-企业信息管理平台(1).md`(视觉规范权威来源，demo 的 CSS 就是照这份规范写的)。

## 2. 技术选型

| 项 | 选择 | 理由 |
|---|---|---|
| 构建工具 | Vite | React 官方推荐,冷启动/HMR 快,配置量小 |
| 语言 | TypeScript | 后端全程强类型(Pydantic),前端跟进同一水准；接口契约(`{code,data,msg}`)用类型直接约束,减少字段拼错这类低级错误 |
| 路由 | react-router-dom v7 | 事实标准 |
| 数据请求/缓存 | TanStack Query | UI 规范 §5.6 要求"三态必备"(加载中/空态/失败),TanStack Query 的 `isLoading/isError/data` 正好对应,配合 mutation 的 `onSuccess` 做"改完自动刷新列表",比手写 `useEffect+useState` 更不容易漏状态 |
| 样式 | 无框架,直接移植 UI 规范 §9 CSS 基座 + §3 组件配方 | demo 本身就是照这份规范手写的纯 CSS,规范明确"不允许即兴新增色值"——引入 Tailwind/MUI 等于另起一套视觉语言,和已验证的 demo 视觉不一致,也违反规范 §11 的初衷 |
| 测试 | Vitest + React Testing Library + MSW | MSW 在网络层拦截真实的 `fetch` 调用,比 mock 模块更接近"真实请求-响应"的集成测试精神(和后端"跑真实数据库"的测试哲学呼应,前端这里的对应物是"真实发出的 HTTP 请求，只是响应体是编好的") |

项目目录：`frontend/`,与 `backend/` 同级。

## 3. 目录结构

```
frontend/
  src/
    api/
      client.ts        # fetch 封装,处理 {code,data,msg} 信封
      knowledgeBases.ts # 知识库相关的请求函数 + TanStack Query hooks
    components/
      layout/           # Sidebar / TopBar / AppShell
      ui/                # Modal / Toast(Provider) / Pager / Button 等通用组件
    pages/
      KnowledgeBaseListPage.tsx
    styles/
      tokens.css        # UI 规范 §9 CSS 基座(设计令牌 + 全局 reset)
      components.css    # §3 组件配方(按钮/卡片/表格/表单/标签/弹窗/分页/toast...)
    main.tsx
    App.tsx             # 路由表
  vite.config.ts
  tsconfig.json
  .env.example          # VITE_API_BASE_URL
```

## 4. 需要明确的工程细节

### 4.1 后端缺 CORS 配置——本 issue 顺带补上

前端(Vite dev server,默认 `5173` 端口)请求后端(`8000` 端口,见 `backend/README.md`)是跨源请求,后端当前完全没有配置 `CORSMiddleware`,浏览器会直接拦掉请求。这是前后端集成的硬阻塞,不是"以后再说"的问题——issue #6 的验收标准"项目可以本地起服务，接入后端知识库 API"做不到就无法验收。在 `backend/src/kb_backend/config.py` 加一个 `cors_allowed_origins` 配置项(逗号分隔字符串,默认含 `http://localhost:5173`/`http://127.0.0.1:5173`),`main.py` 里挂 `CORSMiddleware`。这是本 issue 唯一需要动后端代码的地方。

**只加中间件不够,必须显式声明 `allow_methods`/`allow_headers`(对抗式自校发现的 blocker)。** Starlette `CORSMiddleware` 不传这两个参数时默认值是 `allow_methods=("GET",)`、`allow_headers=()`——新增知识库用 `POST`、编辑用 `PATCH`、停用启用用 `POST`,并且全部带 `Content-Type: application/json` 请求头,这些都不是 CORS 规范里的"安全默认值",浏览器会先发一次 `OPTIONS` 预检请求,默认配置下预检会失败,导致除了 `GET` 以外的所有请求在浏览器里全部被拦掉——代码审查时中间件"看起来加上了",实际上除了列表查询,别的功能都会静默失败,只有在浏览器里点按钮才会发现。必须显式写 `allow_methods=["GET","POST","PATCH"]`、`allow_headers=["Content-Type"]`(或都用 `["*"]`，dev 环境不存在敏感头/方法暴露风险)。

### 4.2 侧栏导航只渲染已经存在的页面,不放死链接

demo 的侧栏有"知识库列表/维度管理/操作日志"三个入口,但后两个对应的页面(issue #13、#14)还没做。渲染出去点了却 404 或者什么都不做,是比"暂时不显示"更差的体验。本 issue 侧栏只渲染"知识库列表"这一项,其余导航项随对应 issue 交付时再加入,不做"渲染但禁用/即将推出"这种中间状态——UI 规范和 demo 都没有定义"禁用导航项"的样式,不要自己发明一种。

### 4.3 知识库名称先不做超链接,操作列也不放"进入"

demo 的操作列里,"启用中"的知识库除了名称本身是链接,还单独有一个"进入"文字链接,两个都指向知识点列表页(`index.html?kb=...`)——这个页面是 issue #7 的范围,现在还不存在。本 issue 里两处都不放：名称是纯文本,操作列对 active 的知识库只有"编辑"+"停用"两项,对 deprecated 的知识库是"编辑"+"启用"两项,没有"进入"。等 #7 交付知识点列表页后,再把名称改成 `<Link>`、操作列加回"进入"。

### 4.4 统一错误处理：`ApiError` + Toast

`client.ts` 里对每个响应先看 HTTP 状态,再解析 body 的 `{code,data,msg}`：
- `code === 200` → 返回 `data`
- `code !== 200`(约定里恒为 444) → 抛出 `ApiError(msg)`
- HTTP 层面炸了(网络错误、非 JSON 响应、5xx 没有走到业务 code)→ 抛出 `ApiError("网络异常，请稍后重试")` 这样的兜底文案,不把原始的 `TypeError: Failed to fetch` 之类的技术性报错抛给用户

所有 mutation(创建/编辑/停用/启用)的 `onError` 统一转成 `toast.err(error.message)`；不在每个页面单独写 try/catch。查询类的 `isError` 状态在页面里用 UI 规范 §5.6 的"失败态"渲染(文案+重试)。

### 4.5 表单校验错误(422)与业务错误(444)展示位置不同

422(字段格式错误,比如名称超长)在 demo 原型里是弹窗内联提示(`kbFormHint`),不是 toast；444(业务错误,比如"名称已存在")在真实后端里也是通过同一个响应体返回,但**语义上属于表单级错误**(和名称输入框相关),所以两者都走"弹窗内联提示"这一条路径,不是"表单校验错误内联、业务错误 toast"两套逻辑——只有创建/编辑这类表单类操作的错误内联在弹窗里,停用/启用/删除这类"确认类"操作的错误才用 toast(因为它们没有一个"表单"可以内联)。

**422 的 `msg` 是一句固定的通用文案,不含具体字段信息(对抗式自校核实)。** `envelope.py` 的 `RequestValidationError` 处理器故意把 pydantic 报错的字段级细节丢弃、只在服务端日志里留一份,返回给客户端的 `msg` 统一是"请求参数校验失败"这句固定文案,不会说"名称超过255个字符"这种具体内容(这是 issue #20 Kimi 终审就定下的设计,不是本 issue 才发现的疏漏)。所以前端表单必须**提前在客户端做好和后端一致的约束**(名称必填、trim 后非空、`maxLength=255`；描述 `maxLength=2000`),让 422 变成"几乎不会真的触发"的兜底路径,而不是依赖 422 的返回文案指导用户改哪里——如果真的触发了 422(说明客户端校验和后端约束不一致),内联提示只能显示这句通用文案,这是已知的、可接受的降级体验,不是本 issue 要解决的问题。

## 5. 知识库列表页组件拆解

对照 `kb-list.html`：
- `Notice`(说明知识库/维度关系,§3.18 `notice` 组件)
- `Card`(§3.3):内含
  - `CardHead`(tick+"知识库列表"+"全部知识库"+渐变延伸线+"+ 新增知识库" primary 按钮)
  - 搜索行(关键词输入,Enter 提交 + 查询/重置按钮)
  - `KnowledgeBaseTable`(名称/描述/知识点数/状态/创建时间/操作)
  - `Pager`
- `KnowledgeBaseFormModal`(新增/编辑共用,内联错误提示)
- `ToggleStatusModal`(停用需要风险说明块;启用不需要,对应 §5.2 危险操作三要素——只有"停用"是危险操作,"启用"不是)

搜索：前端本地过滤还是请求后端？issue #2 的 `GET /knowledge-bases` 目前不支持关键字搜索(`?status=` 是唯一的过滤参数)。知识库数量级小(§7 非功能需求没把知识库列表列为需要服务端分页的对象),延续 demo 的做法——**一次性拉取全部知识库(含 deprecated),关键字搜索和分页都在前端内存里做**,不新增后端接口。

## 6. 测试计划

- `client.ts`:`code=200` 返回 `data`；`code=444` 抛 `ApiError`；HTTP 500 抛兜底错误
- KB 列表页(MSW 拦截 `/knowledge-bases`):加载态 → 数据渲染;空列表渲染空态文案;请求失败渲染失败态
- 搜索:关键词过滤名称/描述,Enter 提交,清空重置
- 新增:表单校验(名称必填)内联提示;提交成功后弹窗关闭+列表刷新+toast
- 新增重名(mock 444 响应):内联错误提示显示后端返回的 `msg`,弹窗不关闭
- 编辑:预填现有值;提交成功后列表刷新
- 停用:确认弹窗展示风险说明;确认后调用 `.../deactivate`,列表刷新
- 启用:确认弹窗不展示风险说明(非危险操作);确认后调用 `.../activate`

## 7. 手动验证

跑真实后端(`uv run uvicorn kb_backend.main:app`)+ 真实前端 dev server,在浏览器里过一遍：搜索、新增(含重名报错)、编辑、停用(含风险提示)、启用,确认网络请求打到真实 API、数据库里的行确实发生变化(通过 `GET /knowledge-bases` 或直连 DB 核对)。

**这一步不是可选的,尤其是 CORS。** MSW 是在 Node 里拦截 `fetch` 调用做单测,不会模拟浏览器真实的 CORS 预检/跨源检查——§4.1 那类"中间件加了但 `allow_methods`/`allow_headers` 没配对"的 bug,Vitest+MSW 套件会全部跑绿,只有在真浏览器里点"新增/编辑/停用/启用"才会暴露。手动验证时打开浏览器 devtools 的 Network 面板,确认这几个非 GET 请求没有被 CORS 拦截(没有 `OPTIONS` 预检失败、没有 "blocked by CORS policy" 的报错),不能只看页面表面上"看起来正常"就算过。

**实际执行记录：这次没有真实 GUI 浏览器可用,退而求其次用 curl 模拟了浏览器会发出的真实请求。** 同时跑真实后端(`8000` 端口)和真实 Vite dev server(`5173` 端口),用 `curl` 手工构造浏览器会发出的 `OPTIONS` 预检请求(带 `Origin: http://localhost:5173`、`Access-Control-Request-Method`/`Headers`),确认响应里 `access-control-allow-origin`/`access-control-allow-methods` 都正确,再用同样的 `Origin` 头发真实的 `POST`/`PATCH`/激活/停用请求,确认业务逻辑(含重名报错)和数据库状态变化都正确。这比 TestClient 跑的 `test_cors.py`(同进程 ASGI 调用,不是真实 HTTP)更接近真实场景,但仍然不是"在浏览器里点按钮"本身——没有条件跑这一步就诚实说明,不假装已经做了完整的浏览器验证。
