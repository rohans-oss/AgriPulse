"use client";

import Link from "next/link";
import { DailyMovementChart, HBars } from "@/components/charts";
import { RecentMovements } from "@/components/MovementsTable";
import {
  Badge,
  CapacityBar,
  Card,
  EmptyState,
  ErrorState,
  Loading,
  PageHeader,
  StatTile,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { useApi } from "@/lib/api";
import { ROLE_LABELS, useAuth } from "@/lib/auth";
import { fmt, fmtDate, fmtQty, title, UNIT_SHORT } from "@/lib/format";
import type { Dashboard, InventoryItem, RoleCode, Warehouse } from "@/lib/types";

export default function DashboardPage() {
  const { data, error, loading, reload } = useApi<Dashboard>("/dashboard");
  const { can } = useAuth();

  if (loading && !data) return <Loading />;
  if (error) return <ErrorState message={error.message} onRetry={reload} />;
  if (!data) return null;

  const d = data;
  const hasStock = d.kpis.length > 0 && (d.inventory_by_commodity?.length || d.inventory_items?.length);

  return (
    <div>
      <PageHeader
        title={d.title}
        description={
          <>
            {d.subtitle} · <span className="text-ink">{d.scope_label}</span>
            {d.is_synthetic && (
              <span className="ml-2">
                <Badge tone="warn">Synthetic data</Badge>
              </span>
            )}
          </>
        }
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        {d.kpis.map((k) => (
          <StatTile
            key={k.key}
            label={k.label}
            value={typeof k.value === "number" ? fmt(k.value) : k.value}
            unit={k.unit}
            hint={k.hint}
            tone={k.tone}
          />
        ))}
      </div>

      {!hasStock && d.warehouses?.length === 0 && (
        <Card className="mt-6">
          <EmptyState
            title="No warehouses in your scope yet"
            body={
              can("warehouse.manage")
                ? "Add regions, commodities and warehouses to start tracking stock."
                : "Ask your organization admin to assign you a region or warehouse."
            }
            action={
              can("warehouse.manage") ? (
                <Link href="/warehouses" className="text-sm font-medium text-brand hover:underline">
                  Set up warehouses →
                </Link>
              ) : undefined
            }
          />
        </Card>
      )}

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        {d.organization && (
          <Card title="Organization">
            <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
              <dt className="text-ink-2">Name</dt>
              <dd className="font-medium">{d.organization.organization.name}</dd>
              <dt className="text-ink-2">Workspace ID</dt>
              <dd className="truncate font-mono text-xs">{d.organization.organization.slug}</dd>
              <dt className="text-ink-2">Created</dt>
              <dd>{fmtDate(d.organization.organization.created_at)}</dd>
              <dt className="text-ink-2">Users</dt>
              <dd>
                {d.organization.active_users} active of {d.organization.total_users}
              </dd>
            </dl>
            <div className="mt-4 border-t border-line pt-3">
              <div className="mb-2 text-xs font-medium uppercase tracking-wide text-ink-3">Users by role</div>
              <ul className="grid grid-cols-2 gap-1 text-sm">
                {Object.entries(d.organization.users_by_role).map(([role, n]) => (
                  <li key={role} className="flex justify-between gap-2">
                    <span className="text-ink-2">{ROLE_LABELS[role as RoleCode] ?? role}</span>
                    <span className="tabular">{n}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="mt-4 flex flex-wrap gap-3 text-sm">
              {can("users.manage") && <QuickLink href="/users">Manage users</QuickLink>}
              {can("region.manage") && <QuickLink href="/regions">Regions</QuickLink>}
              {can("commodity.manage") && <QuickLink href="/commodities">Commodities</QuickLink>}
              {can("warehouse.manage") && <QuickLink href="/warehouses">Warehouses</QuickLink>}
              {can("settings.manage") && <QuickLink href="/settings">Settings & audit log</QuickLink>}
            </div>
          </Card>
        )}

        {d.inventory_by_commodity && (
          <Card title="Inventory by commodity">
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
              <EmptyState title="No stock recorded" />
            )}
          </Card>
        )}

        {d.inventory_by_region && (
          <Card title="Inventory by region" flush>
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
                      <Td>{r.name}</Td>
                      <Td right>{r.warehouse_count}</Td>
                      <Td right>{fmt(r.quantity_tonnes)}</Td>
                      <Td right>{fmt(r.capacity_tonnes)}</Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            ) : (
              <EmptyState title="No regions yet" />
            )}
          </Card>
        )}

        {d.movement_summary && (
          <Card title={`Stock movement — last ${d.movement_summary.days} days`}>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="text-xs text-ink-2">Inbound</div>
                <div className="tabular text-xl font-semibold">{fmt(d.movement_summary.inbound_tonnes)} t</div>
                <div className="text-xs text-ink-3">{d.movement_summary.inbound_count} movements</div>
              </div>
              <div>
                <div className="text-xs text-ink-2">Outbound</div>
                <div className="tabular text-xl font-semibold">{fmt(d.movement_summary.outbound_tonnes)} t</div>
                <div className="text-xs text-ink-3">{d.movement_summary.outbound_count} movements</div>
              </div>
            </div>
            {d.daily_movements && (
              <div className="mt-5 border-t border-line pt-4">
                <div className="mb-2 text-xs font-medium uppercase tracking-wide text-ink-3">
                  Daily movement, last 14 days
                </div>
                <DailyMovementChart rows={d.daily_movements} />
              </div>
            )}
          </Card>
        )}
      </div>

      {d.warehouses && d.warehouses.length > 0 && (
        <WarehouseTable warehouses={d.warehouses} showCoords={d.role === "LOGISTICS_MANAGER"} />
      )}
      {d.inventory_items && d.inventory_items.length > 0 && <StockTable items={d.inventory_items} />}
      {d.recent_movements && <RecentMovements rows={d.recent_movements} />}
    </div>
  );
}

function QuickLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link href={href} className="font-medium text-brand hover:underline">
      {children}
    </Link>
  );
}

function WarehouseTable({ warehouses, showCoords }: { warehouses: Warehouse[]; showCoords: boolean }) {
  return (
    <Card title={showCoords ? "Warehouse locations" : "Warehouses"} flush className="mt-6">
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

function StockTable({ items }: { items: InventoryItem[] }) {
  return (
    <Card title="Warehouse stock" flush className="mt-6">
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
              <Td>{i.commodity.name}</Td>
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
