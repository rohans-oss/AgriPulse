// Mirrors backend/app/schemas. Keep in sync when the API changes.

export type RoleCode =
  | "ORGANIZATION_ADMIN"
  | "OPERATIONS_MANAGER"
  | "PROCUREMENT_MANAGER"
  | "WAREHOUSE_MANAGER"
  | "LOGISTICS_MANAGER"
  | "ANALYST"
  | "VIEWER";

export type Unit = "TONNE" | "QUINTAL" | "KG";
export type RecordStatus = "ACTIVE" | "INACTIVE";
export type WarehouseStatus = "ACTIVE" | "INACTIVE" | "MAINTENANCE";
export type StorageType = "NORMAL" | "COLD_STORAGE" | "CONTROLLED";
export type Category = "VEGETABLE" | "FRUIT" | "GRAIN" | "PULSE" | "SPICE" | "OILSEED" | "OTHER";

export interface Ref {
  id: string;
  name: string;
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  is_demo: boolean;
  created_at: string;
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  org_wide_access: boolean;
  roles: RoleCode[];
  region_ids: string[];
  warehouse_ids: string[];
  created_at: string;
  last_login_at: string | null;
}

export interface Me {
  user: User;
  organization: Organization;
  roles: RoleCode[];
  primary_role: RoleCode | null;
  permissions: string[];
  scope: { org_wide: boolean; regions: Ref[]; warehouses: Ref[]; accessible_warehouse_count: number };
}

export interface Role {
  id: string;
  code: RoleCode;
  name: string;
  description: string;
  permissions: string[];
}

export interface Region {
  id: string;
  name: string;
  state: string;
  code: string | null;
  status: RecordStatus;
  warehouse_count: number;
  created_at: string;
  updated_at: string;
}

export interface Commodity {
  id: string;
  name: string;
  category: Category;
  unit: Unit;
  status: RecordStatus;
  created_at: string;
  updated_at: string;
}

export interface Warehouse {
  id: string;
  name: string;
  region: Ref;
  address: string;
  latitude: number | null;
  longitude: number | null;
  capacity_tonnes: number;
  used_tonnes: number;
  utilization_pct: number;
  storage_type: StorageType;
  status: WarehouseStatus;
  created_at: string;
  updated_at: string;
}

export interface InventoryItem {
  id: string;
  warehouse: Ref & { region_id: string };
  commodity: Ref & { unit: Unit; category: Category };
  quantity: number;
  unit: Unit;
  quantity_tonnes: number;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface Movement {
  id: string;
  warehouse: Ref;
  commodity: Ref;
  movement_type: "INITIAL" | "INBOUND" | "OUTBOUND" | "REMOVAL";
  quantity_delta: number;
  quantity_after: number;
  reason: string;
  created_at: string;
}

export interface AuditEntry {
  id: string;
  action: string;
  entity_type: string;
  entity_id: string | null;
  actor_email: string | null;
  details: Record<string, unknown>;
  created_at: string;
}

export interface Kpi {
  key: string;
  label: string;
  value: number | string;
  unit: string | null;
  hint: string | null;
  tone: "neutral" | "good" | "warn" | "bad";
}

export interface Dashboard {
  role: RoleCode | null;
  title: string;
  subtitle: string;
  scope_label: string;
  is_synthetic: boolean;
  generated_at: string;
  kpis: Kpi[];
  organization: {
    organization: Organization;
    active_users: number;
    total_users: number;
    users_by_role: Record<string, number>;
  } | null;
  warehouses: Warehouse[] | null;
  inventory_by_commodity:
    | { commodity_id: string; name: string; category: string; quantity_tonnes: number; warehouse_count: number }[]
    | null;
  inventory_by_region:
    | {
        region_id: string;
        name: string;
        state: string;
        quantity_tonnes: number;
        warehouse_count: number;
        capacity_tonnes: number;
      }[]
    | null;
  inventory_items: InventoryItem[] | null;
  movement_summary: {
    days: number;
    inbound_tonnes: number;
    outbound_tonnes: number;
    inbound_count: number;
    outbound_count: number;
  } | null;
  daily_movements: { day: string; inbound_tonnes: number; outbound_tonnes: number }[] | null;
  recent_movements: Movement[] | null;
}
