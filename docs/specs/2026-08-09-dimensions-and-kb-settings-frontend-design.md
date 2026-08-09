# 维度管理页 + 知识库设置页（issue #13）设计文档

## 1. 范围

issue #13 明确要求（P1，参考 `frontend-mock/dimensions.html`、`frontend-mock/kb-settings.html`）：

- 维度管理页（全局）：新增/编辑/停用维度、权重设置
- 知识库设置页（每个知识库单独一份）：勾选/取消勾选本知识库启用的维度

依赖 issue #9（维度定义管理写接口 + 知识库启用维度勾选写接口，已完成）。两个页面都是纯前端工作，后端接口已全部就位，不需要任何后端改动。

不做（issue 未提及，也不在这两个页面的职责范围内）：
- demo `kb-tabs` 里的"回收站"标签——核实后，这个页面在本项目里从未被实现，backlog（issue #1–#16）里也没有任何一条追踪它，是 PRD 落地过程中的一个既有缺口，不是本 issue 的责任；本设计新增的知识库内 tab 组件只放"知识点列表"/"知识库设置"两个真实存在的标签，不放一个会 404 的"回收站"标签（跟 `Sidebar.tsx` 现有注释"只渲染真的存在的页面"这条既定原则一致）。
- `KnowledgePointListPage` 里"在用答案"/"今日变更"两个统计卡目前显示"—"和"统计接口开发中"——issue #12 的后端统计接口已经上线，接入这两个卡片是一个真实存在的后续工作，但没有被本 issue 或任何其它已知 issue 认领，属于超出本 issue 范围的事，本设计不顺手做掉，只在这里记录、留给后续排期。
- 维度的"默认取值提示"（`default_value`）在本设计里可以被管理员配置，但从来没有任何地方真正读它去预填答案条件的输入框——核实后，这不是本 issue 引入的回归：`frontend-mock`（`app.js` 的 `condRowsHtml`，选中维度时显式把 `value` 置成 `''`，不读 `def.default_value`）自己就从未把这个值接到答案条件编辑器里，issue #7/#8 移植出的 `CoordEditor`/`WriteAnswerModal` 也是同样的行为，且只读的 `Dimension`/`useEnabledDimensions`（issue #7 定义）本身就没有 `default_value` 这个字段——要接上，需要改这两个属于别的 issue 的组件和一个全应用共用的类型契约，超出本 issue"维度管理页+知识库设置页"这两个页面的范围。Codex 外门审查在 PR #29 第三轮指出了这一点；记录在此，不在本 issue 里顺手解决。

## 2. 页面与路由设计

| 路径 | 页面 | 说明 |
|---|---|---|
| `/dimensions` | `DimensionsPage` | 全局维度管理，Sidebar 新增一个同级导航项（跟"知识库列表"平级） |
| `/knowledge-bases/:kbId/settings` | `KnowledgeBaseSettingsPage` | 单个知识库的启用维度勾选页 |

`Sidebar.tsx` 现有注释明确写着"维度管理/操作日志 留给 #13/#14"——本 issue 把"维度管理"这一半填上，"操作日志"仍然留给 #14，注释相应更新（不要整段删掉，"操作日志留给#14"这句话仍然真实有效）。

`KnowledgeBaseSettingsPage` 复用 `KnowledgePointListPage` 已经确立的"先按 `kbId` 查 `useKnowledgeBases()`，找不到或非 active 就渲染引导返回列表页的空状态"这套模式（`KnowledgePointListPage.tsx:117-133`），不重新发明一套知识库合法性校验逻辑。

### 2.1 新增共享组件：`KbTabs`（`components/layout/KbTabs.tsx`）

```tsx
interface KbTabsProps {
  kbId: number;
  active: 'kp-list' | 'settings';
}
```

渲染两个 `<Link>`（不是 `<a href>`，走 React Router 内部导航，不重新加载整页），`className="tab active"`/`"tab"` 由 `active` prop 直接决定，不用 `useLocation()` 做路径匹配——demo 的 `renderKbTabs(activeKey, kbId)` 本来就是每个页面显式声明自己是哪个 tab，这个显式声明的方式更简单、也更容易在测试里断言，没有理由换成路径匹配再反推出同样的结果。放在 `AppShell` 的 `children` 最前面（`<main class="content">` 内部顶端），这是 `AppShell` 现有结构本来就支持的用法，不需要改 `AppShell` 本身。

`KnowledgePointListPage` 需要在它现有的 `return` 里补上 `<KbTabs kbId={kbId} active="kp-list" />`（放在 `<AppShell>` 的 `children` 最前面），跟新增的 `KnowledgeBaseSettingsPage` 用同一个组件、同一个视觉位置，两个页面之间才能真正切换。

**这个页面实际有 4 个互相独立的 `return` 分支（`kbLoading`/`kbIsError`/无效知识库/正常渲染），不是一个"return"，必须逐一决定每个分支是否展示 `KbTabs`（对抗式审查第 6 点）**：

- `kbLoading`（数据还在加载）、`kbIsError`（拉取知识库列表失败）：**展示** `KbTabs`。`KbTabs` 只需要一个已经从路由参数拿到的 `kbId`，不依赖 `useKnowledgeBases()` 的返回结果，展示它没有额外成本；让用户在列表加载失败时仍能尝试切到"知识库设置"页面（那个页面会独立地再发一次自己的请求，如果后端整体不可达，两个页面会各自展示各自的失败态，不会因为看不到入口而彻底卡住）。
- 无效知识库（`!kb || kb.status !== 'active'`）：**不展示** `KbTabs`——这个分支跟 demo 的 `kb-settings.html:91-101`（`!kb || kb.status !== "active"` 时也不渲染 `renderKbTabs`）保持一致，一个不存在/已停用的知识库没有"设置"可言，展示一个会指向同样打不开的页面的 tab 没有意义。

`KnowledgeBaseSettingsPage` 反过来对齐：同样的 4 种知识库状态判断分支，`KbTabs` 的展示与否跟上面完全对称。

## 3. API 层新增

### 3.1 `api/client.ts` 补一个 `put` 方法

现有 `apiClient` 只有 `get`/`post`/`patch`，issue #9 已经在后端加了 `PUT /knowledge-bases/{kb_id}/enabled-dimensions`，但前端从来没消费过，`put` 方法完全没写。补一个跟 `patch`同构的 `put`：

```ts
put: <T>(path: string, body: unknown, options?: { signal?: AbortSignal }) =>
  request<T>(path, { ...options, method: 'PUT', body }),
```

### 3.2 `api/dimensions.ts` 补管理端 hooks

现有文件只有只读的 `Dimension` 类型 + `useEnabledDimensions`（issue #7 为条件筛选器写的，字段是 `key/label/field_type/weight`，对应后端 `DimensionOut`）。本次新增：

```ts
// Mirrors backend/src/kb_backend/schemas/dimension.py::DimensionAdminOut
export interface AdminDimension extends Dimension {
  default_value: string | null;
  status: 'active' | 'deprecated';
  answer_count: number;
}

// create/update 结构性分离，镜像后端 DimensionCreate/DimensionUpdate 本身
// 结构性分离 field_type 的做法（后端 DimensionUpdate 里 field_type "整个
// 不存在"，不是"存在但会被拒绝"）——不用一个共享类型加注释去回避这个区
// 别，让 TypeScript 类型本身说明"编辑请求体里没有 field_type 这个字段"，
// 调用者也不需要为一个必然不变、已 disabled 的字段硬凑一个值。对抗式审
// 查第 2 点。
export interface DimensionCreateInput {
  label: string;
  field_type: Dimension['field_type'];
  weight: number;
  default_value: string | null;
}

export interface DimensionUpdateInput {
  label: string;
  weight: number;
  // string | null，不是 string | undefined —— 这个字段永远显式携带、永远
  // 发送用户当前在输入框里看到的真实值（哪怕本次编辑完全没碰这个输入
  // 框）：非空字符串照实发送，清空后发 null，从不省略。省略这个 key 会
  // 被后端 DimensionUpdate 按 model_fields_set 解释成"不变"（design doc
  // §4.2 详述），如果前端在"用户清空了这个字段"时省略它（比如用
  // `value || undefined` 这种常见写法把空字符串变成 undefined 再被
  // JSON.stringify 丢掉），清空操作会在保存后又原样弹回；如果反过来在
  // "用户完全没碰这个字段"时也无条件携带它，则不会引入新问题——因为发
  // 的就是它本来的值，不是凭空写入的新值。对抗式审查第 1 点（阻塞级）。
  default_value: string | null;
}

export const ADMIN_DIMENSIONS_KEY = ['admin-dimensions'] as const;

export function useAdminDimensions() // GET /admin/dimensions, queryKey: ADMIN_DIMENSIONS_KEY
export function useCreateDimension()  // POST /dimensions,  body: DimensionCreateInput
export function useUpdateDimension()  // PATCH /dimensions/{key}, body: DimensionUpdateInput
export function useSetDimensionStatus() // POST /dimensions/{key}/activate|deactivate
export function useSetEnabledDimensions(kbId: number) // PUT /knowledge-bases/{kbId}/enabled-dimensions, body: {dimension_keys: string[]}
```

`useCreateDimension`/`useUpdateDimension`/`useSetDimensionStatus` 三者的 `onSuccess` 都要 `invalidateQueries` `ADMIN_DIMENSIONS_KEY`（管理页自己的列表，三处 `invalidateQueries` 调用和 `useAdminDimensions` 自己的 `queryKey` 必须引用同一个具名常量，不写字面量字符串——镜像 `knowledgeBases.ts::KNOWLEDGE_BASES_KEY` 这个既有先例，避免四处手写同一个字符串数组、其中一处笔误就导致缓存失效静默失败，没有任何类型检查能捕获这种漂移。对抗式审查第 3 点）。

**没有第二个固定 query key 可以 invalidate**（这一点本文档初版写错了，写成了 invalidate 一个字面量 `['dimensions']`——Codex 外门审查在 PR #29 第五轮指出，这个项目里**没有任何查询**用这个 key，是一次彻头彻尾的空操作，创建/更新/停用/启用维度之后，任何页面已经缓存的 `useEnabledDimensions` 结果全部悄悄地没被刷新）：`useEnabledDimensions` 是按知识库分别缓存的（`['knowledge-bases', kbId, 'enabled-dimensions']`），全局维度改名/停用/启用/改权重会影响**任意一个**启用过这个维度的知识库，不只是管理员当下正在看哪个知识库。正确做法是用 `invalidateQueries` 的 `predicate` 按 key 前缀批量匹配，把所有形如 `['knowledge-bases', <任意 kbId>, 'enabled-dimensions']` 的已缓存查询一次性标记为失效：

```ts
queryClient.invalidateQueries({
  predicate: (query) => query.queryKey[0] === 'knowledge-bases' && query.queryKey[2] === 'enabled-dimensions',
});
```

`useSetEnabledDimensions` 的 `onSuccess` 不用这个批量版本——它只需要 invalidate 自己这一个知识库的 `['knowledge-bases', kbId, 'enabled-dimensions']`（`useEnabledDimensions` 已经在用的 key，issue #7 定的），因为它改的就是这一个知识库自己的启用集合，不影响其它知识库。

## 4. 关键设计决策

### 4.1 维度管理页表单：新增/编辑共用一个 Modal，编辑时锁定字段类型

跟 `KnowledgeBaseListPage` 的 `KnowledgeBaseFormModal`（新增/编辑共用一个组件，靠 `target: X | 'create'` 区分）完全同一个模式，不重新设计一套。表单字段：

- 维度名称(`label`)：`maxLength={100}`（镜像后端 `DimensionCreate.label` 的 `max_length=100`——这个值创建时同时变成 `key`，见后端设计文档 §4.1）；新增时可编辑，编辑时也可编辑（后端允许改 `label`，不允许改 `key`，两者不是一回事）。
- 字段类型(`field_type`)：新增时是一个可选 `<select>`；**编辑时 disabled，但仍然显示当前值**，不隐藏这个字段——用户需要知道"这个维度当前是什么类型"这个事实性信息，即使不能改；`disabled` 传达"不可编辑"，不是"不存在"。
- 权重(`weight`)：`<input type="number" min={1} max={100}>`，提交前用 `Math.min(100, Math.max(1, ...))` 夹到合法区间（镜像 demo `submitDim()` 的同一段夹取逻辑），不是提交后等后端 422 再报错——权重错一位数字是最常见、最无害的输入失误，直接纠正比报错体验更好，这跟"名称"这类需要用户明确知道自己填错了什么的字段不是同一类问题。
- 默认取值提示(`default_value`，可选)：见 §4.2。

### 4.2 "默认取值提示"输入框复用已有的 `ValueInput` 组件，不新写一套类型分支

`components/ui/dimensionValue.tsx` 的 `ValueInput`（issue #7/#8 为条件筛选器/答案条件写的）已经把"文本/数值/时间/布尔四种字段类型各自该用什么原生 input"这件事解决过一次，且它的存在理由本来就是"避免同一段类型分支逻辑在多处重复漂移"（该文件头部注释）。默认取值提示框只是又一个"给定 `field_type`，渲染对应类型的输入框"的场景，构造一个只有 `field_type` 字段有意义的临时 `Dimension` 对象传给 `ValueInput` 即可：

```tsx
<ValueInput dim={{ key: '', label: '', weight: 0, field_type }} value={defaultValue} onChange={setDefaultValue} />
```

不对 `ValueInput` 的返回值做 `toFilterValue` 类型转换——那个函数是为"写进答案 coord、要被后端 `normalize_coord` 按类型解析"这个场景存在的；`default_value` 后端存的是 `str | None`，不做任何类型转换（PRD/demo 都明确"仅作为提示，不做强制校验"），`ValueInput` 给出的字符串原样提交即可（包括 `boolean` 类型时给出的 `"true"`/`"false"` 字符串——这正是 `default_value: str | None` 期望的形态，不需要转成 JS 布尔再转回去）。

**提交时的转换规则（对抗式审查第 1 点，阻塞级）**：组件内部状态永远是字符串（`ValueInput` 的 `value` prop 类型是 `string`，输入框清空时是 `''`，不是 `null`），但 `DimensionCreateInput`/`DimensionUpdateInput` 的 `default_value` 字段是 `string | null`——提交前必须做这个转换：

```ts
const submittedDefaultValue = trimmedDefaultValue === '' ? null : trimmedDefaultValue;
```

这一步不能省略、也不能写成 `trimmedDefaultValue || undefined`——后者会让"清空"和"整个字段不存在"变成同一件事（`JSON.stringify` 会丢掉值为 `undefined` 的 key），而后端 `DimensionUpdate` 恰恰是靠"这个 key 存不存在"（`model_fields_set`）区分"不变"和"清空"的：省略这个 key 会被解释成"不变"，用户刚刚执行的"清空"操作会在保存后又原样弹回，是一个真实、当场可复现的 bug。**这个字段必须每次编辑都携带**（不管这次编辑有没有碰这个输入框），值就是输入框里当前的真实内容（用 `null` 表示空、字符串表示非空）——因为发的是它本来的值，不会引入语义漂移；反而是"只在用户碰过这个字段时才携带"这种看似更保守的写法，会在"用户没碰它"的路径上误判该字段的当前值（初次进入编辑表单时，要把 `AdminDimension.default_value`——可能是 `null`——原样载入 state，不能用 `?? ''` 之后就再也分不清"本来是 null"还是"本来是空字符串"；两者提交时的转换结果碰巧一致（都是 `null`），所以这里不构成 bug，只是需要说明初始化时的处理同样要走一致的字符串化）。

### 4.3 名称里的"/"字符：客户端前置校验，不只是等后端 422

后端 `DimensionCreate.label` 的校验器明确拒绝含"/"的名称（会破坏 `/dimensions/{key}/activate` 这类路径路由，issue #9 设计文档已经讲过原因）。`KnowledgeBaseListPage` 的表单曾经"设计了 `maxLength` 但没有真正接上"，被 Codex 外门审查抓到过——这次直接把两条前置校验都写实：`maxLength={100}` 靠 HTML 属性天然生效，"/"这条额外加一个提交前检查：

```ts
if (trimmedLabel.includes('/')) {
  setError('名称不能包含斜杠(/)');
  return;
}
```

不依赖后端 422 兜底来發现这个问题——维度名称输入框离路由校验的关系不直观，用户在提交前看到明确的中文提示比等一次网络往返再看到通用错误文案体验更好。

**这条校验只在"新增"语义上跟后端对称，编辑模式下前端比后端更严格，不是单纯的镜像**（对抗式审查第 4 点）：后端 `DimensionCreate.label` 拒绝"/"是因为这个值创建时同时变成路由里用到的 `key`；`DimensionUpdate.label`（`schemas/dimension.py:73-78`）只校验非空，**没有**"/"这条规则，因为编辑不改 `key`，标签里出现"/"在编辑场景下不会产生任何路由风险。本设计仍然选择在编辑模式下也拦截"/"——这是一个独立的产品决策（保持 `label` 跟已经生成的 `key` 视觉上不产生落差，避免用户以为"标签"和"key"是两个可以随意分道而行的字符串），比后端规则更严格，不要理解成"前端只是照抄了一遍后端已有的规则"。

### 4.4 知识库设置页"使用中的答案"计数：复用管理端接口的全局口径，不是本知识库口径

demo 的 `kb-settings.html`（`renderDimCheckList`）里每一行维度旁边显示"全局共 N 条答案在用"——`dimensionUsageCount(d.key)` 统计的是**全库**（不分知识库）写过这个维度取值的答案数，不是"本知识库"的数字。后端目前也只有一个全局口径的 `answer_count`（`DimensionAdminOut.answer_count`，来自 `GET /admin/dimensions`），没有"某维度在某知识库下的使用数"这个更细的接口——本设计不为这一个数字新增一个后端接口，直接复用已有的 `useAdminDimensions()`（管理页也在用同一个 hook），在知识库设置页里过滤出 `status === 'active'` 的维度构建勾选列表，`answer_count` 字段照抄展示，跟 demo 保持同一个（全局）口径，不假装它是"本知识库"的数字，也不在文案上误导（沿用demo"全局共 N 条答案在用"的措辞，不写"本知识库"）。

**已知的、有意接受的认知偏差（对抗式审查第 8 点）**：即使措辞完全准确，一个维度即便在**当前**知识库从未启用/从未被写入过，只要它在其它知识库用量很大，这里仍然会显示一个很大的数字，容易让管理员对"取消勾选"这个本来无风险的操作产生不必要的犹豫。这个偏差是单向的（全局用量 ≥ 本知识库用量，不会出现"数字很小但本知识库其实依赖很深"这种反向低估、导致真正危险的漏判），所以不构成推翻"不为这一个数字新增后端接口"这个决定的理由——只在这里记录下来；如果后续用户反馈这确实造成误操作顾虑，再考虑要不要为此单独加一个按知识库拆分的 `answer_count` 接口。

### 4.5 保存启用维度：整集替换（PUT 一次提交全部勾选的 key），不是逐项增删

后端 `PUT /{kb_id}/enabled-dimensions` 本来就是"整集替换"语义（issue #9 设计文档 §3.2：镜像 demo 的"勾选列表 + 一个保存按钮"交互，不是每次勾选/取消勾选都单独发一次请求）。本页面点击"保存"时，读取当前 DOM 里全部被勾选的 `<input type="checkbox">` 的 `data-key`，一次性提交 `{dimension_keys: [...]}`，不做增量 diff（不用先算出"新增了哪些、去掉了哪些"再分别调用两个不存在的增量接口——那样的接口从来没被设计出来）。

**失败处理的具体渲染位置（对抗式审查第 5 点）**：这个页面没有 `KnowledgeBaseListPage` 那样的 Modal 容器可以依附，是"整页勾选列表 + 页面下方一个孤立的保存按钮"结构（demo `kb-settings.html:82-84` 的 `form-row`），"就地错误提示"具体是指错误文案渲染在这个 `form-row` 里、紧贴保存按钮：

```tsx
<div className="form-row" style={{ marginTop: 6 }}>
  {error && <p className="hint" style={{ color: 'var(--red)' }}>{error}</p>}
  <button type="button" className="btn primary" disabled={mutation.isPending} onClick={save}>
    保 存
  </button>
</div>
```

分类原则（表单类操作→就地提示，确认类操作→toast）跟 `KnowledgeBaseListPage` 已经定下的既定分工一致，但这是该分工第一次应用在"没有 Modal 包裹的整页表单"这种新的 UI 结构上，不是跟 Modal 内联错误完全同一个场景的直接复制——具体渲染位置需要单独定下来，不能只停留在"就地"这个笼统结论。典型的失败场景：勾选后、点保存前，另一个管理员把其中一个维度停用了——后端会返回"维度「xxx」已停用，无法启用"（400），错误消息原样展示在上面这个位置，不吞掉、也不转成一个泛泛的"操作失败"。

## 5. 组件结构

```
frontend/src/api/client.ts                          新增 put 方法
frontend/src/api/dimensions.ts                       新增 AdminDimension、DimensionCreateInput、
                                                       DimensionUpdateInput、ADMIN_DIMENSIONS_KEY、
                                                       useAdminDimensions、useCreateDimension、
                                                       useUpdateDimension、useSetDimensionStatus、
                                                       useSetEnabledDimensions
frontend/src/components/layout/KbTabs.tsx             新增：知识库内两个 tab（知识点列表/知识库设置）
frontend/src/pages/DimensionsPage.tsx                 新增：维度管理页
frontend/src/pages/KnowledgeBaseSettingsPage.tsx      新增：知识库设置页
frontend/src/pages/KnowledgePointListPage.tsx         补上 <KbTabs active="kp-list" />
frontend/src/components/layout/Sidebar.tsx            新增"维度管理"导航项
frontend/src/App.tsx                                  新增 /dimensions、/knowledge-bases/:kbId/settings 两条路由
frontend/src/test/server.ts                           新增 makeAdminDimension 工厂 + 对应的 mock handlers
frontend/src/pages/DimensionsPage.test.tsx            新增
frontend/src/pages/KnowledgeBaseSettingsPage.test.tsx 新增
frontend/src/api/client.test.ts                       补 put 方法的单测
```

## 6. 测试计划

**`DimensionsPage`**：
- 渲染已有维度列表（key/显示名称/字段类型/权重/状态/使用中的答案/操作 全部列正确显示）。
- 新增维度成功，表单清空后关闭弹窗，列表刷新。
- 名称留空 → 就地错误提示，不发请求。
- 名称含"/" → 就地错误提示（回归 §4.3，不能只靠后端 422）。
- 编辑维度：字段类型下拉框 `disabled`，但显示当前值；只改权重/显示名称、完全不碰"默认取值提示"输入框，提交后列表反映新值，且该维度原有的 `default_value` 保持不变（回归 §4.2 对抗式审查第 1 点——"没碰的字段被静默改写"这一类 bug）。
- 编辑一个 `default_value` 本来非空的维度，清空这个输入框后保存，再重新打开编辑弹窗 → 显示为空，不是保存前的旧值弹回（回归 §4.2 对抗式审查第 1 点——"清空操作不生效"这一类 bug，两个方向都要各写一条测试锁住）。
- 名称留空 → 就地错误提示，不发请求。
- 名称含"/" → 就地错误提示（新增和编辑两种模式下都要各测一次：新增模式回归 §4.3 的"镜像后端"部分，编辑模式回归 §4.3 补充说明的"前端比后端更严格"这条独立决策——两条测试的存在理由不同，不能只写一条就当作覆盖了两种模式）。
- 停用一个 active 维度：确认弹窗展示影响提示（"使用中的答案"非零时的风险文案），确认后状态变为"已停用"。
- 后端返回业务错误（如重名）→ 就地/toast（按 §4.5 的表单 vs 确认对话框分工）正确落位，不是泛化文案覆盖具体原因。

**`KnowledgeBaseSettingsPage`**：
- 渲染全部 active 维度的勾选列表，已启用的维度默认勾选；每行展示字段类型标签、权重、全局使用数（回归 §4.4，措辞不能写成"本知识库"）。
- 已停用（非 active）的维度不出现在勾选列表里。
- 取消勾选一项、勾选另一项后保存 → 提交的 `dimension_keys` 是保存时点提交那一刻 DOM 里全部勾选项的快照，不是相对上次保存的增量。
- 保存失败（如目标维度已被停用）→ 就地错误提示，不是 toast（回归 §4.5）。
- 全局没有任何 active 维度时的空状态提示（"还没有任何启用中的全局维度，先去「维度管理」新增一个"，附一个跳转链接）。
- 无效/非 active 知识库 → 复用 `KnowledgePointListPage` 已验证过的引导空状态，不重新写一遍校验逻辑。

**`KbTabs` / 页面联动**：
- 从知识点列表页点击"知识库设置" tab，能正确跳转到 `/knowledge-bases/:kbId/settings`，且该 tab 处于 active 视觉状态；反向跳转同理。
- `KnowledgePointListPage` 原有测试全部保持通过（新增的 `<KbTabs>` 不能破坏任何既有断言——尤其不能引入跟已有文案冲突的新增文本节点）。
- 知识库列表拉取失败（`kbIsError` 分支）时，`KbTabs` 仍然渲染（回归 §2.1 对该分支的显式决定，不是留白后随实现方式漂移）。
- 无效/非 active 知识库分支下，`KbTabs` 不渲染（跟 demo 保持一致，回归 §2.1）。

**`api/client.ts` 的 `put`**：
- 补一个跟现有 `patch` 单测同构的用例：确认 `Content-Type: application/json`、方法为 `PUT`、body 正确序列化、非 200 code 抛 `ApiError`。
