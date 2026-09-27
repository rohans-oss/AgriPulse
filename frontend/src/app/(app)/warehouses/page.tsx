"use client";

import { Warehouse as WarehouseIcon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { WarehouseModal } from "@/components/WarehouseModal";
import {
  Badge,
  Button,
  CapacityBar,
  Card,
  EmptyState,
  ErrorState,
  Loading,
  PageHeader,
  Select,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { qs, useApi } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmt, title } from "@/lib/format";
import type { Region, Warehouse } from "@/lib/types";

export default function WarehousesPage() {
  const { can, me } = useAuth();
  const manage = can("warehouse.manage");
  const [region, setRegion] = useState("");
  const [storage, setStorage] = useState("");
  const [status, setStatus] = useState("");
  const { data, error, loading, reload } = useApi<Warehouse[]>(
    `/warehouses${qs({ region_id: region, storage_type: storage, status })}`,
  );
  const regions = useApi<Region[]>("/regions");
  const [editing, setEditing] = useState<Warehouse | "new" | null>(null);
  const filtered = Boolean(region || storage || status);

  return (
    <div>
      <PageHeader
        icon={WarehouseIcon}
        eyebrow="Operations"
        title="Warehouses"
        description={
          me?.scope.org_wide
            ? "All warehouses in your organization."
            : "Only warehouses within your assigned location scope are shown."
        }
        actions={manage && <Button onClick={() => setEditing("new")}>Add warehouse</Button>}
      />

      <div className="mb-4 flex flex-wrap gap-3">
        <Select className="w-44" value={region} onChange={(e) => setRegion(e.target.value)} aria-label="Region">
          <option value="">All regions</option>
          {regions.data?.map((r) => (
            <option key={r.id} value={r.id}>
              {r.name}
            </option>
          ))}
        </Select>
        <Select className="w-44" value={storage} onChange={(e) => setStorage(e.target.value)} aria-label="Storage type">
          <option value="">Any storage type</option>
          <option value="NORMAL">Normal</option>
          <option value="COLD_STORAGE">Cold storage</option>
          <option value="CONTROLLED">Controlled</option>
        </Select>
        <Select className="w-40" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
          <option value="">Any status</option>
          <option value="ACTIVE">Active</option>
          <option value="MAINTENANCE">Maintenance</option>
          <option value="INACTIVE">Inactive</option>
        </Select>
      </div>

      <Card flush>
        {loading && !data ? (
          <div className="px-4">
            <Loading />
          </div>
        ) : error ? (
          <div className="p-4">
            <ErrorState message={error.message} onRetry={reload} />
          </div>
        ) : !data?.length ? (
          <EmptyState
            art
            icon={WarehouseIcon}
            title={filtered ? "No warehouses match these filters" : "No warehouses available"}
            body={
              filtered
                ? undefined
                : manage
                  ? "Add your first warehouse to start recording stock."
                  : "No warehouses are assigned to you yet."
            }
            action={manage && !filtered && <Button onClick={() => setEditing("new")}>Add warehouse</Button>}
          />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Warehouse</Th>
                <Th>Region</Th>
                <Th>Storage</Th>
                <Th>Status</Th>
                <Th right>Stock / capacity (t)</Th>
                <Th>Utilization</Th>
                {manage && <Th />}
              </tr>
            </thead>
            <tbody>
              {data.map((w) => (
                <tr key={w.id}>
                  <Td>
                    <Link href={`/warehouses/${w.id}`} className="font-medium hover:text-brand">
                      {w.name}
                    </Link>
                    {w.address && <div className="max-w-xs truncate text-xs text-ink-3">{w.address}</div>}
                  </Td>
                  <Td>{w.region.name}</Td>
                  <Td>{title(w.storage_type)}</Td>
                  <Td>
                    <Badge tone={w.status === "ACTIVE" ? "good" : "warn"}>{title(w.status)}</Badge>
                  </Td>
                  <Td right>
                    {fmt(w.used_tonnes)} / {fmt(w.capacity_tonnes)}
                  </Td>
                  <Td className="w-48">
                    <CapacityBar pct={w.utilization_pct} />
                  </Td>
                  {manage && (
                    <Td right>
                      <Button size="sm" variant="ghost" onClick={() => setEditing(w)}>
                        Edit
                      </Button>
                    </Td>
                  )}
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      <WarehouseModal
        warehouse={editing}
        regions={regions.data ?? []}
        onClose={() => setEditing(null)}
        onSaved={() => {
          setEditing(null);
          reload();
        }}
      />
    </div>
  );
}
