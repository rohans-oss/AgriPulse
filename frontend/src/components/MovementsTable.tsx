"use client";

import { ArrowDownRight, ArrowUpRight, History } from "lucide-react";
import { Badge, Card, EmptyState, Table, Td, Th } from "@/components/ui";
import { fmtDate, fmtQty, title } from "@/lib/format";
import type { Movement } from "@/lib/types";

export function RecentMovements({ rows, heading = "Recent inventory movements" }: { rows: Movement[]; heading?: string }) {
  return (
    <Card title={heading} subtitle="Every quantity change is recorded here" icon={History} flush className="mt-6 first:mt-0">
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
                <Td className="font-medium">{m.commodity.name}</Td>
                <Td>
                  <Badge tone={m.quantity_delta >= 0 ? "brand" : "neutral"} icon={m.quantity_delta >= 0 ? ArrowDownRight : ArrowUpRight}>
                    {title(m.movement_type)}
                  </Badge>
                </Td>
                <Td right className={m.quantity_delta >= 0 ? "text-good" : "text-ink-2"}>
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
        <EmptyState icon={History} title="No movements recorded yet" body="Movements appear when stock is added, adjusted or removed." />
      )}
    </Card>
  );
}
