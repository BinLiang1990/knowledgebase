# 答案"设为默认"与"撤回" API（issue #10）设计文档

## 1. 范围

issue #10 明确要求（P1，PRD §4.5/§6 规则 #3/#4/§8）：
- 设为默认：把某条答案内容写成默认答案(coord={})版本链的新版本，原答案不变
- 撤回：对某个条件组合的整条版本链做逻辑删除，必须填写撤回原因

不做：批量导入（issue #11）。

> **2026-08-10 修订**：本节原本还列了"撤回的撤回"作为不做项（当时 PRD §8 把它列为 v1 明确不做）。用户实测发现"往一个已撤回的条件组合写新答案被 400 拒绝"不符合预期，要求放开——现在往任何已撤回的链写入新版本（新建/编辑/迁移进来/设为默认目标）都会把整条链复活为未撤回状态，不再是一个需要"联系我方人工处理"的终态。详见 `docs/specs/2026-08-08-knowledge-point-answer-api-design.md` 的同名修订章节；本设计文档下面 §4.3 提到的"目标（默认链）若已被撤回，同样 400 拒绝"已不再成立，改为成功并复活该链。

依赖 issue #4（答案的写入/编辑接口、`Answer` 模型、`coord.py`）——不需要新 migration，`Answer` 表已有 `revoked`/`revoked_at`/`revoked_by`/`revoke_reason` 全部字段（issue #1 建表时就留好了）。

## 2. 端点设计

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/knowledge-bases/{kb_id}/knowledge-points/{kp_id}/answers/{answer_id}/promote-to-default` | 设为默认。body：`effective_time`(必填)、`note`(可选) |
| `POST` | `/knowledge-bases/{kb_id}/knowledge-points/{kp_id}/answers/{answer_id}/revoke` | 撤回。body：`revoke_reason`(必填，`max_length=500`——`Answer.revoke_reason` 是 `String(500)`，不是 LONGTEXT，跟 `content`/`note` 不一样；照抄 `KnowledgePointDeleteRequest.delete_reason`/`AnswerEdit.migration_reason` 已经用过的同一个上限) |

两个端点都用"某个已存在答案的 `answer_id`"作为入口，不是让客户端自己传一个原始 `coord` 字典——原因见 §4.1、§4.2。

## 3. 数据来源（不新增 migration，不新增业务表）

复用 issue #4 已有的一切：`Answer` 模型全部字段、`coord.py::compute_coord_hash`、`knowledge_point.py` 里已有的 `_get_kp_or_404`、`_ANSWER_NOT_FOUND_MSG`（`_chain_is_revoked` 本身已在 2026-08-10 修订里被 `_revive_chain_if_revoked` 取代并删除，见 §1 顶部的修订说明）。`edit_answer` 的迁移分支已经写过一次"整条链批量撤回"的 SQL，本次撤回端点直接复用同一个写法，不是重新发明——**必须逐字复用，包括 `knowledge_point_id` 这个过滤条件**：

```python
db.execute(
    update(Answer)
    .where(
        Answer.knowledge_point_id == kp_id,
        Answer.coord_hash == target.coord_hash,
        Answer.revoked.is_(False),
    )
    .values(revoked=True, revoked_at=func.now(), revoked_by="admin", revoke_reason=payload.revoke_reason)
)
```

这个 `knowledge_point_id == kp_id` 条件不是可以省略的细节——`compute_coord_hash`（`coord.py:201-203`）是纯函数，只取决于归一化后的 coord 字典本身，跟任何知识点/知识库都没有关系。`compute_coord_hash({})` 对**全库所有知识点**都是同一个值；只要漏掉 `knowledge_point_id` 这个过滤条件，撤回任何一个知识点的默认答案链，就会把全库所有知识点的默认答案链一起撤回（对非空 coord，只要两个知识点碰巧用了同一个条件组合，也会撞上同样的问题）。对抗式审查在这里抓到了一处初稿里漏写这个条件的错误——写代码时对着这段贴，不要凭记忆重新写一遍。

`Answer.revoked.is_(False)` 这个条件同样不是可以省略的细节——见 §4.5：幂等判断必须落在这条 `UPDATE` 语句自己的 `WHERE` 里，不能是先在 Python 里 `if not target.revoked` 判断一次再跑这条不带该条件的 `UPDATE`（Kimi 终审在实现阶段抓到的一处竟态：两个并发的重复撤回请求都可能在各自事务里读到 `revoked=False`，都跑了 `UPDATE`，第二个提交会覆盖第一个的 `revoked_at`/`revoked_by`/`revoke_reason`，违反本节开头"保留第一次撤回原因"的承诺）。

获取目标答案（`target = ...`）同样要三重过滤：`Answer.id == answer_id, Answer.knowledge_point_id == kp_id, Answer.knowledge_base_id == kb_id`——跟 `edit_answer` 现有代码完全一致，防止拿别的知识点/知识库下的 `answer_id` 冒充。

## 4. 关键设计决策

### 4.1 撤回端点用 `answer_id` 定位版本链，不接收原始 `coord` 字典

demo 的 `revokeAnswerGroup(kbId, kpId, coord, reason)` 直接传一个 `coord` 对象。真实后端不这么做：客户端只需要传"这条答案链上随便一个版本的 `answer_id`"（前端已经有——详情页展示答案组时，每一行本来就带着 `live_answer.id`），后端从这个 `answer_id` 反查 `target.coord_hash`，再用这个 hash 去 §3 那条**带 `knowledge_point_id` 过滤**的 `UPDATE` 批量撤回整条链。

这样做的好处：不需要客户端重新构造一遍 `coord`（连带着还要保证类型转换跟服务端 `normalize_coord` 完全一致，才能算出同一个 hash），也不需要后端再重新校验一遍这个 `coord` 里的维度是否都启用——`answer_id` 指向的这条记录已经是数据库里真实存在的一行，它的 `coord_hash` 直接可用，不需要重新推导。跟 `edit_answer` 定位"要编辑哪条答案"的方式（`answer_id`，不是 `coord`）保持同一套约定。

### 4.2 设为默认端点同样用 `answer_id` 定位"抄哪条答案的内容"，不接收客户端传来的 `content` 字符串

PRD 原文："把**当前这条答案**的内容，写成默认答案版本链的新版本"——"当前这条答案"指的是 UI 上已经展示出来的某一条具体答案，不是让客户端自己拼一段文本传上来冒充"设为默认"。所以入口是 `answer_id`（要设为默认的源答案），`content` 由后端从这条记录里读出来，客户端没法在这个请求里注入任意内容。

### 4.3 设为默认在实现上就是"给默认答案链(coord={})写一条新答案，内容复制自源答案"

不单独建一个"设为默认"的专用写路径——它和 `create_answer` 唯一的区别就是 `content` 从哪儿来（客户端传 vs 从源答案抄）、`coord` 固定是 `{}`。所以复用 `create_answer` 已经有的两条校验：
- 知识点已删除 → 拒绝（"知识点已删除，无法写入答案"，跟 `create_answer`/`edit_answer` 一致——这是一次"写新内容"的操作，不是撤回那种清理性操作，见 §4.4 的对比）
- 默认答案链本身已被整体撤回 → 不再拒绝（2026-08-10 修订）：`_revive_chain_if_revoked(db, kp_id, compute_coord_hash({}))` 先把该链复活，再正常写入，跟直接调用 `create_answer(coord={})` 的行为完全对齐

源答案本身是否已经被撤回，不做限制——"设为默认"抄的是**内容**（一段文本），不是把源答案链本身复活；抄一条曾经正确、后来被撤回的答案的文字说法，不违反任何 PRD 规则。这是本设计的一个判断，PRD 没有明确写要不要限制，此处放开。

新写入的这一行，`operator`/`source` 固定为 `"admin"`/`"人工填报"`——跟 `create_answer` 完全一致（PRD §6 规则 #10 定义的固定值；本设计把"设为默认"归类为"写新内容"操作，就该用这一类操作的固定值，不是 `edit_answer` 用的 `"人工编辑"`）。

### 4.4 撤回端点不检查知识点是否已删除；设为默认端点检查

PRD §6 规则 #8："知识点软删除是粗粒度操作，独立于答案撤回……两者互不影响、可独立操作"——撤回是清理性操作（把一个错误的条件组合下线），即使知识点本身已经被软删除，撤回其下某条答案链也应该能独立完成，不应该因为"知识点已删除"就被拦下来。这跟 `create_answer`/`edit_answer`（"写新内容"类操作，知识点已删除时确实不该再写新内容）不是同一类操作，故意不对齐它们的校验规则。

设为默认本质是"写一条新答案"（§4.3），所以它跟 `create_answer`/`edit_answer` 站在同一边，检查知识点已删除。

### 4.5 重复撤回同一条链：幂等成功，保留第一次的撤回原因，不是报错、也不是覆盖

三种候选设计：
1. 报错拒绝（"该条件组合已被撤回"）
2. 幂等成功，用最新一次请求的 `revoke_reason` 覆盖旧的
3. 幂等成功，保留第一次记录的 `revoke_reason` 不变

选 3，直接照抄知识点删除接口（issue #4）已经确立的先例——`delete_knowledge_point` 对已删除的知识点重复调用会返回 200，但**保留第一次的 `delete_reason`**，不用重试请求里的新原因覆盖（测试 `test_delete_is_idempotent_and_keeps_original_reason` 已经锁定这个行为）。留痕的第一要务是"准确记录第一次真正发生撤回的原因和时间"，一个后来的重复调用（可能只是网络重试，也可能是另一个管理员没意识到已经撤回过）不应该覆盖历史真相。

不选 1（报错）是因为 PRD 没有把"重复撤回"列为错误场景，且 §8"不支持撤回的撤回"讨论的是"能不能恢复"，不是"能不能再撤回一次"——两者是不同的问题，不应该混为一谈去推导出"重复撤回必须报错"的结论。

**这条幂等判断必须落在 §3 那条 `UPDATE` 语句自己的 `WHERE` 里（`Answer.revoked.is_(False)`），不能是在 Python 里先 `if not target.revoked` 判断一次、再跑一条不带这个条件的 `UPDATE`**：`edit_answer` 的迁移分支能不加任何幂等判断就直接跑一条不带 `revoked=False` 的 `UPDATE`，是因为它上面已经有 `if target.revoked: raise BusinessError(...)` 挡住了"目标本来就是已撤回状态"这个入口——到迁移分支时，链条必然还没被撤回过，不存在并发重复撤回的场景。本设计的撤回端点没有类似的上游拦截（它必须支持对已撤回的链再调用一次），如果照搬"Python 先判断、再跑不带条件的 UPDATE"这个思路，两个并发的重复撤回请求会在各自事务里都读到 `revoked=False`、都跑那条 `UPDATE`，第二个提交覆盖第一个的 `revoked_at`/`revoked_by`/`revoke_reason`，正好违反本节"保留第一次原因"的结论（Kimi 终审在实现阶段抓到的竟态，见 §3 的批注）。正确做法是让 `UPDATE` 本身只在 `revoked=False` 时才生效：命中 0 行就是"已经撤回过，本次是no-op"，命中 1 行（按 chain 内版本数，多行）就是"第一次撤回，成功写入"——幂等性由数据库的原子写入保证，不依赖 Python 里任何"先查后写"的判断。

### 4.6 设为默认/撤回都不改变 `answer.coord_hash` 以外任何"这条答案属于哪条链"的判定逻辑

这两个操作都不需要碰 `resolve.py`/`coord.py` 一行代码——`compute_live_groups`/`compute_all_answer_groups` 已经是通用的"按 `coord_hash` 分组 + 按 `revoked`/`effective_time` 过滤"逻辑，设为默认只是给 `coord_hash = hash({})` 这一组多插一行，撤回只是把某个 `coord_hash` 对应的所有行的 `revoked` 翻成 `True`——两个操作产出的都是"完全符合现有分组/解析规则的普通数据行"，不需要教这些函数任何新概念。

## 5. 组件结构

```
backend/src/kb_backend/schemas/knowledge_point.py   新增 AnswerRevoke、AnswerPromoteToDefault
backend/src/kb_backend/routers/knowledge_point.py   新增 promote_answer_to_default、revoke_answer
backend/tests/test_api_answer_promote_revoke.py     新增，覆盖本 issue 全部场景
```

## 6. 测试计划

- 设为默认：成功创建 coord={} 的新版本，内容与源答案一致；源答案本身不受影响（内容、`revoked`、`coord` 均不变）；`effective_time` 必填；`note` 可选；知识点已删除时拒绝；默认答案链已被整体撤回时拒绝；源答案不存在返回 404；跨知识点/知识库的 `answer_id` 返回 404（不能拿别的知识点下的答案 id 冒充）。
- 撤回：成功后同一 `coord_hash` 下全部历史版本（不只是目标那一条）都被标记 `revoked`；必须填写 `revoke_reason`，为空拒绝，超过 500 字符拒绝；`GET .../resolve` 对该条件返回 `none`（或按权重回退到别的兼容组，视是否还有别的答案）；`GET .../answer-groups` 里这个组仍然可见，`revoked=true`、`live_answer=null`、历史版本数不变；重复撤回同一条链幂等成功，第一次的 `revoke_reason`/`revoked_at`/`revoked_by` 不被覆盖；知识点已删除时仍能成功撤回（§4.4 的验收测试）；答案不存在返回 404；跨知识点/知识库的 `answer_id` 返回 404；**两个不同知识点各自都有默认答案链（`coord={}`，`coord_hash` 必然相同）时，撤回其中一个知识点的默认答案链，另一个知识点的默认答案链必须原样不受影响**——这是对抗式审查抓到的一处设计初稿漏洞（撤回的 `UPDATE` 语句忘了带 `knowledge_point_id` 过滤），专门写一个测试钉住，不能只靠代码审查。
