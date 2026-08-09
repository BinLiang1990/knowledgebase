# 变更留痕接口（知识点级+全局）+ 知识库统计接口（issue #12）设计文档

## 1. 范围

issue #12 明确要求（P1，PRD §4.7"变更留痕"部分/§4.8/§4.9）：

- 知识点级变更留痕：`GET /knowledge-bases/{kb_id}/knowledge-points/{kp_id}/change-log`
- 全局操作日志：`GET /change-log`（跨全部知识库，多"知识库""知识点"两列定位）
- 知识库统计：`GET /knowledge-bases/{kb_id}/stats`

三者都是"对 `Answer`/`KnowledgePoint` 历史数据的只读派生视图"（issue 原文），**不新增业务表、不新增 migration**——直接从 `Answer` 现有的 `created_at`/`revoked`/`revoked_at`/`revoked_by`/`revoke_reason`/`coord_hash` 等字段在查询时推导。

不做（issue Out of Scope / 依赖关系明确划定）：
- 版本历史 tab（PRD §4.7 单独一行，issue 原文允许拆出去，本 issue 默认仍包含在范围外——issue 的 Proposed Change 列表只提了"变更留痕""全局日志""统计"三项，不包含"版本历史"，视为本次不做）。
- 全局日志的撤回能力——issue 原文"支持对仍生效的答案直接触发撤回（复用 Issue #10 的撤回接口）"指的是**前端**直接调用已有的 `POST .../answers/{answer_id}/revoke`（issue #10 已完成），后端不需要为此新增任何接口；本设计要做的只是确保变更留痕的每一行都带上可用于调用该接口的 `answer_id`（见 §4.3）。

依赖 issue #4（`Answer`/`KnowledgePoint` 模型）、issue #10（`revoke_reason`/`revoked_by`/`revoked_at` 字段与撤回接口——本设计消费这些字段，不重新定义）。

参考 `frontend-mock/logs.html` + `frontend-mock/assets/app.js` 的 `changeLogRows`/`buildChangeLog`/`buildGlobalChangeLog`/`computeKbStats`（demo 已验证的推导算法，本设计原样复用算法逻辑，但输出字段改为英文机器可读值，见 §4.2 的说明）。

## 2. 端点设计

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/knowledge-bases/{kb_id}/knowledge-points/{kp_id}/change-log` | 该知识点全部答案的操作流水（§4.7） |
| `GET` | `/change-log` | 跨全部知识库的同类流水，每行多带 `knowledge_base_id`/`knowledge_base_name`/`knowledge_point_title` 三个定位字段（§4.8，见 §4.4） |
| `GET` | `/knowledge-bases/{kb_id}/stats` | 知识库统计卡：知识主题数/在用答案数/启用维度数/今日变更数（§4.9） |

三个接口都不接收任何查询参数——不做分页、不做筛选，见 §4.6。

## 3. 数据来源（不新增 migration，不新增业务表）

`change-log` 两个接口共用同一套"按 `coord_hash` 分组、按写入顺序还原每条版本链的时间线"算法（§4.1），只是输入的 `Answer` 集合范围不同：知识点级取该 `(kb_id, kp_id)` 下全部答案；全局取全库全部答案（外连 `KnowledgePoint`/`KnowledgeBase` 取 `title`/`name`，见 §4.4）。

`stats` 接口复用 `knowledge_base.py` 里已有的 `_get_active_point_count` 辅助函数（"知识主题"），复用 `dimensions.py::get_enabled_dimension_types`（"启用维度"，其长度即为启用数——这个函数本身已经把"全局已停用的维度即使还挂在 KB 上也不算启用"这条规则处理好了，issue #9 定的约定，这里不用重新判断），"在用答案"/"今日变更"新写两条聚合查询（§4.5）。

## 4. 关键设计决策

### 4.1 变更留痕的分组/排序算法：按 `(knowledge_point_id, coord_hash)` 分组、按 `(created_at, id)` 升序复原写入顺序——这跟 `resolve.py` 已有的分组函数是两个不同的算法，不能复用

**分组键必须是 `(knowledge_point_id, coord_hash)`，不能只用 `coord_hash`**——这是对抗式审查抓到的阻塞级问题，本节先把这一点单独讲清楚，再讲排序键的区别（下一段）。`compute_coord_hash`（`coord.py:201-203`）是纯函数，只取决于归一化后的 coord 字典本身，跟任何知识点/知识库都没有关系；issue #10 的撤回接口设计已经因为同一个事实踩过一次坑（"漏掉 `knowledge_point_id` 过滤，撤回一个知识点的默认答案链会连带撤回全库同 hash 的链"），这里是同一个根因在**读路径**上的镜像版本：**知识点级**接口输入本来就已经限定在单个 `(kb_id, kp_id)` 下（§3），单独按 `coord_hash` 分组在这个场景里是安全的（等价于按 `(kp_id, coord_hash)` 分组，因为所有输入行的 `kp_id` 本来就相同）；但**全局**接口的输入是全库所有知识点的全部答案，任意两个知识点只要写过同一个 `coord`（最典型、几乎必然发生的场景就是"默认答案" `coord={}`——几乎每个知识点都会有），如果只按 `coord_hash` 分组，会把它们当成同一条版本链：后创建的一方 `action` 从 `"create"` 被误判成 `"edit"`，`before_content` 会引用**另一个知识点**的答案内容，如果其中一个知识点的链被整体撤回，还会污染到另一个完全不相关知识点的 `status` 计算。demo 自己的 `changeLogRows`（`app.js:327`）分组键其实是 `kbId + "::" + kpId + "::" + coordKeyOf(coord)`——三元组，从来不是单独的 `coord`；"直接对着 demo 移植"这句话如果只搬了 `coord_hash` 这一段，就是对 demo 算法的误移植，不是原样复用。正确的分组键是 `(a.knowledge_point_id, a.coord_hash)`（`knowledge_base_id` 不需要额外加入，因为 `knowledge_point_id` 已经唯一属于一个 `knowledge_base_id`，加了也不会改变分组结果，纯属冗余）。

`resolve.py` 已经有 `compute_all_answer_groups`/`compute_live_groups`，两者都按 `coord_hash` 分组，但它们回答的问题是"在查询时间点 `at`，这条链当前生效的是哪个版本"——排序键是 `(effective_time, created_at, id)`，`effective_time` 是**主**排序键（PRD §4.5"以 created_at 更新的一条作为该组的当前版本"这条规则本身就是在 `effective_time` 相同时才生效的**次级**规则）。

变更留痕要回答的是完全不同的问题："这条链是按什么顺序被**写入**的"——一个后填的历史生效时间（`effective_time` 早于其他版本，但是后来才创建的一条修订）在"当前生效哪个版本"的问题里可能排在前面，但在"这次修改是什么时候做的"这个审计问题里，它就是发生在它真实被 `created_at` 记录的那个时间点，跟 `effective_time` 完全无关。所以变更留痕必须用一套独立的排序键：**纯 `created_at` 升序**（`id` 作为同一毫秒内的确定性兜底，`Answer.created_at` 是 `DATETIME(6)` 微秒精度，理论上仍可能重复，不能省略这个兜底），不能复用 `resolve.py` 那两个函数、也不能给它们加参数改排序键——它们的排序键是被"当前生效"这个概念定义死的，跟审计视图的"写入顺序"是两个不相关的概念，硬要合并成一个参数化的函数反而会让两边的调用者都要小心"我这次要哪种排序"，增加出错面。

新写一个专门的纯函数，直接对着 demo 的 `changeLogRows` 移植（`frontend-mock/assets/app.js:324-356`）：

```python
def build_change_log(answers: list[Answer]) -> list[ChangeLogEntry]:
    by_chain: dict[tuple[int, str], list[Answer]] = {}
    for a in answers:
        by_chain.setdefault((a.knowledge_point_id, a.coord_hash), []).append(a)

    entries: list[ChangeLogEntry] = []
    for chain in by_chain.values():
        chain.sort(key=lambda a: (a.created_at, a.id))
        for i, a in enumerate(chain):
            is_last = i == len(chain) - 1
            status = "revoked" if (is_last and a.revoked) else ("superseded" if not is_last else "live")
            entries.append(ChangeLogEntry(
                time=a.created_at,
                knowledge_point_id=a.knowledge_point_id,
                answer_id=a.id,
                operator=a.operator,
                action="create" if i == 0 else "edit",
                coord=a.coord,
                before_content=None if i == 0 else chain[i - 1].content,
                after_content=a.content,
                source=a.source,
                revoke_reason=None,
                status=status,
                revocable=is_last and not a.revoked,
            ))
        last = chain[-1]
        if last.revoked:
            entries.append(ChangeLogEntry(
                time=last.revoked_at or last.created_at,
                knowledge_point_id=last.knowledge_point_id,
                answer_id=last.id,
                operator=last.revoked_by or "admin",
                action="revoke",
                coord=last.coord,
                before_content=last.content,
                after_content=None,
                source=last.source,
                revoke_reason=last.revoke_reason,
                status="revoked",
                revocable=False,
            ))
    entries.sort(key=lambda e: (e.time, e.answer_id), reverse=True)
    return entries
```

### 4.2 `status` 字段改用英文机器可读枚举（`live`/`superseded`/`revoked`），并且撤回这一行的 `status` 从 demo 的 `"生效"` 改成 `"revoked"`——一处刻意的、有依据的偏离

demo 里 `state` 字段直接是给人看的中文文案（`"生效"`/`"已被新版替代"`/`"已撤回"`），这跟本项目其余接口的既有约定不一致——`AnswerOut`/`KnowledgePointOut`/`resolve` 的 `status` 字段全部是英文机器可读值（`"active"`/`"deleted"`/`"exact"`/`"weighted"`/...），把"翻译成人话"这一步留给前端。本设计延续这个约定，不搬 demo 的中文字符串进 API。

更关键的一处偏离：demo 给"撤回答案"这条合成日志行的 `state` 硬编码成 `"生效"`（`app.js:349`：`state: "生效"`），这是 demo 自己的一处逻辑瑕疵——这条合成行描述的正是"这条链刚刚被撤回"这个事实，它显示成"生效"在语义上是自相矛盾的（本项目其它地方，比如 `answer-groups`/`AnswerOut.revoked`，从来不会在一条已经 `revoked=True` 的记录上标"生效"）。本设计不照抄这个瑕疵，撤回行的 `status` 诚实地设为 `"revoked"`——跟它上面那一条"最后版本"行（同样因为链已撤回而是 `"revoked"`）保持一致，两行都在描述同一个已撤回的事实，只是一条是"内容版本"、一条是"撤回动作"本身。

### 4.2.1 已知局限：撤回合成行无法区分"真正的撤回"和"编辑答案时迁移适用条件"——跟 demo 同样的局限，本设计不新增列去解决

`edit_answer` 的迁移分支（条件组合改变时）把 `payload.migration_reason`（"迁移原因"）写进的是跟专门撤回接口（issue #10）完全同一个 `Answer.revoke_reason` 列，`revoked_by` 两条路径都固定是 `"admin"`——数据库层面这两种"revoked=True"完全不可区分：一种是管理员主动点了"撤回"，这条链的内容从此彻底下线；另一种只是"把这条内容搬到了另一个条件组合下"，内容以新版本链的形式活在别处，并未真正消失。`build_change_log` 目前对这两种情况一视同仁，都合成一条 `action="revoke"` 的日志行，`revoke_reason` 原样搬运——这意味着审计人员看到一条"撤回"记录时，读到的原因文案实际上可能是一句"迁移原因"，且日志行本身不会告诉你"迁移去了哪条新链"。

这是对抗式审查指出的一个真实存在的语义缺口，本设计**有意选择不解决**：demo 本身也是同样的局限（`changeLogRows` 无差别处理两种来源），要彻底区分需要给 `Answer` 加一列标记"这次撤回的来源"，这违反了本 issue"不新增 migration、不新增业务表"的前提（issue 原文 Acceptance Criteria 第一条），属于超出本 issue 范围的改动。留痕本身没有丢失任何信息（`revoke_reason` 文本仍然完整保留，只是语义上可能是"迁移原因"而不是字面意义的"撤回原因"），只是审计人员需要结合具体文案自行判断这次"撤回"是主动下线还是内容搬迁——记录在此，作为已知限制，不在本 issue 里解决。

### 4.3 撤回行（以及每一条版本行）都带 `answer_id`，不带 `coord` 给前端重新拼撤回请求——复用 issue #10 已经定好的约定

issue #10 的撤回接口设计（`docs/specs/2026-08-08-answer-promote-revoke-api-design.md` §4.1）明确"撤回端点用 answer_id 定位版本链，不接收原始 coord 字典"，理由是 `answer_id` 指向数据库里真实存在的一行，不需要客户端重新构造 `coord` 并保证跟服务端 `normalize_coord` 算出同一个 hash。本设计的每一条变更留痕行本来就来自一条真实的 `Answer` 行（或者是从某条真实行派生出的撤回合成行），天然就带着 `answer_id`——`revocable=true` 的那一行，前端直接拿它的 `answer_id` 去调 `POST .../answers/{answer_id}/revoke`，不需要额外查询。`coord` 字段仍然保留在响应里（跟 `AnswerOut`/`AnswerGroupOut` 一样返回结构化 dict，不是 demo 里预先格式化好的 `"条件: xxx"` 文本），是给前端展示"这条记录属于哪个条件组合"用的，不是撤回请求要用的定位字段——两者互不冲突，各司其职。

### 4.4 全局日志额外携带 `knowledge_base_id`/`knowledge_base_name`/`knowledge_point_id`/`knowledge_point_title`；不按知识点/知识库状态过滤

知识点级接口的 URL 路径里已经有 `kb_id`/`kp_id`，每一行没必要再重复；全局接口没有这两个路径参数，PRD §4.8 原文明确要求"在 §4.7 基础上增加'知识库''知识点'两列用于定位"，所以全局响应的每一行额外带 `knowledge_base_id`/`knowledge_base_name`/`knowledge_point_id`/`knowledge_point_title` 四个字段。`knowledge_point_title` 必须内联返回（不能让前端自己按 `knowledge_point_id` 反查）——跟知识库列表（数量小、前端大概率已经整体拉取过）不同，知识点在全局范围内可能有几十上百个、分散在不同知识库下，指望前端为了显示日志页而提前拉全量知识点列表并不现实；`knowledge_base_name` 同理一起内联，两者都是一次 JOIN 就能带出来的信息，没有理由只带一个。

不按 `knowledge_point.status`（是否已软删除）或 `knowledge_base.status`（是否已停用）过滤——这是一个审计/追溯页面，PRD 原文强调"不可物理删除"，一个知识点被软删除、一个知识库被停用之后，它们过去发生过的变更历史仍然应该可查（不然"审计"这个能力本身就有缺口：管理员恰恰最需要在事后追查一个已经被处理掉的知识点当年经历了什么）。demo 的 `buildGlobalChangeLog`（用 `getAllAnswers()`，不做任何按知识点/知识库状态的过滤）也是这个语义，本设计与之一致——这跟 §4.5 统计接口"只统计当前生效知识点"的口径是刻意不同的两件事，不要混淆（统计卡回答的是"知识库现在的状态"，日志回答的是"知识库历史上发生过什么"）。

### 4.5 统计接口口径：与 demo 的 `computeKbStats` 逐项对齐

| 指标 | 计算方式 | 与 demo 对齐点 |
|---|---|---|
| 知识主题（`subject_count`） | `KnowledgePoint` 里 `status == "active"` 的行数 | 复用 `knowledge_base.py::_get_active_point_count`，不重新写一遍同样的查询 |
| 在用答案（`active_answer_count`） | `Answer.revoked == False`，且 `Answer.knowledge_point_id` 属于该 KB **当前状态为 active** 的知识点 | demo 用 `listActiveKPs(kbId)` 取知识点后再统计其答案——一个已软删除知识点名下未撤回的答案不算"在用"，即使 `Answer` 本身没有被撤回。SQL 上通过 JOIN `KnowledgePoint` 并加 `KnowledgePoint.status == "active"` 条件实现，不是只看 `Answer.revoked` |
| 启用维度（`enabled_dimension_count`） | `len(get_enabled_dimension_types(db, kb_id))` | 与 demo 的 `getKbEnabledDims(kbId).length` 同一口径（已排除全局已停用的维度，issue #9 定的规则） |
| 今日变更（`today_change_count`） | `Answer.knowledge_point_id` 属于 active 知识点，且 `created_at` 或 `revoked_at` 落在服务器"今天"（`date.today()`）范围内的 `Answer` 行数（去重计数，一行如果创建和撤回都发生在今天只算一次） | 与 demo 的 `created_at.slice(0,10) === MOCK_NOW \|\| revoked_at.slice(0,10) === MOCK_NOW` 同一语义；demo 用固定的 `MOCK_NOW` 常量模拟"今天"，真实后端用服务器当前日期，跟 `list_knowledge_points` 的 `at` 参数默认值用的是同一个 `date.today()` |

"今日变更"按**行数**计（一条 `Answer` 记录，不管它今天到底发生了创建还是撤回还是两者都发生），不是按"事件数"计——跟 demo 用一个 `filter()` 条件（不是两次独立计数相加）完全对齐，这个细节如果搞错（比如分别统计"今天创建的"和"今天撤回的"再相加）会在"今天创建又今天撤回"的答案上重复计数，跟 demo 口径不一致。

**"今天"的边界计算方式，以及一个跟 demo 不对等的风险点**：demo 用字符串 `slice(0,10)` 比较是因为它只有一个 JS 进程、一个时钟，没有"两个不同机器的时钟是否一致"这个变量；真实后端里 `created_at`/`revoked_at` 是 **MySQL 服务器**用 `CURRENT_TIMESTAMP(6)`/`func.now()` 生成的（`models/base.py`、`knowledge_point.py` 的 `revoke_answer`/`edit_answer` 迁移分支），而"今天"如果用应用进程的 `date.today()` 算，两者是**两个不同机器的时钟**，理论上可能不一致（应用容器和数据库容器分属不同时区配置时，"今天"的边界会整体偏移）。本设计采用的做法：应用层用 `date.today()` 算出 `[today, today+1day)` 这个左闭右开的日期区间，转成 `>= 区间起点 AND < 区间终点` 的范围条件下推给 SQL（不用 `DATE(created_at) = CURDATE()` 这种在 `created_at` 上做函数运算的写法——那种写法即使未来给 `created_at` 加索引也用不上,是不可优化的写法，即便本 issue 不做这个优化，也没有理由从设计上就把路堵死），同时明确记录一条假设：**v1 阶段假设应用服务器和数据库服务器使用同一时区，不做时区换算**——如果后续部署环境两者时区不一致，"今日变更"在午夜前后可能有偏差，这是一个已知的、跟"批量导入请求体无大小上限"同一类"记录下来但不在本 issue 解决"的残留风险，不属于阻塞项。

### 4.6 不做分页、不做筛选参数

三个接口都直接返回完整的派生结果，不接受任何 `page`/`limit` 之类的查询参数——理由：
- 跟本项目目前**所有**其它列表接口（`list_knowledge_points`、`list_dimensions`、`list_dimensions_admin`、`list_answer_groups`）保持一致，这些接口全部返回未分页的完整列表；只在这一个 issue 里单独引入一套分页约定，会让"这个项目到底分不分页"这个问题从"从来不用考虑"变成"每个接口都要各自决定"，而消费方（issue #14 的前端）目前也没有已知的分页 UI 需求。
- PRD §4.10 把"大规模知识点/答案场景下的查询性能优化"明确列为 🟢 P2，"不阻塞本轮 P0/P1 交付"——分页本质上是性能优化的一种手段（避免一次性拉取全量数据），把它单独提前到这个 P1 issue 里引入，超出了 issue 本身"只读派生视图"的范围。
- demo 本身也不是后端分页——`logs.html` 把全量数据一次性算出来，只在前端渲染时按 10 条一页做客户端切片；本设计的"不分页"跟这个行为是等价的（只是没有把客户端切片这一步搬进本设计文档，交给未来的前端 issue 视需要自行决定怎么展示）。

这是一个已知的、有意接受的残留风险（全库历史数据无限增长后，`/change-log` 全局接口的响应会越来越大），跟 issue #11 里"批量导入请求体无总大小上限"是同一类"跟随 PRD 既有决定，不在本 issue 单独加码"的判断，留给 PRD §4.10 的 P2 阶段统一解决。

## 5. 组件结构

```
backend/src/kb_backend/change_log.py                新增：ChangeLogEntry dataclass + build_change_log() 纯函数
backend/src/kb_backend/schemas/change_log.py        新增：ChangeLogEntryOut、GlobalChangeLogEntryOut(继承并加 kb/kp 定位字段)
backend/src/kb_backend/schemas/knowledge_base.py    新增：KnowledgeBaseStatsOut
backend/src/kb_backend/routers/knowledge_point.py   新增 GET /{kp_id}/change-log
backend/src/kb_backend/routers/knowledge_base.py    新增 GET /{kb_id}/stats
backend/src/kb_backend/routers/audit_log.py         新增：GET /change-log（全局，无 kb_id 前缀，跟 dimension.py 的 /admin/dimensions 一样是个不带前缀的 router）
backend/src/kb_backend/main.py                      注册 audit_log 的 router
backend/tests/test_change_log.py                    新增：build_change_log() 纯函数单测
backend/tests/test_api_change_log.py                新增：两个 change-log 接口的集成测试
backend/tests/test_api_kb_stats.py                  新增：stats 接口的集成测试
```

## 6. 测试计划

**`build_change_log` 纯函数单测**（不需要数据库，直接构造 `Answer` 对象或等价的轻量对象）：
- 单版本、未撤回：一行 `action="create"`, `status="live"`, `revocable=True`, `before_content=None`。
- 同一条件组合两个版本（改答案，未撤回）：第一行 `action="create"`/`status="superseded"`/`revocable=False`；第二行 `action="edit"`/`status="live"`/`revocable=True`/`before_content` 等于第一行的 `content`。
- 链已撤回（如 issue #10 的 revoke 或 edit_answer 的迁移分支都会产生这个状态）：最后一条版本行 `status="revoked"`/`revocable=False`；额外多出一行 `action="revoke"`/`status="revoked"`/`revoke_reason` 非空/`answer_id` 等于最后一条版本的 id。
- **三个版本的链被整体撤回**（对应 `revoke_answer`/`edit_answer` 迁移分支对整条链批量 `UPDATE revoked=True` 的真实行为，此时链上**每一行**的 `revoked` 字段字面值都是 `True`，不只是最后一行）：第 1、2 个版本行的 `status` 仍然是 `"superseded"`（不能因为它们的 `revoked` 字段现在也是 `True` 就误判成 `"revoked"`——这是对抗式审查专门点出的、反直觉但正确的场景，`status` 计算只看 `is_last`，非最后版本永远不看 `revoked` 字段），只有第 3 个（最后一个）版本行是 `"revoked"`。
- **两个不同知识点、各自的答案共享同一个 `coord_hash`**（最典型：两个知识点各写一条默认答案，`coord={}`）混在同一个列表里传入：`build_change_log` 必须把它们分成两条独立的链（分组键是 `(knowledge_point_id, coord_hash)`，不是单独的 `coord_hash`），互不影响——这是对抗式审查抓到的阻塞级问题 F0 的直接回归测试，不能只测"两个不同知识库的知识点各写一条答案"却让它们的 `coord` 恰好不同（那样测不出这个 bug，因为不同 `coord` 天然产生不同 `coord_hash`，不会撞车）。
- 同一毫秒的 tie-break：构造两个 `created_at` 完全相同的答案，确认按 `id` 排序结果稳定、不抛异常。

**知识点级/全局 change-log 接口集成测试**：
- 写入一个答案再编辑一次（同条件组合）→ 两行流水，字段跟单测覆盖的场景对齐。
- 撤回一条链 → 出现撤回行，`answer_id` 可以直接拿去调 `POST .../revoke`（跑一次确认真的能调通，回归 §4.3）。
- **全局接口：两个不同知识库下的两个知识点，各写一条 `coord` 完全相同的答案（比如都只写默认答案）** → 两条各自独立成链，各自的 `before_content`/`action` 都不受另一方影响，且每一行的 `knowledge_base_name`/`knowledge_point_title` 都对应到自己所属的知识库/知识点，不串号——这是集成测试层面对 F0 的端到端回归（纯函数单测已经覆盖了算法本身，这里额外确认真实的数据库查询+JOIN 链路上这个修复同样生效）。
- 全局接口：知识点被软删除后，其历史变更依然出现在全局日志里（回归 §4.4，跟 stats 的口径故意不同）。
- 知识点不存在 / 知识库不存在 → 404。

**stats 接口集成测试**：
- 空知识库：四个数字全部为 0。
- 一个知识库有 2 个 active 知识点、1 个已软删除知识点：`subject_count == 2`（软删除的不计入）。
- 软删除知识点下有未撤回答案：`active_answer_count` 不包含这些答案（回归 §4.5 的核心场景，防止只看 `Answer.revoked` 漏掉这层过滤）。
- 撤回一条答案后 `active_answer_count` 相应减少。
- 启用/停用维度后 `enabled_dimension_count` 相应变化。
- 今天创建一条答案、今天撤回另一条已存在的答案 → `today_change_count` 正确累加两条；同一条答案今天创建又今天撤回 → 只计 1 条，不计 2 条（回归 §4.5 "按行数不按事件数"）。
