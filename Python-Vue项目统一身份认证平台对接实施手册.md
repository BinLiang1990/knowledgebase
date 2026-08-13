<!-- markdownlint-disable MD013 -->

# Python + Vue 项目统一身份认证平台对接实施手册

> 版本：v1.0  
> 日期：2026-08-13  
> 适用技术栈：Python 3.9+、FastAPI（Flask/Django 可按同样分层迁移）、Vue 3、Vite、TypeScript、Axios、Pinia  
> 统一平台前端：`https://platform-identity.yicall.com/web/`  
> 统一平台后端：`https://platform-identity.yicall.com/`

## 1. 目标与最终行为

完成接入后，系统必须同时支持两种互斥运行模式：

| 环境 | 认证方式 | 登录入口 | 请求凭证 |
| --- | --- | --- | --- |
| 本地开发 | 本系统账号密码 | 展示本地登录页 | `Authorization: Bearer <local-token>` |
| 正式环境 | 统一身份认证平台 | `/login` 直接跳转统一平台 | `IDENTITYTOKEN: <identity-token>` |

统一平台只负责认证身份和本系统访问资格，本系统继续负责业务角色、租户、菜单、按钮和数据权限。前端不得直接请求统一平台后端接口；Ticket 换票、Token 验证和用户信息查询全部通过本系统后端转发。

正式环境中的完整流程：

```text
统一工作台
  → 子系统 /sso?ticket=...
  → Vue 立即清除地址栏 Ticket
  → POST 子系统后端 /api/auth/sso_login
  → Python 后端携带 HMAC 调用统一平台 /core/sso/exchange
  → Python 后端使用返回的 IDENTITYTOKEN 查询 /core/user/userInfo
  → Python 后端同步本地用户快照并计算本地权限
  → Vue 保存 IDENTITYTOKEN 和 loginDeviceType
  → 后续请求只访问本系统后端
```

## 2. 接入前必须向统一平台确认的信息

在开发前取得并确认以下参数，禁止自行猜测：

```yaml
systemCode: 统一平台登记的系统编码
clientId: HMAC 客户端标识，通常与 systemCode 相同
clientSecret: HMAC 明文密钥，只存后端
authDomain: PUBLIC 或 INTRANET
entryUrl: 本系统正式前端接票地址，例如 https://example.com/app/#/sso
acceptedTicketTypes: SAME_DOMAIN，内网跨域系统可能还包括 CROSS_DOMAIN
```

统一平台需要保证用户信息接口能提供稳定的角色编码 `roleCode`，或者提供使用当前 Token 查询角色列表的接口：

```http
POST /core/user/roleList
IDENTITYTOKEN: <identity-token>
X-App-Type: <loginDeviceType>
system-code: <systemCode>
```

角色列表项至少包含：

```json
{
  "id": 1,
  "roleName": "超级管理员",
  "roleCode": "super_admin"
}
```

角色自动映射的唯一规则：

| 统一平台角色编码 | 本系统初始角色 |
| --- | --- |
| `super_admin` | 系统管理员 |
| `admin` | 普通用户 |
| 其他角色编码或无角色 | 普通用户 |

不得根据角色名称判断，不得把 `admin` 映射为管理员，不得长期写死某个 `roleId` 等于超级管理员。角色 ID 是数据库标识，角色编码才是跨系统稳定契约。

## 3. 统一平台接口契约

以下字段依据 2026-08-13 的统一平台 OpenAPI 整理。接入时应保存一份当时的 OpenAPI 快照并进行契约测试。

### 3.1 同域 Ticket 换票

```http
POST https://platform-identity.yicall.com/core/sso/exchange
Content-Type: application/json
X-Sso-Client: <clientId>
system-code: <systemCode>
X-Sso-Timestamp: <13位毫秒时间戳>
X-Sso-Nonce: <32位随机十六进制字符串>
X-Sso-Signature: <HMAC-SHA256小写十六进制>

{"ticket":"一次性Ticket"}
```

HMAC 签名原文固定为六段，各段使用一个换行符连接，末尾不追加换行：

```text
POST
/core/sso/exchange
<clientId>
<timestamp>
<nonce>
<SHA256(实际请求体字节)>
```

计算方式：

```text
signature = hex_lowercase(
  HMAC-SHA256(clientSecret明文字节, 签名原文UTF-8字节)
)
```

请求体参与摘要，因此用于计算摘要的 JSON 字节必须和实际发送的 JSON 字节完全一致。推荐使用紧凑 JSON：无空格、UTF-8、中文不转义。

成功响应结构：

```json
{
  "code": 200,
  "msg": "成功",
  "data": {
    "systemCode": "目标系统编码",
    "tokenInfo": {
      "tokenName": "IDENTITYTOKEN",
      "tokenValue": "统一Token",
      "tokenTimeout": 28800,
      "loginDeviceType": "ADMIN"
    },
    "userId": 10001,
    "account": "zhangsan",
    "realName": "张三",
    "orgId": 10,
    "orgCode": "ORG001",
    "orgName": "示例组织"
  }
}
```

注意：平台可能使用 HTTP 200 返回业务失败。只有业务字段 `code=200` 才是成功，其他业务码必须使用平台返回的 `msg` 报错。

### 3.2 跨域 Ticket 换票

只有系统注册允许跨域且后端配置接受 `CROSS_DOMAIN` 时才开放：

```http
POST /core/cross-domain/session/login
```

请求体：

```json
{
  "ticket": "一次性Ticket",
  "ticketType": "CROSS_DOMAIN",
  "systemCode": "服务端固定系统编码"
}
```

签名路径必须改为 `/core/cross-domain/session/login`。`systemCode` 仍由后端固定配置，不能接受前端指定。

### 3.3 查询当前统一用户

```http
POST https://platform-identity.yicall.com/core/user/userInfo
Content-Type: application/json
IDENTITYTOKEN: <identity-token>
X-App-Type: <loginDeviceType>
system-code: <systemCode>

{}
```

`X-App-Type` 可选值为 `PORTAL`、`ADMIN`、`H5`、`DASHBOARD`。它不是本系统业务类型，而是统一 Token 的登录设备类型。

必须优先使用换票结果的 `data.tokenInfo.loginDeviceType`。若换票结果未提供，才使用后端配置的兜底值 `ADMIN`。使用错误的设备类型会导致统一平台认为 Token 无效或报“Token 设备类型不匹配”。

当前 OpenAPI 声明的用户信息主要字段：

```json
{
  "id": 10001,
  "account": "zhangsan",
  "realName": "张三",
  "orgId": 10,
  "orgCode": "ORG001",
  "orgName": "示例组织",
  "roleId": 1,
  "systems": ["your-system-code"]
}
```

如果 `/core/user/userInfo` 没有返回 `roleCode`，后端必须在同一 Token 和同一 `X-App-Type` 下调用 `/core/user/roleList` 获取角色编码。禁止仅凭 `roleId` 推导 `super_admin`。

## 4. 后端环境配置

建议提供可提交仓库的 `.env.auth.example`，真实 `.env` 不提交。示例文件只能放占位符，不得包含真实 `clientSecret`。

后端需要 HTTP 客户端依赖，若项目尚未安装：

```bash
pip install httpx
```

本地环境：

```dotenv
AUTH_MODE=local
LOCAL_LOGIN_ENABLED=true
AUTH_SYSTEM_CODE=your-system-code
AUTH_DOMAIN=PUBLIC
AUTH_ACCEPTED_TICKET_TYPES=SAME_DOMAIN
```

正式环境：

```dotenv
AUTH_MODE=unified
LOCAL_LOGIN_ENABLED=false
AUTH_SYSTEM_CODE=your-system-code
AUTH_DOMAIN=PUBLIC
AUTH_ACCEPTED_TICKET_TYPES=SAME_DOMAIN

IDENTITY_BASE_URL=https://platform-identity.yicall.com
IDENTITY_CLIENT_ID=your-client-id
IDENTITY_CLIENT_SECRET=统一平台分配的明文客户端密钥
IDENTITY_EXCHANGE_URL=https://platform-identity.yicall.com/core/sso/exchange
IDENTITY_USERINFO_URL=https://platform-identity.yicall.com/core/user/userInfo
IDENTITY_ROLE_LIST_URL=https://platform-identity.yicall.com/core/user/roleList
IDENTITY_APP_TYPE=ADMIN
IDENTITY_SSO_TIMEOUT=10

```

安全要求：

- `IDENTITY_CLIENT_SECRET` 是明文 HMAC 密钥，不进行密码哈希，但必须由部署密钥系统或服务器 `.env` 管理。
- Secret 不得进入前端环境变量、Git、镜像、浏览器、日志、错误响应或监控事件。
- `AUTH_SYSTEM_CODE`、Ticket 类型允许列表和第三方接口地址只能来自后端配置。
- 生产环境必须设置 `AUTH_MODE=unified` 且 `LOCAL_LOGIN_ENABLED=false`。
- 配置变更后必须重启或重新创建后端进程/容器。

## 5. 后端数据库模型

不要把统一平台用户整表复制到本系统。推荐“登录时即时同步身份快照 + 本系统独立维护业务授权”。

用户表至少增加：

```sql
ALTER TABLE users ADD COLUMN identity_user_id BIGINT NULL;
ALTER TABLE users ADD COLUMN identity_account VARCHAR(255) NULL;
ALTER TABLE users ADD COLUMN display_name VARCHAR(255) NULL;
ALTER TABLE users ADD COLUMN auth_source VARCHAR(16) NOT NULL DEFAULT 'local';
ALTER TABLE users ADD COLUMN platform_role_id BIGINT NULL;
ALTER TABLE users ADD COLUMN platform_role_code VARCHAR(64) NULL;
ALTER TABLE users ADD COLUMN identity_updated_at DOUBLE NULL;
CREATE UNIQUE INDEX uk_users_identity_user_id ON users(identity_user_id);
```

如果项目支持多租户，使用关系表，不要把一个用户限制为单一租户：

```sql
CREATE TABLE user_tenant_roles (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  tenant_id BIGINT NOT NULL,
  role VARCHAR(32) NOT NULL,
  created_at DOUBLE NOT NULL,
  updated_at DOUBLE NOT NULL,
  UNIQUE KEY uk_user_tenant_role (user_id, tenant_id)
);
```

本系统角色建议：

```text
sysadmin     系统管理员，跨全部租户，不设置租户角色
tenant_admin 某个租户管理员
user         某个租户普通用户；没有租户时可登录但无业务数据权限
```

统一用户首次进入：

1. 使用统一 `userId` 查找本地用户。
2. 不存在则创建 `auth_source=unified`、无本地密码、角色 `user`、无租户的身份快照。
3. 存在则更新账号、姓名、组织、角色编码等身份字段。
4. 若 `roleCode=super_admin`，自动成为系统管理员并清空历史租户角色。
5. 若 `roleCode=admin` 或其他值，平台角色本身不授予本系统管理权限。
6. 非超级管理员是否保留此前由本系统人工设置的系统管理员权限，应由项目明确。推荐保留人工授权，除非业务规定平台降级必须同步撤权。

## 6. Python 后端参考实现

以下代码可以直接拆分到 `app/core/unified_auth.py`、`app/core/user_access.py` 和认证路由中。数据库函数需要替换为目标项目自己的 ORM 或 DAO。

### 6.1 统一平台客户端

```python
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
import httpx


AUTH_MODE = os.getenv("AUTH_MODE", "local").strip().lower()
SYSTEM_CODE = os.getenv("AUTH_SYSTEM_CODE", "").strip()
ACCEPTED_TICKET_TYPES = {
    item.strip().upper()
    for item in os.getenv("AUTH_ACCEPTED_TICKET_TYPES", "SAME_DOMAIN").split(",")
    if item.strip()
}
IDENTITY_BASE_URL = os.getenv(
    "IDENTITY_BASE_URL", "https://platform-identity.yicall.com"
).rstrip("/")
IDENTITY_CLIENT_ID = os.getenv("IDENTITY_CLIENT_ID", SYSTEM_CODE).strip()
IDENTITY_CLIENT_SECRET = os.getenv("IDENTITY_CLIENT_SECRET", "").strip()
IDENTITY_EXCHANGE_URL = os.getenv(
    "IDENTITY_EXCHANGE_URL", f"{IDENTITY_BASE_URL}/core/sso/exchange"
)
IDENTITY_USERINFO_URL = os.getenv(
    "IDENTITY_USERINFO_URL", f"{IDENTITY_BASE_URL}/core/user/userInfo"
)
IDENTITY_ROLE_LIST_URL = os.getenv(
    "IDENTITY_ROLE_LIST_URL", f"{IDENTITY_BASE_URL}/core/user/roleList"
)
IDENTITY_APP_TYPE = os.getenv("IDENTITY_APP_TYPE", "ADMIN").strip().upper()
IDENTITY_APP_TYPES = {"PORTAL", "ADMIN", "H5", "DASHBOARD"}
SSO_TIMEOUT = max(1.0, float(os.getenv("IDENTITY_SSO_TIMEOUT", "10")))


class UnifiedAuthError(RuntimeError):
    pass


def is_unified_mode() -> bool:
    return AUTH_MODE == "unified"


def _unwrap(body: object) -> dict:
    if not isinstance(body, dict):
        raise UnifiedAuthError("统一身份认证平台返回格式无效")
    if body.get("code") is None:
        return body
    if str(body.get("code")) != "200":
        raise UnifiedAuthError(
            str(body.get("msg") or body.get("message") or "统一身份认证平台处理失败")
        )
    data = body.get("data")
    return data if isinstance(data, dict) else {}


def _hmac_headers(path: str, body_bytes: bytes) -> dict[str, str]:
    if not IDENTITY_CLIENT_SECRET:
        raise UnifiedAuthError("未配置 IDENTITY_CLIENT_SECRET")
    timestamp = str(int(time.time() * 1000))
    nonce = secrets.token_hex(16)
    digest = hashlib.sha256(body_bytes).hexdigest()
    message = f"POST\n{path}\n{IDENTITY_CLIENT_ID}\n{timestamp}\n{nonce}\n{digest}"
    signature = hmac.new(
        IDENTITY_CLIENT_SECRET.encode(), message.encode(), hashlib.sha256
    ).hexdigest()
    return {
        "Content-Type": "application/json",
        "X-Sso-Client": IDENTITY_CLIENT_ID,
        "system-code": SYSTEM_CODE,
        "X-Sso-Timestamp": timestamp,
        "X-Sso-Nonce": nonce,
        "X-Sso-Signature": signature,
    }


def _post_json(url: str, **kwargs) -> dict:
    try:
        response = httpx.post(url, timeout=SSO_TIMEOUT, **kwargs)
    except httpx.HTTPError as exc:
        raise UnifiedAuthError("统一身份认证平台暂时不可用") from exc
    try:
        body = response.json()
    except ValueError as exc:
        raise UnifiedAuthError("统一身份认证平台返回格式无效") from exc
    if response.status_code >= 400:
        message = body.get("msg") if isinstance(body, dict) else None
        raise UnifiedAuthError(str(message or "统一身份认证平台请求失败"))
    return body


def exchange_ticket(ticket: str, ticket_type: str = "SAME_DOMAIN") -> dict:
    ticket_type = ticket_type.upper()
    if not ticket:
        raise ValueError("单点登录票据不能为空")
    if ticket_type not in {"SAME_DOMAIN", "CROSS_DOMAIN"}:
        raise ValueError("不支持的单点登录票据类型")
    if ticket_type not in ACCEPTED_TICKET_TYPES:
        raise PermissionError("当前系统不接受此类型的单点登录票据")

    path = (
        "/core/sso/exchange"
        if ticket_type == "SAME_DOMAIN"
        else "/core/cross-domain/session/login"
    )
    request_data = {"ticket": ticket}
    if ticket_type == "CROSS_DOMAIN":
        request_data.update({"ticketType": ticket_type, "systemCode": SYSTEM_CODE})
    body_bytes = json.dumps(
        request_data, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    url = (
        IDENTITY_EXCHANGE_URL
        if ticket_type == "SAME_DOMAIN"
        else f"{IDENTITY_BASE_URL}{path}"
    )
    body = _post_json(url, content=body_bytes, headers=_hmac_headers(path, body_bytes))
    data = _unwrap(body)
    if data.get("systemCode") and data["systemCode"] != SYSTEM_CODE:
        raise UnifiedAuthError("Ticket 目标系统不匹配")
    token_info = data.get("tokenInfo") or {}
    if not token_info.get("tokenValue"):
        raise UnifiedAuthError("统一身份认证平台未返回统一 Token")
    return {"tokenInfo": token_info, "exchangeUser": data}


def _app_type(value: str | None) -> str:
    fallback = IDENTITY_APP_TYPE if IDENTITY_APP_TYPE in IDENTITY_APP_TYPES else "ADMIN"
    current = str(value or fallback).strip().upper()
    return current if current in IDENTITY_APP_TYPES else fallback


def identity_headers(token: str, app_type: str | None) -> dict[str, str]:
    return {
        "IDENTITYTOKEN": token,
        "X-App-Type": _app_type(app_type),
        "system-code": SYSTEM_CODE,
    }


def current_identity(token: str, app_type: str | None) -> dict:
    body = _post_json(
        IDENTITY_USERINFO_URL,
        json={},
        headers=identity_headers(token, app_type),
    )
    data = _unwrap(body)
    identity = data.get("user") or data.get("identityUser") or data
    if not isinstance(identity, dict) or not (identity.get("id") or identity.get("userId")):
        raise UnifiedAuthError("统一身份认证平台未返回用户ID")
    systems = identity.get("systems")
    if isinstance(systems, list) and SYSTEM_CODE not in systems:
        raise PermissionError("当前用户无本系统访问权限")
    return identity


def current_role_codes(token: str, app_type: str | None) -> set[str]:
    body = _post_json(
        IDENTITY_ROLE_LIST_URL,
        json={},
        headers=identity_headers(token, app_type),
    )
    if not isinstance(body, dict):
        raise UnifiedAuthError("统一身份认证平台角色返回格式无效")
    if body.get("code") is not None and str(body.get("code")) != "200":
        raise UnifiedAuthError(str(body.get("msg") or "统一身份认证平台角色查询失败"))
    items = body.get("data") or []
    if not isinstance(items, list):
        raise UnifiedAuthError("统一身份认证平台角色返回格式无效")
    return {
        str(item.get("roleCode") or "").strip().lower()
        for item in items
        if isinstance(item, dict) and item.get("roleCode")
    }
```

### 6.2 用户同步和角色映射

```python
def is_platform_super_admin(role_codes: set[str]) -> bool:
    # 唯一自动提权条件。admin 和其他角色都返回 False。
    return "super_admin" in {code.lower() for code in role_codes}


def sync_identity(identity: dict, role_codes: set[str]) -> dict:
    identity_user_id = identity.get("userId") or identity.get("id")
    if identity_user_id in (None, ""):
        raise ValueError("统一身份认证平台未返回用户ID")

    # 以下 repo.* 由目标项目使用 SQLAlchemy、Django ORM 或自有 DAO 实现。
    user = repo.find_by_identity_user_id(int(identity_user_id))
    if user is None:
        user = repo.create_unified_user(
            identity_user_id=int(identity_user_id),
            account=str(identity.get("account") or f"identity:{identity_user_id}"),
            display_name=str(identity.get("realName") or identity.get("account") or ""),
            local_role="user",
            password_hash=None,
        )

    repo.update_identity_snapshot(
        user.id,
        account=identity.get("account"),
        display_name=identity.get("realName"),
        platform_role_id=identity.get("roleId"),
        platform_role_code=",".join(sorted(role_codes)),
        org_id=identity.get("orgId"),
        org_code=identity.get("orgCode"),
        org_name=identity.get("orgName"),
    )

    platform_super_admin = is_platform_super_admin(role_codes)
    if platform_super_admin:
        # 系统管理员跨全部租户，不再设置租户角色。
        repo.clear_tenant_roles(user.id)

    return repo.build_local_permission_payload(
        user.id,
        platform_super_admin=platform_super_admin,
    )
```

关键约束：

- `admin` 只能得到普通用户初始身份，不能映射为 `tenant_admin` 或 `sysadmin`。
- 普通统一用户无租户时允许登录，但只能访问 `/api/auth/me`、租户查询和“暂无权限”页面，不能读写业务数据。
- 系统管理员不设置租户角色，成为系统管理员时清空历史租户关系。
- 前端只展示后端返回的权限结果，不自行根据 `roleCode` 推导权限。

### 6.3 FastAPI SSO 路由

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/auth", tags=["认证"])


class SsoLoginIn(BaseModel):
    ticket: str
    # 当前公网平台可能只回传 ticket，缺省按同认证域处理。
    ticketType: str = "SAME_DOMAIN"


@router.post("/sso_login")
def sso_login(body: SsoLoginIn):
    if not is_unified_mode():
        raise HTTPException(400, "当前环境未启用统一身份认证登录")
    try:
        exchanged = exchange_ticket(body.ticket, body.ticketType)
        token_info = exchanged["tokenInfo"]
        token = token_info["tokenValue"]
        app_type = token_info.get("loginDeviceType")
        identity = current_identity(token, app_type)
        role_codes = current_role_codes(token, app_type)
        local_user = sync_identity(
            {**exchanged["exchangeUser"], **identity}, role_codes
        )
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except (UnifiedAuthError, ValueError) as exc:
        raise HTTPException(401, str(exc)) from exc
    return {
        "tokenInfo": {"tokenName": "IDENTITYTOKEN", **token_info},
        "identityUser": identity,
        "localUser": local_user,
    }
```

### 6.4 受保护接口鉴权

后端应从浏览器请求读取：

```text
IDENTITYTOKEN
X-Identity-App-Type
```

`X-Identity-App-Type` 是子系统内部请求头。后端校验允许值后，将它转换成调用统一平台时的 `X-App-Type`。不要允许前端提供统一平台地址、`system-code` 或 HMAC 参数。

```python
def verify_identity_token(token: str, app_type: str | None) -> dict | None:
    if not token:
        return None
    try:
        identity = current_identity(token, app_type)
        role_codes = current_role_codes(token, app_type)
        return sync_identity(identity, role_codes)
    except (UnifiedAuthError, ValueError, PermissionError, KeyError, TypeError):
        return None
```

FastAPI 依赖示例：

```python
from fastapi import Header, HTTPException, Request


def get_current_user(
    request: Request,
    identitytoken: str | None = Header(None, alias="IDENTITYTOKEN"),
):
    payload = getattr(request.state, "auth_payload", None)
    if payload is None:
        payload = verify_identity_token(
            identitytoken or "",
            request.headers.get("X-Identity-App-Type"),
        )
    if not payload:
        raise HTTPException(401, "登录已过期，请重新登录")
    return payload
```

生产流量较大时，不建议每个请求都远程调用统一平台。优先采用统一平台提供的认证域 Redis、Sa-Token 官方 SDK 或本地短时校验缓存；但无论采用哪种方式，都必须校验 Token 有效性、本系统 Scope/系统准入和本地业务权限，并做到认证状态不确定时拒绝请求。

## 7. Vue 前端参考实现

### 7.1 环境配置

Vue 项目至少需要 Axios、Pinia 和 Vue Router；已安装时无需重复执行：

```bash
npm install axios pinia vue-router
```

`.env.development`：

```dotenv
VITE_APP_BASE_API=/api
VITE_AUTH_MODE=local
VITE_AUTH_DOMAIN=PUBLIC
VITE_SYSTEM_CODE=your-system-code
```

`.env.production`：

```dotenv
VITE_APP_BASE_API=/your-api-prefix
VITE_AUTH_MODE=unified
VITE_IDENTITY_LOGIN_URL=https://platform-identity.yicall.com/web/
VITE_AUTH_DOMAIN=PUBLIC
VITE_SYSTEM_CODE=your-system-code
```

前端只能配置统一平台前端登录页。禁止配置 `clientSecret`，禁止直接配置或请求 `/core/sso/exchange`、`/core/user/userInfo`、`/core/user/roleList`。

### 7.2 认证常量与存储

```typescript
export const AUTH_MODE = import.meta.env.VITE_AUTH_MODE === 'unified'
  ? 'unified'
  : 'local'
export const IS_UNIFIED_AUTH = AUTH_MODE === 'unified'
export const IDENTITY_LOGIN_URL = import.meta.env.VITE_IDENTITY_LOGIN_URL || ''
export const AUTH_DOMAIN = import.meta.env.VITE_AUTH_DOMAIN || 'PUBLIC'
export const SYSTEM_CODE = import.meta.env.VITE_SYSTEM_CODE || ''

export const TOKEN_KEY = IS_UNIFIED_AUTH
  ? `enterprise-platform:auth:${AUTH_DOMAIN}:token`
  : `${SYSTEM_CODE}:local-token`
export const IDENTITY_APP_TYPE_KEY
  = `enterprise-platform:auth:${AUTH_DOMAIN}:app-type`
export const USER_KEY = `enterprise-platform:app:${SYSTEM_CODE}:user`
export const TOKEN_HEADER = IS_UNIFIED_AUTH ? 'IDENTITYTOKEN' : 'Authorization'

export function tokenHeaderValue(token: string): string {
  return IS_UNIFIED_AUTH ? token : `Bearer ${token}`
}
```

```typescript
export const getToken = () => localStorage.getItem(TOKEN_KEY) || ''
export const setToken = (token: string) => localStorage.setItem(TOKEN_KEY, token)
export const removeToken = () => localStorage.removeItem(TOKEN_KEY)

export const getIdentityAppType
  = () => localStorage.getItem(IDENTITY_APP_TYPE_KEY) || ''
export const setIdentityAppType
  = (value: string) => localStorage.setItem(IDENTITY_APP_TYPE_KEY, value)
export const removeIdentityAppType
  = () => localStorage.removeItem(IDENTITY_APP_TYPE_KEY)
```

禁止使用 `localStorage.clear()`，否则同源部署的其他系统也会被清理。

### 7.3 Axios 请求拦截器

```typescript
service.interceptors.request.use((config) => {
  const token = getToken()
  if (token)
    config.headers.set(TOKEN_HEADER, tokenHeaderValue(token))

  const appType = getIdentityAppType()
  if (IS_UNIFIED_AUTH && appType)
    config.headers.set('X-Identity-App-Type', appType)

  return config
})
```

SSE、文件上传、文件下载等绕过 Axios 的请求也必须携带相同请求头。

401 处理：

```typescript
function handleNotLogin(): void {
  removeToken()
  removeIdentityAppType()
  resetDynamicRoutes()
  location.hash = '#/login'
}
```

登录接口自身的 401 是 Ticket 或账号错误，不应被当作存量会话失效重复跳转。

### 7.4 SSO API 与 Pinia

```typescript
export type TicketType = 'SAME_DOMAIN' | 'CROSS_DOMAIN'

export interface SsoResult {
  tokenInfo: {
    tokenName: string
    tokenValue: string
    tokenTimeout?: number
    loginDeviceType?: 'PORTAL' | 'ADMIN' | 'H5' | 'DASHBOARD'
  }
  localUser: UserMe
}

export function ssoLogin(ticket: string, ticketType: TicketType) {
  return request.post<SsoResult>('/auth/sso_login', { ticket, ticketType })
}
```

```typescript
async function loginByTicket(ticket: string, ticketType: TicketType) {
  const result = await ssoLogin(ticket, ticketType)
  setToken(result.tokenInfo.tokenValue)
  if (result.tokenInfo.loginDeviceType)
    setIdentityAppType(result.tokenInfo.loginDeviceType)
  applyCurrentUser(result.localUser)
}
```

### 7.5 `/sso` 接票页

必须支持统一平台当前只回传 `ticket` 的形式：

```text
https://your-domain.example.com/app/#/sso?ticket=...
```

同时兼容 Query 位于 Hash 前的部署形式。参考实现：

```typescript
async function handleSsoEntry(): Promise<void> {
  const pageQuery = new URLSearchParams(window.location.search)
  const hashQuery = new URLSearchParams(window.location.hash.split('?')[1] || '')
  const ticket = hashQuery.get('ticket') || pageQuery.get('ticket') || ''
  const ticketType = String(
    hashQuery.get('ticketType') || pageQuery.get('ticketType') || 'SAME_DOMAIN',
  ).toUpperCase() as TicketType

  // Ticket 只留在当前函数内存，读取后立即清除地址栏。
  window.history.replaceState({}, '', `${window.location.pathname}#/sso`)

  if (!ticket || !['SAME_DOMAIN', 'CROSS_DOMAIN'].includes(ticketType)) {
    showError('单点登录参数无效，请从统一工作台重新进入')
    return
  }

  try {
    await loginByTicket(ticket, ticketType)
    await router.replace('/')
  }
  catch {
    showError('单点登录失败，请从统一工作台重新进入')
  }
}
```

禁止把 Ticket 或 Token 输出到控制台、日志、埋点、错误上报，禁止把 Ticket 存入浏览器存储，禁止使用同一个 Ticket 自动重试。

### 7.6 路由守卫

```typescript
router.beforeEach(async (to) => {
  if (to.path === '/login' && IS_UNIFIED_AUTH) {
    window.location.replace(IDENTITY_LOGIN_URL)
    return false
  }

  // 接票页优先放行，避免浏览器残留旧 Token 阻止消费新 Ticket。
  if (to.path === '/sso')
    return true

  if (!getToken())
    return { path: '/login', query: { redirect: to.fullPath } }

  try {
    await ensureCurrentUserLoaded()
  }
  catch {
    clearCurrentSession()
    return { path: '/login' }
  }
})
```

正式环境的 `/login` 只做统一平台跳转，不渲染本地账号密码表单；本地环境继续展示原登录页。

## 8. 本系统用户与权限规则

建议统一采用以下规则，避免项目间口径不一致：

1. 能取得本系统 Ticket 的统一用户允许进入系统，不要求管理员提前创建本地同名账号。
2. 用户首次进入按统一 `userId` 创建身份快照，不保存统一平台密码。
3. 只有统一平台角色编码 `super_admin` 自动成为本系统系统管理员。
4. 统一平台角色编码 `admin` 只是普通用户，不自动拥有租户或管理权限。
5. 普通用户首次进入默认不关联租户，可登录但看不到业务数据。
6. 本系统管理员可以为普通用户分配一个或多个租户，每个租户独立设为租户管理员或普通用户。
7. 系统管理员跨全部租户，不设置租户角色；设为系统管理员时清空历史租户角色。
8. 统一平台管理用户身份和访问资格，本系统管理最终业务权限和数据范围。
9. 前端权限展示只用于体验，所有接口必须在后端再次鉴权。

## 9. 错误处理规范

| 场景 | HTTP | 建议错误码 | 用户提示/行为 |
| --- | ---: | --- | --- |
| Ticket 缺失、过期或已消费 | 401 | `AUTH_TICKET_INVALID` | 从统一工作台重新进入，不自动重试 |
| Token 缺失、失效、设备不匹配 | 401 | `AUTH_TOKEN_INVALID` | 清 Token 和设备类型，重新登录 |
| 统一平台不可达 | 503 | `AUTH_IDENTITY_UNAVAILABLE` | 提示稍后重试 |
| 平台响应不是 JSON/结构缺失 | 502 | `AUTH_IDENTITY_RESPONSE_INVALID` | 记录安全日志并报警 |
| 用户无本系统准入 | 403 | `AUTH_SYSTEM_ACCESS_DENIED` | 返回统一工作台 |
| 用户无本系统业务权限 | 403 | `AUTH_PERMISSION_DENIED` | 保留登录态，只提示无权限 |
| 普通用户未分配租户 | 403 | `AUTH_TENANT_UNASSIGNED` | 展示“联系系统管理员分配租户” |

平台返回 HTTP 200、业务 `code!=200` 时必须保留平台 `msg`。只有 JSON 解析失败或必要字段确实缺失时，才使用“统一身份认证平台返回格式无效”。

服务端日志可以记录：接口路径、HTTP 状态、平台业务码、traceId、耗时、异常栈。不得记录：Ticket、完整 Token、clientSecret、带 Ticket 的完整 URL、HMAC 签名原文。

## 10. 安全红线

- 前端不得调用统一平台后端接口。
- 前端不得持有 `clientSecret`。
- Ticket 一次性消费，不重试、不持久化、不记录。
- `system-code` 必须由后端固定，不能信任前端参数。
- `loginDeviceType` 只用于统一 Token 校验，不能当作业务角色。
- `admin` 不能自动映射成本系统管理员。
- 不得仅凭 `roleId` 自动提权。
- 不得仅验证登录而跳过本地租户、角色和数据权限。
- 不得把完整 Token 保存到数据库或日志。
- 正式环境必须关闭本地登录、新增本地用户和重置本地密码功能。
- 本地环境账号不得同步到统一平台，也不能用于正式环境登录。

## 11. 测试用例

### 11.1 后端单元与契约测试

- HMAC 固定输入产生固定签名。
- HMAC 使用的请求体字节与实际发送字节完全一致。
- 换票请求携带 `X-Sso-Client`、`system-code`、时间戳、Nonce、签名。
- `code=200` 正确解析 `data.tokenInfo.tokenValue` 和 `loginDeviceType`。
- HTTP 200、业务失败时保留平台 `msg`。
- 用户信息请求使用换票返回的 `loginDeviceType`。
- 非法设备类型回落到 `ADMIN`，不能原样转发任意值。
- `roleCode=super_admin` 自动映射系统管理员。
- `roleCode=admin` 映射普通用户。
- 其他角色和空角色映射普通用户。
- 平台超级管理员的历史租户角色被清空。
- 普通无租户用户可调用 `/api/auth/me`，但不能访问业务接口。
- 正式模式拒绝本地账号密码登录。
- 本地模式不调用统一平台。

### 11.2 前端测试

- 正式模式访问 `/login` 直接跳统一平台前端地址。
- 本地模式访问 `/login` 展示账号密码表单。
- `/sso?ticket=...` 能读取 Ticket，并立即从地址栏删除。
- 只有 `ticket` 时默认使用 `SAME_DOMAIN`。
- 非法 `ticketType` 被拒绝。
- SSO 成功后保存 Token 和 `loginDeviceType`。
- Axios、SSE、上传和下载均携带正确请求头。
- 401 清理 Token 和设备类型，业务 403 不清理登录态。
- 浏览器存储中不存在 Ticket、clientSecret 和无命名空间的共享用户状态。

### 11.3 联调验收矩阵

| 用例 | 预期结果 |
| --- | --- |
| 统一平台 `super_admin` 进入 | 自动成为系统管理员，可访问全部租户 |
| 统一平台 `admin` 首次进入 | 普通用户、无租户、无业务数据 |
| 统一平台普通角色首次进入 | 普通用户、无租户、无业务数据 |
| 为普通用户分配租户管理员 | 仅在指定租户有管理权限 |
| 同一用户分配多个租户 | 可切换租户，每个租户角色独立 |
| 提升为本系统系统管理员 | 清除租户角色，跨全部租户 |
| Ticket 重复使用 | 第二次必须失败 |
| 修改 `system-code` | Ticket 或系统准入校验失败 |
| 使用错误 `X-App-Type` | 统一平台拒绝；正确实现应使用换票设备类型 |
| 统一平台不可用 | 子系统失败关闭，不降级为免登录 |

## 12. 上线步骤

1. 在统一平台登记系统：确认 `systemCode`、`clientId`、`clientSecret`、`entryUrl`、认证域和 Ticket 类型。
2. 确认统一平台能通过 `userInfo` 或 `roleList` 返回稳定 `roleCode`。
3. 执行数据库迁移，先增加身份字段和多租户关系表。
4. 发布后端，先用测试 Ticket 验证换票签名、`system-code` 和设备类型。
5. 发布前端，确认正式构建使用 `VITE_AUTH_MODE=unified`。
6. 检查 Nginx：前端 `/#/sso` 可访问，API 前缀正确转发，允许自定义请求头。
7. 使用 `super_admin`、`admin`、普通用户分别完成一次登录验收。
8. 确认正式环境本地登录、新增本地用户、重置本地密码全部关闭。
9. 检查日志和监控中没有 Ticket、Token、Secret。
10. 保留回滚版本，但不得通过开启正式环境本地登录来绕过统一认证故障。

容器部署修改 `.env` 后应重新创建服务，例如：

```bash
docker compose up -d --force-recreate web worker
```

## 13. 常见故障定位

| 报错 | 常见原因 | 排查方法 |
| --- | --- | --- |
| 当前环境未启用统一身份认证登录 | 后端 `AUTH_MODE` 不是 `unified`，或容器未重启 | 容器内检查环境变量并重新创建服务 |
| 统一身份认证平台暂时不可用 | 后端无法连接平台、DNS/TLS/代理异常 | 从后端容器请求平台健康地址/OpenAPI |
| SSO 请求签名错误 | Secret 错误、请求体字节不一致、签名路径错误、时钟偏差 | 对照六段式原文逐段核对 |
| Ticket 不存在、已过期或已使用 | Ticket 超过有效期、重复消费、手工刷新接票页 | 从工作台重新进入，禁止自动重试 |
| 统一平台未返回统一 Token | 响应包络解析错误，或平台业务失败被当成成功 | 只接受 `code=200`，读取 `data.tokenInfo.tokenValue` |
| 统一平台返回格式无效 | 真正的非 JSON/字段缺失，或错误地吞掉平台业务消息 | 先检查 `code/msg`，业务错误原样保留 |
| Token 设备类型不匹配 | 用户信息请求固定写了错误的 `X-App-Type` | 使用换票返回的 `loginDeviceType` |
| 当前用户未配置本系统账号 | 仍要求预建本地账号 | 改为按统一 `userId` 首次登录即时创建快照 |
| `admin` 被误判为系统管理员 | 按角色名称或 `roleId` 判断 | 仅检查 `roleCode == 'super_admin'` |
| 新用户登录后无数据 | 默认没有租户，属于正常权限状态 | 由本系统管理员分配租户 |

## 14. 交付检查清单

### 统一平台

- [ ] 系统注册信息正确且启用。
- [ ] `entryUrl` 精确指向正式前端 `/#/sso`。
- [ ] 当前用户确实在该系统允许访问范围内。
- [ ] 能返回 Token 的 `loginDeviceType`。
- [ ] 能返回或查询稳定的 `roleCode`。

### Python 后端

- [ ] 提供 local/unified 两种认证模式。
- [ ] 正式环境关闭本地登录。
- [ ] HMAC 六段式签名和请求体一致。
- [ ] 换票请求携带固定 `system-code`。
- [ ] 用户信息请求使用 Token 对应设备类型。
- [ ] 角色编码只认 `super_admin` 自动提权。
- [ ] `admin` 和其他角色均为普通用户。
- [ ] 本地用户按统一 `userId` 即时同步。
- [ ] 本地业务权限和数据权限独立校验。
- [ ] 错误信息区分平台业务失败和格式错误。
- [ ] 日志不包含 Ticket、Token 和 Secret。

### Vue 前端

- [ ] 正式 `/login` 直接跳统一平台前端。
- [ ] 本地 `/login` 保留账号密码登录。
- [ ] `/sso` 支持只有 `ticket` 的回跳。
- [ ] Ticket 读取后立即从地址栏清除。
- [ ] 只调用本系统后端，不调用统一平台后端。
- [ ] 保存 `IDENTITYTOKEN` 和 `loginDeviceType`。
- [ ] Axios/SSE/上传/下载请求头全部覆盖。
- [ ] 401 与业务 403 分开处理。
- [ ] 正式环境隐藏新增本地用户和密码重置。
- [ ] 未使用 `localStorage.clear()`。

全部勾选并完成 `super_admin`、`admin`、普通用户三类账号联调后，才可以认为接入完成。

## 15. 参考接口

- 统一平台 OpenAPI：`https://platform-identity.yicall.com/v3/api-docs`
- 同域换票：`POST /core/sso/exchange`
- 当前用户：`POST /core/user/userInfo`
- 当前用户角色：`POST /core/user/roleList`

OpenAPI 是接口结构依据，本文中的安全规则、角色映射和本地权限模型是子系统必须额外实现的业务约束。
