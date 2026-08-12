# 设计：答案撤回后重新启用（issue #32）

对应 issue：[#32](https://github.com/BinLiang1990/knowledgebase/issues/32)。
现状：2026-08-10 已落了一个过渡实现 `_revive_chain_if_revoked`（三个调用点都走、PRD §8 已更新），但它是"静默恢复"且**抹掉撤回历史**（revoked_at/revoked_by/revoke_reason 置 NULL），与 issue 规格冲突。本设计补齐剩余四项：恢复原因必填、撤回历史保留、变更留痕展示"撤回→恢复"、前端感知。

## 1. 数据模型（迁移 0005）

`answer` 表新增三个链级字段（与 revoke 三件套同构，链上所有行同值）：

| 字段 | 类型 | 说明 |
|---|---|---|
| reactivated_at | DATETIME(6) NULL | 最近一次恢复时间 |
| reactivated_by | VARCHAR(100) NULL | 恢复操作人（v1 固定 admin） |
| reactivate_reason | VARCHAR(500) NULL | 恢复原因（必填校验在接口层） |

**保留粒度**：与 revoke 字段现状一致，只保留**最近一次**撤回与最近一次恢复——"撤回→恢复→再撤回→再恢复"的完整事件史需要事件表，v1 不做（写入本节即视为设计阶段确认）。恢复时 revoked_* 三字段**保留原样**（issue 明确要求，参照 `restore_knowledge_point`）。

## 2. 接口行为

`_revive_chain_if_revoked` 改名 `_reactivate_chain_if_revoked(db, kp_id, coord_hash, reactivate_reason)`：

- 链上无 revoked 行 → no-op（传了 reason 也忽略，字段可总是出现在请求里）；
- 链处于撤回态且 reason 为空/空白 → `BusinessError("该条件组合此前已被撤回，重新启用需填写原因")`；
- 否则同一事务内：整链 `revoked=False`（revoked_* 保留），写入 reactivated_* 三字段，随后调用方照常追加新版本。

三个调用点（issue 验收项 1）：`create_answer`、`edit_answer`（迁移/非迁移共用的那次对目标链的调用）、`promote_answer_to_default`。请求 schema `AnswerCreate` / `AnswerEdit` / `AnswerPromoteToDefault` 各加 `reactivate_reason: str | None`（max_length=500，仅目标链撤回态时必填）。`AnswerOut` 增加三个只读字段。

## 3. 变更留痕（issue 验收项 5）

`build_change_log` 的撤回/恢复条目改为从**保留的字段**推导，新增 action `reactivate` 与 status `reactivated`：

| 条目 | 产生条件 | time | status |
|---|---|---|---|
| 撤回（action=revoke） | `last.revoked_at is not None`（不再看 last.revoked 标志） | revoked_at | 链当前撤回态 → `revoked`；已被恢复 → **`reactivated`**（"已恢复"，表达"这次撤回已不再生效"） |
| 恢复（action=reactivate） | `last.reactivated_at is not None` | reactivated_at | 链当前非撤回态 → `live`；恢复后又被再次撤回 → `superseded` |

恢复条目：before_content=None、after_content=链上当前版本内容（恢复使其重新生效）、新字段 `reactivate_reason` 承载原因（revoke_reason 保持 None）。"恢复后又撤回"场景两个条目按各自时间排序自然正确；更早轮次的时间被字段覆盖（§1 的保留粒度限制）。

前端 `ACTION_LABEL` 加 `reactivate: '恢复答案'`，`CHANGE_LOG_STATUS_LABEL` 加 `reactivated: '已恢复'`。

版本历史（timeline.ts）只看 `answer.revoked` 标志，恢复后自然恢复正常展示，无需改动（issue 的"正确展示"以变更留痕为主载体）。

## 4. 前端（issue 验收项 4）

`WriteAnswerDialog` 增加 `groups: AnswerGroup[]` prop（详情页已加载的全部条件组，含撤回组）：

- 实时用 `diffCoord` 把当前编辑的条件与撤回组比对，命中 → 显示提示条 +「重新启用原因」必填输入框；
- 提交时带上 `reactivate_reason`；未命中时不发送该字段。

覆盖三种路径：新写答案写到撤回条件上、编辑迁移到撤回条件上、编辑撤回链自身。Vue 版界面没有"设为默认"入口，promote 的前端感知暂无载体（后端字段已备好）。

## 5. 测试

纯逻辑测试（构造 Answer 对象直接喂 `build_change_log`，零 DB）：撤回→恢复的条目序列与状态、恢复后再撤回、未恢复链行为不回归。接口层的"撤回态必填 reason"校验依赖 DB fixture，受测试库隔离问题（conftest 会重置真实库）限制暂不写，风险记录于此。

## 6. mock 同步

`frontend-mock` 暂不同步本特性（demo 的撤回链在"写答案"时本来就是静默复活的旧行为）——如需演示再单独同步。
