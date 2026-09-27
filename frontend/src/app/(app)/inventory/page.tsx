"use client";

import { Boxes as BoxesIcon } from "lucide-react";
import { useState } from "react";
import { InventoryTable } from "@/components/InventoryTable";
import { RecentMovements } from "@/components/MovementsTable";
import { Button, Field, FormError, Input, Modal, PageHeader, Select } from "@/components/ui";
import { api, ApiError, qs, useApi } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmt, title, UNIT_SHORT } from "@/lib/format";
import type { Commodity, InventoryItem, Movement, Region, Warehouse } from "@/lib/types";

export default function InventoryPage() {
  const { can } = useAuth();
  const [warehouse, setWarehouse] = useState("");
  const [commodity, setCommodity] = useState("");
  const [region, setRegion] = useState("");
  const [creating, setCreating] = useState(false);

  const items = useApi<InventoryItem[]>(
    `/inventory${qs({ warehouse_id: warehouse, commodity_id: commodity, region_id: region })}`,
  );
  const moves = useApi<Movement[]>(`/inventory/movements${qs({ warehouse_id: warehouse, commodity_id: commodity, limit: "20" })}`);
  const warehouses = useApi<Warehouse[]>("/warehouses");
  const commodities = useApi<Commodity[]>("/commodities");
  const regions = useApi<Region[]>("/regions");

  const total = items.data?.reduce((s, i) => s + i.quantity_tonnes, 0) ?? 0;
  const reload = () => {
    items.reload();
    moves.reload();
  };

  return (
    <div>
      <PageHeader
        icon={BoxesIcon}
        eyebrow="Operations"
        title="Inventory"
        description={
          items.data
            ? `${items.data.length} record${items.data.length === 1 ? "" : "s"} · ${fmt(total)} t in view`
            : "Current stock by warehouse and commodity"
        }
        actions={can("inventory.create") && <Button onClick={() => setCreating(true)}>Add inventory record</Button>}
      />

      <div className="mb-4 flex flex-wrap gap-3">
        <Select className="w-56" value={warehouse} onChange={(e) => setWarehouse(e.target.value)} aria-label="Warehouse">
          <option value="">All warehouses</option>
          {warehouses.data?.map((w) => (
            <option key={w.id} value={w.id}>
              {w.name}
            </option>
          ))}
        </Select>
        <Select className="w-44" value={commodity} onChange={(e) => setCommodity(e.target.value)} aria-label="Commodity">
          <option value="">All commodities</option>
          {commodities.data?.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </Select>
        <Select className="w-44" value={region} onChange={(e) => setRegion(e.target.value)} aria-label="Region">
          <option value="">All regions</option>
          {regions.data?.map((r) => (
            <option key={r.id} value={r.id}>
              {r.name}
            </option>
          ))}
        </Select>
        {(warehouse || commodity || region) && (
          <Button
            variant="ghost"
            onClick={() => {
              setWarehouse("");
              setCommodity("");
              setRegion("");
            }}
          >
            Clear filters
          </Button>
        )}
      </div>

      <InventoryTable
        items={items.data}
        loading={items.loading}
        error={items.error?.message}
        onChanged={reload}
        emptyAction={
          can("inventory.create") && !warehouse && !commodity && !region ? (
            <Button onClick={() => setCreating(true)}>Add inventory record</Button>
          ) : undefined
        }
      />
      {moves.data && <RecentMovements rows={moves.data} heading="Recent movements" />}

      <CreateInventoryModal
        open={creating}
        warehouses={(warehouses.data ?? []).filter((w) => w.status === "ACTIVE")}
        commodities={(commodities.data ?? []).filter((c) => c.status === "ACTIVE")}
        defaultWarehouse={warehouse}
        onClose={() => setCreating(false)}
        onSaved={() => {
          setCreating(false);
          reload();
        }}
      />
    </div>
  );
}

function CreateInventoryModal({
  open,
  warehouses,
  commodities,
  defaultWarehouse,
  onClose,
  onSaved,
}: {
  open: boolean;
  warehouses: Warehouse[];
  commodities: Commodity[];
  defaultWarehouse: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState({ warehouse_id: "", commodity_id: "", quantity: "", notes: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [wasOpen, setWasOpen] = useState(false);

  if (open !== wasOpen) {
    setWasOpen(open);
    if (open) {
      setError(null);
      setForm({
        warehouse_id: defaultWarehouse || warehouses[0]?.id || "",
        commodity_id: commodities[0]?.id || "",
        quantity: "",
        notes: "",
      });
    }
  }

  // Option lists may finish loading after the modal opens; fall back to the first option.
  const warehouseId = warehouses.some((w) => w.id === form.warehouse_id) ? form.warehouse_id : warehouses[0]?.id ?? "";
  const commodityId = commodities.some((c) => c.id === form.commodity_id) ? form.commodity_id : commodities[0]?.id ?? "";
  const unit = commodities.find((c) => c.id === commodityId)?.unit;
  const selectedWh = warehouses.find((w) => w.id === warehouseId);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/inventory", {
        method: "POST",
        json: { ...form, warehouse_id: warehouseId, commodity_id: commodityId },
      });
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open={open} title="Add inventory record" onClose={onClose}>
      {!warehouses.length || !commodities.length ? (
        <p className="text-sm text-ink-2">
          You need at least one active warehouse in your scope and one active commodity before adding stock.
        </p>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <Field
            label="Warehouse"
            hint={selectedWh ? `${fmt(selectedWh.capacity_tonnes - selectedWh.used_tonnes)} t free` : undefined}
          >
            <Select required value={warehouseId} onChange={(e) => setForm({ ...form, warehouse_id: e.target.value })}>
              {warehouses.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Commodity">
            <Select required value={commodityId} onChange={(e) => setForm({ ...form, commodity_id: e.target.value })}>
              {commodities.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} ({title(c.unit).toLowerCase()})
                </option>
              ))}
            </Select>
          </Field>
          <Field label={`Opening quantity${unit ? ` (${UNIT_SHORT[unit]})` : ""}`}>
            <Input
              required
              type="number"
              min="0"
              step="0.001"
              value={form.quantity}
              onChange={(e) => setForm({ ...form, quantity: e.target.value })}
            />
          </Field>
          <Field label="Notes">
            <Input maxLength={500} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
          </Field>
          <FormError message={error} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={busy}>
              {busy ? "Saving…" : "Add record"}
            </Button>
          </div>
        </form>
      )}
    </Modal>
  );
}
