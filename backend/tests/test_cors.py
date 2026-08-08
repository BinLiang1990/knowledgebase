from fastapi.testclient import TestClient

_ORIGIN = "http://localhost:5173"


def test_preflight_for_post_succeeds(client: TestClient) -> None:
    """Found during issue #6 design review: CORSMiddleware's own defaults
    (allow_methods=("GET",), allow_headers=()) would fail this exact
    preflight for every create/edit/toggle request the frontend sends,
    even with the middleware "present"."""
    resp = client.options(
        "/knowledge-bases",
        headers={
            "Origin": _ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == _ORIGIN
    assert "POST" in resp.headers["access-control-allow-methods"]


def test_preflight_for_patch_succeeds(client: TestClient) -> None:
    resp = client.options(
        "/knowledge-bases/1",
        headers={
            "Origin": _ORIGIN,
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert resp.status_code == 200
    assert "PATCH" in resp.headers["access-control-allow-methods"]


def test_preflight_for_put_succeeds(client: TestClient) -> None:
    """PUT .../enabled-dimensions (issue #9) worked fine against TestClient
    (no CORS involved there) but was unreachable from any real browser
    until PUT was added to allow_methods — same class of bug as the POST/
    PATCH cases above. Codex outer-gate finding on PR #25."""
    resp = client.options(
        "/knowledge-bases/1/enabled-dimensions",
        headers={
            "Origin": _ORIGIN,
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert resp.status_code == 200
    assert "PUT" in resp.headers["access-control-allow-methods"]


def test_disallowed_origin_is_not_echoed_back(client: TestClient) -> None:
    resp = client.options(
        "/knowledge-bases",
        headers={
            "Origin": "http://evil.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.headers.get("access-control-allow-origin") != "http://evil.example.com"


def test_actual_get_response_includes_cors_header_for_allowed_origin(client: TestClient) -> None:
    resp = client.get("/health", headers={"Origin": _ORIGIN})
    assert resp.headers.get("access-control-allow-origin") == _ORIGIN
