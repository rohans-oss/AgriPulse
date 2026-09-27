"use client";

import { useState } from "react";
import { Button, Card, EmptyState, ErrorState, Field, FormError, Input, Loading, Modal, Table, Td, Th } from "./ui";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmt, fmtDate, fmtQty, title, UNIT_SHORT } from "@/lib/format";
import type { InventoryItem } from "@/lib/types";

export function InventoryTable({
  items,
  loading,
  error,
  onChanged,
  heading = "Inventory",
  hideWarehouse = false,
  className = "",
  emptyAction,
}: {
  items: InventoryItem[] | null;
  loading: boolean;
  error?: string;
  onChanged: () => void;
  heading?: string;
  hideWarehouse?: boolean;
  className?: string;
  emptyAction?: React.ReactNode;
}) {
  const { can } = useAuth();
  const canUpdate = can("inventory.update");
  const canDelete = can("inventory.delete");
  const [adjusting, setAdjusting] = useState<InventoryItem | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  async function remove(i: InventoryItem) {
    if (!confirm(`Remove the ${i.commodity.name} record from ${i.warehouse.name}? The removal is kept in history.`))
      return;
    setActionError(null);
    try {
      await api(`/inventory/${i.id}`, { method: "DELETE" });
      onChanged();
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : String(e));
    }
  }

  return (
    <Card title={heading} flush className={className}>
      {actionError && (
        <div className="p-4 pb-0">
          <ErrorState message={actionError} />
        </div>
      )}
      {loading && !items ? (
        <div className="px-4">
          <Loading />
        </div>
      ) : error ? (
        <div className="p-4">
          <ErrorState message={error} />
        </div>
      ) : !items?.length ? (
        <EmptyState title="No inventory records" body="Nothing matches in your scope." action={emptyAction} />
      ) : (
        <Table>
          <thead>
            <tr>
              {!hideWarehouse && <Th>Warehouse</Th>}
              <Th>Commodity</Th>
              <Th right>Quantity</Th>
              <Th right>In tonnes</Th>
              <Th>Notes</Th>
              <Th>Updated</Th>
              {(canUpdate || canDelete) && <Th />}
            </tr>
          </thead>
          <tbody>
            {items.map((i) => (
              <tr key={i.id}>
                {!hideWarehouse && <Td className="font-medium">{i.warehouse.name}</Td>}
                <Td>
                  {i.commodity.name}
                  <span className="ml-1.5 text-xs text-ink-3">{title(i.commodity.category)}</span>
                </Td>
                <Td right>
                  {fmtQty(i.quantity)} <span className="text-ink-3">{UNIT_SHORT[i.unit]}</span>
                </Td>
                <Td right>{fmt(i.quantity_tonnes)}</Td>
                <Td className="max-w-48 truncate text-ink-2">{i.notes || "—"}</Td>
                <Td className="whitespace-nowrap text-ink-2">{fmtDate(i.updated_at)}</Td>
                {(canUpdate || canDelete) && (
                  <Td right>
                    <div className="flex justify-end gap-1">
                      {canUpdate && (
                        <Button size="sm" variant="ghost" onClick={() => setAdjusting(i)}>
                          Adjust
                        </Button>
                      )}
                      {canDelete && (
                        <Button size="sm" variant="ghost" className="hover:text-bad" onClick={() => remove(i)}>
                          Remove
                        </Button>
                      )}
                    </div>
                  </Td>
                )}
              </tr>
            ))}
          </tbody>
        </Table>
      )}
      <AdjustModal
        item={adjusting}
        onClose={() => setAdjusting(null)}
        onSaved={() => {
          setAdjusting(null);
          onChanged();
        }}
      />
    </Card>
  );
}

function AdjustModal({
  item,
  onClose,
  onSaved,
}: {
  item: InventoryItem | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [quantity, setQuantity] = useState("");
  const [notes, setNotes] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loadedFor, setLoadedFor] = useState<InventoryItem | null>(null);

  if (item !== loadedFor) {
    setLoadedFor(item);
    setError(null);
    setQuantity(item ? String(item.quantity) : "");
    setNotes(item?.notes ?? "");
    setReason("");
  }

  const delta = item && quantity !== "" ? Number(quantity) - item.quantity : 0;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!item) return;
    setBusy(true);
    setError(null);
    try {
      await api(`/inventory/${item.id}`, { method: "PATCH", json: { quantity, notes, reason } });
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open={item !== null} title="Adjust quantity" onClose={onClose}>
      {item && (
        <form onSubmit={submit} className="space-y-4">
          <p className="text-sm text-ink-2">
            {item.commodity.name} at <span className="text-ink">{item.warehouse.name}</span> — currently{" "}
            <span className="tabular text-ink">
              {fmtQty(item.quantity)} {UNIT_SHORT[item.unit]}
            </span>
          </p>
          <Field
            label={`New quantity (${title(item.unit).toLowerCase()}s)`}
            hint={
              delta
                ? `${delta > 0 ? "Inbound +" : "Outbound "}${fmtQty(delta)} ${UNIT_SHORT[item.unit]}`
                : "No change in quantity"
            }
          >
            <Input
              required
              type="number"
              min="0"
              step="0.001"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
            />
          </Field>
          <Field label="Reason" hint="Recorded in the movement history">
            <Input maxLength={255} placeholder="e.g. Received from Kolar collection" value={reason} onChange={(e) => setReason(e.target.value)} />
          </Field>
          <Field label="Notes">
            <Input maxLength={500} value={notes} onChange={(e) => setNotes(e.target.value)} />
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
      )}
    </Modal>
  );
}
