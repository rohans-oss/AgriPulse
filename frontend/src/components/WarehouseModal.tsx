"use client";

import { useState } from "react";
import { Button, Field, FormError, Input, Modal, Select } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { title } from "@/lib/format";
import type { Region, StorageType, Warehouse, WarehouseStatus } from "@/lib/types";

const STORAGE: StorageType[] = ["NORMAL", "COLD_STORAGE", "CONTROLLED"];
const STATUSES: WarehouseStatus[] = ["ACTIVE", "MAINTENANCE", "INACTIVE"];

type Form = {
  name: string;
  region_id: string;
  address: string;
  latitude: string;
  longitude: string;
  capacity_tonnes: string;
  storage_type: StorageType;
  status: WarehouseStatus;
};

const EMPTY: Form = {
  name: "",
  region_id: "",
  address: "",
  latitude: "",
  longitude: "",
  capacity_tonnes: "",
  storage_type: "NORMAL",
  status: "ACTIVE",
};

export function WarehouseModal({
  warehouse,
  regions,
  onClose,
  onSaved,
}: {
  warehouse: Warehouse | "new" | null;
  regions: Region[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const isNew = warehouse === "new";
  const [form, setForm] = useState<Form>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loadedFor, setLoadedFor] = useState<unknown>(null);

  if (warehouse !== loadedFor) {
    setLoadedFor(warehouse);
    setError(null);
    setForm(
      warehouse && warehouse !== "new"
        ? {
            name: warehouse.name,
            region_id: warehouse.region.id,
            address: warehouse.address,
            latitude: warehouse.latitude?.toString() ?? "",
            longitude: warehouse.longitude?.toString() ?? "",
            capacity_tonnes: warehouse.capacity_tonnes.toString(),
            storage_type: warehouse.storage_type,
            status: warehouse.status,
          }
        : { ...EMPTY, region_id: regions[0]?.id ?? "" },
    );
  }

  // Regions may finish loading after the modal opens; fall back to the first one.
  const regionId = regions.some((r) => r.id === form.region_id) ? form.region_id : regions[0]?.id ?? "";

  const set = (k: keyof Form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const body = {
      ...form,
      region_id: regionId,
      latitude: form.latitude === "" ? null : Number(form.latitude),
      longitude: form.longitude === "" ? null : Number(form.longitude),
      capacity_tonnes: form.capacity_tonnes,
    };
    try {
      if (isNew) await api("/warehouses", { method: "POST", json: body });
      else if (warehouse) await api(`/warehouses/${warehouse.id}`, { method: "PATCH", json: body });
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open={warehouse !== null} title={isNew ? "Add warehouse" : "Edit warehouse"} onClose={onClose}>
      {regions.length === 0 ? (
        <p className="text-sm text-ink-2">Add a region first — every warehouse belongs to a region.</p>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <Field label="Name">
            <Input required maxLength={160} value={form.name} onChange={set("name")} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Region">
              <Select required value={regionId} onChange={set("region_id")}>
                {regions.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Capacity (tonnes)">
              <Input
                required
                type="number"
                min="0.001"
                step="0.001"
                value={form.capacity_tonnes}
                onChange={set("capacity_tonnes")}
              />
            </Field>
          </div>
          <Field label="Address">
            <Input maxLength={255} value={form.address} onChange={set("address")} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Latitude" hint="Optional">
              <Input type="number" step="any" min={-90} max={90} value={form.latitude} onChange={set("latitude")} />
            </Field>
            <Field label="Longitude" hint="Optional">
              <Input type="number" step="any" min={-180} max={180} value={form.longitude} onChange={set("longitude")} />
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Storage type">
              <Select value={form.storage_type} onChange={set("storage_type")}>
                {STORAGE.map((s) => (
                  <option key={s} value={s}>
                    {title(s)}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Status">
              <Select value={form.status} onChange={set("status")}>
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {title(s)}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <FormError message={error} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={busy}>
              {busy ? "Saving…" : "Save"}
            </Button>
          </div>
        </form>
      )}
    </Modal>
  );
}
