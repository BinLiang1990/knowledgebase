# 设计文档：后端项目骨架 + 数据模型 + 数据库迁移（issue #1）

- **Issue**: [BinLiang1990/knowledgebase#1](https://github.com/BinLiang1990/knowledgebase/issues/1)
- **状态**: Draft → 待对抗式自校验
- **依赖**: 无（本仓库第一个后端 issue）
- **相关 PRD**: `docs/PRD.md` §5（数据模型）、§4.10（响应结构）、§6（业务规则 #6/#12）

## 1. 目标（照抄 issue 验收标准，作为本设计的基线）

- [ ] 服务可以启动并连接 MySQL
- [ ] 四张表按 PRD §5 建好，含 `KnowledgeBase.name` 唯一索引、`KnowledgePoint(knowledge_base_id, title)` 唯一索引、`Answer(knowledge_point_id, coord_hash, effective_time, created_at)` 复合索引
- [ ] 任意接口返回统一的 `{code, data, msg}` 结构，可通过一个健康检查接口验证
- [ ] 迁移脚本可重复执行（幂等），团队其他成员可以拉库后一键建表

不在本 issue 范围内：知识库/知识点/维度/答案的业务 CRUD 接口（issue #2-#5）。

## 2. 技术选型（本 issue 内自主决定，记录理由）

| 选型 | 决定 | 理由 |
|---|---|---|
| Web 框架 | **FastAPI** | issue 里建议的默认项；自带 Pydantic 校验、OpenAPI 文档，和"维度取值强校验"（PRD §6 规则 #5）天然契合 |
| ORM | **SQLAlchemy 2.0（同步模式）** | 业务量级 PRD 里明确"v1 暂不追求高并发"，同步模式心智负担更低、调试更简单；FastAPI 对同步路由函数原生支持（线程池托管），不需要 async 驱动 |
| MySQL 驱动 | **PyMySQL** | 纯 Python 实现，Windows/Linux 都免编译，同步驱动，配合 SQLAlchemy 同步引擎 |
| 迁移工具 | **Alembic** | issue 明确要求；SQLAlchemy 官方迁移工具 |
| 配置管理 | **pydantic-settings**，从环境变量 / `.env` 读取 | 数据库连接串是敏感信息，不能进代码库；`.env` 已加入 `.gitignore`，提交 `.env.example` 作为模板 |
| 包管理 | **uv** | 用户环境已装好，`pyproject.toml` + `uv.lock` 保证可复现安装 |
| 测试 | **pytest** | issue-planner/afk 工作流约定的测试框架 |

## 3. 数据模型（相对 PRD §5 草案的两处工程化调整，明确记录）

PRD §5 是产品视角的草案，落地到关系型数据库时做了两处调整：

### 调整 1：`KnowledgeBase.enabled_dim_keys` 从"数组字段"改为独立关联表

PRD 草案里把 `enabled_dim_keys`写成 `KnowledgeBase` 上的一个列表字段（对应 demo 里的 JSON 数组）。落地时改为一张显式的关联表 `knowledge_base_enabled_dimension(knowledge_base_id, dimension_key)`：
- 可以对 `dimension_key` 建外键约束，维度被停用/改名时数据库层面就能保证一致性
- 查询"哪些知识库启用了某个维度"或"某知识库启用了哪些维度"都是标准 JOIN，不需要在应用层解析 JSON 数组
- 对 API 行为没有影响：知识库详情接口仍然可以在应用层把这张关联表拼成 PRD 期望的 `enabled_dimensions: [...]` 数组返回（这是 issue #3 的工作，本 issue 只建表）

### 调整 2：`KnowledgePoint.id` / `Answer.id` 使用全局唯一的自增主键

PRD 原文："id 主键(在所属知识库内唯一即可)"——这是 demo 里"每个知识库内部从 1 开始编号"的产物。落地时使用数据库全局自增 `BIGINT`：
- 全局唯一自动满足"知识库内唯一"这个更弱的要求，不违反 PRD
- 避免"per-parent 自增序列"这种少见模式带来的额外实现复杂度（分布式环境下 per-parent 自增序列容易出并发冲突）
- 对外 API 行为不变：知识点/答案的 ID 依然只在配合 `knowledge_base_id` 时才有业务意义，第三方本来就不会跨知识库直接猜 ID（PRD §8 已明确不支持跨知识库检索）

### 表结构

对抗式自校验发现的三处修订，已经体现在下面的 DDL 里，不再单独罗列旧版本：
- 所有 FK 从 `ON DELETE CASCADE` 改成 `ON DELETE RESTRICT`——PRD §8 明确不支持物理删除，CASCADE 相当于给"不小心的硬删除"开了一条静默销毁历史数据的后门；RESTRICT 让这种误操作直接报错，而不是吞掉数据。
- 所有表显式声明 `utf8mb4` 字符集与 `utf8mb4_0900_ai_ci` 排序规则（本系统内容以中文为主，不能依赖服务器的默认字符集）。
- `dimension_definition.weight` 加 `CHECK` 约束，`answer.knowledge_point_id` 改成复合外键，确保 `answer.knowledge_base_id` 不会和它所属知识点的 `knowledge_base_id` 产生分裂（该字段本身是 PRD §5 要求的反规范化冗余，用于跨知识库统计，复合外键保证它不会"撒谎"）。

```sql
-- 知识库
CREATE TABLE knowledge_base (
  id            BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  name          VARCHAR(255) NOT NULL,
  description   TEXT NULL,
  status        ENUM('active','deprecated') NOT NULL DEFAULT 'active',
  created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_knowledge_base_name (name)
) DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 维度定义(全局)
CREATE TABLE dimension_definition (
  `key`          VARCHAR(100) PRIMARY KEY,
  label          VARCHAR(255) NOT NULL,
  field_type     ENUM('text','number','date','boolean') NOT NULL,
  weight         SMALLINT UNSIGNED NOT NULL DEFAULT 50,
  default_value  VARCHAR(255) NULL,
  status         ENUM('active','deprecated') NOT NULL DEFAULT 'active',
  created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT ck_dimension_weight CHECK (weight BETWEEN 1 AND 100)
) DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 知识库 <-> 启用维度（工程化调整 1）
CREATE TABLE knowledge_base_enabled_dimension (
  knowledge_base_id  BIGINT UNSIGNED NOT NULL,
  dimension_key       VARCHAR(100) NOT NULL,
  PRIMARY KEY (knowledge_base_id, dimension_key),
  CONSTRAINT fk_kbed_kb FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_base(id) ON DELETE RESTRICT,
  CONSTRAINT fk_kbed_dim FOREIGN KEY (dimension_key) REFERENCES dimension_definition(`key`) ON DELETE RESTRICT
) DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 知识点
CREATE TABLE knowledge_point (
  id                 BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  knowledge_base_id  BIGINT UNSIGNED NOT NULL,
  title              VARCHAR(255) NOT NULL,
  status             ENUM('active','deleted') NOT NULL DEFAULT 'active',
  operator           VARCHAR(100) NOT NULL DEFAULT 'admin',
  created_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  deleted_at         DATETIME NULL,
  delete_reason      VARCHAR(500) NULL,
  CONSTRAINT fk_kp_kb FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_base(id) ON DELETE RESTRICT,
  UNIQUE KEY uq_kp_kb_title (knowledge_base_id, title),
  UNIQUE KEY uq_kp_id_kb (id, knowledge_base_id)
) DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 答案
CREATE TABLE answer (
  id                  BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  knowledge_base_id   BIGINT UNSIGNED NOT NULL,
  knowledge_point_id  BIGINT UNSIGNED NOT NULL,
  coord               JSON NOT NULL,
  coord_hash          CHAR(64) NOT NULL,
  content             LONGTEXT NOT NULL,
  effective_time      DATE NOT NULL,
  operator            VARCHAR(100) NOT NULL DEFAULT 'admin',
  source              VARCHAR(100) NOT NULL DEFAULT '人工填报',
  note                TEXT NULL,
  revoked             BOOLEAN NOT NULL DEFAULT FALSE,
  revoked_at          DATETIME NULL,
  revoked_by          VARCHAR(100) NULL,
  revoke_reason       VARCHAR(500) NULL,
  created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_answer_kp_kb FOREIGN KEY (knowledge_point_id, knowledge_base_id)
    REFERENCES knowledge_point(id, knowledge_base_id) ON DELETE RESTRICT,
  KEY ix_answer_resolve (knowledge_point_id, coord_hash, effective_time, created_at)
) DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```

`coord_hash` 定为 **SHA-256 十六进制摘要（固定 64 字符）**，而不是"排序拼接后截断的字符串"：截断字符串在维度多、取值长时可能超过索引列宽度被截断，导致两个不同的条件组合意外撞成同一个 `coord_hash`，破坏"同 coord = 同一条版本链"这个解析算法(§4.6.1)赖以成立的前提。具体的规范化规则（数值/日期/布尔取值怎么归一化后再参与哈希）由 issue #4/#5 实现，但摘要算法和列宽在本 issue 就锁定，避免两个 issue 对列宽的假设不一致。

不做数据库触发器计算 `coord_hash`——保持迁移脚本纯 DDL，业务逻辑留在应用代码（issue #4/#5 会用到）。本 issue 只需要列存在、索引建好。

## 4. 统一响应结构（PRD §4.10）

**修订**：设计初稿曾打算"HTTP 状态码固定 200，真正的成败信号只放在 body 的 `code` 字段"，对抗式自校验发现这个决定有实际代价——会让基于状态码的基础设施监控/告警在真实故障时也看到 0% 错误率，也会让 OpenAPI 生成的客户端失去按状态码分流的能力，而 PRD §4.10 本身只规定了 body 结构（`code:200/444`），并没有要求 HTTP 状态码也固定为 200。改为：

- **HTTP 状态码保持真实语义**：成功 200；请求体/查询参数校验失败(FastAPI/Pydantic 422) 用 422；路由不存在 404、方法不允许 405 保持原样；自定义业务异常 `BusinessError` 用 400；未捕获异常用 500。
- **无论 HTTP 状态码是什么，响应体永远是 `{code, data, msg}` 结构**：`code` 字段的取值仍按 PRD §4.10 约定——成功 200，任何异常路径统一 444（body 里的 `code` 不跟 HTTP 状态码绑定，第三方只要解析 body 就能拿到一致的成败信号；同时保留了 HTTP 层的可观测性，两边不冲突）。
- 实现方式：
  1. `envelope(data, msg="操作成功")` 帮助函数用于成功路径（HTTP 200）。
  2. 自定义 `BusinessError` 异常 + handler → `{code:444, data:{}, msg:<原因>}`，HTTP 400。
  3. 注册 `RequestValidationError` handler → 同样的 444 body，HTTP 422（覆盖issue #2 起才会出现的带请求体接口，本 issue 就先接好，避免"任意接口"这条验收标准在下一个 issue 就被打破）。
  4. 注册 Starlette `HTTPException` handler → 同样的 444 body，保留其原始状态码（404/405 等）。
  5. 兜底的通用 `Exception` handler → `{code:444, data:{}, msg:"内部错误"}`，HTTP 500，避免把内部堆栈泄露给第三方。
- 健康检查接口 `GET /health`：执行 `SELECT 1`，成功返回 `{code:200, data:{"database":"ok"}, msg:"操作成功"}`（HTTP 200）；数据库连不上时返回 `{code:444, data:{}, msg:"database unavailable"}`，HTTP 500。

## 5. 项目结构

```
backend/
  pyproject.toml
  .env.example
  alembic.ini
  migrations/
    env.py
    versions/
  src/kb_backend/
    __init__.py
    config.py          # pydantic-settings，读 DATABASE_URL 等
    db.py              # engine / SessionLocal / get_db 依赖
    envelope.py         # 响应结构 + BusinessError + 异常处理器注册
    main.py             # FastAPI app 入口，挂 /health
    models/
      __init__.py
      base.py           # DeclarativeBase
      knowledge_base.py
      dimension.py
      knowledge_point.py
      answer.py
  tests/
    conftest.py
    test_config.py
    test_health.py
    test_models_migrate.py
```

## 6. 测试计划（TDD，先写这些再实现）

1. `test_config.py`：`Settings` 能从环境变量正确读出 `database_url`，缺失时报错而不是静默用空字符串。
2. `test_health.py`：
   - 用 FastAPI `TestClient` 打 `/health`，断言返回体是 `{"code":200,"data":{"database":"ok"},"msg":"操作成功"}`，HTTP 状态 200。
   - monkeypatch 模拟 DB 连接失败，断言返回体 `code=444`、HTTP 状态 500，而不是把堆栈原样抛给调用方。
   - 打一个不存在的路径，断言返回体仍是 `{code:444,...}` 结构（HTTP 404）——验证 `HTTPException` handler 生效。
   - 给 `/health` 加一个仅测试用的严格类型 query 参数触发 422，断言返回体仍是 `{code:444,...}`——验证 `RequestValidationError` handler 生效，避免"任意接口"这条验收标准只在 issue #1 里成立、issue #2 一上线就破功。
3. `test_models_migrate.py`：对真实测试数据库（同一个 `knowledgebase` schema，测试自己建、自己清理，不污染）跑 `alembic upgrade head`，断言：
   - 五张表都存在；
   - `knowledge_base.name`、`knowledge_point(knowledge_base_id,title)`、`knowledge_point(id,knowledge_base_id)` 三个唯一索引存在**且** `information_schema.STATISTICS.NON_UNIQUE=0`（只查存在性不够，要确认真的是 UNIQUE 而不是普通 KEY）；
   - `ix_answer_resolve (knowledge_point_id, coord_hash, effective_time, created_at)` 存在；
   - 通过 SQLAlchemy session 分别对 `knowledge_base.name` 和 `knowledge_point(knowledge_base_id,title)` 插入重复值，断言抛出 `IntegrityError`（证明约束真的生效，不只是存在于 DDL 文本里）；
   - 再跑一次 `alembic upgrade head` 验证幂等（不报错、表结构不变）。

## 7. 风险 / 未决问题

- 迁移测试会在真实的 `knowledgebase` schema 上创建/清理表——需要确保测试固件在结束时清理，不留脏数据给后续 issue。采用"每次测试前先 `alembic downgrade base` 再 `upgrade head`"的策略，保证幂等可重复。
- `coord_hash` 摘要算法(SHA-256)与列宽(CHAR(64))已在本 issue 锁定；具体的取值归一化规则（数值/日期/布尔怎么转成参与哈希的规范字符串）留给 issue #4/#5 决定。

## 8. Out of Scope（与 issue 描述一致）

知识库/维度/知识点/答案的业务 CRUD 与查询接口——全部留给 issue #2-#5。
