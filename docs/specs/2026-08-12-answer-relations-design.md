# 设计：答案关联（跨知识库）—— 分析 / 自动关联 / 手动维护

对应 PRD：[`docs/PRD-答案关联.md`](../PRD-答案关联.md) v2.0；issue 正文：[`docs/issues/答案关联-analysis-auto-manual.md`](../issues/答案关联-analysis-auto-manual.md)。
交互形态以 `frontend-mock/detail.html?kb=1&id=1&tab=relations` 的 demo 为准（已浏览器验证）。

## 1. 分层与文件

| 层 | 文件 | 职责 |
|---|---|---|
| 模型 | `backend/src/kb_backend/models/relation.py` + 迁移 `0004` | `answer_relation` / `answer_embedding` / `relation_task` 三表 |
| 网关 | `backend/src/kb_backend/gateway.py` | OpenAI 兼容 embeddings/chat 客户端（httpx 同步、429/5xx 重试 3 次、宽松 JSON 解析） |
| 服务 | `backend/src/kb_backend/relations.py` | 端点枚举、向量增量同步、余弦召回、批量描述生成、任务登记与执行 |
| worker | `backend/src/kb_backend/relation_worker.py` | daemon 线程轮询任务表；乐观 UPDATE 认领；启动时 generating→pending 恢复 |
| 路由 | `backend/src/kb_backend/routers/relation.py` | kp 前缀（analyze / 查询）+ 全局前缀（任务、手动添加、编辑、重新生成、删除） |
| 前端 | `frontend/src/api/relation.ts`、`views/knowledge-base/detail/RelationsPane.vue`、`AddRelationDialog.vue`、`EditRelationDialog.vue`、`detail/index.vue` | 「答案关联」tab、答案卡片「分析关联」入口与关联角标、轮询、两个弹窗 |

## 2. 关键决定（含与 PRD 的差异）

1. **端点无外键**。关联端点是版本链 `(kp_id, coord_hash)`；对端软删除/整链撤回时记录保留、查询层推导灰态（`revoked` / `kp-deleted` / `missing`）。外键会阻碍"历史永久可查"。
2. **端点枚举不复用 `compute_live_groups`**：全库枚举会退化成几千次查询。`collect_endpoints` 一次 JOIN 取全部候选行，在 Python 里做与之相同的 `max(effective_time, created_at, id)` 选链。
3. **纯 Python 余弦，不引入 numpy/向量库**（万级 × ~1024 维在 worker 线程内秒级；China 镜像环境少一个二进制依赖）。
4. **`answer_relation` 无 status 列**（PRD §3.4 草案中的单条 `failed` 态简化掉）：生成失败是任务级状态（`relation_task.status=failed` + `last_error`），关联行只在成功生成/人工添加时存在。唯一例外：手动添加选 AI 生成时先落 `description=""` 的行，前端以"生成中"展示（`generating = description == ""`）。
5. **stale 不落库**：查询时用关联行上的 `content_hash_a/b` 对比两端当前生效版本动态推导。
6. **manual 保护双保险**：分析的候选过滤跳过 manual，`upsert_ai_relation` 再兜一次。
7. **自动关联 = analyze 任务省略 `center_coord_hash`**，worker 对该知识点全部有效链逐条召回、跨 center 去重后统一生成——与单条分析同一条代码路径。
8. **降级**：`Settings.relation_analysis_enabled` 要求 embeddings 与 chat 网关同时配置；未配置时 worker 不启动、analyze/regenerate 返回业务错误、GET 的 `generation_status=disabled`、前端禁用相应入口（手动添加人工描述不受影响）。
9. **CORS 加了 DELETE**（删除关联接口）——沿用该文件里记录过的"显式列表"教训。
10. **前端轮询**：relations 查询由详情页持有（「当前答案」角标与 tab 共用），`generation_status ∈ {pending, generating}` 时每 5s 静默轮询（`silent: true` 走 request 拦截器的免弹窗通道），完成即停。

## 3. 任务模型

```
analyze(center_coord_hash?)  : embedding → recall → generate 三阶段，phase/progress_* 供轮询
generate_pair(relation_id)   : 单对生成（手动添加的 AI 描述、重新生成）
状态机：pending → generating → done | failed(retry≥3) | pending(重试)
```

幂等：向量按 `content_hash+model` 缓存；已有 ai 关联且两端哈希未变则跳过生成；每批 embeddings/描述各自提交，进程中途挂掉不作废已完成部分。

## 4. 测试与验证

- `tests/test_relations_logic.py`：13 项纯逻辑测试（余弦、端点规范化、JSON 宽松解析、批量描述 index 对齐/重试、embeddings 契约）。**零 DB、零网络**——现有 `migrated_schema` fixture 会对真实库 downgrade/upgrade，本特性所有测试严禁使用 DB fixture。
- import 冒烟 + OpenAPI 路由枚举已验证 7 条新路由注册。
- 前端无本机 node 环境，本次为代码级交付，**未经 vue-tsc/vitest 验证**——首次 `pnpm dev` 时需过一遍类型检查。

## 5. 遗留 / 待办

- ⚪ **P3（后置）模型接入**：chat 侧已定 DeepSeek（key 待需求方提供，`RELATION_LLM_BASE_URL=https://api.deepseek.com`，模型 `deepseek-v4-flash`）；embeddings 侧 DeepSeek 不提供，待在"机房 Ollama 经网关 / 硅基流动 / 百炼 / 智谱"中确定后填 `EMBEDDING_*`。配置就绪后跑端到端连通性验证即可上线，代码无需改动。
- 迁移 `0004` 尚未在任何库上执行（部署时 `alembic upgrade head`）。
- 前端任务进度只展示"进行中"横幅，未细化 phase/progress（后端已提供 `GET /answer-relations/tasks/{id}`）。
- 关系图可视化（P2）未做。
