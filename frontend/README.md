# kb-frontend

Vue 3 前端，技术栈与工程约定遵循仓库根目录的《[前端开发规范.md](../前端开发规范.md)》：
Vue 3（`<script setup lang="ts">`）+ TypeScript strict + Vite + vue-router（hash 模式）+
Pinia + Element Plus（unplugin 按需自动引入）+ axios/json-bigint + SCSS + ESLint（antfu）+ pnpm。

视觉设计仍以《UI规范-企业信息管理平台(1).md》为准——设计 tokens 与组件配方在
`src/styles/index.scss`，「任何颜色、字号、圆角、阴影都必须取自该文档，不允许即兴新增色值」。
弹窗/分页/消息提示三类交互原语由 Element Plus 承担（`el-dialog`/`el-pagination`/`ElMessage`），
主题调优见 `src/styles/element.scss` 与 `src/styles/dialog.scss`。

## 环境准备

```bash
cd frontend
corepack enable || npm i -g pnpm@9   # 包管理器固定 pnpm 9.x（见 package.json 的 packageManager）
pnpm install
```

## 启动与常用命令

```bash
pnpm dev          # http://localhost:3300，/kb-api 由 vite 代理到本地后端 8000（见 .env.development）
pnpm build        # vue-tsc 类型检查 + 生产构建，产出 dist/
pnpm build:pack   # 同上并打包为 dist.tar.gz（交付物）
pnpm typecheck    # 仅类型检查
pnpm lint         # eslint . --fix（唯一的风格来源，提交前必须通过）
pnpm test         # vitest：utils/ 纯逻辑单元测试（coord/resolve/timeline）
```

后端启动方式见 `backend/README.md`。dev 走 vite 代理（同源），本地开发不再依赖后端 CORS 配置。

## 环境变量（`.env.development` / `.env.production`，均入库）

| 变量 | 说明 |
|---|---|
| `VITE_APP_TITLE` | 页面标题 |
| `VITE_APP_BASE_API` | 接口前缀（统一 `/kb-api`）：dev 由 vite 代理剥前缀转发，生产由 nginx 反代同一前缀 |
| `VITE_PROXY_TARGET` | 仅 dev：代理的后端地址，默认 `http://127.0.0.1:8000` |

全部变量在 `src/env.d.ts` 的 `ImportMetaEnv` 中声明；新增变量必须同步声明并写中文注释。

## 目录结构

```
src/
  main.ts          # 应用装配入口
  App.vue          # el-config-provider(zhCn) + router-view
  settings.ts      # 全局协议常量（响应码等）
  api/             # 接口层：按后端 Controller 一文件，类型与函数就近成对
  components/      # 跨模块复用组件（ChangeLogTable / RevokeAnswerDialog / ValueInput）
  composables/     # useAsyncData（取数三件套）/ useCrumb（动态面包屑）
  layout/          # 布局壳（侧栏 + 顶栏 + router-view）
  router/          # hash 路由；modules/ 一业务模块一文件，import.meta.glob 自动收集
  store/           # Pinia；modules/app.ts（顶栏面包屑覆盖）
  styles/          # variables.scss（仅变量）/ index.scss（tokens+组件配方）/ element.scss / dialog.scss
  types/           # ApiResult 等跨模块类型、router.d.ts 的 meta 扩展
  utils/           # request（axios+json-bigint）/ format / dimension / coord / resolve / timeline
  views/           # 页面：views/<module>/<page>/index.vue，页面私有弹窗与页面同级
  test/            # 单测数据工厂
```

## 新增一个业务模块的标准步骤

1. `src/api/<module>.ts`：定义类型 + `listXxx/createXxx/...` 函数，JSDoc 标对接文档章节号。
2. `src/router/modules/<module>.ts`：默认导出路由（数组），菜单项带 `meta: { title, icon, order }`，
   子页 `hidden: true`；`asyncRoutes.ts` 自动收集，侧边栏菜单自动出现，其余零改动。
3. `src/views/<module>/<page>/index.vue`：`defineOptions({ name })` 与路由 name 一致；
   取数用 `useAsyncData`，卡片/表格/标签复用 `styles/index.scss` 里已有类名。
4. 弹窗与页面同级：`XxxDialog.vue`，统一「`visible` ref + `defineExpose({ open })` +
   `emit('success')`」非受控模式，`el-dialog` 加 `class="app-dialog"` 与
   `:close-on-click-modal="false"`。
5. 模块内跨页共享的组件放 `views/<module>/components/`，纯函数放 `views/<module>/shared.ts`。

## 测试

`pnpm test` 覆盖 `src/utils/` 的纯逻辑（坐标比较、resolve 排序、时间线分组——历史评审
发现过真实 bug 的部分）。原 React 版的组件/页面测试（React Testing Library + MSW）随框架
迁移移除，尚未以 @testing-library/vue 重建；如需恢复组件级测试，从 git 历史的
`*.test.tsx` 找回用例语义。
