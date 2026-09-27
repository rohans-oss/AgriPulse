"use client";

import { useState } from "react";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Field,
  FormError,
  Input,
  Loading,
  Modal,
  PageHeader,
  Select,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { api, ApiError, qs, useApi } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, title } from "@/lib/format";
import type { Category, Commodity, RecordStatus, Unit } from "@/lib/types";

const CATEGORIES: Category[] = ["VEGETABLE", "FRUIT", "GRAIN", "PULSE", "SPICE", "OILSEED", "OTHER"];
const UNITS: Unit[] = ["TONNE", "QUINTAL", "KG"];

type Form = { name: string; category: Category; unit: Unit; status: RecordStatus };
const EMPTY: Form = { name: "", category: "VEGETABLE", unit: "TONNE", status: "ACTIVE" };

export default function CommoditiesPage() {
  const { can } = useAuth();
  const manage = can("commodity.manage");
  const [category, setCategory] = useState("");
  const [status, setStatus] = useState("");
  const { data, error, loading, reload } = useApi<Commodity[]>(`/commodities${qs({ category, status })}`);
  const [editing, setEditing] = useState<Commodity | "new" | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  async function remove(c: Commodity) {
    if (!confirm(`Delete commodity "${c.name}"?`)) return;
    setActionError(null);
    try {
      await api(`/commodities/${c.id}`, { method: "DELETE" });
      reload();
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : String(e));
    }
  }

  return (
    <div>
      <PageHeader
        title="Commodities"
        description="Products this organization stores and tracks, with the unit their quantities are recorded in."
        actions={manage && <Button onClick={() => setEditing("new")}>Add commodity</Button>}
      />

      <div className="mb-4 flex flex-wrap gap-3">
        <Select className="w-44" value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Category">
          <option value="">All categories</option>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {title(c)}
            </option>
          ))}
        </Select>
        <Select className="w-36" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
          <option value="">Any status</option>
          <option value="ACTIVE">Active</option>
          <option value="INACTIVE">Inactive</option>
        </Select>
      </div>

      {actionError && (
        <div className="mb-4">
          <ErrorState message={actionError} />
        </div>
      )}

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
            title={category || status ? "No commodities match these filters" : "No commodities yet"}
            action={manage && !category && !status && <Button onClick={() => setEditing("new")}>Add commodity</Button>}
          />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Name</Th>
                <Th>Category</Th>
                <Th>Unit</Th>
                <Th>Status</Th>
                <Th>Updated</Th>
                {manage && <Th />}
              </tr>
            </thead>
            <tbody>
              {data.map((c) => (
                <tr key={c.id}>
                  <Td className="font-medium">{c.name}</Td>
                  <Td>{title(c.category)}</Td>
                  <Td>{title(c.unit)}</Td>
                  <Td>
                    <Badge tone={c.status === "ACTIVE" ? "good" : "neutral"}>{title(c.status)}</Badge>
                  </Td>
                  <Td className="text-ink-2">{fmtDate(c.updated_at)}</Td>
                  {manage && (
                    <Td right>
                      <div className="flex justify-end gap-1">
                        <Button size="sm" variant="ghost" onClick={() => setEditing(c)}>
                          Edit
                        </Button>
                        <Button size="sm" variant="ghost" className="hover:text-bad" onClick={() => remove(c)}>
                          Delete
                        </Button>
                      </div>
                    </Td>
                  )}
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      <CommodityModal
        commodity={editing}
        onClose={() => setEditing(null)}
        onSaved={() => {
          setEditing(null);
          reload();
        }}
      />
    </div>
  );
}

function CommodityModal({
  commodity,
  onClose,
  onSaved,
}: {
  commodity: Commodity | "new" | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const isNew = commodity === "new";
  const [form, setForm] = useState<Form>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loadedFor, setLoadedFor] = useState<unknown>(null);

  if (commodity !== loadedFor) {
    setLoadedFor(commodity);
    setError(null);
    setForm(
      commodity && commodity !== "new"
        ? { name: commodity.name, category: commodity.category, unit: commodity.unit, status: commodity.status }
        : EMPTY,
    );
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (isNew) await api("/commodities", { method: "POST", json: form });
      else if (commodity) await api(`/commodities/${commodity.id}`, { method: "PATCH", json: form });
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open={commodity !== null} title={isNew ? "Add commodity" : "Edit commodity"} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <Field label="Name">
          <Input required maxLength={120} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Category">
            <Select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value as Category })}>
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {title(c)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Unit" hint="Locked once stock exists">
            <Select value={form.unit} onChange={(e) => setForm({ ...form, unit: e.target.value as Unit })}>
              {UNITS.map((u) => (
                <option key={u} value={u}>
                  {title(u)}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <Field label="Status" hint="Inactive commodities cannot receive new inventory records">
          <Select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value as RecordStatus })}>
            <option value="ACTIVE">Active</option>
            <option value="INACTIVE">Inactive</option>
          </Select>
        </Field>
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
    </Modal>
  );
}
