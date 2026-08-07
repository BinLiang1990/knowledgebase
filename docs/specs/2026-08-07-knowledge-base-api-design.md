# 知识库管理 API 设计文档（issue #2）

## 1. 范围

实现 `docs/PRD.md` §4.1 的知识库增删改查接口：

- 新增知识库
- 查询知识库列表（含每个知识库当前生效知识点数量、启用状态、创建时间）
- 修改知识库名称/描述
- 停用 / 启用知识库（逻辑操作）

不含（见 issue #2 Out of Scope）：知识库内启用维度管理（#3/#9）、知识点管理（#4）。

## 2. 接口设计

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/knowledge-bases` | 新增知识库 |
| GET | `/knowledge-bases` | 知识库列表 |
| PATCH | `/knowledge-bases/{id}` | 修改名称/描述 |
| POST | `/knowledge-bases/{id}/activate` | 启用 |
| POST | `/knowledge-bases/{id}/deactivate` | 停用 |

沿用 issue #1 已定的 `{code,data,msg}` 响应信封（§4.10），无版本前缀（与现有 `/health` 一致）。

启用/停用拆成两个独立的 POST 动作端点，而不是让 `PATCH` 兼管 `status` 字段——PRD §4.1 表格把"停用"列为与"改名改描述"并列的独立操作，独立端点让语义（以及未来可能加的操作日志/权限点）更清晰，成本也不高。

### 请求/响应体

```
KnowledgeBaseCreate:  { name: string(必填,1-255,去首尾空格), description?: string }
KnowledgeBaseUpdate:  { name?: string(1-255,去首尾空格), description?: string }
KnowledgeBaseOut:     { id, name, description, status, active_knowledge_point_count, created_at, updated_at }
```

`GET /knowledge-bases` 返回 `KnowledgeBaseOut` 列表；单个操作（创建/修改/启停用）返回单个 `KnowledgeBaseOut`。

## 3. 需要在 PRD 基础上明确的工程细节（expand-prd 方法）

PRD 草案在这几处留有空隙，直接影响能不能写出确定性的测试，逐一给出解决方案并记录理由：

1. **`GET /knowledge-bases` 返回范围：只看启用中的，还是全部？**
   §4.1 "查看" 一行写"展示...启用状态"（暗示列表里本来就该同时看到 active 和 deprecated，否则"展示启用状态"这句没有意义）；但"停用"一行又写"知识库列表不再展示"。这两句话的读者对象不同：后一句描述的是**面向使用者的知识库选择器**（比如"写答案"时选知识库),前一句描述的是**本 issue 要交付的管理接口**——第三方正是通过这个接口来管理知识库、把已停用的库重新启用,所以必须能看到它们。参照 §4.2 对"内部管理列表 vs 对外查询接口"的分区处理方式,本接口按"内部管理列表"对待：**返回全部知识库（含 deprecated),用 `status` 字段区分**。"仅返回启用中的"留给未来可能需要的、面向选择器的轻量端点,不在本 issue 范围内。

2. **重名错误的 `msg` 内容。** issue 验收标准举例"返回错误 `knowledge_base_name_duplicated`",但 §4.10 已经明确决策"v1 先不做细分错误码,具体原因写在 `msg` 里"。两者不矛盾：`knowledge_base_name_duplicated` 是 issue 里给这类错误取的**人类可读代号**,不是要求 `msg` 字段就是这个英文 slug。`msg` 统一用清晰的中文说明："知识库名称已存在，请使用其他名称"，与 §4.10 的既有决策保持一致，不引入和其他业务错误不一致的、混杂中英文的错误串风格。

3. **重名校验的范围和时机。** §4.1 校验规则原文"与现有任意知识库（含已停用的）完全重复"——完全匹配（大小写、空白都算数,不做归一化/模糊匹配),范围覆盖 active + deprecated。应用层先查一次给出干净的错误提示,同时数据库唯一索引 `uq_knowledge_base_name`（issue #1 已建）兜底防止两个并发创建请求的竟态漏检——命中该约束时同样转换成同一条 `BusinessError`,不让原始 `IntegrityError` 直接 500 泄露给客户端。修改名称时,校验要把"当前这条记录自己"排除在外,否则改描述不改名字都会被误判成"和自己重名"。

4. **`active_knowledge_point_count` 的口径。** 只统计该知识库下 `knowledge_point.status = 'active'` 的知识点（不含已软删除的）,与 §4.1 "当前生效的知识点数量" 用词一致。知识点管理接口（issue #4）尚未交付,但 `knowledge_point` 表结构已在 issue #1 建好,此处直接按表结构统计,不依赖 #4 的业务代码,不构成阻塞依赖。

5. **启用/停用的幂等性。** 对已经是目标状态的知识库再次调用 activate/deactivate,视为成功（no-op),不报错。理由：这是第三方系统重试、双击等真实会发生的场景,而不是假设性的"不可能发生的输入"；报错反而会让调用方需要先查询当前状态才能安全调用,增加不必要的往返。

6. **对不存在的 `id` 的处理。** PATCH / activate / deactivate 在找不到对应知识库时返回 `BusinessError(status_code=404, "知识库不存在")`，遵循已有 `envelope.py` 的统一异常处理路径（HTTP 404 + body `code=444`）。

## 3.7 对抗式自校发现的问题（写代码前修正）

1. **`db.refresh()` 缺失会导致返回体里 `status`/`created_at`/`updated_at` 序列化成 `null`。** `created_at`/`updated_at` 是纯 DB `server_default`,`status` 也是 `server_default="active"`——Python 对象在 `commit()` 之前从未被赋值。`db.py` 里 `expire_on_commit=False` 的说明已经预告了这个坑（"Future CRUD issues (#2-5)... must `db.refresh(obj)`"）,但本设计文档最初漏了。**修正**：新增写路径（POST 新增）必须在 `db.commit()` 之后显式 `db.refresh(kb)` 才能序列化返回体；`status` 也在 Python 侧显式赋值为 `"active"`（不依赖 DB 默认值,避免同一个问题在别的字段上重演）。修改/启停用路径同理,`commit()` 后 `refresh()` 以取回真实的 `updated_at`。

2. **`GET` 是否只返回全部知识库,还是也支持按状态过滤。** 前面第 1 点判断"本接口是管理接口,应返回全部"是合理的,但完全不给过滤能力,会让"只要 active 列表"这种（同样合理的）第三方需求必须自己在客户端过滤。**修正**：加一个可选 query 参数 `status: Literal["active","deprecated"] | None`,不传则返回全部,传则精确过滤。不引入分页（知识库数量级不需要）。

3. **列表接口的知识点计数必须是一次分组查询,不能对每个知识库单独 `COUNT`。** 用 `LEFT JOIN` + `GROUP BY knowledge_base_id`（或等价的一次性子查询)算出每个知识库的 active 知识点数,而不是循环里对每一行发一次 `COUNT(*)`。

4. **唯一性冲突的 `IntegrityError` 兜底,不能只覆盖"新增"路径。** 改名（PATCH）存在同样的并发竟态（两个并发改名请求改成同一个新名字）,必须用同一段"捕获 `IntegrityError` → `db.rollback()` → 转换成同一条 `BusinessError`"逻辑覆盖新增和改名两条写路径,并且捕获后必须先 `rollback()` 才能让 session 恢复可用状态,不能在失败事务上继续操作。

5. **幂等的启用/停用不能仍然执行一次空 `UPDATE`。** 因为 `updated_at` 是 `ON UPDATE CURRENT_TIMESTAMP` 自动维护的,如果目标状态和当前状态相同还是跑一次 `UPDATE`,会让 `updated_at` 变成"最近一次被调用的时间"而不是"最近一次真正状态变化的时间",污染这个字段本来的含义。**修正**：状态相同时直接返回当前记录（`refresh` 一次即可,不执行 `UPDATE`)。

6. **每个 API 测试用例必须显式依赖 `client` 和 `migrated_schema` 两个 fixture。** 不合并成一个 fixture（`test_health.py` 有些用例故意不需要真实 schema),但新增的 `test_api_knowledge_base.py` 里每个测试函数签名都要同时带上这两个参数,遗漏会导致"看似能跑但打在没有表的 schema 上"的静默错误——写测试时逐一检查,不依赖自动组合。

## 4. 测试基础设施调整

issue #1 的 `test_models_migrate.py` 里定义的 `migrated_schema` fixture（downgrade base → upgrade head → yield → downgrade base，每个测试用例独立跑一轮迁移）被**上提到 `conftest.py`** 成为共享 fixture,新增的 `test_api_knowledge_base.py` 复用同一个 fixture。

为什么不做"整个 session 迁移一次、之后只清理各测试自己插入的行"这种更快的方案：所有测试都跑在同一个真实 Aliyun RDS 数据库上,`test_models_migrate.py` 里已有的用例本身就需要每个用例独立地把 schema 打到干净状态来验证约束（唯一索引、CHECK 约束等），它的 fixture 无条件地在每个用例结束后 downgrade 到 base。如果给 API 测试另设一个"只在 session 开始/结束时迁移一次"的 fixture,一旦 pytest 的收集顺序让两类测试交替执行,`test_models_migrate.py` 某个用例的 teardown 就会把 API 测试还需要的表删掉——这是一个只在特定执行顺序下才会暴露的隐藏 bug。让所有测试统一复用同一个"每用例独立迁移"的 fixture,牺牲一些测试运行时间,换取不依赖收集顺序这个隐藏假设的正确性。

## 5. 文件改动

- `backend/src/kb_backend/schemas/knowledge_base.py`（新增）——pydantic 请求/响应模型
- `backend/src/kb_backend/routers/knowledge_base.py`（新增）——路由 + 业务逻辑（规模小,不单独拆 service 层）
- `backend/src/kb_backend/main.py`——挂载新路由
- `backend/tests/conftest.py`——上提 `migrated_schema` fixture
- `backend/tests/test_models_migrate.py`——改为使用 conftest 里的共享 fixture（删除本地重复定义）
- `backend/tests/test_api_knowledge_base.py`（新增）——API 行为测试

## 6. 测试计划

- 新增：合法请求成功、返回体字段齐全、初始 `active_knowledge_point_count=0`
- 新增：与现有 active 知识库重名 → 拒绝
- 新增：与现有 deprecated 知识库重名 → 同样拒绝（验证"含已停用"）
- 新增：空白名称 → 422
- 列表：同时包含 active/deprecated,且 `active_knowledge_point_count` 只统计状态为 active 的知识点(插入一个 active + 一个 deleted 知识点验证)
- 修改：改名成功；改名撞现有其他库名 → 拒绝；只改描述不改名 → 不会误判成"和自己重名"
- 修改：目标 id 不存在 → 404
- 停用/启用：状态正确切换；对已处在目标状态的库重复调用 → 幂等成功；目标 id 不存在 → 404
