from tests.conftest import PASSWORD, login, register


def test_register_creates_org_and_admin(client):
    r = client.post("/api/auth/register", json={"organization_name": "Acme Foods", "full_name": "Asha",
                                                 "email": "Asha@Acme.demo", "password": PASSWORD})
    assert r.status_code == 201
    me = r.json()["me"]
    assert me["organization"]["name"] == "Acme Foods"
    assert me["user"]["email"] == "asha@acme.demo"
    assert me["roles"] == ["ORGANIZATION_ADMIN"]
    assert me["primary_role"] == "ORGANIZATION_ADMIN"
    assert me["scope"]["org_wide"] is True
    assert "users.manage" in me["permissions"]
    assert "agriflow_session" in r.cookies  # httpOnly session cookie is set


def test_register_rejects_duplicate_email_and_weak_password(client):
    register(client)
    dup = client.post("/api/auth/register", json={"organization_name": "X", "full_name": "Y",
                                                   "email": "admin@acme.demo", "password": PASSWORD})
    assert dup.status_code == 409
    weak = client.post("/api/auth/register", json={"organization_name": "X", "full_name": "Y",
                                                    "email": "new@acme.demo", "password": "short"})
    assert weak.status_code == 422


def test_login_works(client):
    register(client)
    api = login(client, "admin@acme.demo")
    assert api.get("/api/auth/me").json()["user"]["email"] == "admin@acme.demo"


def test_invalid_credentials_fail(client):
    register(client)
    wrong = client.post("/api/auth/login", json={"email": "admin@acme.demo", "password": "WrongPass1"})
    unknown = client.post("/api/auth/login", json={"email": "nobody@acme.demo", "password": PASSWORD})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]  # no account enumeration


def test_protected_endpoints_reject_unauthenticated(client):
    for url in ["/api/auth/me", "/api/inventory", "/api/warehouses", "/api/regions", "/api/commodities",
                "/api/users", "/api/dashboard", "/api/organizations/current"]:
        assert client.get(url).status_code == 401, url


def test_garbage_and_tampered_tokens_rejected(client):
    api = register(client)
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"}).status_code == 401
    tampered = api.token[:-4] + ("AAAA" if not api.token.endswith("AAAA") else "BBBB")
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {tampered}"}).status_code == 401


def test_logout_revokes_session(client):
    api = register(client)
    assert api.get("/api/auth/me").status_code == 200
    assert api.post("/api/auth/logout").status_code == 204
    assert api.get("/api/auth/me").status_code == 401


def test_cookie_session_works(client):
    r = client.post("/api/auth/register", json={"organization_name": "Cookie Co", "full_name": "C",
                                                 "email": "c@cookie.demo", "password": PASSWORD})
    assert r.status_code == 201
    assert client.get("/api/auth/me").status_code == 200  # authenticated via cookie only
    assert client.post("/api/auth/logout").status_code == 204
    client.cookies.clear()
    assert client.get("/api/auth/me").status_code == 401


def test_deactivated_user_cannot_login_and_is_signed_out(world, client):
    admin, ravi = world["admin"], world["ravi"]
    uid = ravi.me["user"]["id"]
    assert admin.patch(f"/api/users/{uid}", {"is_active": False}).status_code == 200
    assert ravi.get("/api/auth/me").status_code == 401
    r = client.post("/api/auth/login", json={"email": "ravi@acme.demo", "password": PASSWORD})
    assert r.status_code == 403
