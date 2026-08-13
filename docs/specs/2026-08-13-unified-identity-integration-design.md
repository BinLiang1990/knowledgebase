# 设计：统一知识库接入统一身份认证平台（SSO）

依据：《Python-Vue项目统一身份认证平台对接实施手册》v1.0（2026-08-13，标签系统同款方案）+ 《系统架构图》v0.5（统一身份管理系统 R9：只发门禁卡、进门后权限归各系统自建）。

## 0. 结论先行

- 本系统（统一知识库，横向能力层）**在接入范围内**，理论上必须接：架构铁律是"身份统一/授权下放"，R9 身份下发覆盖全部子系统。
- 与标签系统不同的关键点：**我们目前没有任何用户体系**（无登录页、无 users 表、无鉴权头，`operator` 是前端自由文本输入）。所以这不是"改造现有登录"，而是"从零建最小用户体系 + 对接"，历史包袱为零，但手册中"本地账号密码模式"需要裁剪决策（见 §2 D1）。
- 接入顺带解决两件悬案：
  - **#31 操作人身份**：登录后 `operator` 由后端从认证身份取（realName/account），前端不再传自由文本——#31 可就此关闭。
  - **#15-A 接口鉴权**：原设计的"静态 API Key + nginx 注入"针对运营前端的部分**被本方案取代**（真登录替代假注入）；第三方只读对接面的鉴权仍是独立轨道（见 §4）。

## 1. 现状 vs 手册假设

| 手册假设 | 我们的现状 | 差距 |
| --- | --- | --- |
| 子系统已有本地账号密码登录 | 无任何登录 | 需决策：本地开发模式是建本地登录，还是保持免登录（D1） |
| 已有 users 表，增加身份快照字段 | 无 users 表 | 全新建表（反而简单，无迁移兼容问题） |
| 已有业务角色/租户体系 | 无角色概念 | 不是多租户系统，只需最小角色（sysadmin / user）（D2） |
| 前端 Axios + Pinia + Router 齐备 | ✅ 都有（Pinia 目前是空壳 app store） | 加 user store、登录页、/sso 接票页、守卫、拦截器 |
| API 全部面向已登录人类用户 | 有**第三方只读 GET 对接面**（对接约定 v1 明确无鉴权 + 过渡期承诺） | IDENTITYTOKEN 流程不适用于机器调用，需要路由分面（D3 / §4） |
| hash 路由 `/#/sso` 接票 | ✅ 本来就是 hash router | entryUrl = `https://platform-enterprise.yicall.com/#/sso` |

## 2. 需要决策的点

### D1 本地开发模式：建议「免登录直通」而非本地账号密码

手册的双模式是为已有本地登录的项目设计的。我们为了本地开发凭空建一套账号密码（注册/哈希/重置）不值得。建议：

- `AUTH_MODE=off`（本地默认）：后端鉴权依赖直通，返回内置开发者身份（`operator="dev"`）；前端不渲染登录页。行为 = 今天的现状。
- `AUTH_MODE=unified`（正式）：完整 SSO 流程，手册全套红线适用。
- **不实现** 手册的 local 账号密码模式。偏离手册之处仅此一项，且方向更严（少一种可被误开的登录方式；手册红线本来就要求正式环境关闭本地登录）。

### D2 角色与权限粒度（对齐打标系统模式，2026-08-13 用户确认方向）

打标系统的既定模式：**用户由统一平台下发（首次进入自动出现在用户管理页），未授权时可登录但看不到业务数据；权限由子系统自己的「用户管理」页人工授权**（打标系统的授权粒度是租户）。本系统对齐同一模式：

| 平台 roleCode | 首次进入的本系统状态 | 说明 |
| --- | --- | --- |
| `super_admin` | `sysadmin`（系统管理员） | 唯一自动提权；全部业务数据读写 + 用户管理页 |
| `admin` / 其他 / 无角色 | `user` + **未授权** | 可登录，只能访问"暂无权限"页与 /auth/me，看不到业务数据 |

授权模型（我们没有租户，业务对象是**系统级角色**，v1 不做按知识库授权）：

- 用户管理页（系统管理员可见）对每个用户授予系统级角色：`admin`（读写全部业务数据）/ `editor`（读写知识点/答案/关联，不含维度配置与用户管理）/ `viewer`（只读）/ 未授权（默认）。
- 手动授予的角色与平台快照分开存储（`role` 人工授权 vs `platform_role_code` 快照）——平台角色变化不覆盖人工授权，`super_admin` 例外（自动 sysadmin）。
- 预留扩展：若将来需要"按知识库授权"（对应打标系统的按租户授权），加 `user_kb_roles` 关系表即可，users 表结构不变。

（手册红线严格遵守：`admin` 不自动获得任何管理权限；不凭 roleId 提权。）

### D3 第三方只读对接面怎么办

见 §4。建议 v1 保持开放（对接约定的既有承诺），写接口全部上锁；机器凭证是平台既有能力（架构图：服务间机器凭证），等平台侧流程明确后作为二期。

## 3. 实施设计

### 3.1 后端（FastAPI）

**新表 `users`**（alembic 0006）：

```text
id / identity_user_id (UNIQUE, NULL for dev) / identity_account / display_name
/ role (sysadmin|admin|editor|viewer|none)   ← none=未授权（首登默认）
/ auth_source (unified|dev) / org_id / org_code / org_name
/ platform_role_code / identity_updated_at / first_login_at / created_at / updated_at
```

**新模块 `kb_backend/auth/`**：

- `unified_client.py`：手册 §6.1 参考实现适配——httpx（新依赖）、HMAC 六段式签名、`/core/sso/exchange` 换票、`/core/user/userInfo` + `/core/user/roleList`、紧凑 JSON 字节一致性、业务包络 `code=200` 判定、`loginDeviceType` 优先。逐条对照手册 §11.1 测试用例写纯逻辑单测（HMAC 固定输入固定签名等，不依赖 DB fixture）。
- `sync.py`：按统一 `userId` 首登即建快照 / 再登更新；仅 `roleCode == 'super_admin'` 映射 `sysadmin`。
- `deps.py`：`get_current_user` 依赖——`AUTH_MODE=off` 直通开发者身份；`unified` 读 `IDENTITYTOKEN` + `X-Identity-App-Type`，带**进程内 TTL 缓存（60s，键=token 哈希）**避免每请求远程验证（手册 §6.4 建议；本系统规模小，无需 Redis）；失效返回 401（envelope code=401，前端拦截器识别）。

**路由 `routers/auth.py`**：`POST /auth/sso_login`、`GET /auth/me`、`POST /auth/logout`（仅清本地态说明，平台 Token 由平台管理）。

**路由 `routers/user.py`（用户管理，仅 sysadmin）**：`GET /users`（列表：用户/来源/平台角色快照/本系统角色/首次进入时间）、`PATCH /users/{id}/role`（授权，写 change_log 式留痕）。

**鉴权覆盖面**（unified 模式；off 模式全部直通）：

- 运营前端全部业务接口挂 `get_current_user` + 角色检查：读需 `viewer+`；知识点/答案/关联写需 `editor+`；维度配置/建删知识库需 `admin+`；用户管理仅 `sysadmin`。`role=none` 一律 403 `AUTH_PERMISSION_DENIED`（保留登录态，前端展示"暂无权限，请联系系统管理员"）。
- **第三方只读 GET 对接面豁免**（D3/§4）：豁免清单按对接文档路由前缀显式列出，不用"所有 GET 都豁免"的隐式规则。
- **`operator` 字段改由后端从当前用户取 `display_name`**，schema 中前端传入的 operator 降级为可选并忽略（unified 模式）/沿用（off 模式），#31 关闭。

**配置**（`config.py` + `.env`，key 永不入库）：`AUTH_MODE`、`AUTH_SYSTEM_CODE`、`IDENTITY_BASE_URL`、`IDENTITY_CLIENT_ID/SECRET`、`IDENTITY_APP_TYPE=ADMIN` 兜底、`AUTH_ACCEPTED_TICKET_TYPES=SAME_DOMAIN`。

### 3.2 前端（Vue 3）

- `store/modules/user.ts`（Pinia）：token/appType/当前用户；storage key 按手册 §7.2 命名空间（`enterprise-platform:auth:PUBLIC:token` 共享同域 Token），**禁 `localStorage.clear()`**。
- `views/sso/index.vue`：接票页——hash/query 双兼容取 ticket、**立即 replaceState 清地址栏**、失败提示"从统一工作台重新进入"、不重试不落盘。
- `router/guard.ts`：unified 模式下 `/login` 直接 `location.replace` 平台登录页；`/sso` 无条件放行；无 token 跳 `/login`；off 模式保持现状（只写标题）。
- `api/request.ts` 拦截器：请求带 `IDENTITYTOKEN` + `X-Identity-App-Type`；响应 401 清 token/appType → 跳登录（登录接口自身的 401 除外）。
- 构建配置：`VITE_AUTH_MODE`（off/unified）、`VITE_IDENTITY_LOGIN_URL`；正式构建 unified。
- 写答案等表单的 `operator` 输入框：unified 模式隐藏（后端自动取）。
- `views/system/users.vue` 用户管理页（对齐打标系统布局：用户/来源/最高角色/授权/首次进入/操作），仅 sysadmin 可见，侧边栏「系统设置」分组。
- `views/no-permission.vue` 暂无权限页：`role=none` 用户登录后的落点，提示联系系统管理员。
- 顶栏用户区：显示当前用户姓名 + 角色 + 退出。

### 3.3 运维 / 平台侧

- nginx：确认自定义头透传（`IDENTITYTOKEN`、`X-Identity-App-Type` 无下划线，默认放行，无需 `underscores_in_headers`）。
- 平台登记（手册 §2，**禁止猜测，需向平台方取**）：
  - `systemCode` / `clientId` / `clientSecret`
  - `authDomain`：应为 `PUBLIC`（我们在 platform-enterprise.yicall.com 公网域）
  - `entryUrl`：`https://platform-enterprise.yicall.com/kb-web/#/sso`（前端挂在 /kb-web 子路径下）
  - `acceptedTicketTypes`：`SAME_DOMAIN`
  - 确认 `userInfo`/`roleList` 能返回稳定 `roleCode`

## 4. 第三方只读对接面（与 SSO 分轨）

- 对接方是**机器调用**（R1 知识点引用等），没有浏览器登录态，IDENTITYTOKEN 流程天然不适用。
- v1：GET 对接面维持无鉴权（对接约定基准版的既有承诺 + 过渡期条款），网络层白名单为底线（#15-A1，运维项）。
- 二期：架构图明确统一身份系统签发**服务间机器凭证**——待平台机器凭证的申请/校验流程有文档后，对接面切机器凭证，同样走"发凭证→联调→约定日期强制"过渡。原 #15-A2 的自建 api_client 表方案**挂起**，避免和平台机器凭证重复建设。

## 5. 与既有 issue 的关系

| issue | 影响 |
| --- | --- |
| #15-A 鉴权 | 运营前端部分由本方案取代（真登录）；第三方部分转"平台机器凭证"二期；自建 API Key 挂起 |
| #31 操作人身份 | 由本方案直接解决（operator=认证身份），实现后可关闭 |
| #15-B/C 并发/性能 | 不受影响，独立排期 |

## 6. 工作量与阶段

| 阶段 | 内容 | 估时 |
| --- | --- | --- |
| P1 后端 | users 表 + unified_client + 鉴权依赖（角色检查/对接面豁免）+ auth/user 路由 + operator 收编 + 纯逻辑单测 | ~2.5 天 |
| P2 前端 | user store + /sso + 守卫 + 拦截器 + 登录跳转 + 用户管理页 + 暂无权限页 + operator 输入框隐藏 | ~2 天 |
| P3 联调 | 平台登记参数到位后：测试 Ticket 换票 → 三类角色验收（手册 §11.3 矩阵）+ 未授权/授权后数据可见性验收 | 依赖平台方 |

**前置阻塞**：手册 §2 的平台登记参数（systemCode/clientId/clientSecret/entryUrl）必须先向统一平台方申请，代码可先行（AUTH_MODE=off 下开发不受影响）。
