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
import { api, ApiError, useApi } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Region } from "@/lib/types";

type Form = { name: string; state: string; code: string; status: "ACTIVE" | "INACTIVE" };
const EMPTY: Form = { name: "", state: "", code: "", status: "ACTIVE" };

export default function RegionsPage() {
  const { can } = useAuth();
  const manage = can("region.manage");
  const { data, error, loading, reload } = useApi<Region[]>("/regions");
  const [editing, setEditing] = useState<Region | "new" | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  async function remove(r: Region) {
    if (!confirm(`Delete region "${r.name}"?`)) return;
    setActionError(null);
    try {
      await api(`/regions/${r.id}`, { method: "DELETE" });
      reload();
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : String(e));
    }
  }

  return (
    <div>
      <PageHeader
        title="Regions"
        description="Operating regions for this organization. Warehouses belong to a region."
        actions={manage && <Button onClick={() => setEditing("new")}>Add region</Button>}
      />
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
            title="No regions yet"
            body={manage ? "Add the districts or cities you operate in." : "Your admin has not added regions yet."}
            action={manage && <Button onClick={() => setEditing("new")}>Add region</Button>}
          />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Name</Th>
                <Th>State</Th>
                <Th>Code</Th>
                <Th right>Warehouses</Th>
                <Th>Status</Th>
                {manage && <Th />}
              </tr>
            </thead>
            <tbody>
              {data.map((r) => (
                <tr key={r.id}>
                  <Td className="font-medium">{r.name}</Td>
                  <Td>{r.state || "—"}</Td>
                  <Td className="font-mono text-xs">{r.code || "—"}</Td>
                  <Td right>{r.warehouse_count}</Td>
                  <Td>
                    <Badge tone={r.status === "ACTIVE" ? "good" : "neutral"}>{r.status === "ACTIVE" ? "Active" : "Inactive"}</Badge>
                  </Td>
                  {manage && (
                    <Td right>
                      <div className="flex justify-end gap-1">
                        <Button size="sm" variant="ghost" onClick={() => setEditing(r)}>
                          Edit
                        </Button>
                        <Button size="sm" variant="ghost" className="hover:text-bad" onClick={() => remove(r)}>
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

      <RegionModal
        region={editing}
        onClose={() => setEditing(null)}
        onSaved={() => {
          setEditing(null);
          reload();
        }}
      />
    </div>
  );
}

function RegionModal({
  region,
  onClose,
  onSaved,
}: {
  region: Region | "new" | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const isNew = region === "new";
  const [form, setForm] = useState<Form>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loadedFor, setLoadedFor] = useState<unknown>(null);

  if (region !== loadedFor) {
    setLoadedFor(region);
    setError(null);
    setForm(
      region && region !== "new"
        ? { name: region.name, state: region.state, code: region.code ?? "", status: region.status }
        : EMPTY,
    );
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const body = { ...form, code: form.code || null };
    try {
      if (isNew) await api("/regions", { method: "POST", json: body });
      else if (region) await api(`/regions/${region.id}`, { method: "PATCH", json: body });
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open={region !== null} title={isNew ? "Add region" : "Edit region"} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <Field label="Name">
          <Input required maxLength={120} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="State">
            <Input maxLength={80} value={form.state} onChange={(e) => setForm({ ...form, state: e.target.value })} />
          </Field>
          <Field label="Code" hint="Optional short code">
            <Input maxLength={16} value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} />
          </Field>
        </div>
        <Field label="Status">
          <Select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value as Form["status"] })}>
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
