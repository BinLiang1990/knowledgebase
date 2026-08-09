# 知识点批量导入 API（issue #11）设计文档

## 1. 范围

issue #11 明确要求（P1，PRD §4.4.1）：在单个知识库内一次性批量创建多条知识点（各自可选携带一条默认答案），减少第三方迁移存量数据时逐条调用创建接口的成本。

不做：跨知识库批量导入（v1 不支持，PRD §8）；批量编辑/批量删除（issue 未提及，超出范围）。

依赖 issue #4（`create_knowledge_point` 单条创建的全部规则——标题唯一性、默认答案原子写入——本设计直接复用，不重新发明）。不需要新 migration，不新增业务表。

### 待产品确认项的处理

issue 原文把"部分失败时的处理策略：整体回滚 vs 部分成功+返回失败清单"标注为"[待产品确认]"。本项目采用 AFK 全自动流程、当前排期阶段无法等待产品实时确认，比照本项目已有先例（issue #9 设计文档里对 PRD §4.10 并发控制"证据充分即可自行判断，不空等"的处理方式），在这里给出一个有依据的决定，写入 §4.1，而不是阻塞在这个问题上。

## 2. 端点设计

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/knowledge-bases/{kb_id}/knowledge-points/batch-import` | 批量创建知识点(+可选默认答案)。body：`{"items": [...]}`，每个 item 结构与现有 `POST /knowledge-bases/{kb_id}/knowledge-points`（单条创建）的请求体完全一致（`title` 必填，`default_answer` 可选） |

复用现有的 `KnowledgePointCreate` schema 作为 `items` 数组的元素类型，不新建一个内容相同的重复 schema。

请求体新增外层包装：

```python
class KnowledgePointBatchImportRequest(BaseModel):
    items: list[KnowledgePointCreate] = Field(min_length=1, max_length=500)
```

`max_length=500`：批量导入的意义就是"减少逐条调用的成本"，但不能没有上限——参照本项目已有先例（`EnabledDimensionsUpdate.dimension_keys` 用 `Field(max_length=200)` 给列表加上限，防止无界列表拖垮单次请求/事务），批量导入的每个 item 比一个维度 key 字符串重得多（一次 INSERT，可能还带一次答案 INSERT），有效上限应该更保守；500 是一个"对存量数据迁移场景足够实用、又不会让单次请求处理时间/事务时长失控"的判断，不是从 PRD 推导出的精确值。

**已知的、有意接受的残留风险**：`max_length=500` 只限制了 item **条数**，不限制单条请求体的**总字节数**——`DefaultAnswerInput.content`/`note` 本身没有长度上限（PRD §4.5 明确的 v1 决定："答案内容、变更说明暂不设长度上限"），批量场景把这个既有决定放大了最多 500 倍。这不是本设计新引入的风险（PRD 层面本来就接受单条 `content` 无上限），项目目前也没有任何应用层的请求体总大小限制；这里选择跟 PRD 保持一致、不额外加码去做本设计范围之外的事，把"要不要限制请求体总大小"留给 PRD §4.10 那类基础设施类问题统一考虑，不在这个 issue 里单独解决。

## 3. 数据来源（不新增 migration，不新增业务表）

复用 issue #4 已有的一切：`KnowledgePoint`/`Answer` 模型、`coord.py::compute_coord_hash`、`knowledge_point.py` 里已有的 `_get_kb_or_404`、`_ensure_title_available`。单条创建的核心逻辑（`create_knowledge_point`，`knowledge_point.py:148-183`）原样复用，批量导入只是在一个循环里对每个 item 重复同样的步骤，并且要让"某一个 item 的失败"不牵连其他 item（见 §4.1、§4.2）。

## 4. 关键设计决策

### 4.1 部分失败策略：选"部分成功 + 返回逐项结果清单"，不选"整体回滚"

三种候选：
1. 整体回滚：任何一个 item 失败，整批全部失败，客户端需要修好那一个 item 后重新提交全部 500 条
2. 部分成功，不告知哪些失败（只返回成功计数）
3. 部分成功，返回每个 item 的成功/失败结果清单（成功给出新建的 `id`，失败给出失败原因），客户端据此只需重试失败的那一小部分

选 3。理由：
- PRD 明确这个接口存在的意义是"第三方迁移存量数据时减少逐条调用的成本"——如果选 1（整体回滚），当批量条数较大时，任何一条标题冲突都会导致整批失败，第三方要么把批量拆得很小以降低单批出错概率（违背这个接口本来要解决的问题），要么每次全量重试（成本比逐条调用更高，因为重试还要再次承担前面已经成功那部分的写入开销）。
- 选 2（不返回详情）会让第三方无法定位是哪一条、以什么原因失败，仍然需要靠人工排查或退化成逐条调用来定位问题，没有真正减少对接成本。
- 选 3 是批量导入类接口的通行做法（"每条独立评估、逐项报告结果"），第三方可以直接用返回清单里的 `index`/`reason` 定位问题记录，只重新提交失败的那一小部分，不用管已经成功的部分。

这个决定的代价是实现复杂度更高（需要让一个 item 的失败不回滚同一批次里其他 item 已经成功的写入，见 §4.2），但换来的可用性收益，对"批量导入本来就是为了降低第三方接入成本"这个目标更对齐。

### 4.2 单个 item 失败不牵连其他 item：用 SAVEPOINT（`db.begin_nested()`），不是每个 item 单独一次 HTTP 事务

单条创建 `create_knowledge_point` 现有的失败处理方式是：`db.flush()` 抛 `IntegrityError` → `db.rollback()`（整个事务回滚）→ 转换成 `BusinessError`。**批量场景绝对不能照搬这个 `db.rollback()` 调用**——`db.rollback()` 回滚的是最外层事务，不是某一个 SAVEPOINT，会把同一个数据库会话里前面已经成功、还未 `commit()` 的 item 一起冲掉。这是对抗式审查抓到的第一处阻塞级问题：如果实现者机械地把单条创建接口的 `except IntegrityError: db.rollback(); ...` 原样搬进 `with db.begin_nested():` 块内部，`db.rollback()` 会把这个嵌套事务标记为已结束，`with` 块退出时 `begin_nested()` 自己的 `__exit__` 还会再尝试对这个已失效的嵌套事务做一次收尾，触发 SQLAlchemy 自己的 `InvalidRequestError`——这个二次异常会终止整个 for 循环，落到 FastAPI 通用异常处理变成一个不含任何逐项信息的 500，此时 session 从未 `commit()`，之前所有真正成功的 item 全部随 session 关闭而丢失，"部分成功"这个 §4.1 选的核心设计直接在这条路径上失效。

正确写法：**`with db.begin_nested():` 块内部不做任何 `try/except`**，让 `BusinessError`/`IntegrityError` 原样从块内传播出去，交给 `begin_nested()` 自己的上下文管理器完成 `ROLLBACK TO SAVEPOINT`；`try/except` 转换成"这一条失败，记录 reason，继续下一条"的逻辑放在 `with` 块**外面**：

```python
for index, item in enumerate(payload.items):
    try:
        with db.begin_nested():
            _ensure_title_available(db, kb_id, item.title)
            kp = KnowledgePoint(knowledge_base_id=kb_id, title=item.title, status="active", operator="admin")
            db.add(kp)
            db.flush()

            if item.default_answer is not None:
                empty_coord: dict = {}
                db.add(Answer(
                    knowledge_base_id=kb_id,
                    knowledge_point_id=kp.id,
                    coord=empty_coord,
                    coord_hash=compute_coord_hash(empty_coord),
                    content=item.default_answer.content,
                    effective_time=item.default_answer.effective_time,
                    note=item.default_answer.note,
                    operator="admin",
                    source="人工填报",
                ))
                db.flush()
    except IntegrityError as exc:
        results.append(_failed_result(index, item.title, _batch_item_failure_reason(exc)))
        continue
    except BusinessError as exc:
        results.append(_failed_result(index, item.title, exc.message))
        continue

    results.append(_created_result(index, item.title, kp.id))

db.commit()
```

（`_batch_item_failure_reason` 是新增的辅助函数，只返回失败文案、**不调用 `db.rollback()`**——跟单条创建接口用的 `_raise_if_duplicate_title` 不是同一个函数，`_raise_if_duplicate_title` 里的 `db.rollback()` 在批量场景下绝对不能复用，见上文。）

第二处阻塞级问题（Codex 外门审查在 PR #27 抓到，本文档定稿前的初版曾错误地在这里加一层 `except Exception` 兜底，已修正）：per-item 的 `except` **只能**覆盖 `IntegrityError`（标题重复等约束冲突）和 `BusinessError`（`_ensure_title_available` 主动拒绝）这两种——它们的共同特征是只影响这一条自己的 SAVEPOINT，`begin_nested()` 的 `__exit__` 能干净地 `ROLLBACK TO SAVEPOINT`，外层事务和批次里其他 item 已经 flush 过的数据完全不受影响。

**绝不能**再加一层 `except Exception` 把"标题重复之外的任何失败"也当成"这一条失败、继续下一条"处理——MySQL 死锁（`OperationalError`，错误码 1213）或锁等待超时（1205）这类错误，MySQL 会把它们所属的**整个外层事务**回滚掉，不只是当前 SAVEPOINT；如果这时候仍然把它当成"局部失败"吞掉、继续处理下一条，那么：
- 批次里所有在这次死锁之前"成功"、已经 `RELEASE SAVEPOINT` 的 item，其实也随外层事务一起被数据库整体回滚了，但 `results` 里已经记录了它们是 `"created"` 并带着看起来有效的 `knowledge_point_id`；
- 最后的 `db.commit()` 对一个已经被数据库单方面回滚过的事务几乎不会产生任何真实效果（甚至可能报错），但响应已经"承诺"了一批实际上从未真正落库的记录——这是比"漏报一种错误"严重得多的数据完整性问题：客户端会拿着一批看似成功、实际查不到的 `id` 去做后续操作。

正确做法是让这类"整个事务已经失效"的异常原样往外传播，不在 for 循环内用任何 `except Exception` 拦截——异常会在到达 `db.commit()` 之前中断整个 handler，交给项目里已有的全局异常处理器（`envelope.register_exception_handlers` 注册的 `_unhandled_exception_handler`，记录日志后返回标准 500）；这个数据库会话从未 `commit()`，请求结束时 `get_db()` 的 `finally: session.close()` 会丢弃所有未提交的写入——批次里"真的"成功过的 item 和被死锁牵连的 item 一起被彻底放弃，不会有任何"声称成功但其实没有"的记录被返回给客户端。代价是"批次中途遇到一次死锁，前面已成功的 item 也要跟着报废、由第三方整批重试"，但这比返回一份不可信的成功清单要安全得多——真实性优先于"部分成功"这个 §4.1 的设计目标，二者冲突时以不撑破数据完整性为准。

批次内部的标题重复检测天然工作，不需要额外写"批次内去重"的代码：`_ensure_title_available` 是一条 `SELECT`，同一个数据库连接内，前一个 item 即使还没 `commit()`，只要已经 `flush()` 过，这条 `SELECT` 就能看到它（同一事务内自己写入的行总是对自己可见，这跟隔离级别无关）——所以"批次里第 3 条和第 7 条标题相同"这种情况，会被 `_ensure_title_available` 当成"跟一条已存在的记录重复"正常拦下，走跟"跟数据库里旧记录重复"完全相同的失败路径，不需要区分这两种来源。若某个 item 触发 `ROLLBACK TO SAVEPOINT`，它插入的行会被真正撤销，后续 item 的 `SELECT` 不会再看到这行已回滚的记录——不会被误判为仍然存在。这一切成立的前提是每个 item 处理完都显式 `db.flush()` 过一次（session 配置了 `autoflush=False`，见 `db.py`），上面的骨架代码在每次 `db.add()` 后都保留了这一步，不能省略。

批量路径**不需要**在成功分支调用 `db.refresh(kp)`：session 配置了 `expire_on_commit=False`，且自增主键 `kp.id` 在 `db.flush()` 之后（不需要等 `db.commit()`）就已经由 SQLAlchemy 从游标取回并赋值到 ORM 对象上。单条创建接口调用 `db.refresh(kp)` 是因为它要在响应里返回 `created_at`/`updated_at` 等服务端生成字段（`expire_on_commit=False` 意味着这些字段在 commit 后不会自动刷新）；批量路径的成功响应只回 `knowledge_point_id`（见 §4.3），不需要这些字段，因此不需要 refresh——不要机械照抄单条创建接口"commit 后 refresh"的写法。

### 4.3 响应结构：每条给出 index + 结果，成功给 id，失败给原因

```python
class BatchImportItemResult(BaseModel):
    index: int
    status: Literal["created", "failed"]
    title: str
    knowledge_point_id: int | None = None
    reason: str | None = None

class BatchImportResult(BaseModel):
    created_count: int
    failed_count: int
    results: list[BatchImportItemResult]
```

`index` 对应请求里 `items` 数组的下标（数组本身没有其他天然可关联的 key），成功时只回 `knowledge_point_id`（不回整条 `KnowledgePointOut`）——批量场景下客户端需要的是"这条 item 对应的新 id 是多少"以便下一步操作，不是每条的创建时间/`active_answer_count` 等详情（要看详情可以用已有的单条查询接口），没必要让一个 500 条的批量响应体膀胗成携带 500 份完整记录。

批次内每个 item 本身的字段校验（`title` 非空、`default_answer.content` 非空等）由 `KnowledgePointCreate` 的 Pydantic 校验在请求体反序列化阶段完成，任何一个 item 字段不合法，FastAPI 在处理函数被调用之前就直接对整个请求返回 422（不会产生"部分校验失败"的中间状态，跟单条创建接口的行为一致）；`_get_kb_or_404` 只在批次开头执行一次（`kb_id` 是路径参数，对整批 item 是同一个值，不需要每个 item 各查一次）。

进入 handler 之后，每个 item 的失败原因只有 §4.2 骨架代码里那两层 `except` 覆盖的范围：`IntegrityError`（`_batch_item_failure_reason` 命中 1062 时给"标题重复"的固定文案，命中其他约束冲突时给一个通用的"写入失败（未知错误）"，两者都不影响其他 item）和 `BusinessError`（`_ensure_title_available` 主动拒绝时的文案）。**不存在**第三类"兜底吞掉任意异常"的失败分支——§4.2 已经说明为什么这么做是错的：任何逃出这两层 `except` 的异常（典型如数据库死锁）必须让整个请求失败，不能被当成"这一条失败"处理。

**重试/幂等语义（已知限制，不在本设计范围内解决）**：`knowledge_point` 表上有真实的 `(knowledge_base_id, title)` 唯一约束，这保证重复提交不会产生重复数据——重试在数据安全性上无害。但第三方在网络超时、不确定上一次调用是否已经生效的情况下重试整批，"标题重复"这个失败原因会同时覆盖"这确实是重复数据"和"上一次调用其实已经成功、这次是多余的重试"两种语义，客户端从响应本身无法区分。这是 PRD §8 层面就接受的限制（v1 不支持第三方自带外部 ID 做 upsert），批量导入的典型场景（第三方存量数据迁移，网络抖动概率更高）会让这个问题出现得更频繁，但解决它（比如引入外部幂等 key）超出本 issue 范围，这里只记录下来：第三方按响应里的 `index`/`reason` 只需重试真正失败的那部分，"重复"报错不会产生脏数据。

### 4.4 不做批次级别的整体状态字段（如 HTTP 状态码随成功/失败比例变化）

无论批次里有多少条失败，只要请求本身合法（`kb_id` 存在、`items` 非空且不超过 500 条），HTTP 状态码固定 `200`，业务层面的成功/失败在 `results` 里逐条体现。这是把项目一贯的设计哲学（`envelope.py` 头部注释："HTTP 状态码保留其本来含义……`code` 与业务结果故意不绑定"）延伸到一个新场景，不是简单复用现成先例——`resolve` 接口"查不到也 200"是一个只读查询的"未命中"语义，跟"批量写入、部分条目失败"不是同一类事情，代码库里目前也没有其他"批量写入部分失败"的接口可以直接类比；这里是独立做出的判断：合法请求应该整体 200，因为服务端确实"正确处理"了这个请求（对每一条都给出了明确结果），"部分条目未能创建"是业务结果，不是请求处理异常。

## 5. 组件结构

```
backend/src/kb_backend/schemas/knowledge_point.py   新增 KnowledgePointBatchImportRequest、BatchImportItemResult、BatchImportResult
backend/src/kb_backend/routers/knowledge_point.py   新增 batch_import_knowledge_points；新增 _batch_item_failure_reason（只返回失败文案，不调用 db.rollback()、不重新 raise，跟单条创建接口用的 _raise_if_duplicate_title 不是同一个函数，见 §4.2）
backend/tests/test_api_knowledge_point_batch_import.py   新增，覆盖本 issue 全部场景
```

## 6. 测试计划

- 批量创建 3 条知识点（含默认答案/不含默认答案混合），全部成功；返回的 `results` 顺序与请求 `items` 顺序一致，每条 `index` 正确对应。
- 批次内两条标题相同 → 第一条成功、第二条失败（`reason` 为标题重复），且不影响其他成功的 item（回归 §4.2 的核心场景）。
- 批次内某条标题与知识库里**已存在**的知识点（包括已软删除的）重复 → 该条失败，其余成功。
- 全部失败（比如全部跟已有记录重复）时 `created_count == 0`，`results` 长度仍等于 `items` 长度，HTTP 状态码仍是 200。
- `items` 为空数组 → 422（`min_length=1`）。
- `items` 超过 500 条 → 422（`max_length=500`）。
- `kb_id` 不存在 → 404，不产生任何写入。
- 批量创建的知识点默认答案与单条创建接口产生的记录字段完全一致（`operator`/`source`/`coord`/`coord_hash` 等），确认没有绕开单条创建已有的任何约定。
- 跨知识库：同一批次里的知识点全部落在请求路径里的这一个 `kb_id` 下，不产生跨库副作用。
- **回归对抗式审查抓到的两处阻塞级问题**：批次里第 2 条失败（标题重复）、第 3 条成功，最终 `db.commit()` 之后重新查询知识库，第 1 条和第 3 条必须真的落库（不能因为第 2 条失败、`begin_nested()` 的 `__exit__` 自己处理 `ROLLBACK TO SAVEPOINT` 时的实现方式不当，而连累第 3 条也没能提交）——这是对"批次内某个 item 失败不牵连其他 item"这一核心机制最直接的验证，不能只靠代码审查确认。
- 幂等/重试场景：把同一个批次原样提交两次，第二次里所有 item 都因标题重复而失败，`created_count == 0`；确认知识库里对应的知识点只有一份（唯一约束生效，重试不产生脏数据），锁定 §4.3 "重试语义"小节里"标题重复报错不会造成脏数据"这条结论。
- **回归 Codex 外门审查（PR #27）抓到的问题**：给某个 item 的 `db.begin_nested()` 打桩，让它在处理第 2 条时抛出一个模拟的 `OperationalError`（模拟死锁），验证：整个请求以 500 结束（不是把它当成"第 2 条失败"继续处理第 3 条），且第 1 条（在死锁之前"已经成功"过）最终也没有真的落库——确认这类会让整个外层事务失效的错误不会被误判成局部失败，也不会返回一份不可信的"部分成功"结果。测试需要用 `raise_server_exceptions=False` 的 `TestClient` 才能拿到应用自己产生的 500 响应体来断言（默认的 `TestClient` 会把这类未被专门捕获的异常重新抛给测试本身，这是测试客户端本身的调试行为，不代表应用没有处理它）。
