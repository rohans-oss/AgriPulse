"use client";

import { AlertTriangle, ArrowLeft, ClipboardList, History } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { RunStatusBadge } from "@/components/data";
import { Badge, Card, EmptyState, ErrorState, PageHeader, PageSkeleton, SourceTag, StatTile, Table, Td, Th } from "@/components/ui";
import { useApi } from "@/lib/api";
import { fmtIST, title } from "@/lib/format";
import type { RunDetail } from "@/lib/types";

export default function RunPage() {
  const { id } = useParams<{ id: string }>();
  const { data: r, error, loading } = useApi<RunDetail>(`/data/runs/${id}`);

  if (loading && !r) return <PageSkeleton />;
  if (error || !r)
    return (
      <div className="space-y-4">
        <ErrorState title="Unable to load this run" message={error?.message ?? "Not found"} />
        <Link href="/data" className="text-sm font-medium text-brand hover:underline">
          ← Data sources
        </Link>
      </div>
    );

  const errors = r.issues.filter((i) => i.severity === "ERROR");
  const warnings = r.issues.filter((i) => i.severity === "WARNING");
  const tiles: [string, number][] = [
    ["Received", r.rows_received],
    ["New", r.rows_inserted],
    ["Updated", r.rows_updated],
    ["Unchanged", r.rows_unchanged],
    ["Duplicates", r.rows_duplicate],
    ["Rejected", r.rows_rejected],
    ["Warnings", r.warnings],
  ];

  return (
    <div className="space-y-6">
      <Link href="/data" className="inline-flex items-center gap-1 text-sm text-ink-2 hover:text-ink">
        <ArrowLeft className="h-4 w-4" /> Data sources
      </Link>
      <PageHeader
        icon={History}
        eyebrow="Ingestion run"
        title={r.file_name ?? r.source.name}
        description={
          <span className="flex flex-wrap items-center gap-2">
            <RunStatusBadge status={r.status} />
            <span>
              {title(r.trigger)} · started {fmtIST(r.started_at)}
              {r.duration_seconds !== null && ` · took ${r.duration_seconds.toFixed(1)}s`}
              {r.triggered_by && ` · by ${r.triggered_by}`}
            </span>
          </span>
        }
      />
      <div className="flex flex-wrap items-center gap-2 text-xs text-ink-3">
        <SourceTag source={r.source} />
        <Badge>{r.scope === "PUBLIC" ? "Shared public fetch" : "Your organization"}</Badge>
        {r.endpoint && (
          <span className="min-w-0 max-w-full truncate font-mono" title={r.endpoint}>
            {r.endpoint}
          </span>
        )}
      </div>

      {r.error_message && (
        <ErrorState title={`This run failed${r.error_kind ? ` · ${title(r.error_kind)}` : ""}`} message={r.error_message} />
      )}
      {typeof r.params.note === "string" && <p className="text-sm text-ink-2">{r.params.note}</p>}

      <div className="stagger grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-7">
        {tiles.map(([label, v], i) => (
          <StatTile
            key={label}
            label={label}
            value={v}
            tone={label === "Rejected" && v ? "bad" : label === "Warnings" && v ? "warn" : "neutral"}
            statusText={label === "Rejected" ? "Not stored" : "Flagged"}
            style={{ "--i": i } as React.CSSProperties}
          />
        ))}
      </div>

      <Card
        title="Data-quality issues"
        subtitle="Errors were rejected and not stored. Warnings were stored and flagged."
        icon={ClipboardList}
        action={
          <span className="flex gap-1.5">
            <Badge tone="bad">{errors.length} errors</Badge>
            <Badge tone="warn">{warnings.length} warnings</Badge>
          </span>
        }
        flush
      >
        {r.issues.length === 0 ? (
          <EmptyState icon={ClipboardList} title="No issues" body="Every row passed validation." />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Severity</Th>
                <Th right>Row</Th>
                <Th>Field</Th>
                <Th>Check</Th>
                <Th>Message</Th>
              </tr>
            </thead>
            <tbody>
              {r.issues.map((i, k) => (
                <tr key={k}>
                  <Td>
                    <Badge tone={i.severity === "ERROR" ? "bad" : "warn"} icon={AlertTriangle}>
                      {i.severity === "ERROR" ? "Rejected" : "Warning"}
                    </Badge>
                  </Td>
                  <Td right>{i.row_number ?? "—"}</Td>
                  <Td className="font-mono text-xs">{i.field ?? "—"}</Td>
                  <Td className="font-mono text-xs text-ink-2">{i.code}</Td>
                  <Td>
                    <div>{i.message}</div>
                    {Object.keys(i.raw).length > 0 && (
                      <details className="mt-1">
                        <summary className="cursor-pointer text-xs text-ink-3">Source row</summary>
                        <pre className="mt-1 max-w-xl overflow-x-auto rounded-lg bg-sunken p-2 text-[11px] text-ink-2">{JSON.stringify(i.raw, null, 2)}</pre>
                      </details>
                    )}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </div>
  );
}
