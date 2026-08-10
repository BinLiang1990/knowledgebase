# 后端部署 / 运维手册（Docker 方式）

目标环境：阿里云 CentOS 服务器，用 Docker + Docker Compose 跑容器。

这是**跟 [运维.md](运维.md)（supervisor 直接跑 `.venv` 里的 uvicorn）平行的另一条部署路
径**，两者选一种即可——不要在同一台服务器上同时用两种方式管理同一个 8000 端口，否则会
端口冲突。数据库仍然是阿里云 RDS 上的 MySQL，不在容器里跑，两种部署方式连的是同一个库、
读的是同一份 `.env` 格式，随时可以切换。

## 为什么 Docker 不需要顾虑 运维.md 里提到的跨平台问题

运维.md 里强调不能把本机 `.venv` 直接搬到 CentOS 上，是因为 `uvloop`/`httptools` 是平台相
关的编译产物，Windows 装的和 CentOS x86_64 装的不是同一份文件。

Docker 镜像本身就是在 Linux 容器里现场 `uv sync` 出来的，只要构建镜像的机器（无论是服务
器自己，还是同架构的 CI/开发机）目标平台是 `linux/x86_64`，装出来的依赖就能在同架构的
CentOS 服务器上跑，不存在"从 Windows 搬 `.venv` 过去装不上"的问题。本文默认**直接在服务
器上 `docker build`**，最简单、不需要考虑镜像分发。

## 一、服务器一次性准备

```bash
# 装 Docker（阿里云 CentOS 8/9，官方脚本会自动识别系统）
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker

# 新版 Docker 自带 `docker compose`(v2插件)子命令，无需单独装 docker-compose；
# 用 `docker compose version` 确认一下能用即可。
```

> **不需要配 `/etc/docker/daemon.json` 的 `registry-mirrors`。** 2024 年起国内大部分
> 共享 Docker Hub 镜像加速器（包括曾经能用的 `registry.cn-hangzhou.aliyuncs.com` 通
> 用加速）陆续被收紧/下线，拉 `docker.io` 上的官方镜像经常直接 `403 Forbidden`，配
> registry-mirror 也救不回来。`Dockerfile` 里已经把基础镜像换成直连
> `docker.m.daocloud.io`（DaoCloud 托管的 docker.io 官方镜像镜像拷贝），不依赖
> registry-mirror 转发。build 前建议先手动验证一下这个域名在你的服务器上能不能拉通：
>
> ```bash
> docker pull docker.m.daocloud.io/library/python:3.10-slim-bookworm
> ```
>
> 如果这条也失败（镜像服务的可用性会变化），换成下面任一方案，改的地方都只是
> `Dockerfile` 第一行的 `FROM`：
> - 换一家同样托管了 docker.io 镜像拷贝的厂商，如
>   `ccr.ccs.tencentyun.com/library/python:3.10-slim-bookworm`；
> - 去阿里云容器镜像服务控制台（<https://cr.console.aliyun.com> → 镜像工具 → 镜像加
>   速器）领一个你账号专属的加速地址（形如 `https://xxxxxxxx.mirror.aliyuncs.com`，
>   不是本文之前用过的那个共享地址），配进 `/etc/docker/daemon.json` 的
>   `registry-mirrors` 后 `systemctl restart docker`，`FROM` 保持写
>   `python:3.10-slim-bookworm` 不用改。

## 二、部署代码（首次）

```bash
git clone <repo地址> /opt/kb-backend    # 之后更新用 git pull
cd /opt/kb-backend/backend
cp .env.example .env
vim .env                       # 填生产库的 DB_HOST/DB_USER/DB_PASSWORD 等，跟非 Docker 方式一样

docker compose -f deploy/docker-compose.yml build
docker compose -f deploy/docker-compose.yml up -d
```

`docker compose up` 会：

1. 用 `Dockerfile` 里的 `uv sync --frozen` 在镜像内装出跟 `uv.lock` 精确一致的依赖；
2. 启动容器时先跑一次 `alembic upgrade head` 建表/迁移，再启动 `uvicorn`
   （见 [deploy/docker-entrypoint.sh](deploy/docker-entrypoint.sh)）；
3. `restart: unless-stopped`：服务器重启或容器异常退出后自动拉起，等效于非 Docker 方式里
   `supervisor` 的 `autostart`/`autorestart`。

确认容器状态：

```bash
docker compose -f deploy/docker-compose.yml ps
curl http://127.0.0.1:8000/health
```

## 三、日常运维

```bash
# 查看日志(等效非 Docker 方式里的 /var/log/kb-backend/*.log)
docker compose -f deploy/docker-compose.yml logs -f

# 重启
docker compose -f deploy/docker-compose.yml restart

# 停止(不删除镜像，下次 up -d 直接复用)
docker compose -f deploy/docker-compose.yml down
```

## 四、更新代码（日常运维流程）

```bash
cd /opt/kb-backend && git pull
cd backend
docker compose -f deploy/docker-compose.yml build
docker compose -f deploy/docker-compose.yml up -d
```

`up -d` 会用新镜像重建容器，容器重新启动时 entrypoint 会再跑一次
`alembic upgrade head`——它是幂等的，已经应用过的迁移会被跳过，不会报错或重复执行，所以
不需要手动区分"是否已经迁移过"。

## 五、跟非 Docker 方式（运维.md）怎么选

| | 非 Docker（运维.md） | Docker（本文档） |
| --- | --- | --- |
| 依赖隔离 | `uv sync` 产出的 `.venv/`，跟系统 Python 隔离 | 镜像自带完整文件系统，隔离性更强 |
| 进程管理/自愈 | `supervisor` | Docker 自带的 `restart: unless-stopped` |
| 服务器需要装 | `uv` + `supervisor` | `docker` |
| 更新流程 | `git pull` → `uv sync` → `alembic upgrade head` → `supervisorctl restart` | `git pull` → `docker compose build` → `docker compose up -d` |
| 无外网出口时 | 需要在同架构机器上先 `uv sync` 出 `.venv` 再打包传过去 | 需要在同架构机器上先 `docker build`，再 `docker save`/`scp`/`docker load` 传过去 |

两条路径最终跑起来的都是同一份代码、同一个 `uvicorn kb_backend.main:app`、同一份 `.env`
格式，选哪个纯粹看服务器上更习惯用哪套工具链；不需要两个都部署。
