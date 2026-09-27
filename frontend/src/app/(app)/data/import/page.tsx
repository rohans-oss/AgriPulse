"use client";

import { ArrowRight, CheckCircle2, Download, FileSpreadsheet, FileUp, RotateCcw, ShieldCheck, TrendingUp, Boxes } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useRef, useState } from "react";
import { Badge, Button, Card, ErrorState, Notice, PageHeader, StatTile, Table, Td, Th } from "@/components/ui";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { ImportResult } from "@/lib/types";

type Kind = "market" | "inventory";

const KINDS: Record<Kind, { title: string; icon: typeof TrendingUp; endpoint: string; blurb: string; template: string; columns: [string, string][] }> = {
  market: {
    title: "Market price file",
    icon: TrendingUp,
    endpoint: "/api/imports/market-prices",
    blurb: "Historical mandi prices, for example an AGMARKNET report export. Rows stay private to your organization and are labelled with the file name.",
    template: "State,District,Market,Commodity,Variety,Grade,Arrival_Date,Min_Price,Max_Price,Modal_Price\n",
    columns: [
      ["State, Market, Commodity", "required"],
      ["Arrival_Date", "required — dd/mm/yyyy or yyyy-mm-dd"],
      ["Modal_Price", "required — ₹ per quintal"],
      ["District, Variety, Grade, Min_Price, Max_Price", "optional"],
    ],
  },
  inventory: {
    title: "Inventory file",
    icon: Boxes,
    endpoint: "/api/imports/inventory",
    blurb: "Set stock for many warehouse–commodity pairs at once. The file is applied only if every row is valid; each change is recorded as a movement.",
    template: "warehouse,commodity,quantity,notes\n",
    columns: [
      ["warehouse", "required — exact warehouse name"],
      ["commodity", "required — exact commodity name"],
      ["quantity", "required — in the commodity's own unit; replaces current stock"],
      ["notes", "optional"],
    ],
  },
};

async function upload(endpoint: string, file: File, dryRun: boolean): Promise<ImportResult> {
  const body = new FormData();
  body.append("file", file);
  const res = await fetch(`${endpoint}?dry_run=${dryRun}`, { method: "POST", body, credentials: "same-origin" });
  const json = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, typeof json?.detail === "string" ? json.detail : `Upload failed (${res.status})`);
  return json as ImportResult;
}

function ImportInner() {
  const { can } = useAuth();
  const params = useSearchParams();
  const allowed: Kind[] = [
    ...(can("data.import") ? (["market"] as Kind[]) : []),
    ...(can("inventory.create") && can("inventory.update") ? (["inventory"] as Kind[]) : []),
  ];
  const initial = (params.get("type") as Kind) || allowed[0];
  const [kind, setKind] = useState<Kind>(allowed.includes(initial) ? initial : allowed[0]);
  const [file, setFile] = useState<File | null>(null);
  const [check, setCheck] = useState<ImportResult | null>(null);
  const [done, setDone] = useState<ImportResult | null>(null);
  const [busy, setBusy] = useState<"check" | "import" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [drag, setDrag] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  if (!allowed.length)
    return (
      <div>
        <PageHeader icon={FileUp} eyebrow="Data platform" title="Import CSV" />
        <ErrorState title="No access" message="Your role cannot import files. Ask an organization admin if you need data loaded." />
      </div>
    );
  const k = KINDS[kind];

  function reset() {
    setFile(null);
    setCheck(null);
    setDone(null);
    setError(null);
  }

  async function validate(f: File) {
    setFile(f);
    setCheck(null);
    setDone(null);
    setError(null);
    setBusy("check");
    try {
      setCheck(await upload(k.endpoint, f, true));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  async function commit() {
    if (!file) return;
    setBusy("import");
    setError(null);
    try {
      setDone(await upload(k.endpoint, file, false));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  function downloadTemplate() {
    const url = URL.createObjectURL(new Blob([k.template], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `${kind}-template.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const blocking = kind === "inventory" ? (check?.rows_rejected ?? 0) > 0 : (check?.rows_valid ?? 0) === 0;
  const step = done ? 3 : check ? 2 : 1;

  return (
    <div className="space-y-6">
      <PageHeader icon={FileUp} eyebrow="Data platform" title="Import CSV" description="Validate a file before anything changes. Every import is recorded in the ingestion history." />

      {allowed.length > 1 && (
        <div className="inline-flex rounded-xl border border-line bg-surface p-1 shadow-card">
          {allowed.map((kk) => {
            const Icon = KINDS[kk].icon;
            return (
              <button
                key={kk}
                onClick={() => {
                  setKind(kk);
                  reset();
                }}
                className={`inline-flex items-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium transition-colors ${kind === kk ? "bg-brand text-white" : "text-ink-2 hover:bg-sunken"}`}
              >
                <Icon className="h-4 w-4" /> {KINDS[kk].title}
              </button>
            );
          })}
        </div>
      )}

      <ol className="flex flex-wrap items-center gap-2 text-sm">
        {["Choose file", "Review validation", "Import"].map((label, i) => (
          <li key={label} className="flex items-center gap-2">
            <span
              className={`grid h-6 w-6 place-items-center rounded-full text-xs font-semibold transition-colors ${
                step > i + 1 ? "bg-good text-white" : step === i + 1 ? "bg-brand text-white" : "bg-line text-ink-3"
              }`}
            >
              {step > i + 1 ? "✓" : i + 1}
            </span>
            <span className={step === i + 1 ? "font-medium text-ink" : "text-ink-3"}>{label}</span>
            {i < 2 && <ArrowRight className="h-3.5 w-3.5 text-ink-3" />}
          </li>
        ))}
      </ol>

      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <div className="min-w-0 space-y-6">
          {!done && (
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDrag(true);
              }}
              onDragLeave={() => setDrag(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDrag(false);
                const f = e.dataTransfer.files[0];
                if (f) validate(f);
              }}
              className={`relative flex flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-10 text-center transition-all duration-200 ${
                drag ? "scale-[1.01] border-brand bg-brand-soft" : "border-line-strong bg-surface"
              }`}
            >
              <span className="grid h-12 w-12 place-items-center rounded-2xl bg-brand-soft text-brand">
                <FileSpreadsheet className="h-6 w-6" strokeWidth={1.7} />
              </span>
              <div className="mt-3 text-sm font-semibold">{file ? file.name : `Drop a ${k.title.toLowerCase()} here`}</div>
              <p className="mt-1 max-w-md text-sm text-ink-2">{k.blurb}</p>
              <div className="mt-4 flex gap-2">
                <Button icon={FileUp} loading={busy === "check"} onClick={() => input.current?.click()}>
                  {file ? "Choose another file" : "Choose CSV file"}
                </Button>
                <Button variant="secondary" icon={Download} onClick={downloadTemplate}>
                  Blank template
                </Button>
              </div>
              <input
                ref={input}
                type="file"
                accept=".csv,text/csv"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) validate(f);
                  e.target.value = "";
                }}
              />
              <p className="mt-3 text-xs text-ink-3">CSV, up to 5 MB and 50,000 rows. Validation is a dry run — nothing is saved.</p>
            </div>
          )}

          {error && <ErrorState title="The file could not be processed" message={error} />}

          {check && !done && (
            <div className="animate-fade-up space-y-6">
              <div className="stagger grid grid-cols-2 gap-3 md:grid-cols-4">
                <StatTile label="Rows in file" value={check.rows_total} style={{ "--i": 0 } as React.CSSProperties} />
                <StatTile statusText="Will import" label="Valid rows" value={check.rows_valid} tone={check.rows_valid ? "good" : "neutral"} style={{ "--i": 1 } as React.CSSProperties} />
                <StatTile statusText="Will be skipped" label="Rejected rows" value={check.rows_rejected} tone={check.rows_rejected ? "bad" : "neutral"} style={{ "--i": 2 } as React.CSSProperties} />
                <StatTile statusText="Review" label="Warnings" value={check.warnings} tone={check.warnings ? "warn" : "neutral"} style={{ "--i": 3 } as React.CSSProperties} />
              </div>

              <Card title="Columns detected" subtitle="How your headers were understood" icon={ShieldCheck}>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(check.columns_detected).map(([orig, canon]) => (
                    <span key={orig} className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-sunken px-2 py-1 text-xs">
                      <span className="text-ink-2">{orig}</span> <ArrowRight className="h-3 w-3 text-ink-3" />
                      <code className="font-mono text-brand">{canon}</code>
                    </span>
                  ))}
                </div>
              </Card>

              {check.issues.length > 0 && (
                <Card title="Issues found" subtitle={kind === "inventory" ? "Fix every error before importing — nothing is changed until then." : "Rejected rows will be skipped; warnings are imported and flagged."} flush>
                  <Table>
                    <thead>
                      <tr>
                        <Th right>Row</Th>
                        <Th>Severity</Th>
                        <Th>Field</Th>
                        <Th>Message</Th>
                      </tr>
                    </thead>
                    <tbody>
                      {check.issues.slice(0, 50).map((i, n) => (
                        <tr key={n}>
                          <Td right>{i.row_number ?? "—"}</Td>
                          <Td>
                            <Badge tone={i.severity === "ERROR" ? "bad" : "warn"}>{i.severity === "ERROR" ? "Error" : "Warning"}</Badge>
                          </Td>
                          <Td className="font-mono text-xs">{i.field ?? "—"}</Td>
                          <Td>{i.message}</Td>
                        </tr>
                      ))}
                    </tbody>
                  </Table>
                  {check.issues.length > 50 && <p className="px-5 py-3 text-xs text-ink-3">Showing 50 of {check.issues.length} issues.</p>}
                </Card>
              )}

              {check.preview.length > 0 && (
                <Card title="Preview" subtitle={`First ${check.preview.length} valid rows as they will be stored`} flush>
                  <Table>
                    <thead>
                      <tr>
                        {Object.keys(check.preview[0]).map((h) => (
                          <Th key={h}>{h.replace(/_/g, " ")}</Th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {check.preview.map((row, n) => (
                        <tr key={n}>
                          {Object.entries(row).map(([h, v]) => (
                            <Td key={h} className="whitespace-nowrap">
                              {h === "action" ? <Badge tone={v === "create" ? "brand" : v === "update" ? "info" : "neutral"}>{String(v)}</Badge> : v === null || v === "" ? "—" : String(v)}
                            </Td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </Table>
                </Card>
              )}

              <div className="flex flex-wrap items-center justify-end gap-2">
                <Button variant="ghost" icon={RotateCcw} onClick={reset}>
                  Start over
                </Button>
                <Button icon={CheckCircle2} disabled={blocking} loading={busy === "import"} onClick={commit}>
                  {kind === "inventory" ? `Apply ${check.rows_valid} change${check.rows_valid === 1 ? "" : "s"}` : `Import ${check.rows_valid} valid row${check.rows_valid === 1 ? "" : "s"}`}
                </Button>
              </div>
            </div>
          )}

          {done && (
            <Card className="animate-fade-up">
              <div className="flex flex-col items-center py-6 text-center">
                <span className="grid h-14 w-14 place-items-center rounded-full bg-green-50 text-good ring-8 ring-green-50/50">
                  <CheckCircle2 className="h-7 w-7" />
                </span>
                <h2 className="mt-4 text-lg font-semibold">Import complete</h2>
                <p className="mt-1 text-sm text-ink-2">
                  {done.file_name}: {done.inserted} new, {done.updated} updated, {done.unchanged} unchanged
                  {done.rows_rejected ? `, ${done.rows_rejected} rejected` : ""}
                  {done.warnings ? `, ${done.warnings} warning(s)` : ""}.
                </p>
                <div className="mt-5 flex flex-wrap justify-center gap-2">
                  {done.run_id && (
                    <Link href={`/data/runs/${done.run_id}`} className="inline-flex h-9 items-center rounded-lg border border-line-strong/70 bg-surface px-4 text-sm font-medium shadow-card hover:bg-sunken">
                      View run details
                    </Link>
                  )}
                  <Link
                    href={kind === "inventory" ? "/inventory" : "/market"}
                    className="inline-flex h-9 items-center rounded-lg bg-brand px-4 text-sm font-medium text-white hover:bg-brand-hover"
                  >
                    {kind === "inventory" ? "Open inventory" : "Open market prices"}
                  </Link>
                  <Button variant="ghost" icon={RotateCcw} onClick={reset}>
                    Import another
                  </Button>
                </div>
              </div>
            </Card>
          )}
        </div>

        <aside className="space-y-4">
          <Card title="Expected columns" subtitle="Header names are matched flexibly">
            <ul className="space-y-2.5 text-sm">
              {k.columns.map(([c, d]) => (
                <li key={c}>
                  <code className="font-mono text-xs text-brand">{c}</code>
                  <div className="text-xs text-ink-3">{d}</div>
                </li>
              ))}
            </ul>
          </Card>
          <Notice>
            {kind === "market"
              ? "Uploaded prices are shown as “Uploaded file” with your file name — never as official data. The blank template contains headers only."
              : "Only warehouses in your location scope can be updated. Capacity limits are checked for the whole file."}
          </Notice>
        </aside>
      </div>
    </div>
  );
}

export default function ImportPage() {
  return (
    <Suspense>
      <ImportInner />
    </Suspense>
  );
}
