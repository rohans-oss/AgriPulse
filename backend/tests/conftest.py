import os

os.environ.setdefault("BCRYPT_ROUNDS", "4")  # fast hashing in tests only

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import create_app
from app.services.rbac import sync_rbac

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "sqlite://")
PASSWORD = "Str0ngPass!"


def _make_engine():
    if TEST_DATABASE_URL.startswith("sqlite"):
        engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool)

        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _):
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

        return engine
    return create_engine(TEST_DATABASE_URL)


engine = _make_engine()
TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture(autouse=True)
def _schema():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestingSession() as db:
        sync_rbac(db)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def db():
    with TestingSession() as session:
        yield session


@pytest.fixture
def client():
    app = create_app(run_startup_sync=False)

    def override_db():
        with TestingSession() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as c:
        yield c


class Api:
    """Tiny helper around TestClient that carries a bearer token."""

    def __init__(self, client: TestClient, token: str, me: dict):
        self.client, self.token, self.me = client, token, me

    def _h(self):
        return {"Authorization": f"Bearer {self.token}"}

    def get(self, url, **kw):
        return self.client.get(url, headers=self._h(), **kw)

    def post(self, url, json=None):
        return self.client.post(url, json=json, headers=self._h())

    def patch(self, url, json=None):
        return self.client.patch(url, json=json, headers=self._h())

    def delete(self, url):
        return self.client.delete(url, headers=self._h())


def register(client, org="Acme Foods", email="admin@acme.demo", name="Admin User") -> Api:
    r = client.post("/api/auth/register",
                    json={"organization_name": org, "full_name": name, "email": email, "password": PASSWORD})
    assert r.status_code == 201, r.text
    client.cookies.clear()  # tests authenticate with explicit bearer tokens
    return Api(client, r.json()["access_token"], r.json()["me"])


def login(client, email, password=PASSWORD) -> Api:
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    client.cookies.clear()
    return Api(client, r.json()["access_token"], r.json()["me"])


@pytest.fixture
def world(client):
    """Org A with two regions/warehouses and one user per role; Org B with its own data."""
    admin = register(client)
    blr = admin.post("/api/regions", {"name": "Bengaluru", "state": "Karnataka"}).json()
    hyd = admin.post("/api/regions", {"name": "Hyderabad", "state": "Telangana"}).json()
    wh_blr = admin.post("/api/warehouses", {"name": "BLR Central", "region_id": blr["id"], "capacity_tonnes": 500,
                                            "storage_type": "COLD_STORAGE"}).json()
    wh_hyd = admin.post("/api/warehouses", {"name": "HYD Hub", "region_id": hyd["id"], "capacity_tonnes": 300,
                                            "storage_type": "NORMAL"}).json()
    tomato = admin.post("/api/commodities", {"name": "Tomato", "category": "VEGETABLE", "unit": "TONNE"}).json()
    rice = admin.post("/api/commodities", {"name": "Rice", "category": "GRAIN", "unit": "QUINTAL"}).json()
    inv_blr = admin.post("/api/inventory", {"warehouse_id": wh_blr["id"], "commodity_id": tomato["id"],
                                            "quantity": 120}).json()
    inv_hyd = admin.post("/api/inventory", {"warehouse_id": wh_hyd["id"], "commodity_id": tomato["id"],
                                            "quantity": 40}).json()

    def make_user(local, role, **scope):
        body = {"email": f"{local}@acme.demo", "full_name": local.title(), "password": PASSWORD, "role": role, **scope}
        r = admin.post("/api/users", body)
        assert r.status_code == 201, r.text
        return login(client, body["email"])

    users = {
        "ops": make_user("ops", "OPERATIONS_MANAGER", org_wide_access=True),
        "procurement": make_user("procurement", "PROCUREMENT_MANAGER", org_wide_access=True),
        "ravi": make_user("ravi", "WAREHOUSE_MANAGER", warehouse_ids=[wh_blr["id"]]),
        "logistics": make_user("logistics", "LOGISTICS_MANAGER", region_ids=[blr["id"]]),
        "analyst": make_user("analyst", "ANALYST", org_wide_access=True),
        "viewer": make_user("viewer", "VIEWER", org_wide_access=True),
        "unscoped": make_user("unscoped", "WAREHOUSE_MANAGER"),
    }

    other = register(client, org="Other Co", email="admin@other.demo")
    o_region = other.post("/api/regions", {"name": "Chennai"}).json()
    o_wh = other.post("/api/warehouses", {"name": "Chennai Depot", "region_id": o_region["id"],
                                          "capacity_tonnes": 100, "storage_type": "NORMAL"}).json()
    o_com = other.post("/api/commodities", {"name": "Onion", "category": "VEGETABLE"}).json()
    o_inv = other.post("/api/inventory", {"warehouse_id": o_wh["id"], "commodity_id": o_com["id"],
                                          "quantity": 10}).json()

    return {
        "admin": admin, **users, "other": other,
        "regions": {"blr": blr, "hyd": hyd}, "warehouses": {"blr": wh_blr, "hyd": wh_hyd},
        "commodities": {"tomato": tomato, "rice": rice}, "inventory": {"blr": inv_blr, "hyd": inv_hyd},
        "other_data": {"region": o_region, "warehouse": o_wh, "commodity": o_com, "inventory": o_inv},
    }
