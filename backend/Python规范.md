# Python 编码规范（kb-backend）

本规范从本项目后端现有代码中提炼而来，新代码应与之保持一致。示例均取自真实代码。

## 1. 工具链与项目结构

- Python **3.10+**，用 **uv** 管理依赖与虚拟环境（`pyproject.toml` + `uv.lock`，构建后端为 `uv_build`）。
- 运行命令统一走 `uv run`：`uv run pytest`、`uv run alembic upgrade head`、`uv run uvicorn kb_backend.main:app --reload`。
- 开发依赖放在 `[dependency-groups] dev`（pytest、httpx），不混入运行时依赖。
- 采用 **src 布局**，按职责分层：

```
backend/
├── src/kb_backend/
│   ├── main.py          # FastAPI 应用装配：中间件、异常处理器、include_router
│   ├── config.py        # pydantic-settings 配置
│   ├── db.py            # engine / sessionmaker / get_db 依赖
│   ├── envelope.py      # 统一 {code, data, msg} 响应壳 + 异常处理器
│   ├── coord.py 等      # 纯业务逻辑模块（不依赖 FastAPI）
│   ├── models/          # SQLAlchemy ORM 模型，一个领域一个文件
│   ├── schemas/         # Pydantic 请求/响应模型，与 models 同名对应
│   └── routers/         # APIRouter，一个领域一个文件
├── migrations/          # Alembic 迁移，文件名 000N_描述.py 递增编号
└── tests/               # pytest，平铺 test_*.py
```

分层规则：**routers 只做 HTTP 层**（取参、调库、包 envelope）；可复用的纯逻辑（如 coord 归一化、resolve 算法）放独立模块，不 import FastAPI；models 与 schemas 严格分开，路由永远不直接返回 ORM 对象。

## 2. 命名

- 模块、函数、变量：`snake_case`；类：`PascalCase`；模块级常量：`UPPER_SNAKE_CASE`。
- 模块内私有的函数/常量一律加 `_` 前缀：`_get_or_404`、`_DUPLICATE_KEY_MSG`、`_MYSQL_ER_DUP_ENTRY`。
- 魔法值必须提成命名常量，包括错误消息文案：

```python
_DUPLICATE_KEY_MSG = "维度已存在，请使用其他名称"
_NOT_FOUND_MSG = "维度不存在"
_MYSQL_ER_DUP_ENTRY = 1062
```

- Pydantic schema 命名后缀固定：`XxxCreate` / `XxxUpdate` / `XxxOut`（对外只读视图）/ `XxxAdminOut`（内部管理视图）。

## 3. 类型标注

- 所有函数（含私有函数、测试函数）都写完整签名，包括返回类型；测试函数写 `-> None`。
- 使用 3.10+ 原生语法：`str | None`、`dict[str, Any]`、`list[str]`，不用 `Optional` / `Dict` / `List`。
- 生成器类型从 `collections.abc` 导入：`Generator[Session, None, None]`。
- 需要前向引用或纯注解场景时在文件头加 `from __future__ import annotations`。

## 4. import 顺序与方式

三段式分组，段间空行，段内按字母序（标准库 → 第三方 → 本项目）：

```python
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

from kb_backend.config import get_settings
```

- 子包内部（routers/、models/、schemas/）互相引用用**相对导入**（`from ..db import get_db`、`from .base import Base`）；入口 `main.py` 用绝对导入 `kb_backend.*`。
- 不用 `import *`；同一路由文件把用到的 schema 一行 import 齐。

## 5. 注释与 docstring（本项目最重要的约定）

**注释只写代码本身看不出来的东西**：约束、坑、"为什么这样做而不是另一种做法"。不写"这行在干什么"的复述型注释。

- 凡是决策来自文档或评审发现，**注明出处**：`design doc §4.4`、`docs/PRD.md §4.6.1`、`Found by the Codex outer-gate review on PR #17`。以后有人想"简化"这段代码时，出处就是它不能删的理由。
- 反直觉的行为必须写清机制，例如：

```python
# bool is an int subclass in Python — float(True) == 1.0 would silently
# accept a boolean as a number. Reject explicitly before any conversion.
if isinstance(raw_value, bool):
    raise CoordValueError(key, f"维度 {key} 取值类型错误，应为数值")
```

- 模块级 docstring 说明模块的契约与依据（如 envelope.py 开头解释 `{code, data, msg}` 与 HTTP 状态码的关系）；公共函数 docstring 写调用契约（参数已被谁过滤过、会抛什么异常），而不是重复签名。
- 故意省略某个字段/默认值时，注释说明"为什么没有"，例如 `DimensionUpdate` 里 field_type 被整体省略、`EnabledDimensionsUpdate.dimension_keys` 不设默认值。

## 6. FastAPI 路由层

- 每个领域一个 `APIRouter(tags=["xxx"])`，在 `main.py` 统一 `include_router`。
- 所有接口返回统一信封，声明返回类型 `-> dict`：

```python
@router.post("/dimensions")
def create_dimension(payload: DimensionCreate, db: Session = Depends(get_db)) -> dict:
    ...
    return envelope(out.model_dump(mode="json"))
```

- 成功用 `envelope(data)`（`{code: 200, data, msg: "操作成功"}`）；业务失败抛 `BusinessError("中文消息", status_code=...)`，由 `envelope.py` 注册的全局异常处理器统一转成 `{code: 444, data: {}, msg}`。**路由里不手拼错误 JSON，不直接抛 HTTPException**。
- 面向用户的错误消息一律中文；422 的字段级细节只记日志、不返回给调用方。
- 路由内重复出现的取数/校验逻辑提成模块内 `_` 前缀 helper（`_get_or_404`、`_set_status`、`_to_admin_out`），并与同类文件的既有 helper 命名对齐（注释注明 "Mirrors knowledge_base.py's ..."）。

## 7. Pydantic schema

- 校验尽量前移到 schema，用 `Field` 声明约束：`Field(min_length=1, max_length=100)`、`Field(default=50, ge=1, le=100)`；长度上限要和**实际落库的列宽**对齐（见 `DimensionCreate.label` 取 key 的 100 而非 label 列的 255）。
- 枚举值用 `Literal["text", "number", "date", "boolean"]`，不用裸 str。
- 自定义校验用 `@field_validator` + `@classmethod`，共享逻辑提成模块级 `_` 函数（如 `_stripped_non_empty_label`）。
- PATCH 语义：用 `payload.model_fields_set` 区分"字段没传（保持不变）"和"显式传 null（清空或报错）"，不要只看值是不是 None。
- 创建后不可修改的字段，直接**不出现在 Update schema 里**，让它结构上就发不出来，而不是运行时拒绝。
- 输出模型加 `model_config = {"from_attributes": True}`，序列化用 `model_dump(mode="json")`。

## 8. SQLAlchemy / 数据库

- 全部使用 **SQLAlchemy 2.0 风格**：`Mapped[...]` + `mapped_column`，查询用 `select(...)`，不用 legacy Query API。
- 时间戳列统一用 `models/base.py` 的 `created_at_column()` / `updated_at_column()`（`DATETIME(fsp=6)` + 服务端默认值），不要自己另写。
- 布尔条件用 `.is_(False)` / `.is_(True)`，不用 `== False`。
- 写入的固定模式——commit 失败先 rollback，再把 MySQL 1062 翻译成业务错误，其他完整性错误原样抛出；commit 后 `db.refresh(obj)` 拿服务端生成值（sessionmaker 配了 `expire_on_commit=False`，不 refresh 会拿到旧值）：

```python
db.add(dim)
try:
    db.commit()
except IntegrityError as exc:
    db.rollback()
    _raise_if_duplicate_key(exc)
db.refresh(dim)
```

- 幂等写接口（activate/deactivate 之类）先判断是否已处于目标状态，避免空提交。
- 建表/改表只走 Alembic 迁移；每个迁移必须可 `downgrade`，测试依赖 base↔head 往返。

## 9. 配置

- 配置集中在 `config.py` 的 `Settings(BaseSettings)`，通过 `@lru_cache get_settings()` 获取，不在别处读环境变量。
- `.env` 路径相对本文件解析（`Path(__file__).resolve().parent...`），不依赖进程工作目录。
- 必填配置**不给默认值**——缺了就在启动时报校验错误，绝不静默回退成空字符串。

## 10. 异常与日志

- 业务异常抛 `BusinessError`；包装底层异常时保留异常链：`raise BusinessError(...) from exc`。
- 自定义异常继承合适的内建异常并携带上下文（如 `CoordValueError(ValueError)` 带 `dimension_key`）。
- 日志用 `logging.getLogger("kb_backend")`，`%s` 惰性格式化，不用 f-string 拼日志。未捕获异常必须 `logger.exception(...)` 记完整堆栈，客户端只看到"内部错误"。

## 11. 输入防御

对来自请求的任意文本/数值，先想清楚它最终流向哪里，在入口就设边界：

- 在昂贵操作**之前**做廉价预检（如数值字符串先限长 100，再交给 `Decimal` 解析；先用 `adjusted()` 判断量级，再 `int()` 物化）。
- 不用请求里的任意文本拼 SQL/JSON path 表达式——宁可把数据取回来在 Python 里处理（见 dimension 的 answer_count 统计）。
- 会进入 URL 路径段的值，创建时就拒绝 `/` 等无法回访的字符。
- 精度敏感的比较（浮点、collation 大小写不敏感的 key）要用**库里存的规范值**，不要用请求原文。

## 12. 测试

- pytest，测试平铺在 `tests/`，按功能命名 `test_api_xxx.py` / `test_xxx.py`；公共 fixture 放 `conftest.py`。
- 测试函数名描述行为：`test_normalize_number_rejects_boolean`；同型多输入用 `@pytest.mark.parametrize`。
- 断言异常用 `with pytest.raises(...)`；因坑而生的测试在 docstring 里写清那个坑。
- API 测试用 `fastapi.testclient.TestClient`；需要真实表的测试依赖 `migrated_schema` fixture（function 级，base→head 建表、结束还原到 base），**不要**自建 session 级"只迁移一次"的变体。

> ⚠️ **测试会清空 `.env` 指向的数据库**（`migrated_schema` 会 downgrade 到 base，teardown 还会 TRUNCATE）。目前没有独立测试库隔离，**严禁对着生产库的 `.env` 跑 `pytest`**。

## 13. 其他

- 行宽以现有代码为准（约 110 列以内），长调用链用括号换行（见 `list_dimensions` 的 select 写法）。
- 字符串用双引号。
- 有意忽略的参数显式 `del probe`，不留"未使用变量"的歧义。
- 模块级懒加载单例（engine/sessionmaker）用 `_` 前缀模块变量 + `global` 惰性初始化，见 `db.py`。
