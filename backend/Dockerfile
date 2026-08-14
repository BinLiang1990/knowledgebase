# 基础镜像不直接拉 docker.io/library/python——2024 年起国内大部分共享 Docker Hub
# 镜像加速器（包括曾经能用的 registry.cn-hangzhou.aliyuncs.com 通用加速）陆续被
# 收紧/下线，对 docker.io 上的官方镜像经常直接 403，daemon.json 里配 registry-mirror
# 也救不回来。这里改成直连 DaoCloud 托管的镜像仓库（docker.m.daocloud.io），它本身
# 就是 docker.io 官方镜像的一份镜像拷贝，不走 registry-mirror 转发机制，更稳。
# 如果这个域名某天也失效了，换成别家托管的同一份镜像即可（如
# ccr.ccs.tencentyun.com/library/python:3.10-slim-bookworm），或者去阿里云容器镜像
# 服务控制台（cr.console.aliyun.com → 镜像工具 → 镜像加速器）领一个你账号专属的加速
# 地址配进 /etc/docker/daemon.json 的 registry-mirrors。
#
# uv 从阿里云 PyPI 镜像装——这是 pip 协议的镜像，跟上面 docker 镜像仓库被限流是两回事，
# 一直很稳定。容器内 uv sync 装出的依赖天生是 linux/x86_64 的编译产物，不存在"从
# Windows/macOS 搬 .venv 过去装不上"的问题（对比 运维.md）。
FROM docker.m.daocloud.io/library/python:3.10-slim-bookworm

# uv 版本锁死：不锁的话每次 build 拉最新版，lock 文件格式/镜像源行为可能变化
# （2026-08-14 踩坑：装依赖的源真正由 uv.lock 里记录的 registry 决定——见
# pyproject.toml 的 [[tool.uv.index]] 注释——当年的 UV_INDEX_URL 环境变量在新版
# uv 里对 `uv sync --frozen` 不生效，导致国内服务器 build 直连 pypi.org 卡死）。
# 升级 uv 时同步用同版本重新 `uv lock`，并确认阿里云镜像已同步该版本——
# 刚发布一两天的 uv 新版可能还没进镜像（0.12.4 就因此装不到，退回 0.12.3）。
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple "uv==0.12.3"

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON=python3.10

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
