"use client";

import {
  AlertTriangle,
  Database,
  ExternalLink,
  FileUp,
  FlaskConical,
  History,
  KeyRound,
  Landmark,
  RefreshCw,
  UploadCloud,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { RunStatusBadge } from "@/components/data";
import { waitForRun } from "@/components/weather";
import { Badge, Button, Card, EmptyState, ErrorState, FreshnessBadge, Loading, PageHeader, Skeleton, Table, Td, Th } from "@/components/ui";
import { api, ApiError, useApi } from "@/lib/api";
import { ago, fmtDateOnly, fmtIST, title } from "@/lib/format";
import type { Run, SourceStatus } from "@/lib/types";

const ORIGIN_META: Record<SourceStatus["origin"], { label: string; icon: LucideIcon; tone: "brand" | "info" | "neutral"; blurb: string }> = {
  OFFICIAL_API: { label: "Official government data", icon: Landmark, tone: "brand", blurb: "Published by a government body" },
  PUBLIC_API: { label: "Documented public API", icon: Database, tone: "info", blurb: "Trustworthy third-party public data" },
  USER_UPLOAD: { label: "Your uploaded files", icon: UploadCloud, tone: "neutral", blurb: "Private to your organization" },
};

export default function DataSourcesPage() {
  const sources = useApi<SourceStatus[]>("/data/sources");
  const runs = useApi<Run[]>("/data/runs?limit=30");
  const reload = () => {
    sources.reload();
    runs.reload();
  };

  return (
    <div className="space-y-6">
      <PageHeader
        icon={Database}
        eyebrow="Data platform"
        title="Data sources"
        description="Where every external figure in AgriFlow comes from, how often it updates, and whether the last fetch worked."
      />

      <div className="stagger grid gap-3 md:grid-cols-4">
        {(Object.keys(ORIGIN_META) as SourceStatus["origin"][]).map((o, i) => {
          const m = ORIGIN_META[o];
          return (
            <div key={o} className="rounded-xl border border-line bg-surface px-4 py-3 shadow-card" style={{ "--i": i } as React.CSSProperties}>
              <Badge tone={m.tone} icon={m.icon}>
                {m.label}
              </Badge>
              <p className="mt-1.5 text-xs text-ink-3">{m.blurb}</p>
            </div>
          );
        })}
        <div className="rounded-xl border border-amber-200 bg-harvest-soft/60 px-4 py-3 shadow-card" style={{ "--i": 3 } as React.CSSProperties}>
          <Badge tone="warn" icon={FlaskConical}>
            Synthetic demo data
          </Badge>
          <p className="mt-1.5 text-xs text-ink-3">Invented organization figures in the demo workspace — never mixed with the above</p>
        </div>
      </div>

      {sources.loading && !sources.data ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-72 rounded-xl" />
          ))}
        </div>
      ) : sources.error ? (
        <ErrorState title="Unable to load data sources" message={sources.error.message} onRetry={sources.reload} />
      ) : (
        <div className="stagger grid gap-4 lg:grid-cols-2">
          {sources.data?.map((s, i) => (
            <SourceCard key={s.key} s={s} onChanged={reload} style={{ "--i": i } as React.CSSProperties} />
          ))}
        </div>
      )}

      <Card title="Ingestion history" subtitle="Fetches and uploads by your organization, newest first" icon={History} flush>
        {runs.loading && !runs.data ? (
          <div className="px-5">
            <Loading />
          </div>
        ) : runs.error ? (
          <div className="p-4">
            <ErrorState title="Unable to load ingestion history" message={runs.error.message} onRetry={runs.reload} />
          </div>
        ) : !runs.data?.length ? (
          <EmptyState icon={History} title="No fetches or uploads yet" body="Runs appear here with their row counts and any data-quality issues." />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Started</Th>
                <Th>Source</Th>
                <Th>Status</Th>
                <Th right>Received</Th>
                <Th right>New</Th>
                <Th right>Updated</Th>
                <Th right>Rejected</Th>
                <Th right>Warnings</Th>
                <Th>By</Th>
              </tr>
            </thead>
            <tbody>
              {runs.data.map((r) => (
                <tr key={r.id}>
                  <Td className="whitespace-nowrap">
                    <Link href={`/data/runs/${r.id}`} className="font-medium hover:text-brand">
                      {fmtIST(r.started_at)}
                    </Link>
                    <div className="text-[11px] text-ink-3">
                      {title(r.trigger)}
                      {r.duration_seconds !== null && ` · ${r.duration_seconds.toFixed(1)}s`}
                    </div>
                  </Td>
                  <Td>
                    <div className="max-w-[16rem] truncate">{r.source.name}</div>
                    {r.file_name && <div className="max-w-[16rem] truncate text-[11px] text-ink-3">{r.file_name}</div>}
                  </Td>
                  <Td>
                    <RunStatusBadge status={r.status} />
                  </Td>
                  <Td right>{r.rows_received}</Td>
                  <Td right>{r.rows_inserted}</Td>
                  <Td right>{r.rows_updated}</Td>
                  <Td right className={r.rows_rejected ? "font-medium text-bad" : ""}>
                    {r.rows_rejected}
                  </Td>
                  <Td right className={r.warnings ? "font-medium text-warn" : ""}>
                    {r.warnings}
                  </Td>
                  <Td className="whitespace-nowrap text-ink-2">{r.triggered_by ?? (r.trigger === "SCHEDULED" ? "Schedule" : "—")}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </div>
  );
}

function SourceCard({ s, onChanged, style }: { s: SourceStatus; onChanged: () => void; style?: React.CSSProperties }) {
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const meta = ORIGIN_META[s.origin];
  const upload = s.origin === "USER_UPLOAD";
  const lastFailed = s.last_run?.status === "FAILED";

  async function fetchNow() {
    setRunning(true);
    setErr(null);
    setProgress("Starting…");
    try {
      const run = await api<Run>(`/data/sources/${s.key}/runs`, { method: "POST" });
      const done = await waitForRun(run.id, (r) => setProgress(r.status === "RUNNING" ? `Fetching… ${r.rows_received} rows so far` : null));
      setProgress(null);
      if (done.status === "FAILED") setErr(done.error_message ?? "Fetch failed");
      onChanged();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
      setProgress(null);
    } finally {
      setRunning(false);
    }
  }

  return (
    <section className="flex flex-col overflow-hidden rounded-xl border border-line bg-surface shadow-card" style={style}>
      <div className="flex items-start gap-3 border-b border-line px-5 py-4">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-brand-soft text-brand">
          <meta.icon className="h-5 w-5" strokeWidth={1.8} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-[15px] font-semibold tracking-tight">{s.name}</h2>
            {s.freshness && !upload && <FreshnessBadge freshness={s.freshness} />}
          </div>
          <p className="mt-0.5 text-xs text-ink-3">{s.publisher}</p>
        </div>
      </div>

      <div className="flex-1 space-y-4 px-5 py-4">
        <p className="text-sm text-ink-2">{s.description}</p>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
          <Meta label="Updates">{s.update_frequency}</Meta>
          <Meta label="Licence">{s.license}</Meta>
          <Meta label={s.kind === "INVENTORY" ? "Uploads" : s.kind === "WEATHER" ? "Readings stored" : "Records available"}>{s.record_count.toLocaleString("en-IN")}</Meta>
          <Meta label={s.kind === "WEATHER" ? "Latest reading" : upload && s.kind === "INVENTORY" ? "Last upload" : "Latest report date"}>
            {s.kind === "INVENTORY"
              ? s.last_success_at
                ? fmtIST(s.last_success_at)
                : "—"
              : s.latest_observation
                ? s.kind === "WEATHER"
                  ? fmtIST(s.latest_observation)
                  : fmtDateOnly(s.latest_observation)
                : "—"}
          </Meta>
          <Meta label="Last successful update">{s.last_success_at ? `${fmtIST(s.last_success_at)} (${ago(s.last_success_at)})` : "Never"}</Meta>
          <Meta label="Last run">{s.last_run ? <RunStatusBadge status={s.last_run.status} /> : "—"}</Meta>
        </dl>

        {!s.configured && (
          <div className="flex items-start gap-2.5 rounded-lg border border-line bg-sunken px-3 py-2.5 text-sm">
            <KeyRound className="mt-0.5 h-4 w-4 shrink-0 text-harvest" />
            <div className="text-ink-2">
              <div className="font-medium text-ink">Not configured</div>
              {s.config_message}. Get a key at{" "}
              <a className="text-brand hover:underline" href="https://data.gov.in" target="_blank" rel="noreferrer">
                data.gov.in
              </a>{" "}
              (My Account → API key), add it to <code className="font-mono text-xs">backend/.env</code> and restart the API.
            </div>
          </div>
        )}
        {(err || (lastFailed && s.last_run?.error_message)) && (
          <div className="flex items-start gap-2.5 rounded-lg border border-red-200 bg-red-50/70 px-3 py-2.5 text-sm">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-bad" />
            <div>
              <div className="font-medium text-bad">{err ? "Fetch failed" : "Last fetch failed"}</div>
              <div className="text-ink-2">{err ?? s.last_run?.error_message}</div>
              <div className="mt-0.5 text-xs text-ink-3">
                {s.last_success_at ? `Last successful update ${fmtIST(s.last_success_at)} — that data is still shown.` : "No successful update yet."}
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line bg-sunken px-5 py-3">
        {s.homepage_url ? (
          <a href={s.homepage_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs font-medium text-ink-2 hover:text-ink">
            Source documentation <ExternalLink className="h-3 w-3" />
          </a>
        ) : (
          <span />
        )}
        <div className="flex items-center gap-2">
          {progress && <span className="animate-fade-in text-xs text-ink-3">{progress}</span>}
          {s.can_run && (
            <Button size="sm" icon={RefreshCw} loading={running} onClick={fetchNow}>
              {running ? "Fetching" : "Fetch now"}
            </Button>
          )}
          {s.can_upload && (
            <Link
              href={`/data/import?type=${s.kind === "INVENTORY" ? "inventory" : "market"}`}
              className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-line-strong/70 bg-surface px-3 text-[13px] font-medium shadow-card hover:bg-sunken"
            >
              <FileUp className="h-4 w-4" /> Upload CSV
            </Link>
          )}
        </div>
      </div>
    </section>
  );
}

function Meta({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-3">{label}</dt>
      <dd className="mt-0.5 text-ink">{children}</dd>
    </div>
  );
}
