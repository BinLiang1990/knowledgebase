/* ============================================================
   知识库管理 · 共享数据层 + 业务逻辑 + UI 小工具
   纯前端静态原型：用 localStorage 模拟后端持久化，
   页面之间共享同一份数据，方便跨页联动测试。

   层级：知识库(KnowledgeBase) 1 --- N 知识点(KnowledgePoint) 1 --- N 答案(Answer)
   维度定义(DimensionDefinition) 是全局的，所有知识库共享一套定义；
   每个知识库可以从全局维度里"启用"其中一部分，用于本知识库的答案条件。

   一个知识点下可以同时存在多条"答案"：每条答案 = 一组维度条件(coord) + 内容 + 生效时间，
   条件不同的答案互不覆盖、并存；同一条件下再次编辑 = 生成新版本(同 coord 的版本链)。
   查询(时间 + 维度条件)时：
     - 没有给维度条件 → 用"默认答案"(coord={})；没有默认答案则回退到全部答案里最新的一条
     - 给了维度条件 → 优先找条件完全一致的答案；找不到则按"条件更具体 → 维度权重更高 → 版本更新"的顺序,
       在条件兼容(答案自己写的条件都要对上,没写的不参与比较)的答案里选最匹配的一条
   ============================================================ */

const MOCK_NOW = "2026-08-06";

const LS_KBS = "kb_mock_bases";
const LS_DIMENSIONS = "kb_mock_dimensions";
const LS_KPS = "kb_mock_kps";
const LS_ANSWERS = "kb_mock_answers";
const LS_RELATIONS = "kb_mock_relations";
const LS_SEEDED = "kb_mock_seeded_v7";

const FIELD_TYPE_LABEL = { text: "文本", number: "数值", date: "时间", boolean: "布尔" };

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ---------------- seed data ----------------
function seedIfEmpty() {
  if (localStorage.getItem(LS_SEEDED)) return;

  const bases = [
    { id: "1", name: "产品知识库", description: "产品功能说明、变更记录等知识点", status: "active", created_at: "2026-08-01T09:00:00", enabledDimKeys: ["tenant"] },
    { id: "2", name: "运维知识库", description: "运维排障手册、值班交接事项", status: "active", created_at: "2026-08-04T09:00:00", enabledDimKeys: ["tenant"] },
  ];

  // 维度先只保留"租户"一个，后续需要别的维度(如 Priority、姓名)时，到「维度管理」里按需新增即可
  const dimensions = [
    { key: "tenant", label: "租户", field_type: "text", weight: 90, default_value: "默认租户", status: "active" },
  ];

  const kps = [
    { kbId: "1", id: "1", title: "退款政策", status: "active", operator: "admin", created_at: "2026-08-01T09:00:00" },
    { kbId: "1", id: "2", title: "会员等级说明", status: "active", operator: "admin", created_at: "2026-08-03T09:00:00" },
    { kbId: "1", id: "3", title: "发票开具流程", status: "active", operator: "admin", created_at: "2026-08-05T09:00:00" },
    { kbId: "2", id: "1", title: "值班交接规范", status: "active", operator: "admin", created_at: "2026-08-04T09:00:00" },
    { kbId: "2", id: "2", title: "支付退款故障处置", status: "active", operator: "admin", created_at: "2026-08-05T09:00:00" },
  ];

  let seq = 0;
  const nid = () => "a" + (++seq);
  const answers = [
    { id: nid(), kbId: "1", kpId: "1", coord: {}, content: "订单支付完成后 7 天内，未使用/未核销的订单支持无理由退款。", time: "2026-08-01", operator: "admin", note: "初始创建", revoked: false, created_at: "2026-08-01T09:00:00" },
    { id: nid(), kbId: "1", kpId: "1", coord: {}, content: "退款政策已更新：无理由退款期限从 7 天延长至 15 天，超期需人工审核。", time: "2026-08-06", operator: "admin", note: "延长无理由退款期限", revoked: false, created_at: "2026-08-06T10:00:00" },
    { id: nid(), kbId: "1", kpId: "1", coord: { tenant: "示例租户B" }, content: "「示例租户B」按合同约定执行 30 天无理由退款，与默认政策不同。", time: "2026-08-05", operator: "admin", note: "补充租户定制说法", revoked: false, created_at: "2026-08-05T09:00:00" },

    { id: nid(), kbId: "1", kpId: "2", coord: {}, content: "会员分为普通/银卡/金卡三级，按累计消费金额自动升级，权益详见会员中心。", time: "2026-08-03", operator: "admin", note: "初始创建", revoked: false, created_at: "2026-08-03T09:00:00" },

    { id: nid(), kbId: "1", kpId: "3", coord: {}, content: "订单完成后可在「我的订单」里申请开票，1-3 个工作日内开出。", time: "2026-08-05", operator: "admin", note: "初始创建", revoked: false, created_at: "2026-08-05T09:00:00" },
    { id: nid(), kbId: "1", kpId: "3", coord: { tenant: "示例租户B" }, content: "「示例租户B」需要先在后台提交对公发票信息，审核通过后才能申请开票。", time: "2026-08-05", operator: "admin", note: "补充租户定制说法", revoked: false, created_at: "2026-08-05T09:30:00" },

    { id: nid(), kbId: "2", kpId: "1", coord: {}, content: "值班交接需在群里同步当前故障与待办事项，交接人确认后方可下班。", time: "2026-08-04", operator: "admin", note: "初始创建", revoked: false, created_at: "2026-08-04T09:00:00" },
    { id: nid(), kbId: "2", kpId: "1", coord: { tenant: "示例租户B" }, content: "「示例租户B」的值班交接补充说明：额外检查监控大盘并同步给对方值班群。", time: "2026-08-04", operator: "admin", note: "补充租户定制说法", revoked: false, created_at: "2026-08-04T09:30:00" },

    { id: nid(), kbId: "2", kpId: "2", coord: {}, content: "用户按退款政策发起的退款若支付渠道执行失败，先在工单系统登记异常，再触发人工退款补偿流程，处理时限 24 小时内完成。", time: "2026-08-05", operator: "admin", note: "初始创建", revoked: false, created_at: "2026-08-05T09:00:00" },
  ];

  // 预置两条答案关联：一条 AI 生成的跨知识库关联(其中一端内容已更新，演示 stale 角标)，
  // 一条手动添加的同库跨知识点关联
  const relations = [
    {
      id: "r1",
      a: { kbId: "1", kpId: "1", coordKey: "(默认)", coord: {} },
      b: { kbId: "2", kpId: "2", coordKey: "(默认)", coord: {} },
      contentA: "订单支付完成后 7 天内，未使用/未核销的订单支持无理由退款。",
      contentB: "用户按退款政策发起的退款若支付渠道执行失败，先在工单系统登记异常，再触发人工退款补偿流程，处理时限 24 小时内完成。",
      description: "两条答案主题相关：「退款政策」（产品知识库）规定了面向用户的无理由退款期限与口径；「支付退款故障处置」（运维知识库）描述退款执行失败时的登记与人工补偿流程。前者是政策口径，后者是该政策落地时异常场景的执行预案，二者互补，未见冲突。",
      source: "ai", similarity: 0.31, model: "mock-llm", operator: "admin", created_at: "2026-08-06T11:00:00",
    },
    {
      id: "r2",
      a: { kbId: "1", kpId: "1", coordKey: "tenant:示例租户B", coord: { tenant: "示例租户B" } },
      b: { kbId: "1", kpId: "3", coordKey: "tenant:示例租户B", coord: { tenant: "示例租户B" } },
      contentA: "「示例租户B」按合同约定执行 30 天无理由退款，与默认政策不同。",
      contentB: "「示例租户B」需要先在后台提交对公发票信息，审核通过后才能申请开票。",
      description: "同为「示例租户B」的定制口径：退款按合同约定 30 天执行，开票前需先提交对公发票信息并通过审核。客服为该租户处理“退款后重新开票”类诉求时，需同时遵循这两条约定。",
      source: "manual", similarity: null, model: null, operator: "admin", created_at: "2026-08-06T14:00:00",
    },
  ];

  localStorage.setItem(LS_KBS, JSON.stringify(bases));
  localStorage.setItem(LS_DIMENSIONS, JSON.stringify(dimensions));
  localStorage.setItem(LS_KPS, JSON.stringify(kps));
  localStorage.setItem(LS_ANSWERS, JSON.stringify(answers));
  localStorage.setItem(LS_RELATIONS, JSON.stringify(relations));
  localStorage.setItem(LS_SEEDED, "1");
}

function resetDemoData() {
  localStorage.removeItem(LS_KBS);
  localStorage.removeItem(LS_DIMENSIONS);
  localStorage.removeItem(LS_KPS);
  localStorage.removeItem(LS_ANSWERS);
  localStorage.removeItem(LS_RELATIONS);
  localStorage.removeItem(LS_SEEDED);
  seedIfEmpty();
}

// ---------------- storage access: 知识库 ----------------
function getKnowledgeBases() { return JSON.parse(localStorage.getItem(LS_KBS) || "[]"); }
function saveKnowledgeBases(list) { localStorage.setItem(LS_KBS, JSON.stringify(list)); }
function getActiveKnowledgeBases() { return getKnowledgeBases().filter(b => b.status === "active"); }
function getKnowledgeBase(id) { return getKnowledgeBases().find(b => b.id === id); }

function nextKbId() {
  const bases = getKnowledgeBases();
  const max = bases.reduce((m, b) => Math.max(m, parseInt(b.id, 10) || 0), 0);
  return String(max + 1);
}

function knowledgeBaseKpCount(kbId) {
  return getKnowledgePoints(kbId).filter(k => k.status === "active").length;
}

// 本知识库"启用"的维度定义(全局有效 且 本知识库勾选启用)
function getKbEnabledDims(kbId) {
  const kb = getKnowledgeBase(kbId);
  const enabled = new Set((kb && kb.enabledDimKeys) || []);
  return getActiveDimensions().filter(d => enabled.has(d.key));
}
function setKbEnabledDims(kbId, keys) {
  const bases = getKnowledgeBases();
  const b = bases.find(x => x.id === kbId);
  if (!b) return;
  b.enabledDimKeys = keys;
  saveKnowledgeBases(bases);
}

function addKnowledgeBase({ name, description }) {
  const bases = getKnowledgeBases();
  const id = nextKbId();
  bases.push({ id, name, description: description || "", status: "active", created_at: new Date().toISOString(), enabledDimKeys: [] });
  saveKnowledgeBases(bases);
  return id;
}

function updateKnowledgeBase(id, patch) {
  const bases = getKnowledgeBases();
  const b = bases.find(x => x.id === id);
  if (!b) return { ok: false, error: "知识库不存在。" };
  Object.assign(b, patch);
  saveKnowledgeBases(bases);
  return { ok: true };
}

function toggleKnowledgeBaseStatus(id) {
  const bases = getKnowledgeBases();
  const b = bases.find(x => x.id === id);
  if (!b) return;
  b.status = b.status === "active" ? "deprecated" : "active";
  saveKnowledgeBases(bases);
}

// ---------------- storage access: 维度定义(全局) ----------------
function getDimensions() { return JSON.parse(localStorage.getItem(LS_DIMENSIONS) || "[]"); }
function saveDimensions(list) { localStorage.setItem(LS_DIMENSIONS, JSON.stringify(list)); }
function getActiveDimensions() { return getDimensions().filter(d => d.status === "active"); }
function dimByKey(key) { return getDimensions().find(d => d.key === key); }

// ---------------- storage access: 知识点 / 答案 ----------------
function getAllKnowledgePoints() { return JSON.parse(localStorage.getItem(LS_KPS) || "[]"); }
function saveKnowledgePoints(list) { localStorage.setItem(LS_KPS, JSON.stringify(list)); }
function getKnowledgePoints(kbId) { return getAllKnowledgePoints().filter(k => k.kbId === kbId); }
function getKnowledgePoint(kbId, id) { return getAllKnowledgePoints().find(k => k.kbId === kbId && k.id === id); }

function getAllAnswers() { return JSON.parse(localStorage.getItem(LS_ANSWERS) || "[]"); }
function saveAnswers(list) { localStorage.setItem(LS_ANSWERS, JSON.stringify(list)); }
function getAnswersByKp(kbId, kpId) { return getAllAnswers().filter(a => a.kbId === kbId && a.kpId === kpId); }

function nextKpId(kbId) {
  const kps = getKnowledgePoints(kbId);
  const max = kps.reduce((m, k) => Math.max(m, parseInt(k.id, 10) || 0), 0);
  return String(max + 1);
}

// ---------------- 维度条件(coord) 相关工具 ----------------
function coordKeyOf(coord) {
  const ks = Object.keys(coord).filter(k => coord[k] !== undefined && coord[k] !== "");
  return ks.length ? ks.sort().map(k => k + ":" + coord[k]).join("|") : "(默认)";
}
function coordSpec(coord) { return Object.keys(coord).filter(k => coord[k] !== undefined && coord[k] !== "").length; }
function coordWeight(coord) {
  return Object.keys(coord).filter(k => coord[k] !== undefined && coord[k] !== "")
    .reduce((sum, k) => sum + ((dimByKey(k) || {}).weight || 0), 0);
}
function coordLabel(coord) {
  const ks = Object.keys(coord).filter(k => coord[k] !== undefined && coord[k] !== "");
  if (!ks.length) return `<span class="tag gray">默认答案 · 处处适用</span>`;
  return ks.map(k => {
    const d = dimByKey(k);
    return `<span class="tag blue">${escapeHtml(d ? d.label : k)} = ${escapeHtml(dimValueDisplay(d, coord[k]))}</span>`;
  }).join("");
}
function coordText(coord) {
  const ks = Object.keys(coord).filter(k => coord[k] !== undefined && coord[k] !== "");
  if (!ks.length) return "默认";
  return ks.sort().map(k => (dimByKey(k) ? dimByKey(k).label : k) + " = " + coord[k]).join(" 且 ");
}
// 条件兼容：答案自己写的每个条件都必须和查询条件相符；查询没问到的、或答案没写的，都不参与比较
function coordCompatible(coord, Q) {
  for (const k in coord) {
    if (coord[k] === undefined || coord[k] === "") continue;
    if (Q[k] === undefined || Q[k] === "") continue; // 查询未指定该维度，不过滤
    if (String(coord[k]) !== String(Q[k])) return false;
  }
  return true;
}

// 按 coord 分组，取每组在 atTime 时点"最新且未撤回"的一条(即该组的"当前版本")
function liveGroups(kbId, kpId, atTime) {
  const groups = new Map();
  getAnswersByKp(kbId, kpId).forEach(a => {
    const k = coordKeyOf(a.coord);
    if (!groups.has(k)) groups.set(k, { coordKey: k, coord: a.coord, chain: [] });
    groups.get(k).chain.push(a);
  });
  const out = [];
  for (const g of groups.values()) {
    g.chain.sort((x, y) => y.time.localeCompare(x.time));
    const live = g.chain.find(a => a.time <= atTime && !a.revoked);
    if (!live) continue;
    out.push({
      coordKey: g.coordKey, coord: g.coord, chain: g.chain, live,
      spec: coordSpec(g.coord), weight: coordWeight(g.coord),
      versionCount: g.chain.filter(a => !a.revoked).length,
    });
  }
  return out;
}

// 查询解析：时间 + 维度条件 → 命中哪一组答案
// status: 'exact'(条件完全对上) | 'weighted'(条件不完全对上，按权重规则回退匹配) |
//         'default'(未给条件，命中默认答案) | 'fallback-latest'(未给条件、也没有默认答案，取全局最新)｜'none'(无匹配)
function resolveAnswer(kbId, kpId, Q, atTime) {
  const groups = liveGroups(kbId, kpId, atTime);
  if (!groups.length) return { status: "none" };
  const qKeys = Object.keys(Q).filter(k => Q[k] !== undefined && Q[k] !== "");

  if (!qKeys.length) {
    const def = groups.find(g => g.spec === 0);
    if (def) return { status: "default", ...def, groups };
    const latest = [...groups].sort((a, b) => b.live.time.localeCompare(a.live.time))[0];
    return { status: "fallback-latest", ...latest, groups };
  }

  const candidates = groups.filter(g => coordCompatible(g.coord, Q));
  if (!candidates.length) return { status: "none", groups };
  // A candidate fully explained by what was queried (none of its own
  // dimensions go unasked) outranks one that also pins a dimension the
  // query never specified, regardless of spec — e.g. a plain 人员=Eden
  // match beats a 人员=Eden 且 场景=... rule when 场景 wasn't queried.
  const coveredByQuery = (coord) =>
    Object.keys(coord).filter(k => coord[k] !== undefined && coord[k] !== "").every(k => qKeys.includes(k));
  candidates.sort((a, b) =>
    Number(coveredByQuery(b.coord)) - Number(coveredByQuery(a.coord)) ||
    b.spec - a.spec || b.weight - a.weight || b.live.time.localeCompare(a.live.time));
  const top = candidates[0];
  const exact = top.spec === qKeys.length && Object.keys(top.coord).every(k => String(top.coord[k]) === String(Q[k]));
  return { status: exact ? "exact" : "weighted", ...top, groups, candidates };
}

// ---------------- CRUD: 知识点 ----------------
function createKnowledgePoint(kbId, { title, content, effective_time, note }) {
  const kps = getAllKnowledgePoints();
  const id = nextKpId(kbId);
  kps.push({ kbId, id, title, status: "active", operator: "admin", created_at: new Date().toISOString() });
  saveKnowledgePoints(kps);
  if (content && content.trim()) {
    addAnswer(kbId, id, { coord: {}, content: content.trim(), effective_time, note: note || "初始创建" });
  }
  return id;
}

function updateKnowledgePointTitle(kbId, id, title) {
  const kps = getAllKnowledgePoints();
  const kp = kps.find(k => k.kbId === kbId && k.id === id);
  if (!kp) return { ok: false, error: "知识点不存在。" };
  kp.title = title;
  saveKnowledgePoints(kps);
  return { ok: true };
}

function softDeleteKnowledgePoint(kbId, id, { reason }) {
  const kps = getAllKnowledgePoints();
  const kp = kps.find(k => k.kbId === kbId && k.id === id);
  if (!kp) return { ok: false, error: "知识点不存在。" };
  kp.status = "deleted";
  kp.deleted_at = new Date().toISOString();
  kp.delete_reason = reason || "";
  kp.operator = "admin";
  saveKnowledgePoints(kps);
  return { ok: true };
}

function restoreKnowledgePoint(kbId, id) {
  const kps = getAllKnowledgePoints();
  const kp = kps.find(k => k.kbId === kbId && k.id === id);
  if (!kp) return { ok: false, error: "知识点不存在。" };
  kp.status = "active";
  kp.deleted_at = null;
  kp.delete_reason = "";
  saveKnowledgePoints(kps);
  return { ok: true };
}

function listActiveKPs(kbId) { return getKnowledgePoints(kbId).filter(k => k.status === "active"); }
function listTrash(kbId) { return getKnowledgePoints(kbId).filter(k => k.status === "deleted"); }

// ---------------- CRUD: 答案 ----------------
function addAnswer(kbId, kpId, { coord, content, effective_time, note }) {
  const answers = getAllAnswers();
  answers.push({
    id: "a" + Date.now() + Math.floor(Math.random() * 1000),
    kbId, kpId, coord: coord || {}, content, time: effective_time,
    operator: "admin", note: note || "", src: "人工填报", revoked: false, created_at: new Date().toISOString(),
  });
  saveAnswers(answers);
}

// 编辑一条答案：条件不变 = 同组追加新版本；条件改了 = 旧组整体撤回，在新条件下新增一组
function editAnswer(kbId, kpId, oldCoord, { coord, content, effective_time, note }) {
  const oldKey = coordKeyOf(oldCoord), newKey = coordKeyOf(coord);
  if (oldKey !== newKey) {
    revokeAnswerGroup(kbId, kpId, oldCoord, "条件已迁移至「" + coordText(coord) + "」");
  }
  addAnswer(kbId, kpId, { coord, content, effective_time, note: note || (oldKey !== newKey ? "条件迁移" : "内容更新") });
}

function revokeAnswerGroup(kbId, kpId, coord, reason) {
  const answers = getAllAnswers();
  const key = coordKeyOf(coord);
  const now = new Date().toISOString();
  answers.filter(a => a.kbId === kbId && a.kpId === kpId && coordKeyOf(a.coord) === key).forEach(a => {
    a.revoked = true; a.revoked_at = now; a.revoked_by = "admin"; a.revoke_reason = reason || "";
  });
  saveAnswers(answers);
}

// 设为默认：把这条答案的内容，写成默认答案(coord={})的新版本
function promoteToDefault(kbId, kpId, content, effective_time) {
  addAnswer(kbId, kpId, { coord: {}, content, effective_time, note: "设为默认答案" });
}

// 变更留痕：按答案历史推导出的动作流水(写答案 / 改答案 / 撤回答案)
// 每一行附带 kbId/kpId/coord，方便"全局操作日志"页面跨知识库展示、并支持直接从日志行撤回
function changeLogRows(answers) {
  const groups = new Map();
  answers.forEach(a => {
    const k = a.kbId + "::" + a.kpId + "::" + coordKeyOf(a.coord);
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(a);
  });
  const log = [];
  for (const chain of groups.values()) {
    chain.sort((x, y) => x.created_at.localeCompare(y.created_at));
    chain.forEach((a, i) => {
      const isLast = i === chain.length - 1;
      const state = !isLast ? "已被新版替代" : (a.revoked ? "已撤回" : "生效");
      log.push({
        t: a.created_at, who: a.operator, act: i === 0 ? "写答案" : "改答案",
        tgt: coordText(a.coord), before: i === 0 ? "—" : chain[i - 1].content, after: a.content,
        src: a.src || "人工填报", state, coord: a.coord, kbId: a.kbId, kpId: a.kpId,
        revocable: isLast && !a.revoked,
      });
    });
    const last = chain[chain.length - 1];
    if (last.revoked) {
      log.push({
        t: last.revoked_at || last.created_at, who: last.revoked_by || "admin", act: "撤回答案",
        tgt: coordText(last.coord), before: last.content, after: "(已撤回：" + (last.revoke_reason || "无说明") + ")",
        src: "人工编辑", state: "生效", coord: last.coord, kbId: last.kbId, kpId: last.kpId,
        revocable: false,
      });
    }
  }
  log.sort((a, b) => b.t.localeCompare(a.t));
  return log;
}
function buildChangeLog(kbId, kpId) { return changeLogRows(getAnswersByKp(kbId, kpId)); }
function buildGlobalChangeLog() { return changeLogRows(getAllAnswers()); }

// ---------------- 知识库统计(点 3：顶部统计卡) ----------------
function computeKbStats(kbId) {
  const kps = listActiveKPs(kbId);
  let activeAnswers = 0, todayChanges = 0;
  kps.forEach(kp => {
    const answers = getAnswersByKp(kbId, kp.id);
    activeAnswers += answers.filter(a => !a.revoked).length;
    todayChanges += answers.filter(a => a.created_at.slice(0, 10) === MOCK_NOW || (a.revoked_at || "").slice(0, 10) === MOCK_NOW).length;
  });
  return {
    subjectCount: kps.length,
    activeAnswers,
    enabledDimCount: getKbEnabledDims(kbId).length,
    todayChanges,
  };
}

// ---------------- shared KP / Answer 弹窗 wiring ----------------
let CURRENT_KB_ID = null;
function setCurrentKb(kbId) { CURRENT_KB_ID = kbId; }
function getKbIdFromUrl() { return new URLSearchParams(location.search).get("kb") || ""; }

function valueInputHtmlFor(def, value) {
  value = value ?? "";
  if (def.field_type === "number") return `<input type="number" data-dim="${escapeHtml(def.key)}" value="${escapeHtml(value)}" />`;
  if (def.field_type === "date") return `<input type="date" data-dim="${escapeHtml(def.key)}" value="${escapeHtml(value)}" />`;
  if (def.field_type === "boolean") {
    return `<select data-dim="${escapeHtml(def.key)}">
      <option value="true" ${value === "true" ? "selected" : ""}>是</option>
      <option value="false" ${value === "false" ? "selected" : ""}>否</option>
    </select>`;
  }
  const uniq = [...new Set(getAllAnswers().map(a => a.coord[def.key]).filter(Boolean))];
  return `<input type="text" data-dim="${escapeHtml(def.key)}" value="${escapeHtml(value)}" list="dl-${escapeHtml(def.key)}" placeholder="输入或选择取值" />
    <datalist id="dl-${escapeHtml(def.key)}">${uniq.map(v => `<option value="${escapeHtml(v)}"></option>`).join("")}</datalist>`;
}

function validateDimValue(fieldType, raw) {
  if (raw === undefined || raw === null || raw === "") return { ok: true, value: undefined };
  if (fieldType === "number") {
    const n = Number(raw);
    if (Number.isNaN(n)) return { ok: false, error: "必须是数值" };
    return { ok: true, value: String(n) };
  }
  if (fieldType === "date") {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(raw) || Number.isNaN(new Date(raw + "T00:00:00Z").getTime())) {
      return { ok: false, error: "必须是合法日期(YYYY-MM-DD)" };
    }
    return { ok: true, value: raw };
  }
  if (fieldType === "boolean") return { ok: true, value: raw === "true" ? "true" : "false" };
  return { ok: true, value: String(raw) };
}

// 答案的"适用条件"编辑器：多行 维度 + 取值，维度只能从本知识库启用的维度里选
let COND_ROWS = [];
function condRowsHtml() {
  const dims = getKbEnabledDims(CURRENT_KB_ID);
  return COND_ROWS.map((row, i) => {
    const def = dimByKey(row.key);
    return `<div class="form-row" style="margin-bottom:8px">
      <select onchange="COND_ROWS[${i}].key=this.value;COND_ROWS[${i}].value='';renderCondRows()" style="min-width:120px">
        <option value="">选择维度…</option>
        ${dims.map(d => `<option value="${escapeHtml(d.key)}" ${row.key === d.key ? "selected" : ""}>${escapeHtml(d.label)}</option>`).join("")}
      </select>
      <span class="f-val-wrap">${def ? valueInputHtmlFor(def, row.value) : `<input type="text" disabled placeholder="先选维度" />`}</span>
      <a class="danger" style="font-size:13px" onclick="COND_ROWS.splice(${i},1);renderCondRows()">移除</a>
    </div>`;
  }).join("");
}
function renderCondRows() {
  const box = document.getElementById("ansCondRows");
  if (box) box.innerHTML = condRowsHtml();
}
function addCondRow() { COND_ROWS.push({ key: "", value: "" }); renderCondRows(); }
function readCondRows(hintEl) {
  const coord = {};
  let error = "";
  document.querySelectorAll("#ansCondRows [data-dim]").forEach(inp => {
    const def = dimByKey(inp.dataset.dim);
    const v = validateDimValue(def.field_type, inp.value);
    if (!v.ok) { error = `「${def.label}」${v.error}`; return; }
    if (v.value !== undefined) coord[inp.dataset.dim] = v.value;
  });
  if (error) { if (hintEl) hintEl.textContent = error; return null; }
  return coord;
}

function openAddModal() {
  document.getElementById("kpModalTitle").textContent = "新增知识点";
  document.getElementById("kpId").value = "";
  document.getElementById("kpTitle").value = "";
  document.getElementById("kpContent").value = "";
  document.getElementById("kpTime").value = MOCK_NOW;
  document.getElementById("kpFormHint").textContent = "";
  openModal("kpMask");
}

function submitKp(afterSave) {
  const title = document.getElementById("kpTitle").value.trim();
  const content = document.getElementById("kpContent").value.trim();
  const time = document.getElementById("kpTime").value;
  const hint = document.getElementById("kpFormHint");
  if (!title || !time) { hint.textContent = "标题、生效时间为必填项。"; return; }
  const newId = createKnowledgePoint(CURRENT_KB_ID, { title, content, effective_time: time });
  toast(`已创建知识点 ID ${newId}`, "ok");
  closeModal("kpMask");
  if (afterSave) afterSave(); else location.reload();
}

function openDeleteModal(id, title) {
  document.getElementById("delId").value = id;
  document.getElementById("delTitle").textContent = title;
  document.getElementById("delReason").value = "";
  openModal("delMask");
}

function submitDelete(afterSave) {
  const id = document.getElementById("delId").value;
  const reason = document.getElementById("delReason").value.trim();
  if (!reason) { toast("请填写删除原因", "err"); return; }
  const res = softDeleteKnowledgePoint(CURRENT_KB_ID, id, { reason });
  if (!res.ok) { toast(res.error, "err"); return; }
  toast(`已删除 ID ${id}，可在回收站恢复`, "ok");
  closeModal("delMask");
  if (afterSave) afterSave(); else location.reload();
}

// 写答案 / 编辑答案 共用弹窗
function openWriteAnswerModal(kpId, existing) {
  document.getElementById("ansKpId").value = kpId;
  document.getElementById("ansOldCoord").value = existing ? JSON.stringify(existing.coord) : "{}";
  document.getElementById("ansModalTitle").textContent = existing ? "编辑答案" : "写一条答案";
  document.getElementById("ansContent").value = existing ? existing.content : "";
  document.getElementById("ansTime").value = MOCK_NOW;
  document.getElementById("ansNote").value = "";
  document.getElementById("ansFormHint").textContent = "";
  COND_ROWS = existing ? Object.keys(existing.coord).map(k => ({ key: k, value: existing.coord[k] })) : [];
  renderCondRows();
  openModal("ansMask");
}

function submitAnswer(afterSave) {
  const kpId = document.getElementById("ansKpId").value;
  const oldCoord = JSON.parse(document.getElementById("ansOldCoord").value || "{}");
  const content = document.getElementById("ansContent").value.trim();
  const time = document.getElementById("ansTime").value;
  const note = document.getElementById("ansNote").value.trim();
  const hint = document.getElementById("ansFormHint");
  if (!content || !time) { hint.textContent = "答案内容、生效时间为必填项。"; return; }
  const coord = readCondRows(hint);
  if (coord === null) return;

  const isEdit = document.getElementById("ansModalTitle").textContent === "编辑答案";
  if (isEdit) editAnswer(CURRENT_KB_ID, kpId, oldCoord, { coord, content, effective_time: time, note });
  else addAnswer(CURRENT_KB_ID, kpId, { coord, content, effective_time: time, note });

  toast("已保存答案", "ok");
  closeModal("ansMask");
  if (afterSave) afterSave();
}

function openPromoteModal(kpId, content) {
  document.getElementById("promoteKpId").value = kpId;
  document.getElementById("promoteContent").textContent = content;
  document.getElementById("promoteTime").value = MOCK_NOW;
  openModal("promoteMask");
}
function submitPromote(afterSave) {
  const kpId = document.getElementById("promoteKpId").value;
  const content = document.getElementById("promoteContent").textContent;
  const time = document.getElementById("promoteTime").value;
  promoteToDefault(CURRENT_KB_ID, kpId, content, time);
  toast("已设为默认答案", "ok");
  closeModal("promoteMask");
  if (afterSave) afterSave();
}

function openRevokeAnswerModal(kbId, kpId, coord, contentPreview) {
  document.getElementById("revokeKbId").value = kbId;
  document.getElementById("revokeKpId").value = kpId;
  document.getElementById("revokeCoord").value = JSON.stringify(coord);
  document.getElementById("revokeContent").textContent = contentPreview;
  document.getElementById("revokeReason").value = "";
  openModal("revokeMask");
}
function submitRevoke(afterSave) {
  const kbId = document.getElementById("revokeKbId").value;
  const kpId = document.getElementById("revokeKpId").value;
  const coord = JSON.parse(document.getElementById("revokeCoord").value || "{}");
  const reason = document.getElementById("revokeReason").value.trim();
  if (!reason) { toast("请填写撤回原因", "err"); return; }
  revokeAnswerGroup(kbId, kpId, coord, reason);
  toast("已撤回该条件下的答案", "ok");
  closeModal("revokeMask");
  if (afterSave) afterSave();
}

// ---------------- CRUD: 维度定义(全局) ----------------
function addDimension(def) {
  const dims = getDimensions();
  if (dims.some(d => d.key === def.key)) return { ok: false, error: `维度 key「${def.key}」已存在。` };
  dims.push({ ...def, status: "active" });
  saveDimensions(dims);
  return { ok: true };
}

function updateDimension(key, patch) {
  const dims = getDimensions();
  const d = dims.find(x => x.key === key);
  if (!d) return { ok: false, error: "维度不存在。" };
  Object.assign(d, patch);
  saveDimensions(dims);
  return { ok: true };
}

function toggleDimensionStatus(key) {
  const dims = getDimensions();
  const d = dims.find(x => x.key === key);
  if (!d) return;
  d.status = d.status === "active" ? "deprecated" : "active";
  saveDimensions(dims);
}

function dimensionUsageCount(key) {
  return getAllAnswers().filter(a => !a.revoked && a.coord[key] !== undefined && a.coord[key] !== "").length;
}

/* ---------------- 答案关联 (Answer Relations) ----------------
   见 docs/PRD-答案关联.md。演示实现：
   - "向量召回"用字符 bigram 的 Dice 相似度模拟（正式环境走 Ollama 向量模型 + 余弦）；
   - "关联描述"用本地模板模拟（正式环境走 LLM 批量生成）。
   关联端点 = { kbId, kpId, coordKey, coord }，即一条版本链；描述始终基于两端当前生效版本。
   同一对答案只有一条记录(端点按 key 排序规范化)；source=manual 的不被 AI 分析覆盖。 */

const REL_TOP_K = 10;
const REL_MIN_SIM = 0.04;

function getRelations() { return JSON.parse(localStorage.getItem(LS_RELATIONS) || "[]"); }
function saveRelations(list) { localStorage.setItem(LS_RELATIONS, JSON.stringify(list)); }

function relEndpointKey(e) { return e.kbId + "::" + e.kpId + "::" + e.coordKey; }
function relPairKey(x, y) {
  const kx = relEndpointKey(x), ky = relEndpointKey(y);
  return kx <= ky ? kx + "##" + ky : ky + "##" + kx;
}
function relationsForKp(kbId, kpId) {
  return getRelations().filter(r =>
    (r.a.kbId === kbId && r.a.kpId === kpId) || (r.b.kbId === kbId && r.b.kpId === kpId));
}
function relationsForChain(kbId, kpId, coordKey) {
  return getRelations().filter(r =>
    (r.a.kbId === kbId && r.a.kpId === kpId && r.a.coordKey === coordKey) ||
    (r.b.kbId === kbId && r.b.kpId === kpId && r.b.coordKey === coordKey));
}
function findRelationByPair(x, y) {
  const pk = relPairKey(x, y);
  return getRelations().find(r => relPairKey(r.a, r.b) === pk);
}
function deleteRelation(id) { saveRelations(getRelations().filter(r => r.id !== id)); }
function updateRelation(id, patch) {
  const list = getRelations();
  const r = list.find(x => x.id === id);
  if (!r) return;
  Object.assign(r, patch);
  saveRelations(list);
}

// x/y = 完整端点 { kbId, kpId, coordKey, coord, content, title, kbName }；落库时端点排序规范化
function makeRelation(x, y, description, source, similarity) {
  const [a, b] = relEndpointKey(x) <= relEndpointKey(y) ? [x, y] : [y, x];
  const rel = {
    id: "r" + Date.now() + Math.floor(Math.random() * 1000),
    a: { kbId: a.kbId, kpId: a.kpId, coordKey: a.coordKey, coord: a.coord },
    b: { kbId: b.kbId, kpId: b.kpId, coordKey: b.coordKey, coord: b.coord },
    contentA: a.content, contentB: b.content,
    description, source, similarity: similarity ?? null,
    model: source === "ai" ? "mock-llm" : null,
    operator: "admin", created_at: new Date().toISOString(),
  };
  const list = getRelations();
  list.push(rel);
  saveRelations(list);
  return rel;
}

// 端点解析：返回 { kbObj, kp, live(该链当前生效组), state }
// state: ok | revoked(链无生效版本) | kp-deleted | missing
function relEndpointInfo(e) {
  const kbObj = getKnowledgeBase(e.kbId);
  const kp = kbObj ? getKnowledgePoint(e.kbId, e.kpId) : null;
  let live = null;
  if (kp) live = liveGroups(e.kbId, e.kpId, MOCK_NOW).find(g => g.coordKey === e.coordKey) || null;
  let state = "ok";
  if (!kbObj || !kp) state = "missing";
  else if (kp.status === "deleted") state = "kp-deleted";
  else if (!live) state = "revoked";
  return { kbObj, kp, live, state };
}

// 端点解析(完整版)：附带 title/kbName/当前内容，供描述生成使用；不可用返回 null
function relEndpointFull(e) {
  const info = relEndpointInfo(e);
  if (info.state !== "ok") return null;
  return { kbId: e.kbId, kpId: e.kpId, coordKey: e.coordKey, coord: e.coord, content: info.live.live.content, title: info.kp.title, kbName: info.kbObj.name };
}

// ---- 相似召回（模拟向量）----
function relBigrams(s) {
  s = String(s || "").replace(/\s+/g, "");
  const set = new Set();
  for (let i = 0; i < s.length - 1; i++) set.add(s.slice(i, i + 2));
  return set;
}
function relSimilarity(x, y) {
  const A = relBigrams(x), B = relBigrams(y);
  if (!A.size || !B.size) return 0;
  let inter = 0;
  A.forEach(g => { if (B.has(g)) inter++; });
  return 2 * inter / (A.size + B.size);
}

// 全库全部有效端点(所有启用知识库 × 未删除知识点 × 有生效版本的链)
function collectAllEndpoints() {
  const out = [];
  getActiveKnowledgeBases().forEach(b => {
    listActiveKPs(b.id).forEach(kp => {
      liveGroups(b.id, kp.id, MOCK_NOW).forEach(g => {
        out.push({ kbId: b.id, kpId: kp.id, coordKey: g.coordKey, coord: g.coord, content: g.live.content, title: kp.title, kbName: b.name });
      });
    });
  });
  return out;
}

function clipText(s, n) {
  s = String(s || "");
  return s.length > n ? s.slice(0, n) + "…" : s;
}

// ---- 描述生成（模拟 LLM）----
function mockRelationDescription(x, y) {
  const condOf = e => coordText(e.coord) === "默认" ? "默认条件（处处适用）" : "「" + coordText(e.coord) + "」条件";
  const samePoint = x.kbId === y.kbId && x.kpId === y.kpId;
  const sameKb = x.kbId === y.kbId;
  const head = samePoint
    ? `同一知识点「${x.title}」下两个不同条件的说法。`
    : `两条答案主题相关：「${x.title}」（${x.kbName}）与「${y.title}」（${y.kbName}${sameKb ? "" : "，跨知识库"}）。`;
  const tail = samePoint
    ? "两者按各自适用条件并存，查询时按条件取用；使用时注意二者在口径上的差异。"
    : "两者内容互补：使用其中一条时建议同时参考另一条；若口径出现不一致，需回溯核对并修订较旧的一条。";
  return `${head}前者在${condOf(x)}下的说法是：“${clipText(x.content, 42)}”；后者在${condOf(y)}下的说法是：“${clipText(y.content, 42)}”。${tail}`;
}

// ---- 分析执行：以 center 端点为中心，全库召回 Top-K 并生成/更新关联 ----
// center = 完整端点；返回 { found, created, updated, skipped }
function runRelationAnalysis(center) {
  const centerText = center.title + " " + center.content;
  const candidates = collectAllEndpoints()
    .filter(e => relEndpointKey(e) !== relEndpointKey(center))
    .map(e => ({ e, sim: relSimilarity(centerText, e.title + " " + e.content) }))
    .filter(x => x.sim >= REL_MIN_SIM)
    .sort((m, n) => n.sim - m.sim)
    .slice(0, REL_TOP_K);

  let created = 0, updated = 0, skipped = 0;
  candidates.forEach(({ e, sim }) => {
    const exist = findRelationByPair(center, e);
    if (exist && exist.source === "manual") { skipped++; return; } // 手动维护的不覆盖
    const description = mockRelationDescription(center, e);
    if (exist) {
      const [a] = relEndpointKey(center) <= relEndpointKey(e) ? [center, e] : [e, center];
      const centerIsA = relEndpointKey(a) === relEndpointKey(center);
      updateRelation(exist.id, {
        description,
        contentA: centerIsA ? center.content : e.content,
        contentB: centerIsA ? e.content : center.content,
        similarity: Math.round(sim * 100) / 100,
        source: "ai", model: "mock-llm", created_at: new Date().toISOString(),
      });
      updated++;
    } else {
      makeRelation(center, e, description, "ai", Math.round(sim * 100) / 100);
      created++;
    }
  });
  return { found: candidates.length, created, updated, skipped };
}

// ---- 知识点级自动关联：对该知识点全部有效链逐条执行分析，聚合结果 ----
function runAutoRelate(kbId, kpId) {
  const kpObj = getKnowledgePoint(kbId, kpId), kbObj = getKnowledgeBase(kbId);
  const total = { chains: 0, found: 0, created: 0, updated: 0, skipped: 0 };
  if (!kpObj || !kbObj) return total;
  liveGroups(kbId, kpId, MOCK_NOW).forEach(g => {
    const center = { kbId, kpId, coordKey: g.coordKey, coord: g.coord, content: g.live.content, title: kpObj.title, kbName: kbObj.name };
    const r = runRelationAnalysis(center);
    total.chains++;
    total.found += r.found;
    total.created += r.created;
    total.updated += r.updated;
    total.skipped += r.skipped;
  });
  return total;
}

// ---------------- UI helpers ----------------
function toast(msg, type) {
  const box = document.getElementById("toast");
  if (!box) return;
  const el = document.createElement("div");
  el.className = "toast-item " + (type || "info");
  el.textContent = msg;
  box.appendChild(el);
  setTimeout(() => el.remove(), 2600);
}

function openModal(id) { document.getElementById(id).classList.add("show"); }
function closeModal(id) { document.getElementById(id).classList.remove("show"); }

document.addEventListener("click", (e) => {
  if (e.target.classList && e.target.classList.contains("mask")) {
    e.target.classList.remove("show");
  }
});

function closeAllDropdowns() { document.querySelectorAll(".dd.open").forEach(d => d.classList.remove("open")); }
function toggleDropdown(el) {
  const isOpen = el.classList.contains("open");
  closeAllDropdowns();
  if (!isOpen) el.classList.add("open");
}
document.addEventListener("click", (e) => {
  if (!e.target.closest(".dd")) closeAllDropdowns();
});

// ---------------- 侧栏：仅全局导航 ----------------
function renderSidebar(activeKey) {
  const host = document.getElementById("sideNav");
  if (!host) return;

  host.innerHTML = `
    <div class="side-logo">
      <span class="h-bar"></span>
      <span class="name">知识库管理<small>KNOWLEDGE BASE ADMIN</small></span>
    </div>
    <div class="side-group">全局</div>
    <nav class="side-menu">
      <a class="side-item" data-key="kb-list" href="kb-list.html"><span class="ic">▦</span>知识库列表</a>
      <a class="side-item" data-key="dimensions" href="dimensions.html"><span class="ic">▤</span>维度管理</a>
      <a class="side-item" data-key="logs" href="logs.html"><span class="ic">⟲</span>操作日志</a>
    </nav>
    <div class="side-foot">v0.3 静态原型 · 数据存于浏览器本地<br />后端 / 数据库尚未接入<br /><a onclick="resetDemoData();location.href='kb-list.html';">重置演示数据</a></div>
  `;
  host.querySelectorAll(".side-item[data-key]").forEach(el => {
    el.classList.toggle("sel", el.dataset.key === activeKey);
  });
}

// 知识库内页签：知识点列表 / 回收站 / 知识库设置（显示在内容区右侧，而非侧栏）
function renderKbTabs(activeKey, kbId) {
  const q = "?kb=" + encodeURIComponent(kbId);
  const items = [
    { key: "kp-list", href: "index.html" + q, label: "知识点列表" },
    { key: "trash", href: "trash.html" + q, label: "回收站" },
    { key: "settings", href: "kb-settings.html" + q, label: "知识库设置" },
  ];
  return `<div class="tabs kb-tabs">
    ${items.map(it => `<a class="tab ${it.key === activeKey ? "active" : ""}" href="${it.href}">${it.label}</a>`).join("")}
  </div>`;
}

function initShell(activeKey) {
  renderSidebar(activeKey);
  tickClock();
  setInterval(tickClock, 1000);
}

function tickClock() {
  const t = document.getElementById("topClockTime");
  const d = document.getElementById("topClockDate");
  if (!t || !d) return;
  const now = new Date();
  t.textContent = now.toLocaleTimeString("zh-CN", { hour12: false });
  d.textContent = now.toLocaleDateString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" });
}

function renderPager(container, opts) {
  const { total, page, pageSize, onChange } = opts;
  const pages = Math.max(1, Math.ceil(total / pageSize));
  container.innerHTML = "";
  const info = document.createElement("span");
  info.innerHTML = `共 <b class="num">${total}</b> 条 · 第 <b class="num">${page}</b>/<b class="num">${pages}</b> 页`;
  container.appendChild(info);

  const prev = document.createElement("button");
  prev.textContent = "‹";
  prev.disabled = page <= 1;
  prev.onclick = () => onChange(page - 1);
  container.appendChild(prev);

  for (let p = 1; p <= pages; p++) {
    const b = document.createElement("button");
    b.textContent = p;
    b.className = p === page ? "cur" : "";
    b.onclick = () => onChange(p);
    container.appendChild(b);
  }

  const next = document.createElement("button");
  next.textContent = "›";
  next.disabled = page >= pages;
  next.onclick = () => onChange(page + 1);
  container.appendChild(next);
}

function dimValueDisplay(def, raw) {
  if (raw === undefined || raw === null || raw === "") return "—";
  if (def && def.field_type === "boolean") return raw === "true" ? "是" : "否";
  return raw;
}

seedIfEmpty();
