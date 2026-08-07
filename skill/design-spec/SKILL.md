---
name: design-spec
description: 根据 docs/PRD.md 里的每条需求，生成一份设计规范（配色/字体/风格/布局/反模式），每条需求的原始描述与验收标准和它对应的设计指南并排展示。底层复用 skill/ui-ux-pro-max 的设计知识库（161 套配色、57 组字体搭配、161 种产品类型等）。适用场景：PRD 已经写好，需要一份可以直接交给前端的设计规范文档，而不是从零开始讨论风格。
user-invocable: true
allowed-tools:
  - Read
  - Write
  - Bash
---

# /design-spec — 用 PRD 驱动生成设计规范

把 `docs/PRD.md`（或 `$ARGUMENTS` 指定的 PRD 路径）里的每条需求，变成一份带设计指南的
规范文档：每条需求的描述 + 验收标准，紧跟着它对应页面的配色/字体/风格/布局建议。

底层依赖 `skill/ui-ux-pro-max/scripts/` 下两个脚本：
- `parse_prd.py` — 把 PRD 解析成结构化需求列表（id/标题/描述/验收标准/slug）
- `build_prd_design_spec.py` — 结合关键词简报，生成 `MASTER.md` + 每页 override +
  汇总文档 `PRD-设计规范.md`

## 为什么中间有一步必须由你（Claude）来做，不能全自动

底层设计知识库是纯英文关键词的 BM25 检索（产品类型、风格、配色表全是英文词条，比如
`saas`、`dashboard`、`government`、`fintech`）。PRD 需求通常是中文自然语言，没有可靠的
自动翻译能把"企业数据 CSV 导入与字段映射"直接变成能命中检索库的关键词——这需要理解
需求的产品/交互意图。所以这个技能的核心工作就是：**你读懂每条需求，为它挑出恰当的英文
设计关键词**，脚本只负责机械的解析、检索、拼装。

## 工作流程

### 1. 确定 PRD 路径并解析

默认 `docs/PRD.md`；`$ARGUMENTS` 里给了路径就用那个。

```bash
python skill/ui-ux-pro-max/scripts/parse_prd.py docs/PRD.md
```

（Windows 下用项目里已有的 venv：`.venv/Scripts/python.exe`，如无 venv 用
`python3`/`python`。若命令因中文控制台编码报 `UnicodeDecodeError`/乱码，
临时设置 `PYTHONUTF8=1` 环境变量重试。）

读它的输出（或直接读 PRD 原文），拿到每条需求的 id、标题、描述、验收标准。

### 2. 给每条需求写关键词简报（关键的语义提炼步骤）

对每条需求，判断：
- 它属于什么产品/行业类别？（贴近 `--domain product` 的英文词汇，如
  `government`、`saas`、`b2b`、`analytics dashboard`、`fintech` 等）
- 它对应的页面类型是什么？（`dashboard`、`form`、`chat assistant`、`export`、
  `settings`、`landing` 等）

如果拿不准某个领域关键词是否会命中，可以先用只读检索验证（不会落盘）：

```bash
python skill/ui-ux-pro-max/scripts/search.py "<候选关键词>" --domain product
```

汇总成一份 `brief.json`（写到临时目录或 `design-system/<project-slug>/` 下，
不要提交到仓库）：

```json
{
  "project_query": "<整体产品定位关键词，决定全局 MASTER.md>",
  "pages": {
    "<需求编号>": "<该需求对应页面的关键词>",
    "...": "..."
  }
}
```

没被列进 `pages` 的需求仍会出现在最终文档里，但会标注"沿用全局规范"。不要为了
凑数量给每条需求硬编关键词——拿不准产品类别的需求，宁可留空让它走全局规范。

### 3. 生成

```bash
python skill/ui-ux-pro-max/scripts/build_prd_design_spec.py docs/PRD.md brief.json \
  -p "<项目名>" [--force]
```

项目名优先用 `$ARGUMENTS` 里用户给的；否则从 PRD 第一行标题里提炼一个人可读的英文/
拼音项目名（不要直接塞中文，`_safe_slug` 会把非 ASCII 字符全部吃掉导致目录名冲突）。

首次生成不用 `--force`；如果 `design-system/<project-slug>/` 已存在且要覆盖，
需要显式加 `--force`（和底层 `--persist` 的安全行为一致，避免误覆盖用户手改过的规范）。

### 4. 汇报结果

告诉用户生成了哪些文件（`MASTER.md` / 各 `pages/*.md` / `PRD-设计规范.md`），
以及有哪些需求因为没写关键词简报而回退到全局规范——不要替用户悄悄决定要不要
提交这些文件到 git，只汇报路径。

---

## 边界

- 不负责审查 PRD 本身的完整性（那是 `/expand-prd` 的职责），也不修改 `docs/PRD.md`。
- 关键词简报是这个技能里唯一需要主观判断的步骤，做完之后如果用户对某条需求的设计
  方向不认可，直接改 `brief.json` 对应条目重跑第 3 步即可，不需要重新解析 PRD。
- 生成的是设计**规范**（颜色/字体/布局/组件基调），不是页面代码；实现页面时按
  `skill/ui-ux-pro-max/SKILL.md` 里 Step 3/4 的方式查具体 UX 细则和技术栈实现建议。
