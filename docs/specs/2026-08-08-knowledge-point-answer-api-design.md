# 知识点 CRUD + 答案写入/编辑 API 设计文档（issue #4）

## 1. 范围

实现 `docs/PRD.md` §4.4（知识点增删改查）+ §4.5 写入/编辑部分（答案管理）。

包含：知识点新增（可选带默认答案）/列表/详情/改标题/软删除/恢复；答案写一条/编辑（同条件追加版本 或 条件变更触发整组迁移）。

不含（见 issue #4 Out of Scope，留给别的 issue）：答案"设为默认"/"撤回"独立接口（#10）；按维度条件查询/解析（#5，本 issue 只负责写入路径，不做任何"当前生效版本是什么"的解析）；批量导入（#11）。

## 2. 接口设计

知识点嵌在知识库下,答案嵌在知识点下,路径与 issue #2/#3 已有的 `/knowledge-bases/{kb_id}/...` 风格一致：

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/knowledge-bases/{kb_id}/knowledge-points` | 新增知识点（可选内嵌默认答案） |
| GET | `/knowledge-bases/{kb_id}/knowledge-points` | 列表，`?status=active\|deleted`，默认 `active` |
| GET | `/knowledge-bases/{kb_id}/knowledge-points/{kp_id}` | 详情（头部信息，见 §3.2） |
| PATCH | `/knowledge-bases/{kb_id}/knowledge-points/{kp_id}` | 改标题 |
| POST | `/knowledge-bases/{kb_id}/knowledge-points/{kp_id}/delete` | 软删除，body 需 `delete_reason` |
| POST | `/knowledge-bases/{kb_id}/knowledge-points/{kp_id}/restore` | 恢复 |
| POST | `/knowledge-bases/{kb_id}/knowledge-points/{kp_id}/answers` | 写一条答案 |
| POST | `/knowledge-bases/{kb_id}/knowledge-points/{kp_id}/answers/{answer_id}/edit` | 编辑答案（同条件追加 / 条件变更触发迁移） |

删除用 `POST .../delete` 而不是 HTTP `DELETE`：软删除需要强制携带 `delete_reason`，很多 HTTP 客户端/网关对 `DELETE` 带 body 支持不一致，沿用 issue #2 里 `activate`/`deactivate` 这种"动作型" POST 端点的既有风格。编辑答案同理用 `POST .../edit`,不用 `PATCH`——编辑在语义上是"追加一个新版本"而不是"就地改字段"（版本链只增不改,§6 规则 #1）,`PATCH` 暗示的就地更新语义不准确。

## 3. 需要明确的工程细节

### 3.1 知识库停用状态是否影响其知识点/答案的读写

§4.1 对"停用"的描述是"知识库列表不再展示、无法进入其知识点列表"——这读起来像是**前端导航层**的行为("入口没了"),而不是一条 API 级别的权限规则；同一节又明确说"知识点与答案数据不受影响,重新启用后可继续访问",说明底层数据本来就应该在停用期间保持完全可用。**本设计选择：后端 API 不基于知识库的 active/deprecated 状态做任何读写限制**——本知识库的知识点/答案增删改查照常工作,不因为 KB 处于 deprecated 就报错。这与 issue #3 的判断一致(该 issue 里也认为知识库自身状态不应该拦掉它的子资源查询),用测试锁定这个选择,方便以后 PRD 澄清后对照修改。

### 3.2 "详情"接口的范围——只做头部信息,不做当前答案筛选

§4.7 把知识点详情页拆成头部(P0)/当前答案(P0,但依赖 §4.6 的解析引擎)/版本历史(P1)/变更留痕(P1)/立体全景(P2)。"当前答案"分区需要按条件筛选出命中的答案,这正是 issue #5(按维度条件查询)要交付的解析引擎,本 issue 明确排除在外。因此本 issue 的详情接口**只返回头部信息**：`id`、`knowledge_base_id`、`title`、`status`、`operator`、`created_at`、`updated_at`、`deleted_at`、`delete_reason`、`active_answer_count`(未撤回答案总数,原始计数,不做任何时间点/条件过滤)。第三方如果现在就需要"当前生效答案是什么",要等 issue #5。

### 3.3 列表接口的默认范围——与 issue #2 不同,这次 PRD 有明确说法

issue #2 的知识库列表在"返回全部还是只返回启用中的"上没有 PRD 定论,需要自己判断；这里 §4.4"查看-列表"行原文是"展示知识库**当前生效（未删除）**的知识点"——**已经是明确结论**,不是要重新判断的开放问题。所以列表接口默认（不传 `status`）只返回 `active`；额外加一个可选 `?status=active|deleted` 参数,让"恢复"功能在不知道具体 ID 的情况下也能先浏览回收站里有哪些知识点。

### 3.4 标题唯一性校验——直接复用 issue #2 的既有模式

§4.4 校验规则"标题与同知识库内现有知识点(含已删除)重复",校验范围/时机/并发兜底与 issue #2 的知识库名称校验结构完全一致(应用层预检 + `uq_kp_kb_title` 唯一索引 + `IntegrityError` 1062 兜底转换成清晰错误,改名时排除自身)。错误信息同样用清晰中文而不是 issue 里给的例子 slug `knowledge_point_title_duplicated`,和 issue #2 对 `knowledge_base_name_duplicated` 的处理保持一致的风格。

### 3.5 coord 归一化与哈希算法（issue #1 遗留决定,本 issue 落地）

issue #1 的设计文档定了 `coord_hash` 是固定 `CHAR(64)` 的 SHA-256 十六进制摘要,但把"实际怎么归一化"留给了 #4/#5。规则：

1. 对 `coord` 里每一个 `{dimension_key: raw_value}`,按该 key 当前的 `field_type` 强校验并归一化：
   - `text`：必须是字符串,去首尾空格
   - `number`：**先显式拒绝 `bool`**(Python `bool` 是 `int` 子类,`float(True) == 1.0` 会静默把布尔值误判成数值,必须在做任何数值转换之前单独判断并拒绝)。取整数值(无论输入是 `int`、整数形式的 `float`、还是纯数字字符串)归一化成 Python `int`（任意精度,不损失大整数精度——直接 `float()` 转换在超过 2^53 时会有精度损失,两个不同的大整数取值可能被 `float` 精度损失成同一个数,从而让本该独立的两组条件被误判成同一条链,或者让"条件是否变化"的判断出错）；有小数部分的才归一化成 `float`。`1`/`1.0`/`"1"` 都归一化成整数 `1`,落到同一个 hash。**字符串输入用 `Decimal` 解析,不是"先 `int()` 试探再 `float()` 兜底"**——`int("9007199254740993.0")` 会因为字符串里有小数点直接失败,退到 `float()` 兜底就会精度丢失成 `9007199254740992`；`Decimal` 精确解析字符串数字后再判断"是不是整数值",能在归一化前就把原始精度保住(Codex 外门审查发现)。同时对数值大小设了一个上限——`2**64 - 1`(MySQL `BIGINT UNSIGNED` 的上界)：实测发现超过这个量级,MySQL 的 JSON 类型要么直接报错("Number too big to be stored in double"),要么在大约 1e308 量级之后悄悄退化成精度有损的 double 存储,两种情况都必须在写入前拦掉,不能让请求带着一个"看起来能被 `Decimal` 精确解析、但 MySQL 存不下"的数值走到 DB 层报一个不可控的原始异常。这个上限检查本身也踩了一个坑：`math.isfinite()` 对一个远超 float 范围的 Python 大整数(比如 `10**400`)会直接抛 `OverflowError`,不能对 `int` 分支复用它,必须先用普通整数比较判断量级,再决定要不要走浮点专用的 `math.isfinite()` 检查。
   - `date`：必须是合法的 ISO 日期字符串(`date.fromisoformat`),归一化成 `YYYY-MM-DD` 字符串
   - `boolean`：必须**恰好**是 JSON 布尔值 `true`/`false`(不接受字符串 `"true"`),按 PRD"布尔必须是 true/false"从严解释,不做宽松字符串推断避免"1"/"yes"之类隐式判断带来的歧义
   - 归一化失败 → `BusinessError`,提示具体是哪个维度取值格式不对
2. `coord_hash = sha256(json.dumps(normalized_coord, sort_keys=True, separators=(",", ":"))).hexdigest()`——`sort_keys` 保证 key 顺序不影响结果,归一化步骤保证同一逻辑值的不同书写方式落到同一个 hash。
3. 这两步（归一化 + 求 hash）放进独立的 `kb_backend/coord.py` 模块,不写在路由文件里——issue #5 的解析引擎需要用同一份实现比较查询条件与已有答案组的 coord,复用同一个模块是 §4.6.1"两个接口共享同一套解析引擎"要求的一部分基础设施。
4. **维度启用校验只对"本次请求显式携带的 coord"生效,绝不对"编辑时沿用的旧 coord"重新校验。** §6 规则 #7"维度停用不影响历史"：如果编辑答案时省略了 `coord`(沿用旧链条件不变),不应该因为其中某个维度后来被停用了就让这次追加版本失败——旧条件本来就允许继续存在,只是不能再被选用于新的条件组合。因此实现上：`coord` 字段缺省时,直接复用目标答案的 `coord`/`coord_hash`,完全跳过归一化和维度启用校验；只有显式提供了 `coord`(不管新值和旧值是否相同)才走归一化 + 维度启用校验的完整流程。

### 3.6 写答案时的维度启用校验——复用 issue #3 的 INNER JOIN 查询

`coord` 里每个 key 必须在本知识库的启用维度集合里(全局 active + 该 KB 的 join 表记录都满足)——这正是 issue #3 `list_enabled_dimensions` 内部用的同一个 INNER JOIN 查询,直接复用其逻辑(不重新发明一遍)。命中不到 → `BusinessError`("维度 {key} 未在本知识库启用")。

### 3.7 编辑答案的迁移语义——用独立的 `migration_reason` 字段,不复用 `note`

§6 规则 #2："编辑答案时如果改变了其适用条件,原条件组合的整条版本链会被整体撤回（记录迁移原因）"。这里容易踩的坑：`answer.revoke_reason` 列是 `VARCHAR(500)`,而 `answer.note`(变更说明)按 issue #4 验收标准是**不设长度上限**的——如果直接把 `note` 塞进 `revoke_reason`,超过 500 字就会在写迁移时炸掉一个本该正常处理的请求。**修正为两个独立字段**：
- `note`(变更说明,可选,不限长度)：写入新版本自己的 `note` 列,不管是否触发迁移
- `migration_reason`(迁移原因,`max_length=500` 与 `revoke_reason` 列宽对齐)：只有当 `coord` 与原链不同(触发迁移)时才是必填,写入被撤回旧链每一行的 `revoke_reason`；不迁移时这个字段不会被用到,传了也忽略

编辑请求体里 `coord` 用"是否携带该字段"（而不是"值是否为空"）区分"不改条件"和"显式改成默认条件({})"，和 issue #2 处理 `description` 清空的方式(`model_fields_set`)是同一套模式。

编辑目标必须是**未被撤回**的答案(`revoked=False`)才允许编辑；对已撤回链的编辑请求直接拒绝——撤回后的版本链在 P0 阶段没有"复活"操作,允许对着已撤回的答案继续追加版本会做出一条逻辑上不存在的"半撤回"状态。

**编辑是通过"链的身份"而不是"链的最新版本"来定位的。** 请求路径里的 `answer_id` 只是用来**确定要编辑哪一条版本链**(取该行的 `coord_hash` 作为链的身份标识),不要求这个 `answer_id` 必须是该链当前最新的一行——哪怕第三方拿着版本历史里一条很早的记录 ID 发起编辑(只要没被撤回),效果和拿最新那条 ID 编辑完全一样：不改条件就在链尾追加一条新版本,改条件就撤回**这条链的全部行**(不是"从这一行往后"部分撤回)。这是版本链"只增不改、撤回是整组操作"(§6 规则 #1、#4)的直接推论,不是需要额外实现的特殊分支。

**创建知识点与其默认答案是一个数据库事务。** 校验通过后先 `db.add(kp)` + `db.flush()`(拿到 `kp.id` 但不提交),再用这个 `id` 构建默认答案行、`db.add(answer)`,最后一次 `db.commit()`。不能先 `commit()` 知识点再单独 `commit()` 答案——中途失败会留下一个"看起来新建成功但没有内容"的知识点。

### 3.8 已软删除的知识点：读可以,写答案不行；删除/恢复是否幂等

对抗式自校指出这两个场景设计文档最初完全没提,是真实的空白,补上：

- **已删除(`status=deleted`)的知识点不能写新答案、不能编辑答案。** 与 §3.1(知识库停用不影响其子资源)不同,这里选择更严格的默认——回收站里的知识点语义上是"暂时不存在",不应该在暂存期间继续积累新内容;`POST .../answers` 和 `.../edit` 在目标知识点是 `deleted` 状态时返回 `BusinessError`("知识点已删除,无法写入答案")。详情/列表读取不受影响(照常可读,含 `?status=deleted` 浏览回收站)。
- **删除/恢复本身是幂等的,但不覆盖已有的删除留痕。** 对已经是 `deleted` 的知识点再次调用删除接口(比如第三方网络重试),不报错、直接返回当前状态,但**不用这次请求带的新 `delete_reason` 覆盖第一次删除时记录的原因**——留痕要保留"最早一次真实发生删除操作"的原因,不能被一次身份不明的重试悄悄改写。恢复同理：对已经是 `active` 的知识点再次调用恢复,幂等成功,不报错。

### 3.9 操作人/来源固定值

严格遵守 §6 规则 #10：`operator` 固定 `"admin"`；"写一条答案"的 `source` 固定 `"人工填报"`；"编辑答案"产生的新行(无论是同链追加还是迁移后新链的第一条) `source` 固定 `"人工编辑"`。

## 4. 文件改动

- `backend/src/kb_backend/coord.py`（新增）——`normalize_coord()` + `compute_coord_hash()`,纯函数,不依赖 DB session,方便单独单测
- `backend/src/kb_backend/schemas/knowledge_point.py`（新增）——`KnowledgePointCreate`/`KnowledgePointUpdate`/`KnowledgePointOut`/`AnswerCreate`/`AnswerEdit`/`AnswerOut`
- `backend/src/kb_backend/routers/knowledge_point.py`（新增）——上表全部端点
- `backend/src/kb_backend/main.py`——挂载新路由
- `backend/tests/test_coord.py`（新增）——归一化/哈希纯函数单测
- `backend/tests/test_api_knowledge_point.py`（新增）——知识点 CRUD
- `backend/tests/test_api_answer.py`（新增）——答案写入/编辑（含迁移场景）

## 5. 测试计划

**coord 模块（纯函数,不需要真实 DB）**：
- number/date/boolean/text 各自的合法输入归一化正确；各自的非法输入报错
- 不同书写方式的等价值(`1`/`1.0`/`"1"`；不同 key 顺序)哈希结果相同
- 不等价的值哈希结果不同

**知识点 CRUD**：
- 新增（带/不带默认答案）；带默认答案时确认答案表同时插入一行、coord={}
- 标题重复（含已删除的）→ 拒绝；跨知识库允许重复
- 列表默认只含 active；`?status=deleted` 能看到软删除的
- 详情返回头部字段,`active_answer_count` 只统计未撤回答案
- 改标题；标题重复校验同 issue #2 模式（含"只改别的不改标题不会误判自己重复"）
- 软删除需要 `delete_reason`；软删除后列表默认不再出现；恢复后再次出现
- 重复删除幂等成功,且不覆盖第一次的 `delete_reason`；重复恢复幂等成功
- 已删除的知识点仍可读(详情、`?status=deleted` 列表)
- 找不到的 `kp_id` → 404

**答案写入/编辑**：
- 写答案：合法 coord 成功；coord 含未启用维度 → 拒绝；coord 取值类型错误（数值/日期/布尔）→ 拒绝
- number 维度：布尔值(`true`/`false`)必须被拒绝,不能被 `float()` 静默转换成 1.0/0.0
- number 维度：超过 2^53 的大整数(如 `9007199254740993`)必须精确保留,不能因为转成 `float` 精度丢失,且与相邻的另一个大整数值哈希不同
- 已删除的知识点无法写入/编辑答案 → 拒绝
- 同条件组合、`effective_time` 相同的两条答案都能写入,`created_at` 更新的那条在数据库层面确实更新(为 issue #5 的解析引擎做数据前提保证,不在本 issue 做解析)
- 编辑：不改 coord → 追加同链新版本,旧版本保留不变；且不会因为链里某个维度后来被停用而失败(规则 #7)
- 编辑：改 coord → 旧链全部行被标记撤回(`revoked=True`+`revoke_reason`=迁移原因)、新链首个版本插入
- 编辑：通过版本链中一条较早(非最新)的 `answer_id` 发起编辑,效果与通过最新版本编辑完全一致
- 编辑不改 coord 时不要求 `migration_reason`；改 coord 但不填 `migration_reason` → 拒绝
- 对已撤回的答案发起编辑 → 拒绝
- `content` 允许超长文本（无长度上限）成功写入
