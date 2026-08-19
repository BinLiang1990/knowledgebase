"""角色模型与接口权限规则表（纯逻辑，issue #36 设计文档 §D2/§3.1）。

角色梯度：none(未授权) < viewer(只读) < editor(业务读写) < admin(+维度配置
/建删库) < sysadmin(+用户管理)。用户首登默认 none——可登录但看不到业务
数据；唯一自动提权是平台 roleCode=super_admin → sysadmin。

规则表按 (method, path) 决定一个请求要求的最低角色；auth.deps 的全局
依赖据此放行/拦截。集中一张表而不是在每个端点挂装饰器，保证第三方
豁免面与《对接接口文档-约定基准版》§5 逐条对应、可单测。
"""
from __future__ import annotations

import re

ROLE_LEVELS = {"none": 0, "viewer": 1, "editor": 2, "admin": 3, "sysadmin": 4}
ASSIGNABLE_ROLES = frozenset(ROLE_LEVELS)

# 平台角色 → 本系统初始角色的唯一自动映射（手册 §2：只认 roleCode，
# super_admin 之外一律不提权——admin 也只是普通未授权用户）。
PLATFORM_SUPER_ADMIN = "super_admin"


def is_platform_super_admin(role_codes: set[str]) -> bool:
    return PLATFORM_SUPER_ADMIN in {code.strip().lower() for code in role_codes}


def role_at_least(role: str, minimum: str) -> bool:
    return ROLE_LEVELS.get(role, 0) >= ROLE_LEVELS[minimum]


# ---- 无需任何凭证（unified 模式下也放行） ----
_PUBLIC = [
    ("*", re.compile(r"^/health$")),
    ("POST", re.compile(r"^/auth/sso_login$")),
    # OpenAPI 文档在接入前就是公开的，对接方联调在用，保持现状
    ("GET", re.compile(r"^/(docs|redoc|openapi\.json)$")),
]

# ---- 第三方只读对接面（对接文档 §5 全集，GET only）：过渡期免鉴权 ----
# 显式逐条列出而不是"所有 GET 都豁免"——运营侧独有的读接口(关联列表、
# 全部答案版本、admin/dimensions 等)仍要求 viewer+。
THIRD_PARTY_EXEMPT = [
    re.compile(r"^/dimensions$"),                                                # §5.1
    re.compile(r"^/knowledge-bases$"),                                           # §5.7（v1.1 增补：库列表，2026-08-18 反馈单问题 3）
    re.compile(r"^/knowledge-bases/\d+/enabled-dimensions$"),                    # §5.1
    re.compile(r"^/knowledge-bases/\d+/knowledge-points$"),                      # §5.3
    re.compile(r"^/knowledge-bases/\d+/knowledge-points/\d+/(resolve|answer-groups|change-log)$"),  # §5.2/5.4/5.5
    re.compile(r"^/change-log$"),                                                # §5.5
    re.compile(r"^/knowledge-bases/\d+/stats$"),                                 # §5.6
]

# ---- 服务间机器凭证（X-Service-Token）可访问面：按来源系统自管 ----
# 平台《服务Token接口对接文档》（2026-08-18）§4.2-5/6：平台不维护系统间
# 授权关系，来源系统能访问哪些接口由目标系统自行决定。当前唯一登记的
# 来源系统 bqxt（打标系统）= 基准版 §5 只读面全集，与免鉴权豁免清单同源，
# 将来对接面切服务 Token 时只需摘掉 THIRD_PARTY_EXEMPT 的免鉴权语义。
SERVICE_SOURCE_SURFACES: dict[str, list[re.Pattern[str]]] = {
    "bqxt": THIRD_PARTY_EXEMPT,
}


def service_source_allowed(source_system: str, method: str, path: str) -> bool:
    """携带有效服务 Token 的来源系统能否访问该接口；未登记的来源一律拒绝。"""
    patterns = SERVICE_SOURCE_SURFACES.get((source_system or "").strip())
    if patterns is None:
        return False
    return method.upper() in ("GET", "HEAD") and any(p.match(path) for p in patterns)


# ---- 已登录即可（role=none 也放行）：查自己 / 退出 ----
_AUTHENTICATED_ONLY = [
    ("GET", re.compile(r"^/auth/me$")),
    ("POST", re.compile(r"^/auth/logout$")),
]

# ---- 需要 admin+ 的写操作：维度配置、建/改/停知识库 ----
_ADMIN_WRITE = [
    re.compile(r"^/dimensions(/.*)?$"),                       # POST/PATCH/activate/deactivate
    re.compile(r"^/knowledge-bases$"),                        # POST 建库
    re.compile(r"^/knowledge-bases/\d+$"),                    # PATCH 改名/描述
    re.compile(r"^/knowledge-bases/\d+/(activate|deactivate|enabled-dimensions)$"),
]

_USERS = re.compile(r"^/users(/.*)?$")


def required_role(method: str, path: str, *, third_party_exempt: bool = True) -> str | None:
    """返回该请求要求的最低角色；None = 公开（无需凭证）。

    third_party_exempt=False 时关闭 §5 只读面的过渡期免鉴权（切服务 Token
    强制后的形态）：这些路径回落到 GET 兜底的 viewer——用户登录态仍可访问，
    机器调用则须走 auth_gate 的 X-Service-Token 分支（不经过本函数）。"""
    method = method.upper()
    for m, pattern in _PUBLIC:
        if (m == "*" or m == method) and pattern.match(path):
            return None
    if (
        third_party_exempt
        and method in ("GET", "HEAD")
        and any(p.match(path) for p in THIRD_PARTY_EXEMPT)
    ):
        return None
    for m, pattern in _AUTHENTICATED_ONLY:
        if m == method and pattern.match(path):
            return "none"
    if _USERS.match(path):
        return "sysadmin"
    if method in ("GET", "HEAD"):
        return "viewer"
    if any(p.match(path) for p in _ADMIN_WRITE):
        return "admin"
    return "editor"
