# 基于官方 uv 镜像：自带匹配的 CPython + uv，容器内装的依赖天生是
# linux/x86_64 的编译产物，不存在"从 Windows/macOS 搬 .venv 过去装不上"的问题
# （对比 运维.md 里非 Docker 方式的顾虑）。
FROM ghcr.io/astral-sh/uv:python3.10-bookworm-slim

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# 先只拷依赖清单再 uv sync，代码改动不会让这一层缓存失效，重复 build 更快。
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY alembic.ini ./
COPY migrations ./migrations
RUN uv sync --frozen --no-dev

# .venv/bin 里的 alembic / uvicorn 已经是绑定好隔离环境的可执行文件，
# 加进 PATH 后直接调用即可，不需要在容器里再跑一次 `uv run`。
ENV PATH="/app/.venv/bin:$PATH"

COPY deploy/docker-entrypoint.sh ./docker-entrypoint.sh
RUN chmod +x ./docker-entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
