# 万能只读 Token 使用说明

> 面向：需要**查询**统一知识库数据（知识库、知识点、答案、维度、分类等）的内部同事 / 脚本 / 系统。
> 版本：v1.0（2026-08-20）

## 1. 是什么

万能只读 Token 是本系统自管的一个**静态长期凭证**：拿到 Token 的调用方无需接入统一身份认证平台、无需登录，即可调用全部**查询类接口**。

约束（服务端强制）：

- **只读**：仅允许 `GET` / `HEAD`。任何写操作（新建、修改、删除、启停等）一律返回 `403`。
- **不含用户管理面**：`/users*` 等系统管理员接口不可访问（`403`）。
- Token 值由系统管理员线下发放，**不要**写进任何仓库、前端代码或日志。

## 2. 怎么调用

在请求头带上 `X-Readonly-Token`：

```bash
curl -H "X-Readonly-Token: <发放给你的Token>" \
  "https://platform-enterprise.yicall.com/kb-api/knowledge-bases"
```

注意：

- `X-Readonly-Token` **不能**与 `IDENTITYTOKEN`（用户登录态）或 `X-Service-Token`（服务间凭证）同时携带，否则返回 `400`。
- 响应为统一包络：`{"code": 200, "data": ..., "msg": "操作成功"}`。

## 3. 可用的查询接口

| 接口 | 说明 |
| --- | --- |
| `GET /dimensions` | 启用中的维度定义列表 |
| `GET /admin/dimensions` | 全部维度定义（含停用） |
| `GET /categories` | 知识库分类树 |
| `GET /knowledge-bases` | 知识库列表（支持 `status`、`category_id` 过滤） |
| `GET /knowledge-bases/{kb_id}/enabled-dimensions` | 某库启用的维度 |
| `GET /knowledge-bases/{kb_id}/dimension-values` | 某库各文本维度的既有取值（条件搜索下拉用） |
| `GET /knowledge-bases/{kb_id}/stats` | 某库统计信息 |
| `GET /knowledge-bases/{kb_id}/knowledge-points` | 知识点列表（支持 `status`、`keyword`、`at`、坐标条件） |
| `GET /knowledge-bases/{kb_id}/knowledge-points/{kp_id}` | 知识点详情 |
| `GET /knowledge-bases/{kb_id}/knowledge-points/{kp_id}/resolve` | 按维度坐标解析生效答案 |
| `GET /knowledge-bases/{kb_id}/knowledge-points/{kp_id}/answer-groups` | 答案分组视图 |
| `GET /knowledge-bases/{kb_id}/knowledge-points/{kp_id}/answers` | 全部答案版本 |
| `GET /knowledge-bases/{kb_id}/knowledge-points/{kp_id}/answer-relations` | 答案关联列表 |
| `GET /knowledge-bases/{kb_id}/knowledge-points/{kp_id}/change-log` | 单知识点变更日志 |
| `GET /change-log` | 全局变更日志 |
| `GET /answer-relations/tasks/{task_id}` | 关联分析任务状态 |
| `GET /auth/me` | 回显当前凭证身份（联调自检用） |

各接口的入参与返回结构详见《统一知识库子服务对接文档》§3（读接口面字段说明通用）或在线 OpenAPI 文档 `GET /docs`。

## 4. 错误速查

| HTTP | msg | 原因 |
| --- | --- | --- |
| 401 | 万能只读 Token 无效 | Token 值不对，或服务端未配置该功能 |
| 403 | 万能只读 Token 仅支持查询接口（GET/HEAD）… | 尝试了写操作 |
| 403 | 暂无权限，请联系系统管理员分配权限 | 访问了只读面之外的管理接口（如 `/users`） |
| 400 | 请求不能同时携带万能只读 Token 与其他凭证 | 同时带了 `IDENTITYTOKEN` 或 `X-Service-Token` |

## 5. 运维侧（系统管理员）

- 配置项：后端 `.env` 的 `READONLY_TOKEN`（空 = 功能关闭）；改动后重启后端生效。
- 生成建议：`python -c "import secrets; print(secrets.token_urlsafe(32))"`。
- 轮换：换掉 `READONLY_TOKEN` 值并重启即可，旧值立刻失效；发放给调用方的值需同步更新。
- 实现位置：`backend/src/kb_backend/auth/deps.py` 的 `_readonly_gate`（本地常量时间比对，不经统一平台，viewer 只读角色 + GET/HEAD 双重约束）。
