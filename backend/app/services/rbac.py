"""Single source of truth for permissions and system roles.

``sync_rbac`` is idempotent: it runs on app startup, in the seed script and in
tests, so the database catalog always matches this file. Adding a role or a
permission later is a code change here, nothing else.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Permission, Role
from app.models.enums import RoleCode


class P:
    """Permission codes."""

    INVENTORY_READ = "inventory.read"
    INVENTORY_CREATE = "inventory.create"
    INVENTORY_UPDATE = "inventory.update"
    INVENTORY_DELETE = "inventory.delete"
    WAREHOUSE_READ = "warehouse.read"
    WAREHOUSE_MANAGE = "warehouse.manage"
    REGION_READ = "region.read"
    REGION_MANAGE = "region.manage"
    COMMODITY_READ = "commodity.read"
    COMMODITY_MANAGE = "commodity.manage"
    PROCUREMENT_READ = "procurement.read"
    PROCUREMENT_CREATE = "procurement.create"
    LOGISTICS_READ = "logistics.read"
    ANALYTICS_READ = "analytics.read"
    USERS_READ = "users.read"
    USERS_MANAGE = "users.manage"
    SETTINGS_MANAGE = "settings.manage"
    AUDIT_READ = "audit.read"


PERMISSIONS: dict[str, str] = {
    P.INVENTORY_READ: "View inventory records",
    P.INVENTORY_CREATE: "Create inventory records",
    P.INVENTORY_UPDATE: "Update inventory quantities",
    P.INVENTORY_DELETE: "Remove inventory records",
    P.WAREHOUSE_READ: "View warehouses",
    P.WAREHOUSE_MANAGE: "Create, edit and remove warehouses",
    P.REGION_READ: "View regions",
    P.REGION_MANAGE: "Create, edit and remove regions",
    P.COMMODITY_READ: "View commodities",
    P.COMMODITY_MANAGE: "Create, edit and remove commodities",
    P.PROCUREMENT_READ: "View procurement information",
    P.PROCUREMENT_CREATE: "Create procurement records (used from a later version)",
    P.LOGISTICS_READ: "View logistics information",
    P.ANALYTICS_READ: "View analytics and historical data",
    P.USERS_READ: "View users in the organization",
    P.USERS_MANAGE: "Create users and change roles and location scope",
    P.SETTINGS_MANAGE: "Change organization settings",
    P.AUDIT_READ: "View the audit log",
}

_READ_MASTER = [P.REGION_READ, P.COMMODITY_READ, P.WAREHOUSE_READ, P.INVENTORY_READ]

ROLES: dict[RoleCode, dict] = {
    RoleCode.ORGANIZATION_ADMIN: {
        "name": "Organization Admin",
        "description": "Manages the workspace, users, roles and master data.",
        "permissions": list(PERMISSIONS),
    },
    RoleCode.OPERATIONS_MANAGER: {
        "name": "Operations Manager",
        "description": "Broad operational view across inventory, warehouses and regions.",
        "permissions": _READ_MASTER
        + [
            P.INVENTORY_CREATE,
            P.INVENTORY_UPDATE,
            P.INVENTORY_DELETE,
            P.PROCUREMENT_READ,
            P.LOGISTICS_READ,
            P.ANALYTICS_READ,
        ],
    },
    RoleCode.PROCUREMENT_MANAGER: {
        "name": "Procurement Manager",
        "description": "Tracks available stock and commodities for purchasing.",
        "permissions": _READ_MASTER + [P.PROCUREMENT_READ, P.PROCUREMENT_CREATE],
    },
    RoleCode.WAREHOUSE_MANAGER: {
        "name": "Warehouse Manager",
        "description": "Runs physical inventory for assigned warehouses.",
        "permissions": _READ_MASTER + [P.INVENTORY_CREATE, P.INVENTORY_UPDATE, P.INVENTORY_DELETE],
    },
    RoleCode.LOGISTICS_MANAGER: {
        "name": "Logistics Manager",
        "description": "Sees where stock sits across warehouses and regions.",
        "permissions": _READ_MASTER + [P.LOGISTICS_READ],
    },
    RoleCode.ANALYST: {
        "name": "Analyst",
        "description": "Explores inventory data and history.",
        "permissions": _READ_MASTER + [P.ANALYTICS_READ],
    },
    RoleCode.VIEWER: {
        "name": "Viewer",
        "description": "Read-only access to approved dashboards and data.",
        "permissions": list(_READ_MASTER),
    },
}

# Roles whose location scope is always the whole organization.
ORG_WIDE_ROLES = {RoleCode.ORGANIZATION_ADMIN.value}

# When a user holds several roles, the dashboard follows the first match here.
DASHBOARD_PRIORITY = [
    RoleCode.ORGANIZATION_ADMIN,
    RoleCode.OPERATIONS_MANAGER,
    RoleCode.PROCUREMENT_MANAGER,
    RoleCode.WAREHOUSE_MANAGER,
    RoleCode.LOGISTICS_MANAGER,
    RoleCode.ANALYST,
    RoleCode.VIEWER,
]


def sync_rbac(db: Session) -> None:
    perms = {p.code: p for p in db.scalars(select(Permission))}
    for code, desc in PERMISSIONS.items():
        if code in perms:
            perms[code].description = desc
        else:
            perms[code] = Permission(code=code, description=desc)
            db.add(perms[code])
    db.flush()

    roles = {r.code: r for r in db.scalars(select(Role).where(Role.organization_id.is_(None)))}
    for code, spec in ROLES.items():
        role = roles.get(code.value)
        if role is None:
            role = Role(code=code.value, organization_id=None, is_system=True, name=spec["name"])
            db.add(role)
        role.name = spec["name"]
        role.description = spec["description"]
        role.permissions = [perms[c] for c in spec["permissions"]]
    db.commit()


def get_system_role(db: Session, code: RoleCode | str) -> Role | None:
    code = code.value if isinstance(code, RoleCode) else code
    return db.scalar(select(Role).where(Role.organization_id.is_(None), Role.code == code))
