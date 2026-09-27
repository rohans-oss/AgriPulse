"use client";

import { Badge, Card, EmptyState, Table, Td, Th } from "@/components/ui";
import { fmtDate, fmtQty, title } from "@/lib/format";
import type { Movement } from "@/lib/types";

export function RecentMovements({ rows, heading = "Recent inventory movements" }: { rows: Movement[]; heading?: string }) {
  return (
    <Card title={heading} flush className="mt-6">
      {rows.length ? (
        <Table>
          <thead>
            <tr>
              <Th>When</Th>
              <Th>Warehouse</Th>
              <Th>Commodity</Th>
              <Th>Type</Th>
              <Th right>Change</Th>
              <Th right>After</Th>
              <Th>Reason</Th>
            </tr>
          </thead>
          <tbody>
            {rows.map((m) => (
              <tr key={m.id}>
                <Td className="whitespace-nowrap text-ink-2">{fmtDate(m.created_at)}</Td>
                <Td>{m.warehouse.name}</Td>
                <Td>{m.commodity.name}</Td>
                <Td>
                  <Badge tone={m.quantity_delta >= 0 ? "brand" : "neutral"}>{title(m.movement_type)}</Badge>
                </Td>
                <Td right>
                  {m.quantity_delta > 0 ? "+" : ""}
                  {fmtQty(m.quantity_delta)}
                </Td>
                <Td right>{fmtQty(m.quantity_after)}</Td>
                <Td className="text-ink-2">{m.reason || "—"}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      ) : (
        <EmptyState title="No movements recorded yet" />
      )}
    </Card>
  );
}
