"""统一身份认证的纯逻辑单测（issue #36，手册 §11.1）。

只测不碰网络、不碰数据库的部分：HMAC 签名、请求体字节一致性、平台
包络解析、设备类型归一、角色映射、接口权限规则表。集成路径（换票、
用户同步）依赖真实平台与 DB fixture，挂在联调阶段（issue #38）。
"""
from __future__ import annotations

import hashlib
import hmac as hmac_mod

from kb_backend.auth.deps import _service_cache_ttl
from kb_backend.auth.roles import (
    is_platform_super_admin,
    required_role,
    role_at_least,
    service_source_allowed,
)
from kb_backend.auth.unified_client import (
    UnifiedAuthError,
    compact_json_bytes,
    hmac_signature,
    normalize_app_type,
    unwrap,
)


# ---------------------------------------------------------------- HMAC ----

def test_hmac_signature_fixed_input_fixed_output():
    """固定输入产生固定签名——六段式原文（POST/路径/clientId/时间戳/nonce/
    body摘要）换行连接、末尾无换行、小写十六进制（手册 §3.1/§11.1）。"""
    body = compact_json_bytes({"ticket": "T-123"})
    signature = hmac_signature(
        "secret-1", "/core/sso/exchange", "client-a", "1755000000000", "abcd" * 8, body
    )
    expected_message = (
        "POST\n/core/sso/exchange\nclient-a\n1755000000000\n"
        + "abcd" * 8
        + "\n"
        + hashlib.sha256(body).hexdigest()
    )
    expected = hmac_mod.new(b"secret-1", expected_message.encode(), hashlib.sha256).hexdigest()
    assert signature == expected
    assert signature == signature.lower()


def test_compact_json_bytes_matches_sent_bytes():
    """参与摘要的字节必须与实际发送字节一致：紧凑、无空格、中文不转义。"""
    data = {"ticket": "票据T", "b": 1}
    raw = compact_json_bytes(data)
    assert raw == '{"ticket":"票据T","b":1}'.encode()
    assert b" " not in raw
    assert "票据T".encode() in raw  # ensure_ascii=False：中文原样字节


def test_hmac_signature_changes_with_body():
    sig1 = hmac_signature("s", "/p", "c", "1", "n", b'{"ticket":"a"}')
    sig2 = hmac_signature("s", "/p", "c", "1", "n", b'{"ticket":"b"}')
    assert sig1 != sig2


# ---------------------------------------------------------------- 包络 ----

def test_unwrap_success_returns_data():
    assert unwrap({"code": 200, "msg": "成功", "data": {"x": 1}}) == {"x": 1}
    assert unwrap({"code": "200", "data": {"x": 2}}) == {"x": 2}


def test_unwrap_business_failure_keeps_platform_msg():
    """HTTP 200 + 业务失败：必须保留平台 msg 原文（手册 §3.1/§9）。"""
    try:
        unwrap({"code": 40101, "msg": "Ticket 不存在、已过期或已使用"})
        raise AssertionError("should have raised")
    except UnifiedAuthError as exc:
        assert "Ticket 不存在、已过期或已使用" in str(exc)


def test_unwrap_invalid_shapes():
    for bad in (None, [], "x", 1):
        try:
            unwrap(bad)
            raise AssertionError("should have raised")
        except UnifiedAuthError as exc:
            assert "格式无效" in str(exc)


def test_unwrap_no_code_passthrough_and_non_dict_data():
    # 无包络字段的裸对象原样返回；data 不是对象时回空 dict
    assert unwrap({"userId": 1}) == {"userId": 1}
    assert unwrap({"code": 200, "data": [1, 2]}) == {}


# ------------------------------------------------------------ 设备类型 ----

def test_normalize_app_type_prefers_exchange_value():
    assert normalize_app_type("PORTAL", "ADMIN") == "PORTAL"
    assert normalize_app_type("h5", "ADMIN") == "H5"


def test_normalize_app_type_invalid_falls_back():
    """非法设备类型回落配置兜底，不能原样转发任意值（手册 §11.1）。"""
    assert normalize_app_type("WECHAT", "ADMIN") == "ADMIN"
    assert normalize_app_type(None, "ADMIN") == "ADMIN"
    assert normalize_app_type("", "PORTAL") == "PORTAL"
    # 兜底本身非法时最终回 ADMIN
    assert normalize_app_type("bogus", "bogus") == "ADMIN"


# ------------------------------------------------------------ 角色映射 ----

def test_only_super_admin_auto_promotes():
    assert is_platform_super_admin({"super_admin"})
    assert is_platform_super_admin({"ADMIN", "Super_Admin"})  # 大小写不敏感
    # admin 与其他角色都不是（手册 §2：admin 不得映射为管理员）
    assert not is_platform_super_admin({"admin"})
    assert not is_platform_super_admin({"editor", "ops"})
    assert not is_platform_super_admin(set())


def test_role_hierarchy():
    assert role_at_least("sysadmin", "admin")
    assert role_at_least("editor", "viewer")
    assert not role_at_least("viewer", "editor")
    assert not role_at_least("none", "viewer")
    assert role_at_least("none", "none")
    # 未知角色按最低处理
    assert not role_at_least("bogus", "viewer")


# ------------------------------------------------------ 接口权限规则表 ----

def test_public_surface():
    assert required_role("GET", "/health") is None
    assert required_role("POST", "/auth/sso_login") is None
    assert required_role("GET", "/openapi.json") is None


def test_third_party_readonly_exempt_matches_contract_doc():
    """《对接接口文档-约定基准版》§5 全集逐条豁免（GET only）。"""
    for path in [
        "/dimensions",
        "/knowledge-bases",  # §5.7（v1.1 增补：库列表，2026-08-18 反馈单问题 3）
        "/knowledge-bases/1/enabled-dimensions",
        "/knowledge-bases/1/knowledge-points",
        "/knowledge-bases/1/knowledge-points/2/resolve",
        "/knowledge-bases/1/knowledge-points/2/answer-groups",
        "/knowledge-bases/1/knowledge-points/2/change-log",
        "/change-log",
        "/knowledge-bases/1/stats",
    ]:
        assert required_role("GET", path) is None, path


def test_exemption_is_get_only_and_exact():
    # 同路径的写操作不豁免
    assert required_role("POST", "/dimensions") == "admin"
    assert required_role("PUT", "/knowledge-bases/1/enabled-dimensions") == "admin"
    # 同路径的写操作不豁免（库列表 GET 已豁免，POST 建库仍需 admin）
    assert required_role("POST", "/knowledge-bases") == "admin"
    # 运营侧独有读接口不豁免（需 viewer+）
    assert required_role("GET", "/knowledge-bases/1/knowledge-points/2/answers") == "viewer"
    assert required_role("GET", "/knowledge-bases/1/knowledge-points/2/answer-relations") == "viewer"
    assert required_role("GET", "/admin/dimensions") == "viewer"


def test_authenticated_only_surface():
    """role=none 的用户必须能查自己/退出（手册 §6.2：无授权仍可登录）。"""
    assert required_role("GET", "/auth/me") == "none"
    assert required_role("POST", "/auth/logout") == "none"


def test_write_levels():
    # 业务写 = editor+
    assert required_role("POST", "/knowledge-bases/1/knowledge-points") == "editor"
    assert required_role("POST", "/knowledge-bases/1/knowledge-points/2/answers") == "editor"
    assert required_role("POST", "/knowledge-bases/1/knowledge-points/2/answers/3/revoke") == "editor"
    assert required_role("DELETE", "/answer-relations/5") == "editor"
    # 维度配置/建改停库 = admin+
    assert required_role("POST", "/knowledge-bases") == "admin"
    assert required_role("PATCH", "/knowledge-bases/1") == "admin"
    assert required_role("POST", "/knowledge-bases/1/deactivate") == "admin"
    assert required_role("PATCH", "/dimensions/tenant") == "admin"
    assert required_role("POST", "/dimensions/tenant/activate") == "admin"
    # 用户管理 = sysadmin
    assert required_role("GET", "/users") == "sysadmin"
    assert required_role("PATCH", "/users/3/role") == "sysadmin"


# ---------------------------------------- 服务间机器凭证（X-Service-Token）----

def test_service_source_surface_readonly_set_for_all_registered():
    """所有已登记来源系统都至少有基准版 §5 只读面全集（含 v1.1 §5.7 库列表）。"""
    for source in ("bqxt", "yhfkglxt"):
        for path in [
            "/dimensions",
            "/knowledge-bases",
            "/knowledge-bases/2/enabled-dimensions",
            "/knowledge-bases/2/knowledge-points",
            "/knowledge-bases/2/knowledge-points/5/resolve",
            "/knowledge-bases/2/knowledge-points/5/answer-groups",
            "/change-log",
            "/knowledge-bases/2/stats",
        ]:
            assert service_source_allowed(source, "GET", path), f"{source} {path}"
        # 运营侧独有接口对任何来源系统都不开放
        assert not service_source_allowed(source, "GET", "/admin/dimensions")
        assert not service_source_allowed(source, "GET", "/users")
        assert not service_source_allowed(source, "POST", "/dimensions")
        assert not service_source_allowed(source, "POST", "/categories")
    # 未登记的来源系统一律拒绝
    assert not service_source_allowed("other-sys", "GET", "/dimensions")
    assert not service_source_allowed("", "GET", "/dimensions")


def test_service_source_bqxt_stays_readonly():
    """bqxt（打标系统）登记的是只读面：任何写方法一律拒绝。"""
    assert not service_source_allowed("bqxt", "POST", "/knowledge-bases")
    assert not service_source_allowed("bqxt", "PATCH", "/knowledge-bases/2")
    assert not service_source_allowed("bqxt", "PUT", "/knowledge-bases/2/enabled-dimensions")
    assert not service_source_allowed("bqxt", "POST", "/knowledge-bases/2/knowledge-points")
    assert not service_source_allowed("bqxt", "POST", "/knowledge-bases/2/knowledge-points/5/answers")


def test_service_source_yhfkglxt_management_surface():
    """yhfkglxt 开放知识库/知识点/答案三块管理面（2026-08-21 确认），
    但维度全局配置、分类树、用户管理仍拒绝。"""
    allowed = [
        # 知识库管理
        ("POST", "/knowledge-bases"),
        ("PATCH", "/knowledge-bases/2"),
        ("POST", "/knowledge-bases/2/activate"),
        ("POST", "/knowledge-bases/2/deactivate"),
        ("PUT", "/knowledge-bases/2/enabled-dimensions"),
        ("GET", "/knowledge-bases/2/dimension-values"),
        # 知识点管理
        ("POST", "/knowledge-bases/2/knowledge-points"),
        ("POST", "/knowledge-bases/2/knowledge-points/batch-import"),
        ("GET", "/knowledge-bases/2/knowledge-points/5"),
        ("PATCH", "/knowledge-bases/2/knowledge-points/5"),
        ("POST", "/knowledge-bases/2/knowledge-points/5/delete"),
        ("POST", "/knowledge-bases/2/knowledge-points/5/restore"),
        # 答案管理
        ("GET", "/knowledge-bases/2/knowledge-points/5/answers"),
        ("POST", "/knowledge-bases/2/knowledge-points/5/answers"),
        ("POST", "/knowledge-bases/2/knowledge-points/5/answers/7/edit"),
        ("POST", "/knowledge-bases/2/knowledge-points/5/answers/7/promote-to-default"),
        ("POST", "/knowledge-bases/2/knowledge-points/5/answers/7/revoke"),
    ]
    for method, path in allowed:
        assert service_source_allowed("yhfkglxt", method, path), f"{method} {path}"
    denied = [
        ("DELETE", "/knowledge-bases/2"),                 # 没有物理删除接口
        ("POST", "/dimensions"),                          # 维度全局配置
        ("PATCH", "/dimensions/city"),
        ("POST", "/categories"),                          # 分类树管理
        ("DELETE", "/categories/3"),
        ("GET", "/users"),                                # 用户管理
        ("PATCH", "/users/3/role"),
        ("POST", "/knowledge-bases/2/knowledge-points/5/relations"),  # 答案关联未开放
    ]
    for method, path in denied:
        assert not service_source_allowed("yhfkglxt", method, path), f"{method} {path}"


def test_exemption_switch_off_forces_auth_on_readonly_surface():
    """third_party_exempt=False（约定日期切强制后）：§5 只读面回落 viewer——
    用户登录态仍可读，无凭证机器调用被拒；_PUBLIC 面（/health 等）不受影响。"""
    for path in ["/dimensions", "/knowledge-bases", "/knowledge-bases/2/stats"]:
        assert required_role("GET", path, third_party_exempt=False) == "viewer", path
    assert required_role("GET", "/health", third_party_exempt=False) is None
    # 默认参数保持契约现状：免鉴权
    assert required_role("GET", "/dimensions") is None


def test_service_cache_ttl_capped_by_token_expiry():
    """校验结果缓存不得超过 Token 剩余有效期，常规 TTL 为较短上限（§4.2-3）。"""
    assert _service_cache_ttl(None, 1_000.0, 60) == 60.0        # 平台没回 expiresAt：用常规 TTL
    assert _service_cache_ttl(1_030_000, 1_000.0, 60) == 30.0   # 剩余 30s < 60s：以剩余期为准
    assert _service_cache_ttl(2_000_000, 1_000.0, 60) == 60.0   # 剩余充足：取常规上限
    assert _service_cache_ttl(900_000, 1_000.0, 60) == 0.0      # 已过期：不缓存


def test_service_verify_body_is_compact_fixed_order():
    """校验请求体必须是紧凑 JSON 且字段顺序固定（平台文档 §2.2）。"""
    assert compact_json_bytes({"serviceToken": "abc"}) == b'{"serviceToken":"abc"}'
