# 企业信息管理平台 · UI 设计规范

| 项目 | 内容 |
|---|---|
| 版本 | v1.0 |
| 制定日期 | 2026-07-28 |
| 提炼来源 | `祥符街道企业综合看板-demo.html`（大屏）、`企业信息管理后台-demo.html`（后台）、`企业信息管理后台-登录页-demo.html`（登录页） |
| 适用范围 | 本平台后续新增的全部页面：管理后台、数据大屏、门户/登录页 |
| 基调 | 浅色政务风 · 品牌蓝主导 · 低饱和语义色 · 弱阴影分层 |

> **使用方式**：新页面直接复制 §9 的 CSS 基座，再按 §3 组件配方拼装。任何颜色、字号、圆角、阴影都必须取自本文档，**不允许即兴新增色值**。

---

## 0. 三类页面与共享关系

| 类型 | 载体 | 布局策略 | 信息密度 |
|---|---|---|---|
| **A 管理后台** | 桌面浏览器（≥1440px 最佳） | 侧栏 228px + 顶栏 64px + 自适应内容区 | 高（表格/表单为主） |
| **B 数据大屏** | 投屏/大屏（16:9） | 1920×1080 固定舞台 + 等比缩放 | 中（指标/图表为主） |
| **C 登录/门户** | 桌面 + 窄屏降级 | 左品牌区 + 右卡片分屏 | 低 |

三类页面**共享同一套设计令牌**（§1）与**同一套组件配方**（§3），差异仅在布局骨架（§2）与信息密度。这保证用户在大屏与后台之间切换时视觉连续。

---

## 1. 设计令牌

### 1.1 品牌色

| 令牌 | 值 | 用途 |
|---|---|---|
| `--brand` | `#2f6bff` | **交互主色**：按钮、链接、选中态、标识条、图表主色 |
| `--brand-deep` | `#1a56f0` | **数值强调色**：大数字、指标值、选中文字、品牌标题 |
| `--brand-light` | `#6aa9ff` | 渐变末端、图表次色 |
| `--brand-light2` | `#5a8ffb` | 按钮渐变末端 |
| `--brand-pale` | `#9dbdfb` | hover 边框、装饰下划线 |

**三条标准渐变**（不得自创方向）：

```css
--grad-btn:  linear-gradient(135deg,#2f6bff,#5a8ffb);  /* 主按钮、头像、区块头 */
--grad-bar:  linear-gradient(90deg,#2f6bff,#6aa9ff);   /* 进度条、条形图 */
--grad-mark: linear-gradient(180deg,#2f6bff,#6aa9ff);  /* 竖向标识条 h-bar */
```

### 1.2 语义色（六色制，成套使用）

每色三件套：**文字色 / 边框色 / 背景色**，用于标签、状态、提示块。**禁止拆开混搭**。

| 语义 | 场景 | 文字 | 边框 | 背景 |
|---|---|---|---|---|
| **蓝 blue** | 信息、进行中、主库/系统标识 | `#2f6bff` | `#c9dcfc` | `#eef4ff` |
| **绿 green** | 成功、正常、存续、已完成 | `#0f9d58` | `#bfe9d2` | `#f2fbf6` |
| **橙 orange** | 警告、待处理、生成中、待反哺 | `#e08600` | `#f5ddb0` | `#fdf7ea` |
| **红 red** | 危险、失败、删除、吊销 | `#e5484d` | `#f7c6c8` | `#fff2f2` |
| **紫 purple** | 特殊标记（专精特新、手动操作） | `#7a5af8` | `#e0d7fb` | `#f7f4ff` |
| **灰 gray** | 中性、停用、未分配、注销 | `#7f8ca3` | `#dde5f1` | `#f5f8fd` |

> 大屏另有一枚**金色**仅用于付费/权限遮罩：`#ffd977 → #f2b135` 渐变，文字 `#5a3d00`。业务页面禁用。

### 1.3 文字灰阶（ink 七阶）

| 阶 | 值 | 用途 |
|---|---|---|
| ink-1 | `#1f2b43` | 页面标题、大标题、描述列表值 |
| ink-2 | `#33415c` | 正文、表格单元格、菜单项强调 |
| ink-3 | `#5b6b85` | 次要文字、按钮文字、菜单默认态 |
| ink-4 | `#7f8ca3` | 表头、表单 label、弱说明 |
| ink-5 | `#8a97ad` | 元信息（时间、来源）、副标题 |
| ink-6 | `#9aa7bd` | 提示文字、分组标题、图表轴标 |
| ink-7 | `#b6c0d2` | 占位符、空态、禁用、分隔符 `—` |

### 1.4 背景与线条

| 令牌 | 值 | 用途 |
|---|---|---|
| 页面底 | `radial-gradient(circle at 50% 40%, #eef2f9 0%, #e3e9f4 70%, #d8e0ee 100%)` | **三类页面统一底色**（大屏舞台内为 `#eef2f9` 纯色） |
| 卡片/面板 | `#fff` | 所有内容容器 |
| 浅底块 | `#f5f8fd` | 表头、描述列表 key 列、hover 底、浅色区块 |
| 行 hover | `#fafcff` | 表格行悬停（比浅底块更淡） |
| 分隔线-强 | `#edf1f8` | 卡片内分区、弹窗 head/foot 分界、Tab 底线 |
| 分隔线-弱 | `#f0f4fa` | 表格行线、下拉分隔线 |
| 边框-表单 | `#dde5f1` | 输入框、次按钮、复选卡片 |
| 边框-容器 | `#e8eef8` / `#e2e9f4` | 统计卡描边 / 浮层描边 |
| 渐变分隔线 | `linear-gradient(90deg,#e4ebf7,transparent)` | **卡片标题右侧延伸线**（本系统签名元素） |
| 虚线缩进 | `#dbe3f0` dashed | 树形层级线 |
| 滚动条 | `#d5deee`（5px）/ `#cfd9ea`（6px） | 侧栏菜单 / 内容区与弹窗 |

### 1.5 字体与字阶

```css
/* UI 字体 */
font-family:"PingFang SC","Microsoft YaHei","Segoe UI",sans-serif;

/* 数字字体（强制规则） */
.num { font-family:"Bahnschrift","DIN Alternate","Arial Narrow",sans-serif;
       font-weight:700; letter-spacing:.5px; }
```

> **数字规则（必须遵守）**：所有**指标数值、统计数字、ID、统一社会信用代码、金额、IP、时钟**一律加 `.num`。表格中的纯展示型编号可用 `.num` 但配 `font-weight:400` 降权。

**字阶表**

| 场景 | 后台 | 大屏 |
|---|---|---|
| 超大指标 | — | 64px（核心总数）/ 44px（次级） |
| 大指标 | 36px（统计卡值） | 38px（规模卡值）/ 34px（环心） |
| 详情页主标题 | 21px | 23px（画像名） |
| 页面标题 | 18px | 26px（大屏主标题） |
| 区块标题 | 17px | 17–18px |
| 时钟 | 20px | 26px |
| Tab / 强调正文 | 14.5px | 15px |
| 正文 / 表格 | 13.5px | 13.5px |
| 按钮 / label / 链接 | 13px | 14px |
| 元信息 / hint / 图例 | 12px | 12–13px |
| 分组标题 / 轴标 | 11–12px | 10.5–11.5px |
| 英文副标 | 10px（字距 2.5px） | 11px（字距 4px） |

### 1.6 圆角

| 值 | 用途 |
|---|---|
| `2px` | 标识条 tick、下划线 |
| `4px` | 条形轨道与填充、柱状图 rx |
| `8px` | sm 按钮、下拉项内元素、delta 徽章 |
| `9px` | **按钮、输入框、表头首尾、分页按钮、树节点、下拉项** |
| `10px` | Toast、登录页输入框 |
| `12px` | 通知条、描述列表、浮层（下拉/级联）、流程节点 |
| `14px` | **卡片、面板、统计卡** |
| `18px` | **弹窗、登录卡片** |
| `999px` | 胶囊标签、进度条、圆形徽章 |
| `50%` | 状态圆点、头像、排名徽章 |

### 1.7 阴影层级（与 z-index 配套）

| 层 | 阴影 | z-index | 用途 |
|---|---|---|---|
| L0 卡片 | `0 4px 18px rgba(31,66,135,.05)` | — | 卡片、面板、统计卡 |
| L1 骨架 | 侧栏 `2px 0 12px rgba(31,66,135,.04)`<br>顶栏 `0 2px 10px rgba(31,66,135,.06)` | 6 / 5 | 侧栏、顶栏 |
| L2 主按钮 | `0 5px 12px rgba(47,107,255,.3)` | — | primary 按钮 |
| L3 浮层 | `0 14px 38px rgba(18,35,68,.16)` | 30–40 | 下拉菜单、级联面板 |
| L4 登录卡 | `0 20px 60px rgba(31,66,135,.14)` | — | 登录卡片 |
| L5 弹窗 | `0 30px 80px rgba(10,25,60,.35)` | 100 | Modal（遮罩 `rgba(43,58,94,.55)` + `blur(3px)`） |
| L6 Toast | `0 10px 26px rgba(10,25,60,.3)` | 200 | 轻提示（最高层） |

### 1.8 间距与栅格

| 位置 | 值 |
|---|---|
| 内容区 padding | `18px 28px 32px` |
| 卡片 padding | `18px 22px`；卡片间距 `margin-bottom:16px` |
| 卡片标题下间距 | `14px` |
| 表单行 | `gap:12px 18px`；表单项内 `gap:8px` |
| 弹窗 | head `18px 24px` / body `20px 24px` / foot `14px 24px` |
| 弹窗表单项 | `margin-bottom:14px`；label 下 `6px` |
| 统计卡栅格 | `repeat(auto-fit,minmax(200px,1fr))`，`gap:14px` |
| 双列布局 | `1fr 1fr`，`gap:16px` |
| 树+详情布局 | `300px 1fr`，`gap:16px` |
| 大屏三栏 | `831fr 559fr 442fr`，`gap:14px`，外边距 `14px 32px 18px` |

### 1.9 动效

| 场景 | 规格 |
|---|---|
| 交互过渡 | `.15s`（颜色、边框、背景、阴影） |
| 进度条 | `width .3s` |
| Toast 入场 | `.25s`，`translateY(12px) → 0` + 淡入 |
| 加载旋转 | `1s linear infinite`（2px 环，橙色系 `#f5ddb0` + `#e08600`） |
| 错误抖动 | `shake .5s`（仅登录页失败） |
| 卡片 hover 抬升 | `translateY(-1px)` + 阴影加深（仅大屏企业卡） |

**原则**：只动 `opacity / transform / color / box-shadow`，不做宽高布局动画；无长时间循环动画（除加载态）。

---

## 2. 布局骨架

### 2.1 管理后台（A 型）

```
┌──────────┬─────────────────────────────────────────┐
│ 侧栏228px │ 顶栏 64px（标识条+页面标题 / 徽章+时钟+头像）│
│ 白底      ├─────────────────────────────────────────┤
│ logo 64px │ 内容区（overflow-y:auto，padding 18/28/32）│
│ 分组+菜单 │   卡片流 / 双列 / 树+详情                 │
│ 底部说明  │                                          │
└──────────┴─────────────────────────────────────────┘
```

- **侧栏**：白底 + 右边框 `#e9eef7`；分组标题 12px `#9aa7bd` 字距 2px；菜单项 `padding:10px 20px`，默认 `#5b6b85`，hover `#f5f8fd`+`#2f6bff`，**选中 `#eef4ff` + `#1a56f0` + 左侧 3px `#2f6bff` 竖条 + 600 字重**；图标用 16px 宽字符位（`◧ ▤ ▦ ♟ ♙ ◫ ⟲`）。
- **顶栏**：左侧 `h-bar`（5×30px 渐变竖条）+ 页面标题 18px；右侧依次为状态徽章（胶囊）、实时时钟（`.num` 20px + 12px 日期）、34px 圆形头像。
- **面包屑**：用「一级 / 二级」纯文本置于标题位，不做多级可点面包屑。

### 2.2 数据大屏（B 型）

```css
#stage { width:1920px; height:1080px; position:absolute; top:50%; left:50%;
         transform-origin:center center; }
```
```js
const s = Math.min(innerWidth/1920, innerHeight/1080);
stage.style.transform = `translate(-50%,-50%) scale(${s})`;
// 绑定 resize + load
```

- **禁止**为大屏写响应式断点，一律等比缩放，保证任何屏幕比例下版式不变。
- header 72px；main 高 `1080-72`；三栏 `831fr 559fr 442fr`。
- 面板纵向 flex：固定高度用 `flex:0 0 366px` 这类写法，弹性区用 `flex:1` + `min-height:0`（**必须加 min-height:0，否则内部滚动失效**）。

### 2.3 登录/门户（C 型）

- 左品牌区 `flex:1.15`：品牌渐变 `linear-gradient(135deg,#1a56f0 0%,#2f6bff 45%,#5a8ffb 100%)`，两枚半透明装饰圆（`rgba(255,255,255,.07)` 520px / `.05` 380px）溢出裁切，内容为标识条+系统名+英文副标+一段说明+3 条能力点（26px 圆角小图标块）。
- 右登录区 `flex:1`：420px 卡片，`radius:18px`，`padding:44px 42px 36px`。
- 输入框 44px 高、`radius:10px`、左侧 38px 图标位、右侧 42px 功能位（如显示密码）。
- 提交按钮 46px 高、`letter-spacing:6px`。
- `@media (max-width:860px)` 隐藏左侧品牌区，仅留卡片。

---

## 3. 组件配方

> 以下均为**已在生产 demo 中验证**的配方，直接复制使用。

### 3.1 标识条 `h-bar`（★系统视觉签名）

```css
.h-bar { width:5px; border-radius:3px; background:linear-gradient(180deg,#2f6bff,#6aa9ff); flex:none; }
```
四处必用：侧栏 logo（36px 高）、顶栏页面标题（30px 高）、大屏主标题（40px 高）、以及降级版本——卡片标题 `tick`（4×16px 纯色 `#2f6bff`）、弹窗标题（4×18px）。

### 3.2 按钮

```css
.btn { height:34px; padding:0 16px; border-radius:9px; border:1px solid #dde5f1;
       background:#fff; color:#5b6b85; font-size:13px; transition:all .15s; }
.btn:hover { border-color:#9dbdfb; color:#2f6bff; }
.btn.primary { background:linear-gradient(135deg,#2f6bff,#5a8ffb); border:none; color:#fff;
               font-weight:600; box-shadow:0 5px 12px rgba(47,107,255,.3); }
.btn.primary:hover { filter:brightness(1.06); }
.btn.danger { color:#e5484d; border-color:#f3c1c3; }
.btn.danger:hover { background:#fff2f2; }
.btn.sm { height:28px; padding:0 12px; font-size:12px; border-radius:8px; }
.btn:disabled { opacity:.5; cursor:not-allowed; }
```

**使用规则**
- 一个操作区**最多一个 primary**，且置于最右（弹窗）或最右（卡片头）。
- 弹窗按钮顺序固定：`取消`（默认）→ 次要操作 →`确定/主操作`（primary）。
- **危险操作必须 `danger` 且必须二次确认**（见 §5.2）。
- 按钮文字：两字操作加空格排版（`查 询`、`重 置`、`确 定`），提升可读节奏。
- 图标用字符前缀：`+ 新增`、`⤒ 批量导入`、`↻ 重新生成`、`⇅ 数据同步`、`⋯ 更多`、`‹ 返回`、`↑ / ↓` 表方向。

### 3.3 卡片与卡片头

```css
.card { background:#fff; border-radius:14px; box-shadow:0 4px 18px rgba(31,66,135,.05);
        padding:18px 22px; margin-bottom:16px; overflow-x:auto; }
.card.ov { overflow:visible; }              /* ★含下拉浮层的卡片必须用它，见 §8.1 */
.card-head { display:flex; align-items:center; gap:10px; margin-bottom:14px; }
.card-head .tick { width:4px; height:16px; border-radius:2px; background:#2f6bff; flex:none; }
.card-head h3 { font-size:17px; color:#1f2b43; white-space:nowrap; }
.card-head .sub { font-size:12px; color:#8a97ad; margin-left:4px; }
.card-head .spacer { flex:1; height:1px; background:linear-gradient(90deg,#e4ebf7,transparent); margin:0 10px; }
```
结构固定为：`tick + 标题 + 副说明 + 渐变延伸线 + 右侧操作按钮`。

### 3.4 表格

```css
.tbl { width:100%; border-collapse:collapse; }
.tbl th { background:#f5f8fd; color:#7f8ca3; font-size:13px; font-weight:600; text-align:left;
          padding:11px 12px; white-space:nowrap; }
.tbl th:first-child { border-radius:9px 0 0 9px; }
.tbl th:last-child  { border-radius:0 9px 9px 0; }
.tbl td { padding:11px 12px; font-size:13.5px; border-bottom:1px solid #f0f4fa; color:#33415c; }
.tbl tr:hover td { background:#fafcff; }
.tbl .empty { text-align:center; color:#b6c0d2; font-size:13.5px; padding:30px 0; }
.ops a { margin-right:12px; font-size:13px; }
.ops a:last-child { margin-right:0; }
```

**规则**
- 表头**无竖线、无外边框**，仅靠浅底 + 行线区分。
- **操作列**：文字链接（非按钮），删除类必须 `class="danger"`；不可用项渲染为 `<span style="color:#b6c0d2">—</span>` 而非隐藏，保持列对齐。
- 主键列（名称）做成蓝色链接进详情；代码/ID 列加 `.num` 且 `font-weight:400`。
- **列数 ≥8 时**：卡片保持 `overflow-x:auto` 横滚，**不要靠列自适应压缩**；给操作列固定宽度。
- 空态文案要具体："暂无符合条件的企业" / "该企业暂无「知识产权」数据" / "回收站暂无记录"。

### 3.5 表单

```css
input[type=text],input[type=password],select,textarea{
  border:1px solid #dde5f1; border-radius:9px; padding:8px 12px; font-size:13.5px;
  color:#33415c; background:#fff; outline:none; min-width:150px; font-family:inherit; }
input:focus,select:focus,textarea:focus{ border-color:#2f6bff; box-shadow:0 0 0 3px rgba(47,107,255,.12); }
input::placeholder{ color:#b6c0d2; }
.mf label { font-size:13px; color:#7f8ca3; margin-bottom:6px; }
.mf label .req { color:#e5484d; margin-right:2px; }   /* 必填星号前置 */
.mf .hint { font-size:12px; color:#9aa7bd; margin-top:4px; }
/* 卡片式复选（替代裸 checkbox 列表） */
.chk { display:flex; align-items:center; gap:7px; font-size:13px; color:#33415c;
       border:1px solid #dde5f1; border-radius:9px; padding:9px 11px; cursor:pointer; }
.chk:hover { border-color:#9dbdfb; }
.chk input { accent-color:#2f6bff; }
.chk-grid { display:grid; grid-template-columns:repeat(2,1fr); gap:8px 14px; }
```

**规则**
- 筛选区一律**横向单行**（`.form-row` 自动换行），顺序：关键词 → 下拉筛选 → `查 询`(primary) → `重 置` → 右侧主操作。
- 只读字段：`disabled` + `background:#f5f8fd; color:#8a97ad`，并在 label 或 hint 说明原因（如"系统溯源字段"）。
- 弹窗内字段多于 6 个时用双列：`display:grid; grid-template-columns:1fr 1fr; gap:0 16px`。
- 搜索框**必须支持 Enter 提交**。

### 3.6 标签与状态

```css
.tag { display:inline-block; font-size:12px; padding:2.5px 10px; border-radius:999px;
       border:1px solid; margin:1px 4px 1px 0; white-space:nowrap; }
/* 六色见 §1.2，均为 color/border-color/background 三件套 */
.status-dot { display:inline-flex; align-items:center; gap:6px; font-size:13px; }
.status-dot i { width:7px; height:7px; border-radius:50%; }
.status-dot.ok{color:#0f9d58} .status-dot.ok i{background:#0f9d58}
.status-dot.off{color:#8a97ad} .status-dot.off i{background:#9aa7bd}
.status-dot.warn{color:#e08600} .status-dot.warn i{background:#e08600}
```

**语义映射（跨页面必须一致）**

| 含义 | 呈现 |
|---|---|
| 正常/存续/成功/已完成/在线 | `status-dot.ok` 或 `tag.green` |
| 停用/注销/离线/未分配数据 | `status-dot.off` 或 `tag.gray` |
| 异常/吊销/待处理/生成中 | `status-dot.warn` 或 `tag.orange`（+ `spin`） |
| 失败/删除/高危 | `tag.red` |
| 系统计算/主库来源/信息 | `tag.blue` |
| 人工操作/特殊资质 | `tag.purple` 或 `tag.orange` |

> **禁止用颜色单独传达信息**：状态必须"圆点/标签 + 文字"同时出现。

### 3.7 统计卡（四色循环）

```css
.stat { background:#fff; border:1px solid #e8eef8; border-radius:14px;
        box-shadow:0 4px 18px rgba(31,66,135,.05); padding:18px 20px; }
.stat .lbl { font-size:14px; color:#5b6b85; display:flex; align-items:center; gap:7px; }
.stat .lbl::before { content:""; width:7px; height:7px; border-radius:50%; background:#1a56f0; }
.stat .val { font-size:36px; margin-top:8px; color:#1a56f0; line-height:1.1; }  /* 配 .num */
.stat .val small { font-size:14px; color:#8a97ad; font-weight:600; margin-left:4px; }
.stat .foot { font-size:12px; color:#8a97ad; margin-top:8px; }
/* 第 2/3/4 张自动换色：绿 / 紫 / 橙（含浅底与彩点） */
```
一行 4 张为标准节奏；单位用 `<small>` 包裹；`foot` 放同比/构成说明。

### 3.8 Tabs

```css
.tabs { display:flex; gap:2px; border-bottom:1px solid #edf1f8; margin-bottom:16px; flex-wrap:wrap; }
.tabs .tab { padding:12px 17px; font-size:14.5px; color:#5b6b85; cursor:pointer; position:relative; }
.tabs .tab:hover { color:#2f6bff; }
.tabs .tab.active { color:#2f6bff; font-weight:700; }
.tabs .tab.active::after { content:""; position:absolute; left:14px; right:14px; bottom:-1px;
                           height:3px; border-radius:2px; background:#2f6bff; }
```
下划线**两侧内缩 14px**（不通宽），是本系统 Tab 的识别特征。Tab 数量可到 11 个，允许换行。

### 3.9 描述列表

```css
.desc { display:grid; grid-template-columns:repeat(3,1fr); border:1px solid #edf1f8;
        border-radius:12px; overflow:hidden; }
.desc .di { display:flex; border-bottom:1px solid #f0f4fa; border-right:1px solid #f0f4fa; min-height:44px; }
.desc .di .k { width:120px; flex-shrink:0; background:#f5f8fd; color:#7f8ca3; font-size:12.5px; padding:12px 14px; }
.desc .di .v { flex:1; padding:12px 14px; font-size:13.5px; color:#1f2b43; font-weight:600; word-break:break-all; }
.desc .di.span3 { grid-column:span 3; }   /* 长文本字段独占整行 */
```
详情页用 3 列；弹窗内用 2 列或 1 列（`grid-template-columns` 覆盖即可）。

### 3.10 弹窗 Modal

```css
.mask { position:fixed; inset:0; background:rgba(43,58,94,.55); backdrop-filter:blur(3px);
        display:none; align-items:flex-start; justify-content:center; z-index:100;
        overflow-y:auto; padding:60px 20px; }
.mask.show { display:flex; }
.modal { background:#fff; border-radius:18px; width:560px; max-width:96vw;
         box-shadow:0 30px 80px rgba(10,25,60,.35); overflow:hidden; }
.modal.wide { width:1360px; }
.mo-head { padding:18px 24px; border-bottom:1px solid #edf1f8; display:flex; align-items:center; gap:10px; }
.mo-head::before { content:""; width:4px; height:18px; border-radius:2px; background:#2f6bff; }
.mo-close { margin-left:auto; width:34px; height:34px; border-radius:9px; background:#f1f4fa; color:#5b6b85; }
.mo-body { padding:20px 24px; max-height:62vh; overflow-y:auto; }
.mo-foot { padding:14px 24px; border-top:1px solid #edf1f8; display:flex; justify-content:flex-end; gap:10px; }
```

**宽度分级**

| 宽度 | 用途 |
|---|---|
| `560px`（默认） | 表单类（新增/编辑/确认/删除原因） |
| `1360px`（`.wide`） | **含表格的弹窗**：差异清单、导入记录、生成记录、明细详情 |
| `max-width:96vw` | 两者共用的小屏保护 |

**规则**
- 弹窗顶部对齐（`align-items:flex-start` + `padding:60px 20px`），不垂直居中——长内容不会顶出屏幕。
- 点击遮罩空白处关闭；`.mo-body` 独立滚动（`62vh`）。
- **二级弹窗不叠加遮罩**：直接替换当前弹窗内容，并在 foot 左侧提供 `‹ 返回上级` 按钮（如"‹ 返回差异清单"）。
- 危险确认弹窗在正文下方加红色风险块：
```css
background:#fff2f2; border:1px solid #f7c6c8; border-radius:10px;
padding:12px 16px; font-size:13px; color:#c0353a; line-height:1.8;
```

### 3.11 下拉操作菜单（按钮聚合）

```css
.dd { position:relative; display:inline-block; }
.dd-menu { position:absolute; right:0; top:calc(100% + 6px); min-width:270px; background:#fff;
           border:1px solid #e2e9f4; border-radius:12px; box-shadow:0 14px 38px rgba(18,35,68,.16);
           padding:6px; display:none; z-index:40; text-align:left; }
.dd.open .dd-menu { display:block; }
.dd-item { padding:9px 12px; border-radius:9px; cursor:pointer; display:block; }
.dd-item:hover { background:#f5f8fd; }
.dd-item .t { font-size:13.5px; color:#33415c; font-weight:600; }   /* 标题行 */
.dd-item .d { font-size:12px; color:#9aa7bd; margin-top:3px; line-height:1.6; }  /* 说明行 */
.dd-item.danger .t { color:#e5484d; }
.dd-item.danger:hover { background:#fff2f2; }
.dd-sep { height:1px; background:#f0f4fa; margin:5px 8px; }
.dd-group { font-size:11px; color:#b6c0d2; letter-spacing:1px; padding:7px 12px 3px; }
```

**规则**
- **操作区按钮 >4 个时必须聚合**，保留 1 个主操作 + 1–2 个下拉入口。
- 每个下拉项**必须两行**：操作名 + 一句功能说明（这是易用性硬要求）。
- 同类项用 `dd-group` 分组（如"主表 → 分表" / "分表 → 主表"）；危险项用 `dd-sep` 隔开并置于末位。
- 交互：点击切换、同时只开一个（`closeDd()` 先执行）、点击外部收起、选中后自动收起。
- ⚠ **父容器不能有 `overflow:auto/hidden`**，见 §8.1。

### 3.12 分页

```css
.pager { display:flex; align-items:center; justify-content:flex-end; gap:8px;
         margin-top:14px; font-size:13px; color:#7f8ca3; }
.pager button { min-width:32px; height:32px; padding:0 10px; border-radius:9px;
                border:1px solid #dde5f1; background:#fff; color:#5b6b85; font-size:13px; }
.pager button:hover:not(:disabled):not(.cur) { border-color:#9dbdfb; color:#2f6bff; }
.pager button.cur { background:#2f6bff; border-color:#2f6bff; color:#fff; font-weight:600; }
.pager button:disabled { opacity:.45; cursor:not-allowed; }
```
- 左侧文案：`共 N 条 · 第 x/y 页`；结构：文案 → 上一页 → 页码 → 下一页。
- 页数 >7 时省略：仅显示首页、末页、当前 ±2，断点插 `…`。
- **每页条数基准**：主列表 8–10 条；弹窗内表格 5 条；子表聚合 12 条。**任何可增长的列表都必须分页**。

### 3.13 Toast（唯一的轻反馈机制）

```css
#toast { position:fixed; left:50%; bottom:40px; transform:translateX(-50%); z-index:200;
         display:flex; flex-direction:column; gap:8px; align-items:center; }
.toast-item { background:rgba(31,43,67,.92); color:#fff; border-radius:10px; padding:11px 22px;
              font-size:13.5px; box-shadow:0 10px 26px rgba(10,25,60,.3); animation:tin .25s; }
.toast-item.ok::before  { content:"✓"; color:#4cd48f; font-weight:700; }
.toast-item.err::before { content:"✕"; color:#ff9a9e; font-weight:700; }
.toast-item.info::before{ content:"ℹ"; color:#8fb5ff; font-weight:700; }
```
- **深色**胶囊、**底部居中**、2.6s 自动消失、可堆叠。
- 严禁使用浏览器原生 `alert / confirm`；表单校验错误用 `toast.err`，破坏性确认用弹窗。
- 文案带结果数据："已生成 3 组分表" / "反哺完成，19 条已写回企业主库"。

### 3.14 进度与加载

```css
.prog { height:10px; background:#edf1f8; border-radius:999px; overflow:hidden; }
.prog i { display:block; height:100%; width:0; background:linear-gradient(90deg,#2f6bff,#6aa9ff);
          border-radius:999px; transition:width .3s; }
.spin { display:inline-block; width:11px; height:11px; border:2px solid #f5ddb0;
        border-top-color:#e08600; border-radius:50%; animation:sp 1s linear infinite; }
```
异步任务标准范式见 §5.1。

### 3.15 条形分布（后台图表替代方案）

```css
.bl-row { display:grid; grid-template-columns:150px 1fr 56px; align-items:center; gap:10px; margin-bottom:11px; }
.bl-name { font-size:13px; color:#5b6b85; text-align:right; }
.bl-track { height:12px; background:#edf1f8; border-radius:4px; overflow:hidden; }
.bl-track i { background:linear-gradient(90deg,#2f6bff,#6aa9ff); border-radius:4px; min-width:3px; }
.bl-val { font-size:14px; color:#1a56f0; }   /* 配 .num */
```
后台内的分布类数据优先用此纯 CSS 条形，**不引入图表库**；仅大屏使用 SVG 图表（§4）。

### 3.16 树形

```css
.tnode { display:flex; align-items:center; gap:6px; padding:8px 10px; border-radius:9px;
         color:#33415c; cursor:pointer; transition:background .15s; }
.tnode:hover { background:#f5f8fd; }
.tnode.sel { background:#eef4ff; color:#1a56f0; font-weight:600; }
.tnode .cnt { font-size:12px; color:#9aa7bd; font-weight:400; }   /* (含下级人数) */
.kids { margin-left:18px; border-left:1px dashed #dbe3f0; padding-left:8px; }
```
节点结构：展开符（`▾` / `·`）+ 名称 + 计数 + 状态小标签。布局用 `300px 1fr` 双栏（树 + 详情）。

### 3.17 级联选择器（可搜索）

```css
.cs-panel { position:absolute; top:42px; left:0; background:#fff; border:1px solid #e2e9f4;
            border-radius:12px; box-shadow:0 14px 38px rgba(18,35,68,.16); display:none; z-index:30; }
.cs-col { width:172px; max-height:230px; overflow-y:auto; padding:6px; }
.cs-col + .cs-col { border-left:1px solid #f0f4fa; }
.cs-item.on { background:#eef4ff; color:#1a56f0; font-weight:600; }
.cs-item.dis { opacity:.45; cursor:not-allowed; }
.cs-item .side { font-size:11px; color:#9aa7bd; }   /* 右侧计数/状态 */
```
行为：聚焦展开两级列（父列 + 子列）；输入关键词时切为**扁平搜索结果**并显示全路径；已占用项 `dis` 置灰；选中回填 `父 / 子` 文本。

### 3.18 通知条与详情页头

```css
.notice { background:linear-gradient(135deg,#eef4ff,#f7faff); border:1px solid #d9e6fd;
          border-radius:12px; padding:13px 18px; font-size:13px; color:#33415c; line-height:1.8; }
.notice b { color:#1a56f0; }

.detail-head { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; }
.detail-head h2 { font-size:21px; color:#1f2b43; }
.detail-head .meta { font-size:13px; color:#8a97ad; margin-top:8px; display:flex; gap:18px; flex-wrap:wrap; }
.back-link { display:inline-flex; align-items:center; gap:6px; border:1px solid #c9dcfc;
             background:#eef4ff; color:#2f6bff; font-size:13px; padding:7px 14px; border-radius:9px; }
```
- `notice` 用于**规则说明**（数据方向、联动影响、导入规则），关键词用 `<b>` 蓝色加粗。
- 详情页固定结构：`‹ 返回列表` → 头部卡（标题 + meta 行 + 标签 + 右侧操作）→ Tab 卡。

### 3.19 大屏专属组件

**面板**（大屏版卡片，与后台 `.card` 同源）

```css
.panel { background:#fff; border-radius:14px; box-shadow:0 4px 18px rgba(31,66,135,.05);
         padding:18px 22px; min-height:0; }
.p-head { display:flex; align-items:center; gap:10px; margin-bottom:14px; }
.p-head .tick { width:4px; height:16px; border-radius:2px; background:#2f6bff; }
.p-head h3 { font-size:17px; color:#1f2b43; white-space:nowrap; }
.p-head .rule { flex:1; height:1px; background:linear-gradient(90deg,#e4ebf7,transparent); }
```

**核心指标（超大数字）**

```css
.big-count .n { font-size:64px; color:#1a56f0; line-height:1;
                border-bottom:3px solid #9dbdfb; padding-bottom:6px; transition:.2s; }
.big-count:hover .n { color:#0b3fd6; border-color:#1a56f0; text-shadow:0 4px 18px rgba(26,86,240,.35); }
.big-count .u { font-size:20px; color:#1a56f0; font-weight:600; }   /* 单位 */
```
可点击的核心数字用蓝色下划线 + hover 发光暗示可交互。

**涨跌徽章 delta**

```css
.delta { display:inline-flex; align-items:center; gap:6px; width:max-content;
         background:#eefaf3; color:#0f9d58; border:1px solid #bfe9d2;
         border-radius:8px; padding:6px 12px; font-size:14px; font-weight:600; }
```
上升用 `▲` + 绿色（上表）；下降改用红三件套（`#fff2f2/#f7c6c8/#e5484d`）+ `▼`。

**指标强调卡**（浅绿）

```css
.valid-card { background:#f2fbf6; border:1px solid #d4f0e0; border-radius:12px; padding:12px 14px; }
.valid-num { font-size:26px; color:#0f9d58; }
.valid-bar { height:6px; background:#dcefe4; border-radius:3px; overflow:hidden; }
.valid-bar i { height:100%; background:linear-gradient(90deg,#12b76a,#3ed48f); }
```

**规模四色卡**（一行 4 张，与后台 `.stat` 同构）

```css
.scale-card { border-radius:12px; border:1px solid #e8eef8; background:#fbfcfe; padding:16px 18px; }
.scale-card .t { font-size:14px; color:#5b6b85; display:flex; align-items:center; gap:7px; }
.scale-card .t i { width:7px; height:7px; border-radius:50%; }
.scale-card .v { font-size:38px; line-height:1; }
.sc-blue   .v{color:#1a56f0} .sc-blue i{background:#1a56f0}
.sc-green  { background:#f2fbf5; border-color:#d8f0e0; } .sc-green .v{color:#0f9d58}
.sc-purple { background:#f7f4ff; border-color:#e5ddfa; } .sc-purple .v{color:#7a5af8}
```

**实体卡片（列表项）**

```css
.ent-card { background:#fff; border:1px solid #eaeff8; border-radius:13px; padding:16px 20px;
            display:flex; gap:16px; cursor:pointer; transition:.15s; }
.ent-card:hover { border-color:#9dbdfb; box-shadow:0 8px 22px rgba(47,107,255,.13); transform:translateY(-1px); }
.ent-avatar { width:64px; height:64px; border-radius:13px; color:#fff; font-size:19px; font-weight:700; }
```

**头像渐变色板**（按索引取模，固定顺序）

```js
['linear-gradient(135deg,#4d8bff,#2f6bff)','linear-gradient(135deg,#3fa7ff,#2b7de0)',
 'linear-gradient(135deg,#35c684,#12a05e)','linear-gradient(135deg,#9d7bff,#7a5af8)',
 'linear-gradient(135deg,#ffb35c,#f28c1e)','linear-gradient(135deg,#33c2bd,#0fa8a2)']
```

**大屏内弹窗**：尺寸 `1758×979`（舞台内绝对尺寸）、`radius:18px`、底 `#f5f8fd`（非纯白，与面板形成层次）、遮罩 `rgba(43,58,94,.55)` + `blur(3px)`；关闭按钮 40px 方形 `#f1f4fa`。大屏弹窗内的表格用 `table.dt`（表头 `#f5f8fd`、行线 `#f0f4fa`、hover `#fafcff`），与后台 `.tbl` 等价。

---

## 4. 图表规范（大屏 SVG）

### 4.1 通用

| 项 | 规格 |
|---|---|
| 网格线 | `#eef2f9`，1px，仅横向 |
| 轴文字 | `#9aa7bd`，10.5–11px |
| 数值文字 | `Bahnschrift, Arial`，700 |
| 边框/背景 | 无（面板已提供白底） |
| 图例 | ≥2 系列必备；单系列用标题说明代替 |

### 4.2 颜色使用

- **单系列（默认）**：主蓝 `#2f6bff`；需强调当前项时——当前项 `#2f6bff`，其余 `#b9d2fd`。
- **分类色板（顺序固定，最多 5 类）**：
  `#6aa9ff` → `#2f6bff` → `#0fb5ae` → `#7a5af8` → `#12b76a`
- 超过 5 类：合并为"其他"或改用小多图，**不得自行扩展色板**。

### 4.3 各图型参数

| 图型 | 参数 |
|---|---|
| **面积/折线** | 线 `#2f6bff` 2.5px、`stroke-linejoin:round`；面积渐变 `#2f6bff` 透明度 `.28 → .03`；数据点 `r=3.6` 白填充 + 2.2px 蓝描边 |
| **柱状** | 柱宽 22px、`rx=4`；末项（当期）`#2f6bff`，历史项 `#b9d2fd` |
| **环形** | `r=100`、`stroke-width=34`、段间隙 2.2°、`stroke-linecap:round`；中心三行：说明 14px `#8a97ad` / 数值 34px `#1f2b43` / 单位 13px |
| **排名列表** | 徽章 24px 圆（金 `#ffb74d→#ff9800`、银 `#b0bec5→#90a4ae`、铜 `#d7a173→#c98850`，其余 `#eef1f7`+`#7f8ca3`）；名称 14.5px；进度条 5px 主蓝渐变；数值 19px `#1a56f0`；本级行高亮 `#eef4ff`+`#c9dcfc` |
| **区块头（彩色）** | `linear-gradient(135deg,#2f6bff,#3d7bff 60%,#5a8ffb)`，白字 18px + 半透明徽章 |

### 4.4 禁止项

- ❌ 双 Y 轴（两个量级 → 拆两图或指数化）
- ❌ 彩虹色阶 / 渐变映射数值
- ❌ 单系列多色
- ❌ 3D、阴影、动画旋转饼图
- ❌ 每个数据点都标数值（仅标首末与极值）

---

## 5. 交互与状态规范

### 5.1 异步长任务范式（生成/同步/导入）

1. 提交后**立即关闭弹窗并返回列表**，不阻塞用户；
2. 状态置为「进行中」：`tag.orange` + `spin` 图标；
3. 进行中期间**操作降级**：仅保留"查看记录"，禁用查看详情/编辑/删除/重复触发（点击给 `toast.info` 提示）；
4. 弹窗内执行时展示 `prog` 进度条 + 逐行状态流转（待处理 → 已完成）+ 文案 `正在写回：3/19 条…`；
5. 完成后：`toast.ok` 报结果数量 + 状态转「已完成」+ **追加一条执行记录**（时间/操作人/方式/条数/结果）；
6. 记录可点「查看」进入明细（含前后值对照）。

### 5.2 危险操作三要素

| 要素 | 要求 |
|---|---|
| **红色入口** | `btn.danger` 或 `dd-item.danger`；表格内用 `a.danger` |
| **二次确认** | 弹窗展示对象名称 + 影响范围 |
| **风险说明** | 红色风险块写明**会丢什么** + **建议的前置动作**（例："分表侧尚未反哺的修改将被覆盖，建议先执行数据反哺"） |

删除类还需：**必填删除原因**、**逻辑删除进回收站**（而非物理删除）、回收站可查看快照并恢复。

### 5.3 主从数据双向同步范式

两个方向必须**镜像对称**，用词严格区分：

| 方向 | 命名 | 列名 | 状态词 |
|---|---|---|---|
| 主表 → 分表 | 数据**更新** | 主表值（将下发）/ 分表现值 | 待更新 / 已更新 |
| 分表 → 主表 | 数据**反哺** | 分表值（将写入）/ 主表现值 | 待同步 / 已同步 |

共用结构：差异清单（搜索 + 分页 + 全选/多选）→ 双按钮（`XX选中（N 条）` + `开始XX（全部 M 条）`）→ 进度 → 记录（方式列区分 自动同步/手动/全量）。

### 5.4 一对多数据展示

同一主体的多值（标签、荣誉）**聚合为一行**：字段名标注项数（"新增标签（3 项）"）+ 值列多枚 `tag.blue` chip + 「查看详情」入口；详情内展示逐项元信息（名称/类别/分级/定义）、支持**两侧数据切换**（分表侧 / 主表侧）与逐项多选操作。

### 5.5 变更留痕与撤回

可编辑数据必须有「更新记录」：时间/操作人/范围/数据表/变更内容/变更前/变更后/来源/状态。
- 来源分类：人工编辑（`tag.purple`）、批量导入（`tag.blue`）、系统类（`tag.gray`）；
- **仅人工编辑类可撤回**，系统类操作列置灰 `—` 并用 `title` 说明原因；
- 撤回需二次确认（展示前后值对照），撤回后原记录标「已撤回」并**追加一条撤回留痕**。

### 5.6 三态必备

任何数据区域都要设计：**加载中**（`spin`/骨架）、**空态**（`.empty` + 具体文案 + 可能的引导按钮）、**失败**（`toast.err` + 可重试入口）。

---

## 6. 文案规范

| 场景 | 规范 |
|---|---|
| 按钮 | 动词短语，2 字加空格（`查 询`）；带方向用箭头前缀 |
| 表头 | 名词，不加"的"；带单位写进表头（`项目金额(万元)`） |
| 空态 | 说明 + 引导（"暂无分表，点击右上角「新建分表」"） |
| 提示 | 引用界面元素用「」包裹（"请先执行「数据反哺」"） |
| 规则说明 | 放 `notice`，关键词 `<b>` 加粗；不超过 3 行 |
| 确认弹窗 | 第一句陈述动作对象，第二句说明影响 |
| 数字 | 千分位（`15,420`）；比例保留 1 位小数；条数用"条"、企业用"家"、人员用"人" |
| 时间 | 列表 `YYYY-MM-DD HH:mm`（`#8a97ad` + `nowrap`）；日期字段 `YYYY-MM-DD` |

---

## 7. 层级与无障碍

**z-index 表（不得自创层级）**

| 值 | 用途 |
|---|---|
| 5 / 6 | 顶栏 / 侧栏 |
| 30 / 40 | 级联面板 / 下拉菜单 |
| 100 | 弹窗遮罩 |
| 200 | Toast |

**无障碍要点**
- 正文对比度：`#33415c` on `#fff`（≈9:1）；最弱文字 `#b6c0d2` 仅用于占位与禁用，不承载信息。
- 颜色不单独承载语义（配文字/图标）。
- 键盘：搜索框 Enter 提交；弹窗点遮罩关闭；可点区域最小 28×28px。
- 长文本 `word-break:break-all`；表格 `white-space:nowrap` + 容器横滚。
- 禁用态统一 `opacity:.45~.5` + `cursor:not-allowed`。

---

## 8. 已验证的坑（务必规避）

### 8.1 `overflow-x:auto` 会连带裁剪纵向浮层 ★

CSS 规范中一个方向为 `auto` 时，另一方向的 `visible` 会被强制计算为 `auto`。因此给卡片加 `overflow-x:auto`（防宽表撑破）后，**内部绝对定位的下拉菜单会被裁掉并出现意外滚动条**。

```css
.card { overflow-x:auto; }        /* 含宽表格的卡片 */
.card.ov { overflow:visible; }    /* 含下拉/浮层的卡片必须用这个 */
```
> 判断口径：**该容器内有 `.dd` / `.cs-panel` 等浮层 → 必须 `.ov`**；只有表格 → 保持 `auto`。

### 8.2 其他

| 坑 | 规避 |
|---|---|
| 宽表格被压缩到列消失 | 容器横滚 + 操作列固定宽度，不靠列自适应 |
| 弹窗内表格拥挤 | 含表格弹窗一律 `.wide`（1360px） |
| 表头圆角失效 | 必须写 `th:first-child` / `th:last-child` 圆角 |
| 大屏面板内滚动失效 | 弹性面板必须 `flex:1` + `min-height:0` |
| 大屏在异比例屏变形 | 用舞台等比缩放，禁止响应式断点 |
| 长任务无反馈被重复点击 | 状态位 + 按钮 `disabled` + 加载文案（§5.1） |
| 弹窗层层叠加 | 二级用替换 + `‹ 返回上级`，不叠遮罩 |

---

## 9. CSS 基座（新页面直接复制）

```css
:root{
  /* 品牌 */
  --brand:#2f6bff; --brand-deep:#1a56f0; --brand-light:#6aa9ff; --brand-light2:#5a8ffb; --brand-pale:#9dbdfb;
  --grad-btn:linear-gradient(135deg,#2f6bff,#5a8ffb);
  --grad-bar:linear-gradient(90deg,#2f6bff,#6aa9ff);
  --grad-mark:linear-gradient(180deg,#2f6bff,#6aa9ff);
  /* 语义 */
  --blue:#2f6bff;   --blue-bd:#c9dcfc;   --blue-bg:#eef4ff;
  --green:#0f9d58;  --green-bd:#bfe9d2;  --green-bg:#f2fbf6;
  --orange:#e08600; --orange-bd:#f5ddb0; --orange-bg:#fdf7ea;
  --red:#e5484d;    --red-bd:#f7c6c8;    --red-bg:#fff2f2;
  --purple:#7a5af8; --purple-bd:#e0d7fb; --purple-bg:#f7f4ff;
  --gray:#7f8ca3;   --gray-bd:#dde5f1;   --gray-bg:#f5f8fd;
  /* 文字 */
  --ink-1:#1f2b43; --ink-2:#33415c; --ink-3:#5b6b85; --ink-4:#7f8ca3;
  --ink-5:#8a97ad; --ink-6:#9aa7bd; --ink-7:#b6c0d2;
  /* 背景与线 */
  --page-bg:radial-gradient(circle at 50% 40%, #eef2f9 0%, #e3e9f4 70%, #d8e0ee 100%);
  --surface:#fff; --pale:#f5f8fd; --row-hover:#fafcff;
  --line:#edf1f8; --line-weak:#f0f4fa; --bd-input:#dde5f1; --bd-card:#e8eef8; --bd-float:#e2e9f4;
  --rule:linear-gradient(90deg,#e4ebf7,transparent);
  /* 圆角 */
  --r-sm:8px; --r-md:9px; --r-lg:12px; --r-card:14px; --r-modal:18px; --r-pill:999px;
  /* 阴影 */
  --sh-card:0 4px 18px rgba(31,66,135,.05);
  --sh-btn:0 5px 12px rgba(47,107,255,.3);
  --sh-float:0 14px 38px rgba(18,35,68,.16);
  --sh-toast:0 10px 26px rgba(10,25,60,.3);
  --sh-modal:0 30px 80px rgba(10,25,60,.35);
  /* 动效 */
  --t:.15s;
}
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:100%;height:100%;background:var(--page-bg)}
body{font-family:"PingFang SC","Microsoft YaHei","Segoe UI",sans-serif;color:var(--ink-1);font-size:14px}
a{color:var(--brand);text-decoration:none;cursor:pointer}
a.danger{color:var(--red)}
.num{font-family:"Bahnschrift","DIN Alternate","Arial Narrow",sans-serif;font-weight:700;letter-spacing:.5px}
.h-bar{width:5px;border-radius:3px;background:var(--grad-mark);flex:none}
::-webkit-scrollbar{width:6px} ::-webkit-scrollbar-thumb{background:#cfd9ea;border-radius:3px}
```
> 其余组件按 §3 逐个复制（组件 CSS 已用具体色值书写，可原样使用，或按需替换为上述变量）。

---

## 10. 自检清单（每个新页面提交前逐项确认）

**视觉**
- [ ] 未出现规范外的色值（尤其是随手写的 `#f00`、`#ccc`、`#333`）
- [ ] 所有数字都加了 `.num`
- [ ] 卡片头具备「tick + 标题 + 渐变延伸线」结构
- [ ] 圆角、阴影取自 §1.6 / §1.7
- [ ] 状态同时用「颜色 + 文字」表达

**布局**
- [ ] 后台：侧栏 228 / 顶栏 64 / 内容区 `18px 28px 32px`
- [ ] 大屏：1920×1080 舞台 + 等比缩放，弹性面板有 `min-height:0`
- [ ] 含下拉浮层的卡片用了 `.ov`（§8.1）
- [ ] 宽表格可横滚，操作列不被挤压

**交互**
- [ ] 所有可增长列表都有分页
- [ ] 搜索框支持 Enter
- [ ] 危险操作满足三要素（红色 + 二次确认 + 风险说明）
- [ ] 长任务有状态位、进度、操作降级、完成 toast、执行记录
- [ ] 操作区按钮 >4 个已聚合，且下拉项均带功能说明
- [ ] 无原生 `alert / confirm`
- [ ] 空态 / 加载 / 失败三态齐备

**文案**
- [ ] 引用界面元素用「」；空态给引导；提示带结果数据
- [ ] 数字千分位、单位统一（家/条/人）
