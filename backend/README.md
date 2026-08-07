# kb-backend

后端服务骨架，见 `docs/PRD.md` 与 `docs/specs/2026-08-07-backend-skeleton-design.md`（issue #1）。

## 环境准备

```bash
cd backend
cp .env.example .env   # 填入真实的 MySQL 连接信息，.env 已在 .gitignore 里
uv sync
```

## 建表 / 迁移

```bash
uv run alembic upgrade head      # 建表
uv run alembic downgrade base    # 回滚(清空本项目管理的表)
```

## 启动服务

```bash
uv run uvicorn kb_backend.main:app --reload
curl http://127.0.0.1:8000/health
```

## 测试

```bash
uv run pytest
```

`tests/test_models_migrate.py` 会在 `.env` 指向的真实数据库上跑迁移做断言，测试前后都会把库还原到 `base`（不留数据），不要对着生产库的 `.env` 跑测试。
