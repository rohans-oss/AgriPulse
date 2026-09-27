"use client";

import {
  Activity,
  AlertTriangle,
  ArrowDownToLine,
  ArrowRight,
  ArrowUpFromLine,
  Boxes,
  Building2,
  CloudSun,
  Container,
  Database,
  Gauge,
  History,
  ShieldCheck,
  LineChart as LineIcon,
  MapPin,
  PackageSearch,
  Snowflake,
  Sprout,
  TrendingUp,
  Users,
  Warehouse as WarehouseIcon,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { DailyMovementChart, HBars, LineChart, NotEnoughData } from "@/components/charts";
import { EnvironmentPanel, PriceCard, SourceHealthRow, WeatherCard } from "@/components/data";
import { RecentMovements } from "@/components/MovementsTable";
import {
  Badge,
  CapacityBar,
  Card,
  DataClassBadge,
  EmptyState,
  ErrorState,
  FreshnessBadge,
  PageSkeleton,
  Select,
  SourceTag,
  StatTile,
  SyntheticTag,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { useMemo, useState } from "react";
import { qs, useApi } from "@/lib/api";
import { ROLE_LABELS, useAuth } from "@/lib/auth";
import { fmt, fmtDate, fmtINR, fmtQty, title, UNIT_SHORT } from "@/lib/format";
import type { DataClass, Dashboard, InventoryItem, RoleCode, Trend, Warehouse } from "@/lib/types";

const KPI_ICONS: Record<string, LucideIcon> = {
  users: Users,
  warehouses: WarehouseIcon,
  assigned: WarehouseIcon,
  commodities: Sprout,
  inventory: Boxes,
  stock: Boxes,
  regions: MapPin,
  utilization: Gauge,
  near_capacity: AlertTriangle,
  capacity: Container,
  inbound: ArrowDownToLine,
  outbound: ArrowUpFromLine,
  cold: Snowflake,
  movements: Activity,
};

function greeting() {
  const h = Number(new Date().toLocaleString("en-IN", { timeZone: "Asia/Kolkata", hour: "numeric", hour12: false }));
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

export default function DashboardPage() {
  const [regionId, setRegionId] = useState("");
  const { data, error, loading, reload } = useApi<Dashboard>(`/dashboard${qs({ region_id: regionId })}`);
  const { can, me } = useAuth();
  const scoped = useApi<Warehouse[]>(can("warehouse.read") ? "/warehouses" : null);
  const regionOptions = useMemo(() => {
    const m = new Map<string, string>();
    for (const w of scoped.data ?? []) m.set(w.region.id, w.region.name);
    return [...m].sort((a, b) => a[1].localeCompare(b[1]));
  }, [scoped.data]);

  if (loading && !data) return <PageSkeleton />;
  if (error) return <ErrorState title="Unable to load your dashboard" message={error.message} onRetry={reload} />;
  if (!data || !me) return null;

  const d = data;
  const firstName = me.user.full_name.split(/\s+/)[0];
  const hasWarehouses = (d.warehouses?.length ?? 0) > 0 || (d.inventory_items?.length ?? 0) > 0;
  const today = new Date().toLocaleDateString("en-IN", { timeZone: "Asia/Kolkata", weekday: "long", day: "numeric", month: "long" });
  const trendCommodity = d.role === "ANALYST" ? d.market?.find((m) => m.avg_modal !== null)?.commodity : undefined;
  const envClass = (key: string) => d.environment?.items.find((i) => i.key === key)?.data_class as DataClass | undefined;
  const inventoryClass = envClass("inventory");
  const warehouseClass = envClass("warehouses");
  const syntheticFigures = inventoryClass === "SYNTHETIC_DEMO" || inventoryClass === "MIXED" || warehouseClass === "SYNTHETIC_DEMO" || warehouseClass === "MIXED";

  return (
    <div className="space-y-6">
      {/* Welcome / context */}
      <section className="relative animate-fade-up overflow-hidden rounded-2xl border border-line bg-surface shadow-card">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-y-0 right-0 hidden w-3/5 bg-[url(/art/fields.svg)] sm:block bg-cover bg-center [mask-image:linear-gradient(to_left,black_35%,transparent_95%)]"
        />
        <div aria-hidden className="pointer-events-none absolute inset-0 bg-gradient-to-r from-surface from-35% via-surface/70 to-surface/10" />
        <div className="relative flex flex-col gap-4 px-6 py-6 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <div className="text-xs font-medium text-ink-3">{today}</div>
            <h1 className="mt-1 font-display text-[30px] font-medium leading-tight tracking-tight">
              {greeting()}, {firstName}
            </h1>
            <p className="mt-1 text-sm text-ink-2">
              <span className="font-semibold text-ink">{d.title}</span> — {d.subtitle}
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Badge tone="brand">{d.role ? ROLE_LABELS[d.role as RoleCode] : "No role"}</Badge>
              <Badge icon={MapPin}>{d.scope_label}</Badge>
              {d.is_synthetic && <SyntheticTag />}
            </div>
          </div>
          {regionOptions.length > 1 && (
            <label className="flex shrink-0 items-center gap-2 text-xs font-medium text-ink-2">
              Region
              <Select value={regionId} onChange={(e) => setRegionId(e.target.value)} aria-label="Filter dashboard by region">
                <option value="">All in my scope</option>
                {regionOptions.map(([id, name]) => (
                  <option key={id} value={id}>
                    {name}
                  </option>
                ))}
              </Select>
            </label>
          )}
        </div>
      </section>

      {/* KPIs */}
      <div className="stagger grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        {d.kpis.map((k, i) => (
          <StatTile
            key={k.key}
            label={k.label}
            value={typeof k.value === "number" ? k.value : k.value}
            format={k.unit === "t" || k.unit === "%" ? (n) => fmt(n) : undefined}
            unit={k.unit}
            hint={k.hint}
            tone={k.tone}
            icon={KPI_ICONS[k.key]}
            style={{ "--i": i } as React.CSSProperties}
          />
        ))}
      </div>
      {syntheticFigures && d.kpis.length > 0 && (
        <p className="-mt-3 text-xs text-ink-3">
          {inventoryClass === "MIXED" || warehouseClass === "MIXED"
            ? "Stock and capacity figures above mix synthetic demo records with records your team entered — see Data environment below."
            : "Stock, capacity and movement figures above are synthetic demo values."}
        </p>
      )}

      {!hasWarehouses && (
        <Card>
          <EmptyState
            art
            icon={WarehouseIcon}
            title="No warehouses in your scope yet"
            body={
              can("warehouse.manage")
                ? "Add regions, commodities and warehouses to start tracking stock."
                : "Ask your organization admin to assign you a region or warehouse."
            }
            action={
              can("warehouse.manage") ? (
                <Link href="/warehouses" className="inline-flex items-center gap-1 text-sm font-medium text-brand hover:underline">
                  Set up warehouses <ArrowRight className="h-4 w-4" />
                </Link>
              ) : undefined
            }
          />
        </Card>
      )}

      {/* Real external data first where the role needs it */}
      {d.market && d.role === "PROCUREMENT_MANAGER" && <MarketBlock market={d.market} />}
      {d.weather && (d.role === "WAREHOUSE_MANAGER" || d.role === "LOGISTICS_MANAGER") && <WeatherBlock weather={d.weather} />}

      <div className="grid gap-6 lg:grid-cols-2 lg:[&>*:last-child:nth-child(odd)]:col-span-2">
        {d.environment && (
          <Card title="Data environment" subtitle="What each part of this dashboard is built on" icon={ShieldCheck}>
            <EnvironmentPanel env={d.environment} />
          </Card>
        )}

        {d.data_sources && (
          <Card
            title="Platform & data health"
            subtitle="Are data sources working, and when did they last update?"
            icon={Database}
            action={
              <Link href="/data" className="text-xs font-medium text-brand hover:underline">
                Data sources →
              </Link>
            }
          >
            <div className="-mx-2 -my-1 divide-y divide-line">
              {d.data_sources.map((s) => (
                <SourceHealthRow key={s.key} s={s} />
              ))}
            </div>
          </Card>
        )}

        {trendCommodity && <TrendCard commodity={trendCommodity} />}

        {d.organization && (
          <Card title="Organization" subtitle="Workspace, people and roles" icon={Building2}>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
              <dt className="text-ink-3">Name</dt>
              <dd className="font-medium">{d.organization.organization.name}</dd>
              <dt className="text-ink-3">Workspace ID</dt>
              <dd className="truncate font-mono text-xs">{d.organization.organization.slug}</dd>
              <dt className="text-ink-3">Created</dt>
              <dd>{fmtDate(d.organization.organization.created_at)}</dd>
              <dt className="text-ink-3">Users</dt>
              <dd>
                {d.organization.active_users} active of {d.organization.total_users}
              </dd>
            </dl>
            <div className="mt-4 border-t border-line pt-3">
              <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-3">Users by role</div>
              <ul className="grid grid-cols-1 gap-x-10 gap-y-1 text-sm sm:grid-cols-2">
                {Object.entries(d.organization.users_by_role).map(([role, n]) => (
                  <li key={role} className="flex justify-between gap-2">
                    <span className="text-ink-2">{ROLE_LABELS[role as RoleCode] ?? role}</span>
                    <span className="tabular font-medium">{n}</span>
                  </li>
                ))}
              </ul>
            </div>
          </Card>
        )}

        {d.inventory_by_commodity && (
          <Card title="Inventory by commodity" subtitle="Tonnes in stock across your scope" icon={Boxes} action={<DataClassBadge value={inventoryClass} />}>
            {d.inventory_by_commodity.length ? (
              <HBars
                rows={d.inventory_by_commodity.map((c) => ({
                  key: c.commodity_id,
                  label: c.name,
                  sub: `${c.warehouse_count} warehouse${c.warehouse_count === 1 ? "" : "s"}`,
                  value: c.quantity_tonnes,
                }))}
              />
            ) : (
              <EmptyState icon={PackageSearch} title="No stock recorded" />
            )}
          </Card>
        )}

        {d.inventory_by_region && (
          <Card title="Inventory by region" subtitle="Which regions hold stock" icon={MapPin} flush action={<DataClassBadge value={inventoryClass} />}>
            {d.inventory_by_region.length ? (
              <Table compact>
                <thead>
                  <tr>
                    <Th>Region</Th>
                    <Th right>Sites</Th>
                    <Th right>Stock (t)</Th>
                    <Th right>Capacity (t)</Th>
                  </tr>
                </thead>
                <tbody>
                  {d.inventory_by_region.map((r) => (
                    <tr key={r.region_id}>
                      <Td className="font-medium">{r.name}</Td>
                      <Td right>{r.warehouse_count}</Td>
                      <Td right>{fmt(r.quantity_tonnes)}</Td>
                      <Td right>{fmt(r.capacity_tonnes)}</Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            ) : (
              <EmptyState icon={MapPin} title="No regions yet" />
            )}
          </Card>
        )}

        {d.movement_summary && (
          <Card
            title={`Stock movement — last ${d.movement_summary.days} days`}
            subtitle="Adjustments recorded in the movement ledger"
            icon={History}
            action={<DataClassBadge value={inventoryClass} />}
          >
            <div className="grid grid-cols-2 gap-4">
              <div className="rounded-lg bg-sunken px-3 py-2.5">
                <div className="flex items-center gap-1.5 text-xs text-ink-2">
                  <ArrowDownToLine className="h-3.5 w-3.5 text-series-1" /> Inbound
                </div>
                <div className="tabular mt-0.5 text-xl font-semibold">{fmt(d.movement_summary.inbound_tonnes)} t</div>
                <div className="text-xs text-ink-3">{d.movement_summary.inbound_count} movements</div>
              </div>
              <div className="rounded-lg bg-sunken px-3 py-2.5">
                <div className="flex items-center gap-1.5 text-xs text-ink-2">
                  <ArrowUpFromLine className="h-3.5 w-3.5 text-series-2" /> Outbound
                </div>
                <div className="tabular mt-0.5 text-xl font-semibold">{fmt(d.movement_summary.outbound_tonnes)} t</div>
                <div className="text-xs text-ink-3">{d.movement_summary.outbound_count} movements</div>
              </div>
            </div>
            {d.daily_movements && (
              <div className="mt-5 border-t border-line pt-4">
                <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-3">Daily movement, last 14 days</div>
                <DailyMovementChart rows={d.daily_movements} />
              </div>
            )}
          </Card>
        )}
      </div>

      {d.market && d.role !== "PROCUREMENT_MANAGER" && <MarketBlock market={d.market} />}
      {d.weather && d.role !== "WAREHOUSE_MANAGER" && d.role !== "LOGISTICS_MANAGER" && <WeatherBlock weather={d.weather} />}

      {d.warehouses && d.warehouses.length > 0 && <WarehouseTable warehouses={d.warehouses} showCoords={d.role === "LOGISTICS_MANAGER"} dataClass={warehouseClass} />}
      {d.inventory_items && d.inventory_items.length > 0 && <StockTable items={d.inventory_items} dataClass={inventoryClass} />}
      {d.recent_movements && <RecentMovements rows={d.recent_movements} />}
    </div>
  );
}

function MarketBlock({ market }: { market: NonNullable<Dashboard["market"]> }) {
  const withData = market.filter((m) => m.avg_modal !== null);
  return (
    <section className="animate-fade-up">
      <div className="mb-3 flex items-end justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-[15px] font-semibold tracking-tight">
            <TrendingUp className="h-4 w-4 text-brand" /> Mandi prices for your commodities
          </h2>
          <p className="text-xs text-ink-3">Average modal price across reporting markets · ₹ per quintal · each card names its source</p>
        </div>
        <Link href="/market" className="shrink-0 text-xs font-medium text-brand hover:underline">
          Market prices →
        </Link>
      </div>
      {market.length === 0 ? (
        <Card>
          <EmptyState icon={Sprout} title="No commodities in your catalog" body="Add commodities to see their market prices here." />
        </Card>
      ) : withData.length === 0 ? (
        <Card>
          <EmptyState
            art
            icon={LineIcon}
            title="No market data available yet"
            body="No mandi reports have been fetched or uploaded for your commodities. Check the data source status or upload an AGMARKNET export."
            action={
              <Link href="/data" className="text-sm font-medium text-brand hover:underline">
                Check data sources →
              </Link>
            }
          />
        </Card>
      ) : (
        <div className="stagger grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {market.map((p, i) => (
            <PriceCard key={`${p.commodity}-${p.source?.key ?? "none"}`} p={p} style={{ "--i": i } as React.CSSProperties} />
          ))}
        </div>
      )}
    </section>
  );
}

function WeatherBlock({ weather }: { weather: NonNullable<Dashboard["weather"]> }) {
  return (
    <section className="animate-fade-up">
      <div className="mb-3 flex items-end justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-[15px] font-semibold tracking-tight">
            <CloudSun className="h-4 w-4 text-brand" /> Weather at your warehouses
          </h2>
          <p className="text-xs text-ink-3">
            Current conditions from the Open-Meteo weather model at each warehouse location · forecasts are labelled separately
          </p>
        </div>
        <Link href="/weather" className="shrink-0 text-xs font-medium text-brand hover:underline">
          Weather →
        </Link>
      </div>
      {weather.length === 0 ? (
        <Card>
          <EmptyState icon={CloudSun} title="No warehouses in your scope" />
        </Card>
      ) : (
        <div className="stagger grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {weather.map((w, i) => (
            <WeatherCard key={w.warehouse.id} w={w} style={{ "--i": i } as React.CSSProperties} />
          ))}
        </div>
      )}
    </section>
  );
}

function TrendCard({ commodity }: { commodity: string }) {
  const { data, error, loading } = useApi<Trend>(`/market/trend?commodity=${encodeURIComponent(commodity)}&days=90`);
  const pts = data?.series[0]?.points ?? [];
  return (
    <Card
      title={`${commodity} price trend`}
      subtitle="Average modal price, ₹ per quintal"
      icon={LineIcon}
      action={data && <FreshnessBadge freshness={data.freshness} />}
      footer={data?.source ? <SourceTag source={data.source} /> : undefined}
    >
      {loading && !data ? (
        <div className="skeleton h-52" />
      ) : error ? (
        <ErrorState title="Unable to load price trend" message={error.message} />
      ) : pts.length < 2 ? (
        <NotEnoughData sub="A trend needs reports on at least two dates. History builds up as prices are fetched each day." />
      ) : (
        <LineChart
          series={data!.series.map((s) => ({ label: s.label, points: s.points.map((p) => ({ date: p.date, value: p.modal, note: `${p.markets} market(s)` })) }))}
          valueFormat={(v) => fmtINR(v)}
        />
      )}
    </Card>
  );
}

function WarehouseTable({ warehouses, showCoords, dataClass }: { warehouses: Warehouse[]; showCoords: boolean; dataClass?: DataClass }) {
  return (
    <Card
      title={showCoords ? "Warehouse locations" : "Warehouses"}
      subtitle="Stock against capacity"
      icon={WarehouseIcon}
      flush
      action={<DataClassBadge value={dataClass} />}
    >
      <Table>
        <thead>
          <tr>
            <Th>Warehouse</Th>
            <Th>Region</Th>
            <Th>Storage</Th>
            {showCoords && <Th>Coordinates</Th>}
            <Th right>Stock / capacity (t)</Th>
            <Th>Utilization</Th>
          </tr>
        </thead>
        <tbody>
          {warehouses.map((w) => (
            <tr key={w.id}>
              <Td>
                <Link href={`/warehouses/${w.id}`} className="font-medium hover:text-brand">
                  {w.name}
                </Link>
                {w.status !== "ACTIVE" && (
                  <span className="ml-2">
                    <Badge tone="warn">{title(w.status)}</Badge>
                  </span>
                )}
                {dataClass === "MIXED" && w.data_class === "SYNTHETIC_DEMO" && (
                  <span className="ml-2">
                    <DataClassBadge value={w.data_class} />
                  </span>
                )}
              </Td>
              <Td>{w.region.name}</Td>
              <Td>{title(w.storage_type)}</Td>
              {showCoords && (
                <Td className="font-mono text-xs text-ink-2">
                  {w.latitude != null && w.longitude != null ? `${w.latitude}, ${w.longitude}` : "—"}
                </Td>
              )}
              <Td right>
                {fmt(w.used_tonnes)} / {fmt(w.capacity_tonnes)}
              </Td>
              <Td className="w-48">
                <CapacityBar pct={w.utilization_pct} />
              </Td>
            </tr>
          ))}
        </tbody>
      </Table>
    </Card>
  );
}

function StockTable({ items, dataClass }: { items: InventoryItem[]; dataClass?: DataClass }) {
  return (
    <Card title="Warehouse stock" subtitle="What is stored where" icon={Boxes} flush action={<DataClassBadge value={dataClass} />}>
      <Table>
        <thead>
          <tr>
            <Th>Warehouse</Th>
            <Th>Commodity</Th>
            <Th right>Quantity</Th>
            <Th right>In tonnes</Th>
            <Th>Last updated</Th>
          </tr>
        </thead>
        <tbody>
          {items.map((i) => (
            <tr key={i.id}>
              <Td>{i.warehouse.name}</Td>
              <Td className="font-medium">
                {i.commodity.name}
                {dataClass === "MIXED" && i.data_class === "SYNTHETIC_DEMO" && (
                  <span className="ml-2">
                    <DataClassBadge value={i.data_class} />
                  </span>
                )}
              </Td>
              <Td right>
                {fmtQty(i.quantity)} {UNIT_SHORT[i.unit]}
              </Td>
              <Td right>{fmt(i.quantity_tonnes)}</Td>
              <Td className="text-ink-2">{fmtDate(i.updated_at)}</Td>
            </tr>
          ))}
        </tbody>
      </Table>
    </Card>
  );
}
