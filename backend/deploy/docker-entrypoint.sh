#!/bin/sh
set -e

# alembic upgrade head 是幂等的：已经应用过的迁移会被跳过，容器每次启动重跑一次
# 也不会报错或重复执行，所以放在 entrypoint 里不需要额外判断"是否已迁移过"。
alembic upgrade head

exec uvicorn kb_backend.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers "${UVICORN_WORKERS:-2}"
