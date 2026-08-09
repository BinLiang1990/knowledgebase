# 知识点详情页版本历史 & 变更留痕 tab + 全局操作日志页面（issue #14）设计文档

## 1. 范围

issue #14 明确要求（P1，参考 `frontend-mock/detail.html` 的"版本历史""变更留痕" tab 和 `frontend-mock/logs.html`）：

- 知识点详情页补齐"版本历史" tab：按条件组合选择版本链，时间线展示，标注"当前/已被新版替代/晚于查询时间暂不生效/已撤回"
- 知识点详情页补齐"变更留痕" tab：操作流水表格，含来源/状态列，可直接对生效答案执行撤回
- 新增全局操作日志页面：跨知识库流水，可定位到具体知识库/知识点，同样支持撤回

依赖 issue #12（变更留痕/统计后端接口，已完成）。`KnowledgePointDetailPage.tsx` 已经把这两个 tab 以"占位文案 + 指向本 issue"的形式搭好了骨架（issue #7/#8 定的"未建好的 tab 显示占位，不隐藏"惯例），本设计负责填内容。

不做：立体全景（issue #16，Out of Scope 已明确）；"设为默认"（issue #10 后端已完成，但没有任何 issue 认领前端接入——本 issue 的 Acceptance Criteria 只提"可直接...执行撤回"，没提"设为默认"，记录为已知缺口，不在本 issue 顺手做）。

### 需要一个小的后端补充：`GET .../knowledge-points/{kp_id}/answers`

"版本历史" tab 需要的数据，跟"变更留痕" tab / 全局日志用的 `GET .../change-log` 看起来很像，但**不是同一份数据，也不能互相复用**——详见 §4.1。版本历史需要每个版本的原始字段（`effective_time`、`revoked`、`note`），而 `change-log` 的响应里没有这些字段（那份 schema 是为"写入历史流水"设计的，不是为"某条件组合的完整时间线"设计的）。

新增一个只读、直接复用现有 `AnswerOut` schema（零新增类型）的端点：

```python
@router.get("/{kp_id}/answers")
def list_all_answers(kb_id: int, kp_id: int, db: Session = Depends(get_db)) -> dict:
    """知识点全部答案的原始列表（issue #14）——不分组、不筛选 revoked/effective_time，
    供前端自己按 coord 分组、按 (effective_time, created_at, id) 排序、
    计算"当前/已被新版替代/晚于查询时间暂不生效/已撤回"标注（跟 resolve.py 的算法
    不是一份代码，但要算的是同一件事，见前端设计 §4.2）。跟
    compute_all_answer_groups 用的是完全同一条查询（backend/src/kb_backend/
    resolve.py:118-124: select(Answer).where(kb_id, kp_id)，不加任何过滤），
    只是不做分组汇总，直接把原始行返回。"""
    _get_kp_or_404(db, kb_id, kp_id)
    answers = db.execute(
        select(Answer).where(Answer.knowledge_base_id == kb_id, Answer.knowledge_point_id == kp_id)
    ).scalars().all()
    out = [AnswerOut.model_validate(a) for a in answers]
    return envelope([o.model_dump(mode="json") for o in out])
```

不新增 schema（复用 `AnswerOut`，issue #4 定义的）、不新增 migration、不加分页（跟 `answer-groups`/`change-log` 已有先例一致——见 issue #12 设计文档 §4.6 的分页决定，同一套理由，这里不重复论证）。这是本次唯一的后端改动，是一个纯读取、零新业务逻辑的补充。

## 2. 页面/路由设计

| 路径 | 变化 |
|---|---|
| `/knowledge-bases/:kbId/knowledge-points/:kpId`（已存在） | `KnowledgePointDetailPage` 的 `timeline`/`logs` 两个 tab 从占位文案换成真实内容 |
| `/change-log`（新增） | 全局操作日志页面，路径跟它直接消费的后端端点 `GET /change-log`（`audit_log.py`）同名（不是"镜像 `/dimensions` 的命名习惯"——核实后，前端 `/dimensions` 路由实际消费的是 `GET /admin/dimensions`，跟路径本身只是字面碰巧相同，不构成一个可类比的先例；这里单独判断：`/change-log` 这个名字本身就是它要展示的东西，不需要借别的先例说明） |

`Sidebar.tsx` 补上"操作日志"导航项（现有注释"操作日志留给 #14"这句话在这个 issue 里兑现）。

## 3. API 层新增

```ts
// api/knowledgePoints.ts
export function useAllAnswers(kbId: number, kpId: number, enabled: boolean) {
  return useQuery({
    // 挂在跟 useAnswerGroups/useKnowledgePoint 同一个前缀下
    // (knowledgePointDataKeyPrefix(kbId) + kpId + 'answers')——撤回/编辑/
    // 写入答案的既有 invalidateKnowledgePointDataQueries 不用改一行就能
    // 顺带失效这份数据，见 §4.5。
    queryKey: [...knowledgePointDataKeyPrefix(kbId), kpId, 'answers'] as const,
    queryFn: ({ signal }) =>
      apiClient.get<Answer[]>(`/knowledge-bases/${kbId}/knowledge-points/${kpId}/answers`, { signal }),
    enabled,
  });
}

// api/changeLog.ts（新文件）
export interface ChangeLogEntry {
  time: string;
  knowledge_point_id: number;
  answer_id: number;
  operator: string;
  action: 'create' | 'edit' | 'revoke';
  coord: Record<string, string | number | boolean>;
  before_content: string | null;
  after_content: string | null;
  source: string;
  revoke_reason: string | null;
  status: 'live' | 'superseded' | 'revoked';
  revocable: boolean;
}
export interface GlobalChangeLogEntry extends ChangeLogEntry {
  knowledge_base_id: number;
  knowledge_base_name: string;
  knowledge_point_title: string;
}

export function useChangeLog(kbId: number, kpId: number, enabled: boolean) {
  return useQuery({
    queryKey: [...knowledgePointDataKeyPrefix(kbId), kpId, 'change-log'] as const,
    queryFn: ({ signal }) =>
      apiClient.get<ChangeLogEntry[]>(`/knowledge-bases/${kbId}/knowledge-points/${kpId}/change-log`, { signal }),
    enabled,
  });
}

export const GLOBAL_CHANGE_LOG_KEY = ['change-log'] as const;
export function useGlobalChangeLog() {
  return useQuery({
    queryKey: GLOBAL_CHANGE_LOG_KEY,
    queryFn: ({ signal }) => apiClient.get<GlobalChangeLogEntry[]>('/change-log', { signal }),
  });
}

// api/answers.ts（新增到已有文件）
export function useRevokeAnswer(kbId: number, kpId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ answerId, revokeReason }: { answerId: number; revokeReason: string }) =>
      apiClient.post<Answer>(`/knowledge-bases/${kbId}/knowledge-points/${kpId}/answers/${answerId}/revoke`, {
        revoke_reason: revokeReason,
      }),
    onSuccess: () => {
      invalidateKnowledgePointDataQueries(queryClient, kbId); // 覆盖 answer-groups/change-log/answers(全量)
      queryClient.invalidateQueries({ queryKey: GLOBAL_CHANGE_LOG_KEY }); // 全局日志是独立的顶层 key，必须单独 invalidate
    },
  });
}
```

`knowledgePointDataKeyPrefix`（`knowledgePoints.ts` 已有，非导出的内部函数）需要导出，供 `changeLog.ts`/`useAllAnswers` 复用，不在两处各写一遍同样的前缀数组。

## 4. 关键设计决策

### 4.1 "版本历史"不能复用"变更留痕"的数据——两者对同一条已撤回链的语义天然不同

`change-log`（issue #12 后端设计文档 §4.1）里，一条整体撤回的链，只有**最后一个（按写入顺序）**版本的 `status` 是 `"revoked"`，更早的版本永远是 `"superseded"`——这是刻意的：变更留痕回答的是"写入历史"，一个版本"被更晚的版本取代"这件事，跟这条链后来有没有整体撤回是两件独立的事。

但"版本历史" tab 要回答的是另一个问题：demo 的 `tabTimeline`（`frontend-mock/detail.html:316-350`）对**每一行**都先判断 `a.revoked`（原始的、整条链共享的布尔值——撤回是整链批量 `UPDATE`，链上每一行的 `revoked` 字段字面值都是 `true`），撤回了就都标"已撤回"，不区分是不是最后写入的那一行。这跟 `change-log` 的 `status` 字段的定义直接冲突——如果拿 `change-log` 的 `status` 来渲染版本历史，一条链里除最后一行都会被误标成"已被新版替代"，即使整条链已经被撤回。

另外，`change-log` 的 `status` 判定"当前"用的是**写入顺序**（chain 里按 `created_at` 排序的最后一条，非 revoked 则为 `"live"`），而版本历史的"当前"要用的是 PRD §4.6.1 的**生效时间规则**（`effective_time <= 查询时间` 里最大的那个，同一 `effective_time` 按 `created_at` 破平局）——这两者只在"没有回填历史生效时间"的简单场景下碰巧一致，一旦有人编辑答案时把 `effective_time` 往前回填（一个合法操作，`edit_answer` 不禁止这么做），写入顺序意义上的"最新"和生效时间意义上的"当前"就会指向链上不同的两行。

这两处语义差异，决定了"版本历史"不能拿 `change-log` 的响应改一改就用，必须有自己独立的原始数据（§1 新增的 `GET .../answers`）和独立的标注算法（§4.2）。

### 4.2 版本历史的"当前"判定：独立实现，镜像 `resolve.py::compute_live_groups` 的真实算法，不是 demo 的简化版

demo 的 `liveId` 用 `chain.find(a => a.time <= atTime && !a.revoked)`（链已经按时间降序排过），只有两个排序键（`effective_time` 隐含 + 数组遍历顺序），没有 `created_at`/`id` 破平局。这跟本项目 `answers.ts::sortLiveGroupsByPriority` 上方注释明确指出的"resolve.py 的真实 5 key 排序元组，不是 PRD 文字描述的 3 key 简化版"是同一类问题——如果照抄 demo 这段更简单的逻辑，在"两个版本 `effective_time` 相同"这种真实存在的场景下（PRD §4.5 校验规则明确允许），版本历史 tab 判定的"当前"版本会跟"当前答案" tab（`answers.ts` 已经对齐过 resolve.py 真实算法）的判定结果不一致，用户会看到两个 tab 对"现在到底哪个版本生效"给出矛盾的答案。

新写一个纯函数（不是改 `sortLiveGroupsByPriority`——那个函数的输入输出形状是"多个 coord 组各自的 live_answer"，跟这里"单个 coord 组内所有版本各自的标注"是不同的问题）：

```ts
// api/timeline.ts（新文件）
export type TimelineStatus = 'current' | 'superseded' | 'not-yet-effective' | 'revoked';

export interface TimelineEntry {
  answer: Answer;
  status: TimelineStatus;
}

// 按 coordGroupKey 分组，每组内部按 (effective_time, created_at, id) 降序
// 排列（demo 的展示顺序：新的在上面），并计算每一行的标注。
export function buildTimelineGroups(answers: Answer[]): Map<string, TimelineEntry[]> {
  const byGroup = new Map<string, Answer[]>();
  for (const a of answers) {
    const key = coordGroupKey(a.coord);
    (byGroup.get(key) ?? byGroup.set(key, []).get(key)!).push(a);
  }
  const result = new Map<string, TimelineEntry[]>();
  for (const [key, chain] of byGroup) {
    result.set(key, tagChain(chain));
  }
  return result;
}

function tagChain(chain: Answer[]): TimelineEntry[] {
  const sorted = [...chain].sort(compareForCurrency); // 降序：新的在前
  const currentId = findCurrentId(sorted, today());
  return sorted.map((answer) => ({
    answer,
    status: answer.revoked
      ? 'revoked'
      : answer.id === currentId
        ? 'current'
        : answer.effective_time > today()
          ? 'not-yet-effective'
          : 'superseded',
  }));
}
```

（`compareForCurrency`/`findCurrentId` 的排序键跟 `resolve.py::compute_live_groups` 完全一致：`effective_time` 主键、`created_at` 次键、`id` 兜底破平局；`findCurrentId` 只在未撤回、`effective_time <= atTime` 的候选里取最大。）

**显式函数契约：`buildTimelineGroups`/`tagChain`/`findCurrentId` 故意没有 `atTime` 参数，永远读 `today()`**——这是有意的设计，不是偷懒漏写。`resolve.py::compute_live_groups` 本身是显式带 `at: date` 参数的，实现时很容易"依葫芦画瓢"给这几个函数也加一个对称的 `atTime` 参数、再顺手接上"当前答案" tab 已有的 `qMode`/`qTime` 状态——这正是下一段要明确拒绝的那个决定，加了参数就等于偷偷做了。如果后续真的要支持"回看某天时哪个版本是当前版本"，需要显式修改这几个函数的签名、并在设计文档里重新论证，不能在实现阶段不声不响地加上。

**"查询时间"用当前日期，不提供时间穿梭选择器**——demo 的 `tabTimeline(kpId, atTime)` 接收一个 `atTime`（跟"当前答案" tab 共享同一个查询时间选择器），但本设计选择版本历史 tab 只看"现在"，不接入"当前答案" tab 已有的 `qMode`/`qTime` 状态。理由：PRD 原文对"版本历史"的描述（§4.7）是"展示其完整的时间线：每个版本的生效时间、内容、操作人、变更说明，以及状态标注"，标注本身（当前/已被新版替代/晚于查询时间暂不生效/已撤回）已经完整表达了"这个版本相对于*现在*处于什么状态"，用户不需要先把"当前答案" tab 切到某个历史查询时间、再切到"版本历史" tab 才能看懂——这是一个简化，降低了 UI 复杂度（不用在两个 tab 之间同步一个查询时间状态），如果后续有人明确需要"回看某天时哪个版本是当前版本"这个更细的能力，再补一个选择器，不在本 issue 里为一个 PRD 没有明确要求的交互预先设计。

### 4.3 "变更留痕"/"全局操作日志"直接消费 `change-log` 接口的现成字段，不重新计算任何东西

跟 §4.1/§4.2 的"版本历史"不同，"变更留痕"/"全局操作日志"两个页面要展示的字段（时间、操作人、动作、条件、变更前后、来源、状态）跟后端 `ChangeLogEntryOut`/`GlobalChangeLogEntryOut`（issue #12）的字段是**逐一对应**的，直接渲染即可：

| 后端字段 | 页面列 | 展示转换 |
|---|---|---|
| `action` | 动作 | `create`→"写答案"，`edit`→"改答案"，`revoke`→"撤回答案" |
| `status` | 状态 | `live`→"生效"，`superseded`→"已被新版替代"，`revoked`→"已撤回" |
| `coord` | 条件 | 复用 `KnowledgePointDetailPage.tsx` 已有的 `describeCoord`（提到共享位置，见 §5） |
| `before_content`/`after_content` | 变更前/变更后 | `null` 显示为"—" |
| `source` | 来源 | 原样展示（`"人工填报"`/`"人工编辑"`），套一个 `tag purple`，镜像 demo |
| `revocable`+`answer_id` | 操作列的"撤回"链接 | `revocable=true` 才显示；点击用 `answer_id` 调 `useRevokeAnswer`（见 §4.4），不是 demo 用 `coord` 定位那一套（issue #10 已经定过这条约定，答案相关的所有前端操作都用 `answer_id`，不重新传 `coord`） |

后端的英文枚举值（`action`/`status`）需要一个展示映射表（中文文案），两个页面共用同一份映射（放 `changeLog.ts` 里跟类型定义放一起），不各写一份、不各写一遍映射逻辑。

**`ChangeLogTable` 的 props 必须是判别式联合（discriminated union），不能是 `entries: ChangeLogEntry[] | GlobalChangeLogEntry[]`**——对抗式审查指出：后者是"数组的联合"，`.map` 出来单个元素的类型是 `ChangeLogEntry | GlobalChangeLogEntry`，访问只有后者才有的 `knowledge_base_name`/`knowledge_point_title`/`knowledge_base_id` 会被 TypeScript 直接拒绝；`showLocation?: boolean` 是一个跟 `entries` 类型完全独立的 prop，TS 的控制流窄化不会把"`showLocation` 为 true"和"数组元素一定是 `GlobalChangeLogEntry`"关联起来，实现时必然要靠类型断言或运行时 `'knowledge_base_name' in entry` 硬收窄，这两种都是本该在类型层面就消灭掉的代码异味。正确写法是让 `showLocation` 本身成为判别式：

```ts
type ChangeLogTableProps =
  | { entries: ChangeLogEntry[]; showLocation?: false; kbId: number; kpId: number }
  | { entries: GlobalChangeLogEntry[]; showLocation: true };
```

（`kbId`/`kpId` 只在 `showLocation` 为假/省略的知识点级模式下作为 props 传入——原因见 §4.4 撤回弹窗那一段的"两种模式下 kbId 来源不对称"。）这样组件内部只要检查 `props.showLocation`，TS 就能在对应分支里正确窄化 `props.entries` 的元素类型，不需要任何断言。

### 4.4 撤回弹窗：复用 `DeleteKnowledgePointModal` 的"必填原因 + 风险提示"模式；两种页面下 `kbId` 的来源不对称，必须显式处理

新增一个共享组件 `RevokeAnswerModal`（`components/RevokeAnswerModal.tsx`），结构跟 `DeleteKnowledgePointModal.tsx` 几乎一样（必填 `textarea`，`maxLength={500}`——镜像后端 `AnswerRevoke.revoke_reason` 的 `max_length=500`；风险提示"撤回为逻辑删除：该条件下将不再返回此答案；历史版本与留痕永久保留"——采用 demo `logs.html:73` 的这一版措辞，不是 `detail.html:134` 那句多带了"可在「变更留痕」查看"的版本：后者放在全局日志页面里会自我指代——"你已经在变更留痕/日志页面里了，还提示你去变更留痕查看"，读起来很奇怪；`logs.html` 那句本来就是给"日志类页面"写的通用版本，两个页面共用同一个组件、同一句文案时更合适，这是对抗式审查指出的一处引用不完整、且没意识到 demo 两个页面文案本就不同的问题）。

`RevokeAnswerModal` 的 props 是 `kbId`/`kpId`/`answerId`/`content`（后者只用于展示"将撤回这条答案：xxx"）——**必须在组件内部才调用 `useRevokeAnswer(kbId, kpId)`**（跟 `DeleteKnowledgePointModal` 内部调用 `useDeleteKnowledgePoint(kbId)` 是同一个模式），不能让调用方提前实例化好 mutation 再传进来：`useRevokeAnswer` 是 hook-工厂模式（`kbId`/`kpId` 在实例化时就固定，跟 `useCreateAnswer`/`useEditAnswer` 一样），而全局日志页面每一行的 `kbId`/`kpId` 都可能不同，不可能在页面级只实例化一次。

**两种触发场景下，传给 `RevokeAnswerModal` 的 `kbId`/`kpId` 来源不一样，`ChangeLogTable` 必须显式处理这个分支**（对抗式审查指出的遗漏，原设计文档完全没提）：
- 知识点详情页的"变更留痕" tab：`ChangeLogEntry` 本身**没有** `knowledge_base_id`/`knowledge_point_id` 字段（只有 `answer_id`），`kbId`/`kpId` 只能来自页面路由参数，作为 `ChangeLogTable` 的 `kbId`/`kpId` props（见上面判别式联合类型定义）整页传入，每一行共用同一对。
- 全局操作日志页面：`GlobalChangeLogEntry` 每一行自带 `knowledge_base_id`/`knowledge_point_id`（后端 `audit_log.py` 已经把这两个字段内联进每一行），`kbId`/`kpId` 从**这一行自己的字段**取，不是页面级固定值——同一页里不同行点"撤回"，可能打到不同的知识库。

`ChangeLogTable` 内部据此决定：`showLocation` 为真时用 `entry.knowledge_base_id`/`entry.knowledge_point_id`；否则用 props 里的 `kbId`/`kpId`。

### 4.5 撤回后的缓存失效范围：既有 KP 数据前缀 + 独立的全局日志 key

`useRevokeAnswer` 的 `onSuccess` 需要让下面这些已缓存的数据都变成脏数据：
- 这个知识点的 `answer-groups`（撤回后"当前答案" tab 不再显示这条链）
- 这个知识点的 `answers`（全量列表，§1 新增端点——版本历史 tab 需要看到最新的 `revoked` 状态）
- 这个知识点的 `change-log`（撤回本身会新增一行"撤回答案"记录）
- 全局的 `change-log`（同一条撤回记录，也会出现在全局日志里）

前三者天然共享 `knowledgePointDataKeyPrefix(kbId) + kpId` 这同一个前缀（§3 里三个新 hook 的 `queryKey` 设计成这样，不是巧合），一次 `invalidateKnowledgePointDataQueries(queryClient, kbId)` 调用就全覆盖，跟 `useEditAnswer`/`useCreateAnswer` 现有的失效方式完全一致，不需要专门为撤回写一段新的失效逻辑。全局日志是独立的顶层 key（`['change-log']`，不带 `kbId` 前缀，因为它本来就是跨知识库的），必须单独一行 `invalidateQueries` ——这跟"知识库设置页"当时（issue #13）为维度全局变更单独处理跨 KB 缓存失效是同一类问题，不能因为它是"顺带"的就漏掉。

## 5. 组件结构

```
backend/src/kb_backend/routers/knowledge_point.py    新增 GET /{kp_id}/answers（§1）
frontend/src/api/changeLog.ts                        新增：ChangeLogEntry/GlobalChangeLogEntry 类型、
                                                        useChangeLog、useGlobalChangeLog、动作/状态中文映射表
frontend/src/api/timeline.ts                          新增：buildTimelineGroups 纯函数
frontend/src/api/answers.ts                            新增 useRevokeAnswer；新增 coordGroupKey/describeCoord
                                                        （从 KnowledgePointDetailPage.tsx 移到这里——timeline.ts
                                                        需要 import coordGroupKey，而 api/ 目录反向导入
                                                        pages/ 目录违反本项目现有的单向分层惯例（pages/ 导入
                                                        api/，从没有反过来的先例）。对抗式审查指出的遗漏：原设计
                                                        文档只提了 describeCoord 要挪共享位置，没提 coordGroupKey，
                                                        实际上两个函数都要挪，且理由完全一样，一起处理
                                                        （KnowledgePointDetailPage.tsx 改成从 answers.ts 导入）
frontend/src/api/knowledgePoints.ts                   新增 useAllAnswers；导出 knowledgePointDataKeyPrefix
frontend/src/components/RevokeAnswerModal.tsx          新增，供详情页 + 全局日志页共用；kbId/kpId 由调用方
                                                        （ChangeLogTable，见 §4.4）决定，组件内部才实例化
                                                        useRevokeAnswer
frontend/src/components/ChangeLogTable.tsx             新增：变更留痕表格，判别式联合 props（见 §4.3），
                                                        详情页 tab + 全局日志页共用
frontend/src/pages/KnowledgePointDetailPage.tsx        timeline/logs 两个 tab 从占位换成真实内容
frontend/src/pages/OperationLogPage.tsx                新增：全局操作日志页面
frontend/src/components/layout/Sidebar.tsx             新增"操作日志"导航项
frontend/src/App.tsx                                   新增 /change-log 路由
frontend/src/test/server.ts                            新增 makeChangeLogEntry/makeGlobalChangeLogEntry 工厂 +
                                                        对应 mock handlers
```

`ChangeLogTable` 设计成"知识点级"和"全局"两种模式共用一个组件：接受 `entries: ChangeLogEntry[] | GlobalChangeLogEntry[]`，用一个 `showLocation?: boolean` 参数控制是否多渲染"知识库"/"知识点"两列（`GlobalChangeLogEntry` 特有的字段）——不是复制一份几乎一样的表格代码。

## 6. 测试计划

**后端 `GET .../answers`**：
- 返回该知识点全部答案（跨多个 coord 组、含已撤回的），不做任何过滤。
- 知识点/知识库不存在 → 404。
- 跨知识点/知识库不会串到别的知识点的答案（复用现有的 kb_id+kp_id 双重过滤惯例）。

**`buildTimelineGroups`（纯函数单测）**：
- 单版本、未撤回、`effective_time` 是今天或更早 → `status: 'current'`。
- 两个版本，`effective_time` 相同，`created_at` 不同 → 后创建的判定为 `current`（回归 resolve.py 真实算法，不是 demo 的简化版，§4.2 核心场景）。
- 一条链整体撤回（每一行 `revoked=true`）→ 所有版本（包括非最后写入的）都标 `revoked`，不是只有最后一个（回归 §4.1 跟 change-log 语义故意不同这一点）。
- 某版本 `effective_time` 晚于今天 → `not-yet-effective`，不是 `current`。
- 多个 coord 组混在同一个答案列表里传入 → 分组互不影响。

**`KnowledgePointDetailPage` "版本历史" tab**：
- 选择不同 coord 组，时间线内容切换。
- 渲染出四种状态标注中至少三种（一个测试场景很难同时凑出全部四种，分场景覆盖）。
- 只有一个 coord 组时不显示选择器多余的空态（或显示但只有一个选项，跟 demo 行为一致——待实现时选定，写死不了先，实现阶段确认）。

**`KnowledgePointDetailPage` "变更留痕" tab / `OperationLogPage`**：
- 渲染流水（动作/状态两列的中文映射正确）。
- 点击可撤回行的"撤回"，弹窗要求填写原因，成功后 toast + 列表刷新（该知识点的 change-log 多一行"撤回答案"）。
- 全局日志页面的行额外显示知识库名称/知识点标题，且能正确跳转到对应知识点详情页。
- 撤回原因留空 → 就地错误提示，不发请求。
- 全局日志页面对一个来自 KB-A 的答案执行撤回后，同一个知识点在详情页的"变更留痕" tab 里刷新也能看到这条撤回记录（回归 §4.5 缓存失效范围，两个页面共享的是同一份后端数据，不能各自缓存互不通气）。

**Sidebar / 路由**：
- 新增"操作日志"导航项可以正确跳转到 `/change-log`。
