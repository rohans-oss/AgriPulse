"""Organization isolation, roles/permissions, location scope, viewer, security."""


def ids(resp):
    return {row["id"] for row in resp.json()}


# --------------------------------------------------------------------------- organization isolation


def test_user_sees_own_org_data(world):
    admin = world["admin"]
    assert {r["name"] for r in admin.get("/api/regions").json()} == {"Bengaluru", "Hyderabad"}
    assert {w["name"] for w in admin.get("/api/warehouses").json()} == {"BLR Central", "HYD Hub"}
    assert len(admin.get("/api/inventory").json()) == 2


def test_user_cannot_access_other_org_data(world):
    admin, od = world["admin"], world["other_data"]
    assert "Chennai Depot" not in {w["name"] for w in admin.get("/api/warehouses").json()}
    assert admin.get(f"/api/warehouses/{od['warehouse']['id']}").status_code == 404
    assert admin.get(f"/api/regions/{od['region']['id']}").status_code == 404
    assert admin.get(f"/api/commodities/{od['commodity']['id']}").status_code == 404
    assert admin.get(f"/api/inventory/{od['inventory']['id']}").status_code == 404
    assert admin.patch(f"/api/inventory/{od['inventory']['id']}", {"quantity": 0}).status_code == 404
    assert admin.delete(f"/api/warehouses/{od['warehouse']['id']}").status_code == 404
    assert admin.get(f"/api/users/{world['other'].me['user']['id']}").status_code == 404


def test_cannot_reference_other_org_rows_on_create(world):
    admin, od = world["admin"], world["other_data"]
    r = admin.post("/api/inventory", {"warehouse_id": world["warehouses"]["blr"]["id"],
                                      "commodity_id": od["commodity"]["id"], "quantity": 1})
    assert r.status_code == 422
    r = admin.post("/api/warehouses", {"name": "Sneaky", "region_id": od["region"]["id"],
                                       "capacity_tonnes": 10, "storage_type": "NORMAL"})
    assert r.status_code == 422
    r = admin.post("/api/users", {"email": "x@acme.demo", "full_name": "X", "password": "Str0ngPass!",
                                  "role": "VIEWER", "warehouse_ids": [od["warehouse"]["id"]]})
    assert r.status_code == 422


def test_dashboard_totals_exclude_other_org(world):
    kpis = {k["key"]: k["value"] for k in world["admin"].get("/api/dashboard").json()["kpis"]}
    assert kpis["inventory"] == 160.0 and kpis["warehouses"] == 2


# --------------------------------------------------------------------------- roles & permissions


def test_roles_assigned_correctly(world):
    expected = {"admin": "ORGANIZATION_ADMIN", "ops": "OPERATIONS_MANAGER", "procurement": "PROCUREMENT_MANAGER",
                "ravi": "WAREHOUSE_MANAGER", "logistics": "LOGISTICS_MANAGER", "analyst": "ANALYST",
                "viewer": "VIEWER"}
    for key, role in expected.items():
        me = world[key].get("/api/auth/me").json()
        assert me["roles"] == [role], key


def test_role_permissions_enforced(world):
    # Only admins manage master data and users.
    for key in ["ops", "procurement", "ravi", "logistics", "analyst", "viewer"]:
        api = world[key]
        assert api.post("/api/regions", {"name": f"R-{key}"}).status_code == 403, key
        assert api.post("/api/commodities", {"name": f"C-{key}", "category": "OTHER"}).status_code == 403, key
        assert api.get("/api/users").status_code == 403, key
        assert api.post("/api/users", {"email": f"n-{key}@acme.demo", "full_name": "N", "password": "Str0ngPass!",
                                       "role": "ORGANIZATION_ADMIN"}).status_code == 403, key
        assert api.patch("/api/organizations/current", {"name": "Hacked"}).status_code == 403, key
        assert api.get("/api/audit-logs").status_code == 403, key
    assert world["admin"].get("/api/users").status_code == 200
    assert world["admin"].get("/api/audit-logs").status_code == 200


def test_each_role_gets_its_own_dashboard(world):
    titles = {k: world[k].get("/api/dashboard").json()
              for k in ["admin", "ops", "procurement", "ravi", "logistics", "analyst", "viewer"]}
    assert len({d["title"] for d in titles.values()}) == 7
    assert titles["admin"]["organization"]["total_users"] == 8
    assert titles["ravi"]["recent_movements"] is not None and titles["ravi"]["organization"] is None
    assert titles["analyst"]["daily_movements"] is not None
    assert titles["viewer"]["organization"] is None and titles["viewer"]["inventory_items"] is None


def test_admin_cannot_demote_self_or_remove_last_admin(world):
    admin = world["admin"]
    me_id = admin.me["user"]["id"]
    assert admin.patch(f"/api/users/{me_id}", {"role": "VIEWER"}).status_code == 409
    assert admin.patch(f"/api/users/{me_id}", {"is_active": False}).status_code == 409


def test_role_change_takes_effect_immediately(world):
    admin, viewer = world["admin"], world["viewer"]
    inv = world["inventory"]["hyd"]["id"]
    assert viewer.patch(f"/api/inventory/{inv}", {"quantity": 41}).status_code == 403
    admin.patch(f"/api/users/{viewer.me['user']['id']}", {"role": "OPERATIONS_MANAGER"})
    assert viewer.patch(f"/api/inventory/{inv}", {"quantity": 41}).status_code == 200


# --------------------------------------------------------------------------- inventory


def test_authorized_user_can_read_inventory(world):
    for key in ["ops", "procurement", "analyst", "viewer"]:
        assert len(world[key].get("/api/inventory").json()) == 2, key


def test_authorized_user_can_create_and_update_inventory(world):
    ops = world["ops"]
    rice = world["commodities"]["rice"]["id"]
    wh = world["warehouses"]["blr"]["id"]
    r = ops.post("/api/inventory", {"warehouse_id": wh, "commodity_id": rice, "quantity": 500})
    assert r.status_code == 201
    body = r.json()
    assert body["unit"] == "QUINTAL" and body["quantity_tonnes"] == 50.0
    r = ops.patch(f"/api/inventory/{body['id']}", {"quantity": 450, "reason": "Dispatch"})
    assert r.status_code == 200 and r.json()["quantity"] == 450
    moves = ops.get("/api/inventory/movements", params={"warehouse_id": wh}).json()
    assert [m["movement_type"] for m in moves[:2]] == ["OUTBOUND", "INITIAL"]
    assert moves[0]["quantity_delta"] == -50


def test_unauthorized_user_cannot_modify_inventory(world):
    inv = world["inventory"]["blr"]["id"]
    wh, tomato = world["warehouses"]["blr"]["id"], world["commodities"]["rice"]["id"]
    for key in ["procurement", "logistics", "analyst", "viewer"]:
        api = world[key]
        assert api.patch(f"/api/inventory/{inv}", {"quantity": 1}).status_code == 403, key
        assert api.delete(f"/api/inventory/{inv}").status_code == 403, key
        assert api.post("/api/inventory", {"warehouse_id": wh, "commodity_id": tomato, "quantity": 1}).status_code == 403
    assert world["admin"].get(f"/api/inventory/{inv}").json()["quantity"] == 120


def test_inventory_filters(world):
    admin = world["admin"]
    blr = world["warehouses"]["blr"]["id"]
    assert {i["warehouse"]["id"] for i in admin.get("/api/inventory", params={"warehouse_id": blr}).json()} == {blr}
    tomato = world["commodities"]["tomato"]["id"]
    assert len(admin.get("/api/inventory", params={"commodity_id": tomato}).json()) == 2
    rice = world["commodities"]["rice"]["id"]
    assert admin.get("/api/inventory", params={"commodity_id": rice}).json() == []


def test_inventory_validation(world):
    admin = world["admin"]
    wh, tomato = world["warehouses"]["blr"]["id"], world["commodities"]["tomato"]["id"]
    inv = world["inventory"]["blr"]["id"]
    assert admin.post("/api/inventory", {"warehouse_id": wh, "commodity_id": tomato, "quantity": 5}).status_code == 409
    assert admin.patch(f"/api/inventory/{inv}", {"quantity": -1}).status_code == 422
    assert admin.patch(f"/api/inventory/{inv}", {"quantity": 10_000}).status_code == 409  # over capacity
    assert admin.post("/api/inventory", {"warehouse_id": "not-a-uuid"}).status_code == 422


def test_inventory_delete(world):
    admin = world["admin"]
    inv = world["inventory"]["hyd"]["id"]
    assert admin.delete(f"/api/inventory/{inv}").status_code == 204
    assert admin.get(f"/api/inventory/{inv}").status_code == 404
    assert admin.get("/api/inventory/movements").json()[0]["movement_type"] == "REMOVAL"


# --------------------------------------------------------------------------- location scope


def test_warehouse_manager_can_access_assigned_warehouse(world):
    ravi = world["ravi"]
    blr = world["warehouses"]["blr"]["id"]
    assert ids(ravi.get("/api/warehouses")) == {blr}
    assert ravi.get(f"/api/warehouses/{blr}").status_code == 200
    items = ravi.get("/api/inventory").json()
    assert [i["warehouse"]["id"] for i in items] == [blr]
    assert ravi.patch(f"/api/inventory/{world['inventory']['blr']['id']}", {"quantity": 110}).status_code == 200


def test_warehouse_manager_cannot_access_unauthorized_warehouse(world):
    ravi = world["ravi"]
    hyd = world["warehouses"]["hyd"]["id"]
    hyd_inv = world["inventory"]["hyd"]["id"]
    assert ravi.get(f"/api/warehouses/{hyd}").status_code == 403
    assert ravi.get(f"/api/inventory/{hyd_inv}").status_code == 403
    assert ravi.get("/api/inventory", params={"warehouse_id": hyd}).status_code == 403
    assert ravi.patch(f"/api/inventory/{hyd_inv}", {"quantity": 1}).status_code == 403
    assert ravi.delete(f"/api/inventory/{hyd_inv}").status_code == 403
    rice = world["commodities"]["rice"]["id"]
    assert ravi.post("/api/inventory", {"warehouse_id": hyd, "commodity_id": rice, "quantity": 1}).status_code == 403
    dash = ravi.get("/api/dashboard").json()
    assert {w["name"] for w in dash["warehouses"]} == {"BLR Central"}
    assert all(m["warehouse"]["name"] == "BLR Central" for m in dash["recent_movements"])


def test_region_scope_grants_region_warehouses(world):
    logistics = world["logistics"]
    assert ids(logistics.get("/api/warehouses")) == {world["warehouses"]["blr"]["id"]}
    # A new warehouse in the scoped region becomes visible automatically.
    new = world["admin"].post("/api/warehouses", {"name": "BLR North", "region_id": world["regions"]["blr"]["id"],
                                                  "capacity_tonnes": 50, "storage_type": "NORMAL"}).json()
    assert new["id"] in ids(logistics.get("/api/warehouses"))


def test_user_without_scope_sees_nothing(world):
    unscoped = world["unscoped"]
    assert unscoped.get("/api/warehouses").json() == []
    assert unscoped.get("/api/inventory").json() == []
    assert unscoped.get(f"/api/warehouses/{world['warehouses']['blr']['id']}").status_code == 403


def test_scope_change_by_admin(world):
    admin, ravi = world["admin"], world["ravi"]
    hyd = world["warehouses"]["hyd"]["id"]
    admin.patch(f"/api/users/{ravi.me['user']['id']}", {"warehouse_ids": [hyd]})
    assert ids(ravi.get("/api/warehouses")) == {hyd}


# --------------------------------------------------------------------------- viewer


def test_viewer_can_read(world):
    viewer = world["viewer"]
    for url in ["/api/regions", "/api/commodities", "/api/warehouses", "/api/inventory", "/api/dashboard"]:
        assert viewer.get(url).status_code == 200, url


def test_viewer_cannot_modify(world):
    viewer = world["viewer"]
    wh = world["warehouses"]["blr"]
    assert viewer.patch(f"/api/warehouses/{wh['id']}", {"capacity_tonnes": 1}).status_code == 403
    assert viewer.delete(f"/api/warehouses/{wh['id']}").status_code == 403
    assert viewer.patch(f"/api/regions/{world['regions']['blr']['id']}", {"name": "X"}).status_code == 403
    assert viewer.patch(f"/api/users/{viewer.me['user']['id']}", {"role": "ORGANIZATION_ADMIN"}).status_code == 403
    assert "inventory.update" not in viewer.me["permissions"]


# --------------------------------------------------------------------------- security & audit


def test_password_hash_never_returned(world):
    admin = world["admin"]
    for url in ["/api/auth/me", "/api/users", f"/api/users/{world['ravi'].me['user']['id']}", "/api/dashboard"]:
        text = admin.get(url).text
        assert "password" not in text and "$2b$" not in text, url


def test_audit_log_records_key_actions(world):
    actions = {a["action"] for a in world["admin"].get("/api/audit-logs", params={"limit": 500}).json()}
    for expected in ["organization.create", "user.register", "auth.login", "user.create", "region.create",
                     "warehouse.create", "commodity.create", "inventory.create"]:
        assert expected in actions, expected
    # Org B's actions never appear in Org A's log.
    other_ids = {a["entity_id"] for a in world["admin"].get("/api/audit-logs", params={"limit": 500}).json()}
    assert world["other_data"]["warehouse"]["id"] not in other_ids


def test_master_data_crud_and_conflicts(world):
    admin = world["admin"]
    assert admin.post("/api/regions", {"name": "Bengaluru"}).status_code == 409
    assert admin.delete(f"/api/regions/{world['regions']['blr']['id']}").status_code == 409  # has warehouses
    assert admin.delete(f"/api/commodities/{world['commodities']['tomato']['id']}").status_code == 409
    assert admin.patch(f"/api/commodities/{world['commodities']['tomato']['id']}", {"unit": "KG"}).status_code == 409
    assert admin.delete(f"/api/commodities/{world['commodities']['rice']['id']}").status_code == 204
    wh = world["warehouses"]["blr"]["id"]
    assert admin.patch(f"/api/warehouses/{wh}", {"capacity_tonnes": 10}).status_code == 409  # below stock
    assert admin.patch(f"/api/warehouses/{wh}", {"status": "MAINTENANCE"}).json()["status"] == "MAINTENANCE"
    r = admin.post("/api/regions", {"name": "Mandya", "state": "Karnataka", "code": "MDY"})
    assert r.status_code == 201
    assert admin.delete(f"/api/regions/{r.json()['id']}").status_code == 204


def test_movement_summary_counts_only_real_flows(world):
    ops = world["ops"]
    inv = world["inventory"]["blr"]["id"]  # created with 120 t opening stock (INITIAL)
    before = ops.get("/api/dashboard").json()["movement_summary"]
    assert before["inbound_tonnes"] == 0 and before["outbound_tonnes"] == 0  # opening balances are not flow
    ops.patch(f"/api/inventory/{inv}", {"quantity": 130})
    ops.patch(f"/api/inventory/{inv}", {"quantity": 125})
    after = ops.get("/api/dashboard").json()["movement_summary"]
    assert after["inbound_tonnes"] == 10 and after["outbound_tonnes"] == 5
    assert after["inbound_count"] == 1 and after["outbound_count"] == 1
