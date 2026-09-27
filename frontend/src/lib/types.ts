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
  market_name: string | null;
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
  market: LatestPrice[] | null;
  weather: WeatherNow[] | null;
  data_sources: SourceStatus[] | null;
}

// --------------------------------------------------------------------------- V2 external data

export interface Freshness {
  label: "CURRENT" | "RECENT" | "DAILY" | "HISTORICAL" | "UNAVAILABLE";
  tone: string;
  detail: string;
}

export interface SourceRef {
  key: string;
  name: string;
  origin: "OFFICIAL_API" | "PUBLIC_API" | "USER_UPLOAD";
}

export interface Run {
  id: string;
  source: SourceRef;
  trigger: "MANUAL" | "SCHEDULED" | "UPLOAD";
  status: "RUNNING" | "SUCCESS" | "PARTIAL" | "FAILED";
  started_at: string;
  finished_at: string | null;
  duration_seconds: number | null;
  rows_received: number;
  rows_inserted: number;
  rows_updated: number;
  rows_unchanged: number;
  rows_rejected: number;
  warnings: number;
  error_message: string | null;
  file_name: string | null;
  triggered_by: string | null;
  params: Record<string, unknown>;
}

export interface Issue {
  row_number: number | null;
  field: string | null;
  severity: "ERROR" | "WARNING";
  code: string;
  message: string;
  raw: Record<string, unknown>;
}

export interface RunDetail extends Run {
  issues: Issue[];
}

export interface SourceStatus {
  key: string;
  name: string;
  publisher: string;
  kind: "MARKET_PRICES" | "WEATHER" | "INVENTORY";
  origin: SourceRef["origin"];
  homepage_url: string;
  license: string;
  update_frequency: string;
  description: string;
  configured: boolean;
  config_message: string | null;
  can_run: boolean;
  can_upload: boolean;
  record_count: number;
  latest_observation: string | null;
  freshness: Freshness | null;
  last_run: Run | null;
  last_success_at: string | null;
}

export interface Price {
  id: string;
  state: string;
  district: string;
  market: string;
  commodity: string;
  variety: string;
  grade: string;
  arrival_date: string;
  min_price: number | null;
  max_price: number | null;
  modal_price: number;
  unit: string;
  source: SourceRef;
  fetched_at: string;
}

export interface LatestPrice {
  commodity: string;
  in_catalog: boolean;
  source: SourceRef | null;
  latest_date: string | null;
  markets_reporting: number;
  avg_modal: number | null;
  min_modal: number | null;
  max_modal: number | null;
  previous_date: string | null;
  previous_avg_modal: number | null;
  change_pct: number | null;
  fetched_at: string | null;
  freshness: Freshness;
}

export interface Trend {
  commodity: string;
  source: SourceRef | null;
  series: { label: string; points: { date: string; modal: number; low: number | null; high: number | null; markets: number }[] }[];
  freshness: Freshness;
}

export interface MarketFilters {
  states: string[];
  districts: string[];
  markets: string[];
  commodities: { name: string; rows: number; latest_date: string | null; in_catalog: boolean }[];
  sources: SourceRef[];
}

export interface WeatherNow {
  warehouse: Ref;
  region: Ref;
  latitude: number | null;
  longitude: number | null;
  reading: {
    observed_at: string;
    temperature_c: number | null;
    humidity_pct: number | null;
    precipitation_mm: number | null;
    wind_kmh: number | null;
    weather_code: number | null;
    condition: string | null;
    fetched_at: string;
  } | null;
  freshness: Freshness;
  source: SourceRef | null;
}

export interface WeatherHistory {
  warehouse: Ref;
  days: { date: string; temp_max_c: number | null; temp_min_c: number | null; precipitation_mm: number | null }[];
  source: SourceRef | null;
  freshness: Freshness;
}

export interface ImportResult {
  dry_run: boolean;
  run_id: string | null;
  file_name: string;
  columns_detected: Record<string, string>;
  missing_columns: string[];
  rows_total: number;
  rows_valid: number;
  rows_rejected: number;
  warnings: number;
  inserted: number;
  updated: number;
  unchanged: number;
  issues: Issue[];
  preview: Record<string, unknown>[];
}
