"use client";

import { CloudSun, Gauge, Warehouse as WarehouseIcon } from "lucide-react";
import { WeatherHistoryPanels } from "@/components/weather";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { InventoryTable } from "@/components/InventoryTable";
import { RecentMovements } from "@/components/MovementsTable";
import { WarehouseModal } from "@/components/WarehouseModal";
import { Badge, Button, CapacityBar, Card, ErrorState, Loading, PageHeader, StatTile } from "@/components/ui";
import { api, ApiError, useApi } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmt, fmtDate, title } from "@/lib/format";
import type { InventoryItem, Movement, Region, Warehouse } from "@/lib/types";

export default function WarehouseDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { can } = useAuth();
  const wh = useApi<Warehouse>(`/warehouses/${id}`);
  const inv = useApi<InventoryItem[]>(can("inventory.read") ? `/inventory?warehouse_id=${id}` : null);
  const moves = useApi<Movement[]>(can("inventory.read") ? `/inventory/movements?warehouse_id=${id}&limit=15` : null);
  const regions = useApi<Region[]>(can("warehouse.manage") ? "/regions" : null);
  const [editing, setEditing] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  if (wh.loading && !wh.data) return <Loading />;
  if (wh.error)
    return (
      <div className="space-y-4">
        <ErrorState message={wh.error.message} />
        <Link href="/warehouses" className="text-sm font-medium text-brand hover:underline">
          ← Back to warehouses
        </Link>
      </div>
    );
  const w = wh.data!;
  const reloadAll = () => {
    wh.reload();
    inv.reload();
    moves.reload();
  };

  async function remove() {
    if (!confirm(`Delete warehouse "${w.name}"? This cannot be undone.`)) return;
    try {
      await api(`/warehouses/${w.id}`, { method: "DELETE" });
      router.replace("/warehouses");
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : String(e));
    }
  }

  return (
    <div>
      <Link href="/warehouses" className="text-sm text-ink-2 hover:text-ink">
        ← Warehouses
      </Link>
      <PageHeader
        icon={WarehouseIcon}
        eyebrow="Warehouse"
        title={w.name}
        description={
          <>
            {w.region.name} · {title(w.storage_type)}{" "}
            <Badge tone={w.status === "ACTIVE" ? "good" : "warn"}>{title(w.status)}</Badge>
          </>
        }
        actions={
          can("warehouse.manage") && (
            <>
              <Button variant="secondary" onClick={() => setEditing(true)}>
                Edit
              </Button>
              <Button variant="danger" onClick={remove}>
                Delete
              </Button>
            </>
          )
        }
      />
      {actionError && (
        <div className="mb-4">
          <ErrorState message={actionError} />
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatTile label="Capacity" value={fmt(w.capacity_tonnes)} unit="t" />
        <StatTile label="In stock" value={fmt(w.used_tonnes)} unit="t" />
        <StatTile label="Free" value={fmt(Math.max(w.capacity_tonnes - w.used_tonnes, 0))} unit="t" />
        <StatTile label="Commodities" value={String(inv.data?.length ?? "—")} />
      </div>

      <Card className="mt-6" title="Capacity used" subtitle="Stock against capacity, converted to tonnes" icon={Gauge}>
        <CapacityBar pct={w.utilization_pct} />
        <dl className="mt-4 grid grid-cols-1 gap-2 text-sm sm:grid-cols-3">
          <div>
            <dt className="text-xs text-ink-3">Address</dt>
            <dd>{w.address || "—"}</dd>
          </div>
          <div>
            <dt className="text-xs text-ink-3">Coordinates</dt>
            <dd className="font-mono text-xs">
              {w.latitude != null && w.longitude != null ? `${w.latitude}, ${w.longitude}` : "—"}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-ink-3">Last updated</dt>
            <dd>{fmtDate(w.updated_at)}</dd>
          </div>
        </dl>
      </Card>

      {can("inventory.read") && (
        <>
          <InventoryTable
            className="mt-6"
            heading="Stock in this warehouse"
            items={inv.data}
            loading={inv.loading}
            error={inv.error?.message}
            onChanged={reloadAll}
            hideWarehouse
          />
          {moves.data && <RecentMovements rows={moves.data} heading="Movement history" />}
        </>
      )}

      {can("data.read") && w.latitude != null && w.longitude != null && (
        <section className="mt-6 space-y-3">
          <h2 className="flex items-center gap-2 text-[15px] font-semibold tracking-tight">
            <CloudSun className="h-4 w-4 text-brand" /> Weather at this warehouse
          </h2>
          <WeatherHistoryPanels warehouseId={w.id} />
        </section>
      )}

      {can("warehouse.manage") && (
        <WarehouseModal
          warehouse={editing ? w : null}
          regions={regions.data ?? []}
          onClose={() => setEditing(false)}
          onSaved={() => {
            setEditing(false);
            reloadAll();
          }}
        />
      )}
    </div>
  );
}
