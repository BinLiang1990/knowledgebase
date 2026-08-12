## 需求

任意两条答案（不限知识点、不限知识库）之间可以建立**关联**，核心载荷是一段说明相互关系的中文描述。重点场景：一个知识点里某个维度条件下的答案，和其他知识库的知识点的某条答案产生关联。

PRD：[`docs/PRD-答案关联.md`](../blob/main/docs/PRD-答案关联.md)（v2.0）
交互 demo（已验证）：`frontend-mock/detail.html?kb=1&id=1&tab=relations` —— 「答案关联」tab、「分析关联」（单条答案）、「自动关联」（知识点全部答案）、「手动添加关联」四个入口的交互形态以 demo 为准。

## 功能点

1. **发起分析**（PRD §3.1）：单条答案分析 + 知识点级「自动关联」，异步任务 + 进度轮询
2. **分析执行 worker**（§3.2）：向量补齐（内容哈希缓存）→ 全库余弦召回 Top-K → LLM 批量生成描述 → upsert；`source=manual` 不覆盖
3. **手动添加**（§3.3）：级联选择两端 + 人工描述或 AI 生成
4. **查询/编辑/删除**（§3.4）：对端信息聚合、stale 动态判定、对端撤回/删除灰态；人工改写后转 manual
5. **前端**（§5）：知识点详情页「答案关联」tab、答案卡片「分析关联」入口与关联角标、手动添加弹窗、任务进度轮询

## 技术要点

- 三张新表：`answer_relation` / `answer_embedding` / `relation_task`（§6），alembic 迁移
- MySQL 任务表 + 进程内 worker 线程（lifespan 启停），不引入 Redis（§0.8）
- 召回与生成走 **OpenAI 兼容网关**（机房 FastGPT/OneAPI → Ollama 向量模型 + chat 模型），`EMBEDDING_*` / `RELATION_LLM_*` 环境变量配置（§7）
- **网关未配置时功能降级**：分析入口返回「关联分析未启用」，手动添加（人工描述）始终可用（§0.11）
- 万级答案内存余弦即可，不引入向量数据库（§4.3）

## 待确认 ⚪ P3（模型接入后置，不阻塞开发，阻塞真实模型上线）

- [ ] chat 侧：DeepSeek key（已确定用 `https://api.deepseek.com` + `deepseek-v4-flash`，key 待提供）
- [ ] embeddings 侧：DeepSeek 无 embeddings 能力，待在「机房 Ollama 经 FastGPT/OneAPI / 硅基流动 / 百炼 / 智谱」中选定并提供接入信息（均 OpenAI 兼容，只填 `EMBEDDING_*` 三个配置）

模型确认前，开发按可配置网关实现并用 stub/mock 验证（已完成）。

## 验收标准

- [ ] 对一条答案点「分析关联」→ 任务异步执行 → 「答案关联」tab 出现带描述的关联，跨知识库可见、两端对称
- [ ] 「自动关联」对知识点全部答案逐条分析，幂等（重复执行不重复新增）
- [ ] 手动添加/编辑过的关联不被后续分析覆盖
- [ ] 答案内容更新后关联显示「内容已更新」，可重新生成
- [ ] 对端撤回/知识点删除时关联保留并灰态标记
- [ ] 未配置网关时分析入口明确降级，手动添加可用
- [ ] 测试不触碰真实数据库（mock DB/网关）

⚠️ 测试注意：现有 pytest 的 `migrated_schema` fixture 会对真实库做 downgrade/upgrade，本 issue 的测试必须完全避开 DB fixture。
