# 按维度条件查询知识点：解析引擎 + 列表筛选 + 单点解析（issue #5）

## 1. 范围

实现 `docs/PRD.md` §4.6、§4.6.1、§4.6.2：一套共享的解析引擎,支撑两种消费形态——

1. 知识点列表 + 条件筛选（关键字 + 维度条件 + 查询时间,扩展 issue #4 已有的 `GET /knowledge-bases/{kb_id}/knowledge-points`)
2. 单点解析接口（给定知识库 + 知识点 + 条件 + 时间,直接返回命中答案）

不含：知识点详情页的版本历史/变更留痕(#12)；大规模数据下的性能优化(#15)；"展开查看全部答案分组树"这种详情页可视化(不在本 issue AC 里,归 §4.7)。

## 2. 解析算法（逐条对照 `frontend-mock/assets/app.js` 的 `resolveAnswer`/`liveGroups` 移植,细节以 PRD §4.6.1 文字为准）

### 2.1 第一步：按知识点 + 查询时间 T,求每个条件组合(coord)在 T 时点的"当前版本"

对该知识点下 `effective_time <= T` 且未撤回的答案,按 `coord_hash` 分组；每组内取 `(effective_time, created_at)` 二元组最大的一条作为该组的"当前版本"("current version")。没有任何版本满足 `effective_time <= T` 的组,视为在 T 时点不存在,不参与后续匹配。

> demo 的 `liveGroups()` 只按 `time`(即 `effective_time`)降序排序取第一条,没有显式处理"同一天多次编辑"的 tie-break——这是因为 demo 的种子数据里同一条件组合从未出现过 `effective_time` 相同的两条记录,单纯按插入顺序(稳定排序)也能凑巧给出正确结果。真正的实现按 PRD §4.6.1 第 1 点、issue #4 验收标准"同一 coord 下 effective_time 相同时以 created_at 更大的为准"执行,不能只照抄 demo 代码本身,要照抄 PRD 文字描述的规则。

### 2.2 第二步：给定查询条件 Q,在这些"当前版本"分组里找命中

**第 0 步(对抗式自校发现最初的文字描述漏掉了这一步)：如果第一步算出来的分组列表本身是空的(这个知识点在 T 时点没有任何"当前版本"——一条答案都没写过,或者所有答案的 `effective_time` 都晚于 T),直接返回 `status = "none"`,不管 Q 是否为空,不进入下面任何分支。** demo 的 `resolveAnswer()` 把这一步写在最前面（`if (!groups.length) return {status:"none"}`),必须在"Q 为空/非空"这两条分支之前独立判断,否则"Q 为空但完全没有分组"这种情况(典型场景：查询时间早于任何答案生效)会被错误地当成"没有默认答案,回退取最新"走进 `fallback-latest` 分支,而实际上根本没有分组可取。

- **Q 为空**：
  - 存在 `coord = {}` 的默认答案组 → 命中该组,`status = "default"`
  - 否则,在全部组里取 `effective_time` 最新的一组（同上,用 `(effective_time, created_at)` 排序，比 demo 只比较 `time` 更严格地消除并列歧义）→ `status = "fallback-latest"`
- **Q 非空**：
  1. 筛选"条件兼容"的组：组内 `coord` 自己写明的每个 key,如果 Q 也问到了这个 key,取值必须相等；Q 问到但组没写的 key 不参与过滤；组写了但 Q 没问到的 key 也不参与过滤。**注意这意味着 `coord = {}` 的默认答案组永远是"兼容"的**(它没有任何 key 需要比较),它会作为一个权重最低的候选参与排序,而不是被直接排除——这是 PRD 文字和 demo 代码的字面结论,不是我们自己加的行为。
  2. 没有任何兼容组 → `status = "none"`
  3. 有兼容组：按 `(spec, weight, effective_time, created_at)` 四元组降序取第一条,`spec` = 该组 `coord` 里 key 的个数,`weight` = 这些 key 各自维度当前 `weight` 值之和(用当前维度定义的 weight,不做历史快照)。**`created_at` 作为第四级 tie-break 是本设计新加的决策,不是 PRD 原文或 demo 代码已有的规则**——PRD §4.5/§6 规则 #14 明确要求的 `created_at` tie-break,原文语境是"同一 coord 分组内,`effective_time` 相同时取哪个版本"(即 §2.1 的场景),没有覆盖"不同 coord 分组之间,`spec`/`weight`/`effective_time` 三者都相同时选哪一组"这个场景;demo 对这个场景也没有显式规则,只是 JS 稳定排序恰好保留了 Map 插入顺序,凑巧给出确定结果,不构成"已验证的规则"。这里补一条 tie-break 纯粹是为了让结果确定、可测试,不依赖"谁先插入",作为一个新的、需要单独标注的产品决策记录下来,而不是"和 2.1 一样,PRD 已经要求了"。fallback-latest(2.2 的"Q为空"分支)取最新那一步同理,也是本设计新加的 tie-break。
  4. 判定 `exact`：`top.spec == len(Q的key)` 且 `top.coord` 里每个 key 的取值都等于 Q 里对应取值——两个条件同时满足,精确对应"条件的 key 集合与取值完全一致"（不需要额外比较 key 集合,因为"个数相等 + 每个 key 都对得上" 在兼容性已保证"没有冲突取值"的前提下,足以推出集合相同）。满足 → `status = "exact"`；不满足但有兼容组命中 → `status = "weighted"`。

### 2.3 维度权重的历史一致性

分组里某个 key 对应的维度即使后来被全局停用(`status=deprecated`),排序时依然使用该维度**当前**的 `weight` 值参与计算——停用不影响历史答案的可查性和可排序性(§6 规则 #7),`weight` 字段本身是可修改的,查询时永远读取维度定义表的最新值,不做历史快照。

## 3. 共享解析模块 `kb_backend/resolve.py`

```
compute_live_groups(db, kb_id, kp_id, at) -> list[LiveGroup]
resolve(groups: list[LiveGroup], query_coord: dict) -> ResolveResult
```

`compute_live_groups` 做 DB 查询 + 分组 + 权重查表(纯 I/O)；`resolve` 是纯函数(不碰 DB,输入已经算好的 `groups` + 归一化后的查询条件,输出命中结果)——这个切分是为了让核心排序/判定逻辑可以脱离数据库单独做详尽的单测,也是"两个接口共享同一套解析引擎"这条验收标准字面要求的实现方式：单点解析接口和列表筛选接口各自负责取数据、拼参数,但都调用同一个 `resolve()`。

查询条件 `Q` 在传入 `resolve()` 之前,先用 issue #4 的 `coord.py` 里的 `normalize_coord()` 归一化 + 校验(维度必须是本知识库已启用的,取值必须通过对应 `field_type` 的强校验)——查询条件与写入条件用完全相同的校验规则,这是 §4.2"所有类型在'答案条件'与'查询条件'里都统一做精确相等匹配"的直接要求,不是两套逻辑。

## 4. 接口设计

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/knowledge-bases/{kb_id}/knowledge-points/{kp_id}/resolve` | 单点解析 |
| GET | `/knowledge-bases/{kb_id}/knowledge-points`(扩展 issue #4 已有接口) | 列表 + 条件筛选 |

两个接口都用 **GET + JSON 编码的 `coord` query 参数**,不用 POST——这两个操作都是纯查询、无副作用,GET 在语义上更准确；`coord` 因为 key 集合不固定(取决于每个知识库启用了哪些维度),没法用扁平 query 参数一一列举,所以用一个整体 JSON 字符串（如 `?coord={"tenant":"acme"}`），解析失败直接 422（复用 pydantic 的 JSON 解码,不手写）。

### 4.1 单点解析

`GET .../resolve?at=2026-08-08&coord={"tenant":"acme"}`（两个参数都可省略,`at` 默认当天,`coord` 默认 `{}`）

响应：`{ status, answer }`,`answer` 是完整的 `AnswerOut`(issue #4 已有),`status="none"` 时 `answer=null`。

### 4.2 列表 + 条件筛选

在 issue #4 的 `GET /knowledge-bases/{kb_id}/knowledge-points` 上新增三个可选 query 参数：`keyword`(标题子串,大小写不敏感,对齐 demo 的 `toLowerCase().includes()`)、`at`、`coord`。

**响应形状：无条件地在每一行 `KnowledgePointOut` 基础上加一个 `resolved: {status, answer}` 字段**,不是"只有传了筛选参数才计算"——这对应 §4.6 的字面描述："无维度条件：...每行预览其默认答案"，demo 里 `ansPreview()` 也是无条件对每一行调用 `resolveAnswer()`。计算成本已经在 §4.6.2 里被 PRD 明确列为 v1 不用管的非目标("先按 demo 验证过的'实时解析'方案实现"),不为了省这个成本另设一个"要不要算"的开关,徒增 API 复杂度。

**排除规则**：只有当 `coord` 参数**非空**时,才会把 `resolved.status == "none"` 的知识点从结果里剔除；`coord` 为空(或未传)时,不管 `resolved.status` 是什么,知识点都正常出现在列表里(哪怕它一条答案都没写过,`status` 会是 `"none"`,但仍然展示——对应 demo `visibleKps()` 里 `hasQ` 为 false 时不做这层过滤)。`keyword` 过滤先于 `resolved` 计算执行(标题子串匹配是纯内存操作,不需要碰数据库),减少不必要的解析开销。

**分页。** issue #4 的列表接口本身没有分页(知识库/知识点量级不需要),本 issue 不引入分页。这点专门说明一下：对抗式自校提出了"排除规则要在分页之前对全量结果执行,否则分页会算错"的顾虑——这个顾虑本身是对的,但当前系统没有分页,所以不构成一个需要修的问题,只是先把这个前提记录下来,如果以后知识点量级大到需要分页(§7 非功能需求提到的"量大时需评估"),排除规则必须在分页切片之前对关键字命中的全量结果执行,不能先切页再挑,否则会出现"这一页数量少于 page size"或统计总数不对的问题。

**coord 里的空字符串取值,归一化时当作"没填这个 key"处理,不是一个真实的取值。** 对抗式自校发现 `coord.py`(issue #4)的 `_normalize_text` 只做了 `.strip()`,没有像 demo 的 `coordKeyOf`/`coordSpec`/`coordWeight`/`coordCompatible` 那样把空字符串等同于"未指定"处理。这是 issue #4 遗留的一个行为缺口,不是本 issue 才产生的,但因为查询条件的等价处理规则要求和写入路径完全一致(§4.2),本 issue 顺带修掉：`normalize_coord()` 在文本类型归一化后,如果结果是空字符串,直接把这个 key 从归一化结果里剔除,视为该 key 未指定——这个改动同时影响写入路径(`coord={"tenant":""}` 现在会被当成默认答案组 `coord={}`)和查询路径,两边保持一致,不是只修查询这一侧。

## 5. 测试计划

### 5.1 `resolve.py` 纯函数单测（不需要真实 DB,直接构造 `LiveGroup` 列表）

- 默认答案存在 → `default`；不存在 → `fallback-latest`
- 精确命中 vs 权重回退（含"候选组的 coord 与 Q 完全不重叠但仍被判定为兼容"这个来自算法字面定义、容易被误"修复"掉的行为）
- 无任何兼容组 → `none`
- 同 `(spec, weight, effective_time)` 全部相同时,用 `created_at` 做最终 tie-break(demo 没有这一步,是本设计在 PRD 文字基础上补的)

### 5.2 对照 `frontend-mock/assets/app.js` 种子数据的回归测试

通过 API 重建种子数据里"退款政策"这个知识点的三条答案(默认组两个版本 + `tenant=示例租户B` 一个版本),在 `at="2026-08-06"`（demo 的 `MOCK_NOW`）下逐条验证：

- Q={} → `default`,命中"延长至15天"版本(默认组里 `effective_time` 更新的那条)
- Q={tenant:"示例租户B"} → `exact`,命中"30天无理由退款"版本
- Q={tenant:"从未出现过的租户"} → `weighted`,回退命中默认组("延长至15天"版本)——这是"默认组永远兼容"这条规则的直接体现
- Q={}、`at="2026-07-25"`(早于任何答案的 `effective_time`)→ `none`(时间穿梭到答案存在之前,任何组都没有"当前版本")

这四条覆盖 issue AC 点名的全部四种场景(精确命中/权重回退/默认答案回退/无命中排除)。

### 5.3 API 集成测试

- 单点解析：找不到知识点/知识库 → 404；`coord` 包含未启用维度 → 400；`coord` JSON 格式错误 → 422
- 列表筛选：`keyword` 大小写不敏感子串匹配；`coord` 非空且有知识点为 `none` 时该知识点被排除；`coord` 为空时所有知识点都出现且各自带 `resolved` 字段；`at` 影响每个知识点各自的解析结果
