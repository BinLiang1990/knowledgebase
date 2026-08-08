# 知识点详情页 · 当前答案 tab（issue #8）设计文档

## 1. 范围

issue #8 明确要求（P0）：
- 详情页可达（需要新路由 + 从列表页可以进入）
- "当前答案" tab：带条件筛选器（复用 §4.6 的钉维度=值 + 时间穿梭）+ 按匹配优先级排序的答案列表 + 写一条答案/编辑答案表单
- "设为默认"、"撤回" 按钮先隐藏（依赖 P1 的 Issue #10 后端接口）
- 不做：版本历史、变更留痕、立体全景 tab 内容（Issue #14、#16）

PRD §4.7 把"头部"也标为 P0（标题/ID/在用答案数/创建信息/状态标签 + 写答案/编辑标题/删除三个操作）。详情页离开头部无法自洽存在，本设计把头部一并实现，视为"P0 详情页"隐含范围，而不是 issue #8 的额外扩权。

不做的三个 tab 仍渲染 tab 按钮（IA 与 demo 一致，方便 #14/#16 直接填内容），点击后显示"开发中，见 Issue #xx"占位，而不是完全不显示 tab——延续 issue #7 对未就绪统计卡的处理方式（占位而非隐藏）。

## 2. 路由与可达性

新路由：`/knowledge-bases/:kbId/knowledge-points/:kpId` → `KnowledgePointDetailPage`。

列表页（issue #7 `KnowledgePointRow.tsx`）目前整行点击=展开树，标题本身不可点击进详情。对齐 demo（`frontend-mock/index.html:244`）：
- 标题变成 `<Link>`，`onClick` 里 `stopPropagation`，不影响整行展开的既有交互
- ops 区新增"查看详情"链接（与"删除"并列）

详情页复用 `KnowledgePointListPage.tsx` 已经建立的"知识库无效即拦截"规则（`kb.status !== 'active'` → 显示"没有指定有效的知识库"guard），保持两个页面一致：一个已停用的知识库，其下知识点的详情页也不应该能直接看到。`GET /{kb}/knowledge-points/{kp}` 本身不检查知识库状态（只检查存在性），这个 guard 完全是前端职责。

## 3. 数据来源（不新增后端接口）

全部复用已实现的接口：

| 用途 | 接口 | 来源 issue |
|---|---|---|
| 单个知识点详情（含软删除态） | `GET /knowledge-bases/{kb}/knowledge-points/{kp}` | #4 |
| 编辑标题 | `PATCH /knowledge-bases/{kb}/knowledge-points/{kp}` | #4 |
| 软删除 | `POST .../knowledge-points/{kp}/delete` | #4 |
| 本知识库启用维度（含 weight，供条件编辑器/兼容性排序用） | `GET /knowledge-bases/{kb}/enabled-dimensions` | #3 |
| 写一条新答案 | `POST .../knowledge-points/{kp}/answers` | #4 |
| 编辑答案（同条件追加版本 / 改条件迁移） | `POST .../answers/{id}/edit` | #4 |
| 该知识点全部条件组（含撤回、未生效） | `GET .../knowledge-points/{kp}/answer-groups?at=` | #7 |

"当前答案" tab 需要的是"在 T 时点存活、且与筛选条件兼容的答案组，按优先级排序"——`answer-groups` 接口返回的是全量（含撤回/未生效），恰好是这个列表的超集，直接在前端筛出 `live_answer !== null` 的组即可得到"存活组"，无需新增后端接口。

单个知识点 fetch 用新的 `useKnowledgePoint(kbId, kpId)`（新 hook），因为知识点列表接口（issue #4）不返回软删除的知识点，而详情页按 PRD 要求必须能展示"已删除"知识点的历史答案。后端 `GET /{kp_id}` 本身不过滤 status，直接可用。

## 4. 关键设计决策

### 4.1 "当前答案" 排序/兼容性判断在前端复现 §4.6.1 规则，而不是新增后端接口

demo（纯前端 app）对这个 tab 是这样算的：`liveGroups()` 取每组存活版本 → `coordCompatible()` 过滤 → 按 `spec desc, weight desc, effective_time desc` 排序。后端 `resolve.py::resolve()` 已经实现了同一条规则，但只返回"最佳一条"（供 §4.6.2 单点解析接口用），不返回"全部兼容组的排序列表"——本 tab 需要展示全部可编辑的组，不能只要冠军。

两个选项：
1. 新增后端接口"返回该知识点全部兼容组的排序列表"
2. 前端在已有的 `answer-groups` 数据上复现兼容性判断 + 排序（就是 demo 的做法）

选 2：issue #8 明确标注"前端"、"建议在 #4、#5 之后接真实接口"，且所需字段（`coord`、`live_answer.effective_time`）已经在 `answer-groups` 里；`weight` 从已经在拉的 `enabled-dimensions` 里取。新增一个只服务于本页排序展示的后端接口，超出本 issue 授权范围。复现逻辑做成纯函数 + 单测（`sortLiveGroupsByPriority`），把"逻辑分叉"的风险用测试钉住，而不是猜测两处实现会不会漂移。

兼容性规则原样照抄 §4.6.1 第 3 条（与后端 `_coord_compatible` 语义一致）：组自己写的每个维度值都必须和 Q 里对应维度值一致；Q 问到但组没写的、组写了但 Q 没问的，都不参与过滤。

**排序键必须是完整的 5 元组，不是 PRD prose 的 3 元组。** 对抗式审查发现：真实的 `resolve.py::resolve()`（`resolve.py:194-203`）排序键是 `(spec, weight, effective_time, created_at, id)`，后两个 tie-break 键是"Found by the Kimi review gate on PR #21"专门加上去的（`effective_time` 是天粒度，同一天的多条答案很常见）。§4.6.1 的 PRD 原文只写了三层，是简化表述，不能照抄。`sortLiveGroupsByPriority` 必须用完整 5 元组，否则本 tab 排在最前面（有"此条件下生效"标记）的那条，会和同一知识点在 §4.6.2 `/resolve` 接口或列表页 `resolved` 预览里算出来的"冠军"不一致——这恰好是 issue #8 存在的意义要防止的那种问题。`AnswerOut` 已经带 `id`/`created_at`，前端拿得到，不需要后端改动。

**已知、接受的偏差：coord 引用的维度一旦被停用，前端排序用的 weight 会退化为 0，和后端不一致。** 后端 `resolve.py::_dimension_weights()` 按 key 查权重时完全不看 `status`（`resolve.py:48-54`），所以一条答案的条件里用到的维度即使后来被全局停用/本知识库取消启用，`resolve()`/`compute_live_groups()` 排序时仍然用它停用前的 weight；而前端只有 `GET /enabled-dimensions`（过滤 `status=active` 且本知识库已启用）能拿到 weight，查不到的 key 只能按 0 处理。这会让本 tab 的排序在"某个兼容组用了一个已停用维度"这个窄场景下，与后端 `/resolve` 的排序结果不一致。这是本设计接受的已知偏差（不新增后端接口去暴露停用维度的 weight，超出本 issue 范围），不是遗漏——写在这里是为了下次复现时不必重新debug。

**已知、接受的偏差（第二轮 Codex 外门标为 P1，评估后判定为超出本 issue 范围、有意延后）：number 类型的 coord 值一旦超过 `Number.MAX_SAFE_INTEGER`（2^53），会在 `apiClient` 用浏览器原生 `response.json()` 解析响应体的那一刻就被静默舍入精度——这发生在我方任何比较/展示代码运行之前，无法在组件层面挽回。`coord.py` 特意支持到 uint64 的精确整数（大段专门的 Decimal 解析注释可查），所以理论上：一条答案的某个 number 型条件值若超过这个范围，用户编辑该答案的**另一个**条件触发迁移时，这个没被动的字段会带着已经被浏览器 JSON 解析舍入过的错误数值一起提交，把答案迁移到一个和用户预期不完全一致的条件组合下。

评估后决定不在本 issue 修：
- 这不是本 issue 引入的新问题——issue #4 起 `coord.py` 就支持这个数值范围，issue #5/#7 的只读展示路径（resolve 结果、答案树）早就在用同一条浏览器 JSON 解析链路，只是从来没有一条"读回来再写出去"的路径把这个精度损失变成可观察的后果，issue #8 的编辑表单是第一条这样的路径。
- 正确的修复方式是在 `apiClient` 层面做一个不依赖浏览器原生数字解析、能把超出安全整数范围的数字面值保留成精确字符串的响应体解析——这需要一个逐字符扫描原始响应文本、区分"字符串内部的数字"和"JSON 数字面值"的小型 tokenizer（不能用一个正则整体处理，因为 `content` 等自由文本字段本身可能包含任意数字），或者引入一个第三方大数安全 JSON 解析库。这两种方式都会改动 `apiClient.ts` 这个全站每个请求都会经过的公共模块，仓促赶工的话，破坏它的代价远大于这个边缘场景本身的代价。
- 实际业务场景里，维度取值（"优先级""权重"类）是很小的整数，真实触达 2^53 这个量级的概率可以认为是零——这是纯防御性工程问题，不是产品需求。

如果后续真的需要修（比如维度定义支持了更大范围的业务号段），应该作为一个独立的、覆盖全站 `apiClient` 的精度修复来做，不要在某一个功能 issue 里仓促打补丁。

### 4.2 写/编辑答案共用一个 modal，`适用条件` 是新的多行编辑器（不是 ConditionPicker）

issue #7 的 `ConditionPicker` 是"筛选器"：一次只锁一个维度=值，构建 `filters` 对象供查询用。这里的"适用条件"是"编辑一条答案要挂在哪个条件组合下"：需要同时看到/编辑多个维度=值的组合（0~N 行），且要能从"编辑已有组"预填进来。两者语义、交互都不同，做成新组件 `CoordEditor.tsx`，而不是硬塞进 `ConditionPicker`。

维度取值的类型转换规则（boolean→真布尔、number→字符串保精度、text→trim 后拒绝空值）与 `ConditionPicker` 完全一致——这条规则前后两次改动都证明"每个用到它的地方各写一遍"是漂移高危区（issue #7 的 Codex 轮把 `ConditionPicker` 里漏掉的 trim 抓出来过一次），所以本次把 `toFilterValue` / `displayValue` / `ValueInput` 从 `ConditionPicker.tsx` 抽到共享模块 `components/ui/dimensionValue.tsx`，`ConditionPicker` 改为从这里导入，`CoordEditor` 复用同一份实现。

`CoordEditor` 相比 demo 多一条约束：同一维度不能出现在两行里（demo 的 `condRowsHtml` 下拉不排除已用维度，`readCondRows` 用后一行静默覆盖前一行，等于允许用户在不知情的情况下丢弃一行输入）。改为其他行下拉里排除已被占用的维度 key，从交互上避免这个歧义态，而不是复现 demo 的这个小缺陷。

**编辑一条条件已引用停用维度的答案：该行锁定为只读，禁止在此基础上迁移条件。** 如果 `existing.coord` 里某个 key 不在当前 `enabled-dimensions` 列表里（该维度全局停用，或本知识库取消了启用），对应行渲染成锁定态：显示原始 key + "（已停用）"标签，不可编辑、不可删除，值保持原样传递（不重新校验）。这类答案仍然可以编辑内容/生效时间（见 §4.4，不改条件时前端根本不发送 `coord`，走后端"保留原样、不重新校验"的安全通道）；但如果用户同时改了别的行（触发迁移），提交前端校验直接拦截，提示"该答案的条件包含已停用的维度「X」，暂不支持迁移条件"——因为无论怎么组装新 coord，都会带着这个后端 `normalize_coord` 会拒绝的 key，与其让后端 400，不如前端直接说清楚。

### 4.3 迁移原因字段：demo 没有，真实后端要求

后端 `edit_answer`（issue #4）在 `coord_hash` 变化时强制要求非空 `migration_reason`（`变更适用条件需要填写迁移原因`），demo 没有这个字段（自动生成 note）。表单在"编辑答案"模式下，实时对比当前 `CoordEditor` 算出的 coord 与打开时的原始 coord：不同则显示"迁移原因"必填项，相同则不显示（也不发送该字段）。

判定"是否不同"用 key 集合 + 逐 key 按字段类型比较（`coordValueEquals(fieldType, a, b)`），不是裸的 `String()`/`JSON.stringify` 比较。原因：`answer-groups` 接口返回的原始 coord 里，number 类型的值是 JSON 原生数字（如 `5`），而 `CoordEditor` 走 `toFilterValue` 后 number 类型的草稿值是字符串（如 `"5"`，issue #7 就是故意这么做的，为了保精度走后端 Decimal 解析）——两边类型天然不对称，裸字符串比较在数字类型上容易谁都没改却被判定为"已迁移"（比如 `"1.50"` 和 `1.5`）。`coordValueEquals` 对 number 类型用 `Number(a) === Number(b)` 比较，对 boolean 用 `Boolean(a) === Boolean(b)`，其余（text/date，两边都已经是 trim 过的字符串/ISO 日期串）用 `String(a) === String(b)`。

这个误判不会导致真正的数据问题（后端 `is_migration` 只认 `coord_hash` 是否变化，不受前端这个 diff 影响），但会让用户在明明没碰条件的情况下被要求填"迁移原因"，体验上值得在实现前修好，而不是留到测试阶段才发现。

### 4.4 提交时只在条件确实变化时才携带 `coord`（不是"始终携带"）

`AnswerEdit` 支持"不携带 coord = 保留原条件"：后端在这种情况下跳过 `normalize_coord` 重新校验，直接复用旧值（`routers/knowledge_point.py:419-436`，issue #4 的设计意图：维度被停用后旧数据不因为编辑其他字段而报错）。

最初考虑过"始终携带 `coord`，省去区分'有没有变'的逻辑"，对抗式审查指出这会白白扔掉这条后端专门做的安全通道：只要答案的条件里有任何一个 key 引用了已停用的维度，"始终携带"就会让每一次编辑（哪怕只改内容/生效时间，压根没碰条件）都触发 `normalize_coord` 重新校验，命中"维度 X 未在本知识库启用"直接 400——而这条安全通道存在的唯一目的就是让这种编辑能通过。§4.3 已经算出了"当前 coord 是否与原始 coord 不同"这个 diff，复用它来决定要不要携带 `coord` 几乎是免费的：

- diff 判定"未变化" → 编辑请求里**不带** `coord` 字段（连值相同的 `coord` 都不带），走后端的安全通道
- diff 判定"变化了"（真迁移）→ 带上新的 `coord` + 必填的 `migration_reason`
- 变化了、且当前条件行里存在 §4.2 提到的"锁定态"（引用已停用维度）→ 前端直接拦截提交，不发请求（见 §4.2）

这样"编辑答案引用了已停用维度"这个边缘场景在最常见的子情况（只改内容/时间，不碰条件）下是完全安全的，只有"确实要把这个答案迁移到新条件"这一种子情况会被前端明确拦截并提示原因，而不是让后端 400 掉一个用户看不懂的错误。

### 4.5 缓存失效策略

`api/knowledgePoints.ts` 已有 `invalidateAfterKpMutation(queryClient, kbId)`，同时失效 `['knowledge-bases', kbId, 'knowledge-points']`（前缀）和 `['knowledge-bases']`——issue #7 的 Codex 轮专门修的，创建/删除知识点都会改变知识库的 `active_knowledge_point_count`。

本 issue 新增的三个 hook 都只影响某个知识点自己的数据，不影响知识库聚合数：

- `useKnowledgePoint(kbId, kpId)`、`useUpdateKnowledgePointTitle(kbId, kpId)`：query key 用 `['knowledge-bases', kbId, 'knowledge-points', kpId]`——刻意让它落在 `['knowledge-bases', kbId, 'knowledge-points']` 这个前缀之下（和 `useKnowledgePoints`、`useAnswerGroups` 的 key 前缀完全一样），这样只需要失效这一个前缀，列表页的 `resolved` 预览、详情页自己的单点 fetch、详情页的 `answer-groups` 全部一起刷新，不需要逐个记 key。
- `useCreateAnswer(kbId, kpId)`、`useEditAnswer(kbId, kpId)`：成功后失效 `['knowledge-bases', kbId, 'knowledge-points']`（同一个前缀，不带 `useKnowledgePoints` 已经在用的 `KNOWLEDGE_BASES_KEY`——写答案不改知识库自己的聚合数）。抽一个 `invalidateKnowledgePointDataQueries(queryClient, kbId)` 辅助函数，和 `invalidateAfterKpMutation` 区分开：后者多失效一层 `KNOWLEDGE_BASES_KEY`，专用于创建/删除知识点；前者只失效知识点前缀，专用于答案级别的写操作和标题编辑。
- `useUpdateKnowledgePointTitle` 也走 `invalidateKnowledgePointDataQueries`（标题变了，列表页的知识点标题、详情页头部都要刷新，但不影响知识库聚合数）。

### 4.6 头部操作与 out-of-scope 的取舍

- "设为默认"/"撤回"：issue 明确先隐藏（Issue #10 未交付）。不做置灰按钮（点了没反应的按钮比没有按钮更让人困惑）。
- 已删除知识点：显示"该知识点已被软删除…"提示 + 隐藏"写一条答案/编辑标题/删除"操作，但不显示 demo 的"前往回收站恢复"按钮——本应用还没有回收站页面（demo 的 `trash.html` 对应的是 Issue 列表里没出现的功能，本 session 的 issue 序列里目前没看到"回收站页面"这张卡；等它排上再补这个链接，现在做一个死链接不如不做）。

## 5. 组件结构

```
KnowledgePointDetailPage.tsx        页面：头部 + tabs + "当前答案" tab body
  ├── components/CoordEditor.tsx    适用条件多行编辑器（新增/编辑答案表单共用）
  ├── components/WriteAnswerModal.tsx  写一条答案 / 编辑答案共用弹窗
  ├── components/EditTitleModal.tsx    编辑标题弹窗
  └── components/DeleteKnowledgePointModal.tsx  从 KnowledgePointListPage.tsx 抽出，两个页面共用
components/ui/dimensionValue.tsx    toFilterValue / displayValue / ValueInput（从 ConditionPicker.tsx 抽出）
api/knowledgePoints.ts              新增 useKnowledgePoint、useUpdateKnowledgePointTitle、
                                     invalidateKnowledgePointDataQueries（与既有 invalidateAfterKpMutation 并列）
api/answers.ts                      新增 useCreateAnswer、useEditAnswer；
                                     新增纯函数 sortLiveGroupsByPriority、coordValueEquals、diffCoord
```

## 6. 测试计划

- `sortLiveGroupsByPriority` 纯函数单测：无筛选返回全部存活组；带筛选按兼容性过滤；完整 5 元组排序（含 `effective_time` 相同时按 `created_at`/`id` tie-break）；`uniqueTop` 判定；coord 引用一个不在 `dimensions` 列表里的 key 时按 weight=0 处理（§4.1 已知偏差）而不是抛错。
- `coordValueEquals` 纯函数单测：number 类型 `"5"` vs `5`、`"1.50"` vs `1.5` 判等；boolean/text/date 各类型正常判等/判不等；key 集合不同即判不等。
- `CoordEditor`：添加/移除行；已用维度在其他行下拉里被排除；空值/空白值行提交时报错；初始值引用一个不在 `dimensions` 里的 key 时渲染为锁定态（不可编辑/删除，显示"已停用"）。
- `WriteAnswerModal`：创建答案成功（不带 `migration_reason`）；编辑答案条件不变时请求体不带 `coord`、不要求迁移原因；条件改变时请求体带 `coord` + 要求非空迁移原因；条件里有锁定态行时改动其他行会被前端拦截、不发请求；提交后关闭弹窗+toast。
- `KnowledgePointDetailPage`：
  - 头部渲染标题/ID/在用答案数/创建信息/状态标签
  - 知识库已停用/不存在：显示"没有指定有效的知识库"guard（与列表页一致）
  - 软删除态：显示提示，隐藏写/编辑标题/删除操作
  - 编辑标题成功刷新显示
  - 删除成功后原地刷新为软删除态（不跳转）
  - "当前答案" tab：无筛选显示全部存活组；带筛选按兼容性过滤+排序+"此条件下生效"标记；空结果提示
  - 时间穿梭切换后重新拉取（复用 issue #7 已验证的 `at` 处理方式：最新模式不传 `at`）
  - 创建/编辑答案成功后，同一个知识点前缀下的查询（列表页 `resolved` 预览、本页单点 fetch、`answer-groups`）都会刷新——用一个"创建后 `active_answer_count` 更新"的用例间接验证失效范围，而不是断言内部 query key
  - 其余三个 tab 显示开发中占位
- `KnowledgePointRow.tsx`（列表页）：标题是指向详情页的链接；"查看详情"链接同样指向详情页；两者都不影响整行展开的现有交互
