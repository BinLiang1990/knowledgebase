# 维度定义管理写接口 + 知识库启用维度勾选写接口（issue #9）设计文档

## 1. 范围

issue #9 明确要求（P1，PRD §4.2/§4.3）：
- 维度定义：新增（label/field_type/weight/默认取值提示）、修改（label/weight/默认取值提示，`field_type` 不可改）、停用/启用
- 知识库启用维度：勾选/取消勾选写接口

依赖 issue #1（DB schema）——`dimension_definition`/`knowledge_base_enabled_dimension` 两张表在 issue #1 就已经建好全部需要的列（`key`/`label`/`field_type`/`weight`/`default_value`/`status`），本 issue **不需要新的 migration**，纯粹是加路由 + schema + 业务校验。

不做：只读查询接口（issue #3 已完成，见 §2 关于它的一处补充）。

## 2. 范围内的一个必要补充：内部管理列表接口

PRD §4.2"查看"这一行原文（🔴 P0）：

> 维度定义列表，含"全局共有多少条答案在用"的统计；**内部管理列表**（维度管理页）展示全部维度（含已停用），供管理员重新启用；**对外的维度查询接口**只返回 `status=active` 的维度，已停用的维度不返回

issue #3 交付的 `GET /dimensions` 只实现了后半句（对外查询接口：`status=active`、字段仅 `key/label/field_type/weight`）。前半句"内部管理列表"（全部维度 + 停用的也要看到 + 用量统计）没有对应接口——这是 P0 阶段的一个遗漏，不是本 issue 的新增需求，但本 issue 的写接口（新增/修改/停用/启用）离不开一个能看到"全部维度＋当前状态"的列表接口，管理页也需要它来渲染。所以在这里一并补上，而不是留到 issue #13（前端维度管理页）才发现"没有能读全量维度的接口"。

**新增 `GET /admin/dimensions`**（注意路径不是 `/dimensions/admin`，理由见 §4.6），与 `GET /dimensions`（对外，issue #3，原样不改）并列，是两个独立端点：

| | `GET /dimensions` | `GET /admin/dimensions`（新增） |
|---|---|---|
| 消费者 | 第三方 / 查询侧 | 内部维度管理页 |
| 返回范围 | 仅 `status=active` | 全部（`active`+`deprecated`） |
| 返回字段 | `key/label/field_type/weight` | 以上 + `default_value/status/answer_count` |

两个端点分开而不是给 `/dimensions` 加个 `?include_deprecated=1` 之类的参数，是因为 `/dimensions` 是"对外接口"，PRD 明确写了它的契约（不返回停用维度）——给同一个路径叠加一个能改变默认返回范围的参数，等于给一个已经对外承诺过行为的接口留了一个"参数传错就破坏契约"的口子，不如直接分成两个用途不同、路径不同的端点清楚。

`answer_count`（"全局共有多少条答案在用"）的算法：统计所有**未撤回**答案里，`coord` 出现过这个 key 的条数。跟 demo 的 `dimensionUsageCount(key)` 定义一致。实现上**不**对每个维度单独查一次数据库（避免 N+1），而是一次性把全部未撤回答案的 `coord` 拉到 Python 里按 key 计数一遍——用一次内存遍历换掉给每个维度单独拼 JSON path 查询的复杂度（见 §4.4 的理由）。这是内部管理页用的低频接口，v1 阶段不为大规模答案量做专门优化，跟 §4.6.2 "性能与规模"对查询接口的态度一致；如果后续答案量明显变大，再评估要不要在 `answer` 表上加一个"每个 coord key 用量"的物化统计。

## 3. 端点设计

### 3.1 维度定义

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/dimensions` | 新增。body：`label`/`field_type`/`weight`(可选，默认 50)/`default_value`(可选) |
| `PATCH` | `/dimensions/{key}` | 修改。body 只接受 `label`/`weight`/`default_value`——schema 里根本不定义 `field_type` 字段，从结构上做到"不可改"，不是靠运行时校验挡 |
| `POST` | `/dimensions/{key}/activate` | 启用，镜像知识库的 activate |
| `POST` | `/dimensions/{key}/deactivate` | 停用，镜像知识库的 deactivate |
| `GET` | `/admin/dimensions` | 见 §2 |

### 3.2 知识库启用维度

| 方法 | 路径 | 说明 |
|---|---|---|
| `PUT` | `/knowledge-bases/{kb_id}/enabled-dimensions` | 整体替换本知识库的启用维度集合。body：`{"dimension_keys": ["key1", "key2", ...]}` |

用整体替换（`PUT`，覆盖式）而不是"启用一个 / 取消一个"两个单独端点，是照抄 demo 真实的交互模型：`kb-settings.html` 是一屏勾选框 + 一个"保存"按钮（`saveEnabledDims()` 直接把当前勾选的完整 key 列表整个传给 `setKbEnabledDims`，见 `frontend-mock/assets/app.js:107-113`），不是"每点一下勾选框就发一次请求"。issue #13（前端维度管理页）大概率会照这个交互模式做，整体替换的接口正好匹配，不需要前端自己在多个"单选增删"请求之间做整体保存的事务感。

## 4. 关键设计决策

### 4.1 `key := label`，且只在创建时成立

PRD 原文："新增 | 🟡 P1 | 填写 label(同时作为 key)/field_type/weight/默认取值提示"——创建时管理员只填一个"名字"，这个名字**原样**同时成为 `key`（主键、永久不变、写进 `answer.coord` 的 JSON key）和 `label`（展示名，之后可以改）。不做任何转写/转拼音/去重后缀之类的归一化：管理员输入什么，`key` 就是什么。

这意味着：
- 创建时 `label` 长度上限是 **100**，不是 schema 表面看起来该有的 255——因为它要同时塞进 `key: String(100)`。这是本设计里唯一一处"创建"和"修改"用不同校验规则的地方：`DimensionCreate.label` 用 `max_length=100`，`DimensionUpdate.label` 用 `max_length=255`（跟列宽一致）；创建之后单独改 `label` 时可以比原来的 `key` 更长，因为改的只是 `label` 列，`key` 列纹丝不动。
- 创建时 key 冲突（两个维度重名）走 `dimension_definition.key` 的主键唯一约束，捕获 `IntegrityError` 转成友好错误——跟 `_ensure_name_available`/`_ensure_title_available` 的既有模式一致，只是这里没法用"先 SELECT 判断是否存在"的查重函数，因为并发场景下主键约束仍然是唯一可靠的把关点（先查后插在两个并发请求之间仍有竞态），直接靠 `IntegrityError` 兜底更稳。
- **"重复"是按数据库主键列的排序规则判断的，不是按字节完全相同**：`dimension_definition.key` 用的是 `utf8mb4_0900_ai_ci`（issue #1 迁移文件里的 `CHARSET_KW`，跟 `knowledge_base.name` 同一个约定，`routers/knowledge_base.py` 里已经有类似说明），大小写、重音不敏感——创建一个 `key="Region"` 之后再创建 `key="region"` 会被判定为重复，拒绝。这不是 bug，是复用已经在 `knowledge_base.name` 上确认过的既有约定（对抗式审查确认），但对本 issue 是新出现的行为，需要在测试里显式钉住（见 §6），不能只靠"跟 KB name 一样"这句话心里默认它对，避免以后有人真的拿大小写不同的两个维度名去测，发现"重复"了却不知道为什么。

### 4.2 `weight` 的校验在 Pydantic 层重复一次 DB 的 CHECK 约束

`dimension_definition` 表已经有 `CheckConstraint("weight BETWEEN 1 AND 100")`（issue #1）。`DimensionCreate`/`DimensionUpdate` 的 `weight` 字段同样声明 `ge=1, le=100`——不是多余，是为了让非法输入在应用层就返回一个能读的业务错误（"权重必须在 1-100 之间"），而不是让请求一路走到 DB 层，捕一个 `IntegrityError`/`CheckViolation` 再去猜是不是这个约束触发的（跟 KB name/KP title 的重复校验不一样：那两个错误只可能是"重复"这一种原因，直接捕获转译很干净；`weight` 的 CHECK 约束失败原因单一但捕获+判断成本比 Pydantic 里加两个参数更高，没必要绕这一圈）。

### 4.3 启用维度时拒绝已停用的维度

`PUT .../enabled-dimensions` 的 `dimension_keys` 里如果出现一个 `status=deprecated` 的 key，直接 400 拒绝（"维度「X」已停用，无法启用"），而不是静默接受。

理由：即使接受了也不会有实际影响——`get_enabled_dimension_types()`（issue #4/#5 就已经这么写）本来就是 INNER JOIN 加 `status=active` 过滤，一个已停用的维度即使出现在 `knowledge_base_enabled_dimension` 表里也永远不会被写答案/查询用到。但"接受一个看起来成功、实际什么都不会发生的请求"比直接拒绝更让人困惑——管理页给出的勾选框本来就只应该展示 active 的维度（demo 的 `getActiveDimensions()` 已经这么做），后端在这里加一道拒绝，是防止"前端没做好过滤"或"两个管理员并发操作、一个刚停用了某维度"这种边缘情况下静默出现名不副实的启用记录。

不存在的 key 同理拒绝（404 语义，用 400 + 说明性文案："维度「X」不存在"，不单独为它开一个 404——因为这是一个批量请求里某一项无效，跟"整个资源找不到"的 404 语义不完全对应）。

**`dimension_keys` 里的重复项直接去重，不当错误处理**：请求体里同一个 key 出现两次（前端 checkbox 逻辑写错、或者用户操作触发了重复提交）在语义上等价于出现一次——去重成 `set()` 之后再校验/落库，而不是让它在批量插入时撞上 `(knowledge_base_id, dimension_key)` 的联合主键约束报错。这是一个明确的行为决定，不是"测试恰好这么写就照着实现"：如果不去重，天真的批量插入实现会在同一个事务里对同一个联合主键插两次，直接触发 `IntegrityError`，把一个本该成功的"稍微冗余"的请求误判成失败。

**delete+insert 必须在同一个事务里提交**：整体替换的实现是"删掉这个知识库当前全部启用记录，再按提交的（去重后的）列表插入新记录"，这两步必须包在同一个 `session`/`commit` 里（跟 `update_knowledge_base` 全部改动最后统一 `db.commit()` 一次的既有模式一致）。如果分两次提交，中间失败会让这个知识库的启用维度表被清空却没重新插入——之后所有写答案/查询请求都会看到"这个知识库没有启用任何维度"，是一个静默、影响范围扩大到所有后续请求的坏状态，比操作直接报错失败更糟。

### 4.4 `answer_count` 统计不用动态拼 JSON path

MySQL 的 `JSON_CONTAINS_PATH(coord, 'one', '$.<key>')` 需要把 `key` 拼进 JSON path 表达式里，而 `key` 是管理员自由输入的任意文本（中文、可能包含 `.`/`"`/`$`/`[` 等在 JSON path 语法里有特殊含义的字符）。直接字符串拼接构造 path 表达式，轻则维度名带个点号就查错，重则构造出一个语义完全不对的 path。参数化 JSON path 在 MySQL 8 里可以用 `JSON_CONTAINS_PATH(coord, 'one', JSON_UNQUOTE(?))` 之类的写法绕开转义问题，但既然本来就要在 Python 里遍历、按 key 计数（§2 已经决定的做法），干脆不用 JSON path 表达式，直接拿到 dict 之后用 Python 的 `in`/字典计数，从根上避开这类转义/注入类问题。

### 4.5 已停用维度/知识库取消启用维度，不触碰任何历史答案数据

这是 issue 的三条验收标准里的两条（`field_type` 不可改单独在 §4.1 说了）。实现上天然满足，不需要额外代码：
- 维度停用/启用只 `UPDATE dimension_definition SET status=...`，从不触碰 `answer` 表。
- 知识库取消启用维度只 `DELETE FROM knowledge_base_enabled_dimension WHERE knowledge_base_id=... AND dimension_key IN (...)`（`PUT` 的整体替换语义决定要删掉哪些行），同样不触碰 `answer` 表。

写集成测试直接断言这一点（写一条带该维度条件的答案 → 停用维度/取消启用 → 答案原样可读、`coord` 值不变），把这两条验收标准锁死，而不是只靠"代码没写就等于没改"的推理。

### 4.6 管理列表接口不放在 `/dimensions/admin`，放在 `/admin/dimensions`

§4.1 定下了"`key` 是管理员随便打的自由文本，不做任何归一化"——这意味着完全可能有人创建一个 `label`（也就是 `key`）叫"admin"的维度。如果管理列表接口是 `GET /dimensions/admin`，它和"某个 key 恰好是 admin"这件事就共享了 `/dimensions/{key}` 这个路径段的命名空间；今天没有 `GET /dimensions/{key}` 这个单查端点，所以现在不冲突，但 issue #13（前端维度管理页详情/编辑）大概率会需要一个按 key 查单个维度的接口，一旦加上，`/dimensions/admin` 到底命中"管理列表"还是"key=admin 的维度详情"，就完全取决于 FastAPI 路由注册的顺序——这是那种平时测不出来、有人真创建了一个叫"admin"的维度才会炸的 bug。改成 `/admin/dimensions`，管理列表和"按 key 查单个维度"处在完全不同的路径前缀下，未来加什么单查接口都不会跟它产生歧义。

## 5. 组件结构

```
backend/src/kb_backend/schemas/dimension.py   新增 DimensionCreate/DimensionUpdate/DimensionAdminOut；
                                               新增 EnabledDimensionsUpdate（PUT body: dimension_keys）
backend/src/kb_backend/routers/dimension.py   新增 create/update/activate/deactivate/admin-list
backend/src/kb_backend/routers/knowledge_base.py  新增 PUT .../enabled-dimensions
backend/tests/test_api_dimension_write.py     新增，覆盖本 issue 的全部写路径
backend/tests/test_api_dimension.py           已有的只读测试不变
```

## 6. 测试计划

- 创建维度：成功、`label` 同时成为 `key`、重复 `key` 拒绝（含大小写/重音不同但按 collation 判重复的情况，见 §4.1）、`label` 超过 100 字符拒绝、`weight` 超出 1-100 拒绝、`weight`/`default_value` 省略时的默认值。
- 修改维度：`label`/`weight`/`default_value` 可改；请求体不接受 `field_type` 字段（发了也被忽略/校验拒绝，视 Pydantic 默认行为——多余字段默认忽略，需要显式测试确认改不了）；改 `label` 后 `key` 不变；不存在的 key 返回 404。
- 停用/启用维度：状态翻转；停用后 `GET /dimensions`（对外）不再返回它，`GET /admin/dimensions` 仍返回；停用不影响已写入的历史答案（§4.5 的验收测试）。
- `GET /admin/dimensions`：返回全部状态；`answer_count` 统计正确（含"未撤回才计数"）；创建一个 key 恰好叫 `admin` 的维度，确认 `GET /admin/dimensions` 仍然是管理列表而不是被路由到别处（§4.6 的回归测试）。
- 知识库启用维度整体替换：成功替换；空列表清空；请求体里重复 key 去重后成功（§4.3）；不存在的 key 拒绝；已停用的 key 拒绝；取消启用不影响历史答案（§4.5 的另一半）；返回体是替换后的完整启用列表；knowledge_base_id 不存在返回 404。
