# 知识点列表页 + 维度条件筛选 UI（issue #7）

## 1. 范围

按 issue #7,参考 `frontend-mock/index.html` 实现知识库内的知识点列表页：顶部统计卡(部分占位)、关键字+维度条件筛选器(钉维度=值+时间穿梭)、可展开的知识点行(答案分组树,只读)、新增/删除知识点。对接 issue #4(知识点 CRUD)+ issue #5(列表筛选/单点解析)已有的后端 API。不含知识点详情页(#8)。

## 2. 后端需要补一个小接口——展开行的答案分组树,现有接口给不出来

issue #5 的 `GET .../knowledge-points` 已经能返回每个知识点"当前最匹配的那一条答案"(`resolved: {status, answer}`),但展开行要展示的是demo `kpAnswerTree()` 那种"默认/单维度/组合条件"分层的**全部**条件组合,不是"最匹配的一条"。现有接口(issue #4/#5)里没有一个能拿到"这个知识点所有条件组合各自的当前版本"的读接口。

**不能直接复用 `compute_live_groups()`(对抗式自校发现的 blocker)。** 这个函数专门为"解析出一个最终答案"服务,SQL 查询本身就带了 `Answer.revoked.is_(False)` 过滤——一条已经被整体撤回的版本链,压根不会出现在它的返回结果里,是"完全消失"而不是"标记成已撤回"。但 demo 的 `kpAnswerTree()` 明确把已撤回的组渲染成划线的叶子节点("已撤回，留痕保存"),PRD §4.4 展开行原文也是"知识点**全部答案**的分组树",不是"当前生效的分组树"。P0 阶段已经有真实场景会产生撤回链——`edit_answer` 改变 `coord` 时会自动把旧链整体撤回(issue #4)——所以这不是一个边缘情况,是任何"编辑过条件"的知识点都会遇到的正常路径。

新增 `compute_all_answer_groups(db, kb_id, kp_id, at)`(独立的新函数,不改 `compute_live_groups`,避免影响已经审过的两个既有调用方)：查询该知识点**全部**答案(不加 `revoked`/`effective_time` 过滤),按 `coord_hash` 分组,每组算出：

- `latest_answer`：按 `(effective_time, created_at, id)` 排序最新的一条(不管是否撤回、是否已生效)——对应"这条链最后说了什么"
- `revoked`：即 `latest_answer.revoked`(撤回是整链共享的状态,链内所有行的 `revoked` 值相同,取其一即可判断整条链)
- `live_answer`：`at` 时点、未撤回、`effective_time <= at` 的最新一条,没有则为 `null`——对应"这条链在 `at` 这一刻实际生效的版本"
- `version_count`：该链版本总数

区分 `revoked` 和 `live_answer is null` 两种情况(相比demo 原样照抄的一个改进,理由见 §4.2)：demo 的实现里"当前没有生效版本"统一显示成"已撤回",不区分"真的被撤回"和"这条链的所有版本都晚于回看时间、还没生效"——这是 demo 的一个不精确之处，不是 PRD 要求的行为，本设计选择更准确的表达，不刻意复刻这个不准确的地方。

`GET /knowledge-bases/{kb_id}/knowledge-points/{kp_id}/answer-groups?at=` 返回 `envelope([AnswerGroupOut])`,`AnswerGroupOut = {coord, revoked, version_count, latest_answer: AnswerOut, live_answer: AnswerOut | null}`——`latest_answer`/`live_answer` 复用现有的 `AnswerOut` 序列化(和 `resolve`/列表接口用同一个 `_to_answer_out()` helper,不发明新的序列化方式)。已删除的知识点同样返回空列表(和 `resolve` 接口用同一条"软删除后不出现在查询结果里"的规则)。分组结果按 `coord_hash` 排序,保证响应确定;组内/组间更细的展示顺序交给前端按 §4.2 的分层规则重新组织。

## 3. 前端数据获取架构

| 数据 | 来源 | 说明 |
|---|---|---|
| 当前知识库(名称/状态) | `useKnowledgeBases()`(issue #6 已有,复用) | 后端没有单条知识库详情接口(issue #2 设计时的决定),前端和 demo 一样,从全量列表里按 id 找 |
| 本知识库启用的维度 | 新 hook,`GET /knowledge-bases/{kb_id}/enabled-dimensions`(issue #3) | 条件选择器只能选这些维度(验收标准第一条) |
| 知识点列表(含每行 resolved 预览) | 新 hook,`GET /knowledge-bases/{kb_id}/knowledge-points?keyword=&at=&coord=&status=active`(issue #4/#5) | 关键字/条件筛选都走后端,不像 issue #6 的知识库列表那样client端过滤——知识点量级可能比知识库大得多,后端已经把这套筛选实现好了,没有理由在前端重新拉全量再筛 |
| 展开行的答案分组树 | 新 hook,§2 的新接口,只在某一行被展开时才发请求(`enabled: expanded`) | demo 里这是同步的本地计算,真实后端下变成一次按需请求,不是每行预先都拉 |

**这个 hook 的 query key 必须带 `at`,不能只用 `kpId`(对抗式自校发现)。** 如果 key 只是 `['answer-groups', kpId]`,用户展开一行之后再切换"回看某天"的时间,`enabled` 还是 `true`(行还是展开的),但 key 没变,TanStack Query 会继续把旧时间点缓存的结果当有效数据返回,不会重新请求——界面上看起来"时间穿梭对已展开的行没反应"。key 要写成 `['knowledge-points', kpId, 'answer-groups', at]`,时间一变,key 跟着变,自动触发重新请求。

## 4. 需要明确的工程细节

### 4.1 条件筛选器提交给后端的 `coord` 值,按 field_type 分别处理,不能全部当字符串或全部转数字

选择器的输入控件本身就是原生 `<input type="number">`/`<input type="date">`/`<select>`(布尔),值天然符合各自格式,不需要在前端重新做 `coord.py` 那套强校验(参照后端已经踩过的坑,原生输入控件已经把"输入不合法字符"这条路堵死了)。但**提交前必须做类型转换,而不是把 `.value` 原样塞进 JSON**：

- `boolean`：`<select>` 的 `.value` 永远是字符串 `"true"`/`"false"`,必须转成真正的 JS `true`/`false` 再放进 `coord` 对象——后端 `coord.py` 明确"布尔必须**恰好**是 JSON 布尔值,不接受字符串"(issue #4 设计文档 §3.5),字符串 `"true"` 会被拒绝。
- `number`：`<input type="number">` 的 `.value` 是字符串,但**不转成 JS `Number`,直接把字符串传给后端**——这不是偷懒,是故意的：issue #4 的 `coord.py` 专门把数字字符串走 `Decimal` 精确解析,比 JS `Number`(IEEE754 双精度)更不容易在大整数上丢精度；如果前端先转成 JS `Number` 再传,等于把这条已经修过的精度坑重新引入一次。
- `date`/`text`：原生 `.value` 本来就是字符串,原样传。

**原生输入控件"格式合法"不等于"后端一定接受"(对抗式自校发现的缺口)。** `<input type="number">` 会拦掉非数字字符,但拦不住 `"1e25"` 这种科学记数法或几十位的长数字——这些字符串在浏览器眼里"合法",但后端 `coord.py` 有专门的量级上限检查(超过 `2**64-1`,或者字符串本身长度/指数过大,防的是 DoS 和精度不可靠的输入,issue #4 §3.5),会返回 400。这类请求的报错走**列表查询本身的失败态**,不是筛选器弹窗内联报错——因为提交筛选条件只是更新本地 state,真正触发网络请求的是"知识点列表"这个 query,失败时 `error instanceof ApiError` 就是后端返回的具体 `msg`(比如"维度 priority 取值类型错误,应为数值"),直接展示这条消息而不是写死一个通用文案,用户才知道是哪个筛选条件的问题。

### 4.2 展开行的答案树按 `coord` 里 key 的个数分层,不是按内容分类

对照 demo 的 `kpAnswerTree()`：拿到 `answer-groups` 接口返回的分组列表后,按每组 `coord` 的 key 数量分三层——0 个 key 是"默认答案"分区,1 个 key 按该维度分组(同一维度不同取值归在一起),≥2 个 key 归到"组合条件"分区。分组的**标题标签用维度当前的 `label`**,如果 `coord` 里某个 key 已经不在"本知识库启用维度"列表里(历史上用过、后来被停用/取消启用),标题退回显示原始 key——不是错误,是正常的历史数据展示(§6 规则 #7)。

### 4.3 知识库列表页现在要把名称改成真链接,操作列加回"进入"

issue #6 设计文档 §4.3 明确说了这是故意留到本 issue 才做的：当时知识点列表页(本 issue)还不存在,现在存在了,把 `KnowledgeBaseListPage` 里纯文本的名称改成 `<Link to="/knowledge-bases/{id}/knowledge-points">`,操作列对 active 的知识库补回demo 原有的"进入"文字链接,两者指向同一个地方。

### 4.4 统计卡：两个真实、两个占位,不是四个都假

issue #7 AC 允许统计卡"可先接口占位"，但不代表四张卡都要摆样子——`知识主题`(当前生效知识点数)和`启用维度`(本知识库启用的维度数)这两个数字不用等 issue #12 的统计接口就能给真实数字(具体怎么拿,见 §4.5)。`在用答案`(全知识库未撤回答案总数)和`今日变更`(今天新增/撤回的答案条数)确实没有对应的聚合接口(那是 issue #12 的范围),这两张卡显示"—"占位,foot 文案改成"统计接口开发中"说明原因,不是留空不解释。

### 4.5 "知识主题"统计卡直接读 `KnowledgeBase.active_knowledge_point_count`,不用再发一次请求(对抗式自校纠正)

最初设计想额外发一次"不带任何筛选参数的知识点列表请求"来拿这个数字,是多余的——issue #2 的知识库 API(`KnowledgeBaseOut.active_knowledge_point_count`,后端 `_get_active_point_count()`)本来就是"该知识库当前生效知识点数"这个精确定义,而 §3 已经在用 `useKnowledgeBases()` 拿当前知识库的名称/状态,同一份响应里已经带着这个数字,直接读出来用就是。不能用页面主体列表(会随搜索/筛选变化)的 `length` 代替——那个数字会随搜索结果抖动,语义对不上("这个知识库总共有多少个知识点" vs "当前搜索命中几个")——但也不需要为了拿一个正确的数字单独发请求,数据已经在手上了。

## 5. 组件拆解

- `KnowledgePointListPage`(路由 `/knowledge-bases/:kbId/knowledge-points`)
  - 找不到知识库/知识库已停用 → 引导返回知识库列表(对照demo `renderNoKb()`)
  - `StatGrid`(4 张统计卡,2 真 2 占位)
  - `ConditionFilterCard`：关键字输入 + `ConditionPicker`(时间穿梭 seg + 已选条件 chip + "+加一个条件"下拉,两级：选维度→填值) + 查询/重置按钮
  - `KnowledgePointRow`(可展开):主行(标题链接到详情页——先占位到 issue #8,标题暂不做链接;答案数+用到的维度;查看详情/删除操作) + 预览行(`ansPreview` 等价) + 展开后的 `AnswerGroupTree`(只读)
  - `Pager`(复用 issue #6 已有组件)
  - `AddKnowledgePointModal`(标题+可选默认答案内容+生效时间)
  - `DeleteKnowledgePointModal`(危险操作三要素：红色入口+二次确认+风险说明,必填删除原因)

### 5.0 两处 demo 细节先不做,理由是同一个：只有展开才拉答案分组数据

demo 的知识点行预览里还有两处细节本设计先跳过：(1) "另有 N 条带条件的说法,展开看"这句提示,需要知道该知识点总共有多少个条件组合,而这个数字只有拉取 `answer-groups` 才能拿到；(2) 主行的"维度：租户、优先级"这行元信息,同样需要知道该知识点用过哪些维度,来源也是全量答案数据。这两个都要求"没展开也要提前知道分组信息",和 §3 定的"分组树只在展开时才请求"直接冲突——为了两句提示文案去把"按需加载"改成"预先加载",不值得。跳过,不影响 AC 列出的四条验收标准。

### 5.1 知识点标题暂不做链接

issue #8(知识点详情页)还没交付,和知识库列表页当时的处理方式(issue #6 §4.3)一样：标题先是纯文本,"查看详情"操作先不渲染(demo 有这个链接,指向 `detail.html`,本 issue 还没有对应页面)。等 #8 交付后再补上,不提前放一个指向空白的链接。

## 6. 测试计划

**后端(新增 `answer-groups` 接口)**：
- 一条未撤回的链 → `revoked=false`,`live_answer` 有值
- 一条已被迁移(`edit_answer` 改变 coord)整体撤回的链 → `revoked=true`,`live_answer=null`,`latest_answer` 仍能拿到撤回前最后一条内容
- 回看时间早于某条链的所有版本(尚未生效,但没被撤回) → `revoked=false`,`live_answer=null`——和"已撤回"的响应区分得开,不会被前端误判成同一种状态
- 已删除的知识点 → 空列表
- 找不到的知识点/知识库 → 404

**前端**：
- 条件选择器只列出本知识库启用的维度(mock 一个未启用的维度定义,确认不出现在下拉里)
- 提交布尔类型条件时,请求里的 `coord` 值是 JSON `true`/`false` 不是字符串
- 提交数字类型条件时,请求里的 `coord` 值是字符串(不做 JS Number 转换)
- 筛选条件导致后端 400(如超大数字)时,列表的失败态展示后端返回的具体 `msg`,不是写死的通用文案
- 筛选结果的四种命中标签(精确命中/按权重回退/默认/无默认取最新)渲染正确
- 展开行:请求 `answer-groups`,按 0/1/≥2 个 key 分三层展示;`revoked=true` 的组渲染成划线"已撤回，留痕保存",`live_answer=null` 但未撤回的组渲染成"尚未生效"(不是"已撤回")
- 折叠的行不发 `answer-groups` 请求(lazy,不预取);已展开的行切换"回看某天"的时间后会重新请求(query key 带 `at`)
- 新增知识点(含/不含默认答案内容)、删除知识点(必填原因)成功后列表刷新
- 统计卡:知识主题/启用维度直接读 `useKnowledgeBases()` 已有数据里的对应字段,不发额外请求;在用答案/今日变更显示占位文案
- 知识库列表页:active 知识库名称是链接,点击后进入本页面；deprecated 知识库名称仍是纯文本(和之前一样,没有对应可进入的状态)
