"""Seed a clearly-labelled SYNTHETIC demo workspace.

    python -m app.seed            # create demo org if it does not exist
    python -m app.seed --reset    # drop and recreate the demo org

All values are invented for testing the application. They do not describe
real Indian agricultural operations.
"""

import argparse
import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import (
    AuditLog,
    AuthSession,
    Commodity,
    InventoryItem,
    InventoryMovement,
    Organization,
    Region,
    User,
    UserLocationScope,
    UserRole,
    Warehouse,
)
from app.models.enums import CommodityCategory, MovementType, QuantityUnit, RecordStatus, RoleCode, StorageType
from app.services.data.sources import sync_sources
from app.services.rbac import get_system_role, sync_rbac

DEMO_SLUG = "agriflow-demo-foods"
DEMO_PASSWORD = "Demo@1234"

REGIONS = [
    ("Kolar", "Karnataka", "KLR"),
    ("Bengaluru", "Karnataka", "BLR"),
    ("Mysuru", "Karnataka", "MYS"),
    ("Chikkaballapur", "Karnataka", "CBP"),
    ("Mandya", "Karnataka", "MDY"),
]

COMMODITIES = [
    ("Tomato", CommodityCategory.VEGETABLE, QuantityUnit.TONNE, RecordStatus.ACTIVE),
    ("Onion", CommodityCategory.VEGETABLE, QuantityUnit.TONNE, RecordStatus.ACTIVE),
    ("Potato", CommodityCategory.VEGETABLE, QuantityUnit.TONNE, RecordStatus.ACTIVE),
    ("Rice", CommodityCategory.GRAIN, QuantityUnit.QUINTAL, RecordStatus.ACTIVE),
    ("Wheat", CommodityCategory.GRAIN, QuantityUnit.QUINTAL, RecordStatus.INACTIVE),
]

# name, region, address, lat, lng, capacity (t), storage type
WAREHOUSES = [
    ("Bengaluru Central Warehouse", "Bengaluru", "Synthetic address — Yeshwanthpur industrial area", 13.028, 77.540,
     600, StorageType.COLD_STORAGE),
    ("Kolar Collection Warehouse", "Kolar", "Synthetic address — near Kolar APMC yard", 13.137, 78.129,
     350, StorageType.NORMAL),
    ("Mysuru Distribution Warehouse", "Mysuru", "Synthetic address — Hebbal industrial area, Mysuru", 12.345, 76.617,
     450, StorageType.CONTROLLED),
]

# warehouse -> {commodity: final quantity in the commodity's unit}
STOCK = {
    "Bengaluru Central Warehouse": {"Tomato": 120, "Onion": 80, "Potato": 65, "Rice": 1500},
    "Kolar Collection Warehouse": {"Tomato": 142.5, "Onion": 38, "Potato": 22},
    "Mysuru Distribution Warehouse": {"Onion": 96, "Potato": 110, "Rice": 2200},
}

# email local-part, full name, role, org_wide, scoped warehouses, scoped regions
USERS = [
    ("admin", "Asha Rao", RoleCode.ORGANIZATION_ADMIN, True, [], []),
    ("ops", "Vikram Shetty", RoleCode.OPERATIONS_MANAGER, True, [], []),
    ("procurement", "Meera Iyer", RoleCode.PROCUREMENT_MANAGER, True, [], []),
    ("ravi", "Ravi Kumar", RoleCode.WAREHOUSE_MANAGER, False, ["Bengaluru Central Warehouse"], []),
    ("logistics", "Farhan Ali", RoleCode.LOGISTICS_MANAGER, True, [], []),
    ("analyst", "Divya Nair", RoleCode.ANALYST, True, [], []),
    ("viewer", "Karthik Gowda", RoleCode.VIEWER, False, [], ["Mysuru"]),
]


def _reset(db) -> None:
    org = db.scalar(select(Organization).where(Organization.slug == DEMO_SLUG))
    if not org:
        return
    user_ids = list(db.scalars(select(User.id).where(User.organization_id == org.id)))
    db.execute(delete(AuditLog).where(AuditLog.organization_id == org.id))
    db.execute(delete(InventoryMovement).where(InventoryMovement.organization_id == org.id))
    db.execute(delete(InventoryItem).where(InventoryItem.organization_id == org.id))
    if user_ids:
        db.execute(delete(AuthSession).where(AuthSession.user_id.in_(user_ids)))
        db.execute(delete(UserLocationScope).where(UserLocationScope.user_id.in_(user_ids)))
        db.execute(delete(UserRole).where(UserRole.user_id.in_(user_ids)))
        db.execute(delete(User).where(User.id.in_(user_ids)))
    db.execute(delete(Warehouse).where(Warehouse.organization_id == org.id))
    db.execute(delete(Commodity).where(Commodity.organization_id == org.id))
    db.execute(delete(Region).where(Region.organization_id == org.id))
    db.execute(delete(Organization).where(Organization.id == org.id))
    db.commit()


def seed(reset: bool = False) -> None:
    rng = random.Random(42)
    with SessionLocal() as db:
        sync_rbac(db)
        sync_sources(db)
        if reset:
            _reset(db)
        if db.scalar(select(Organization).where(Organization.slug == DEMO_SLUG)):
            print("Demo organization already exists (use --reset to recreate).")
            return

        org = Organization(name="AgriFlow Demo Foods", slug=DEMO_SLUG, is_demo=True)
        db.add(org)
        db.flush()

        regions = {n: Region(organization_id=org.id, name=n, state=s, code=c) for n, s, c in REGIONS}
        db.add_all(regions.values())
        commodities = {n: Commodity(organization_id=org.id, name=n, category=cat, unit=u, status=st)
                       for n, cat, u, st in COMMODITIES}
        db.add_all(commodities.values())
        db.flush()

        warehouses = {}
        for name, region, addr, lat, lng, cap, stype in WAREHOUSES:
            warehouses[name] = Warehouse(organization_id=org.id, region_id=regions[region].id, name=name,
                                         address=addr, latitude=lat, longitude=lng,
                                         capacity_tonnes=Decimal(cap), storage_type=stype)
        db.add_all(warehouses.values())
        db.flush()

        users = {}
        for local, full_name, role_code, org_wide, wh_names, region_names in USERS:
            u = User(organization_id=org.id, email=f"{local}@agriflow.demo", full_name=full_name,
                     password_hash=hash_password(DEMO_PASSWORD), org_wide_access=org_wide)
            u.role_assignments = [UserRole(role=get_system_role(db, role_code))]
            u.location_scopes = ([UserLocationScope(warehouse_id=warehouses[w].id) for w in wh_names]
                                 + [UserLocationScope(region_id=regions[r].id) for r in region_names])
            db.add(u)
            users[local] = u
        db.flush()

        # Synthetic 14-day movement history that ends exactly at the STOCK figures.
        now = datetime.now(UTC)
        actors = [users["ravi"].id, users["ops"].id]
        for wname, stock in STOCK.items():
            wh = warehouses[wname]
            for cname, final in stock.items():
                com = commodities[cname]
                final = Decimal(str(final))
                deltas = [Decimal(str(round(rng.uniform(-0.12, 0.15) * float(final), 1))) for _ in range(rng.randint(4, 7))]
                opening = final - sum(deltas)
                if opening <= 0:
                    opening, deltas = final, []
                item = InventoryItem(organization_id=org.id, warehouse_id=wh.id, commodity_id=com.id,
                                     quantity=final, notes="Synthetic demo stock")
                db.add(item)
                db.flush()
                t = now - timedelta(days=14)
                qty = opening
                db.add(InventoryMovement(organization_id=org.id, inventory_item_id=item.id, warehouse_id=wh.id,
                                         commodity_id=com.id, movement_type=MovementType.INITIAL,
                                         quantity_delta=opening, quantity_after=opening,
                                         reason="Synthetic opening stock", created_by_id=actors[1], created_at=t))
                offsets = sorted(rng.uniform(0.5, 13.8) for _ in deltas)
                for off, delta in zip(offsets, deltas, strict=True):
                    qty += delta
                    db.add(InventoryMovement(
                        organization_id=org.id, inventory_item_id=item.id, warehouse_id=wh.id, commodity_id=com.id,
                        movement_type=MovementType.INBOUND if delta > 0 else MovementType.OUTBOUND,
                        quantity_delta=delta, quantity_after=qty,
                        reason="Synthetic receipt" if delta > 0 else "Synthetic dispatch",
                        created_by_id=rng.choice(actors), created_at=now - timedelta(days=14) + timedelta(days=off)))

        db.commit()
        print("Seeded SYNTHETIC demo organization 'AgriFlow Demo Foods'.")
        print(f"Demo password for every account: {DEMO_PASSWORD}")
        for local, full_name, role_code, *_ in USERS:
            print(f"  {role_code.value:<22} {local}@agriflow.demo  ({full_name})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="drop and recreate the demo organization")
    seed(reset=parser.parse_args().reset)
