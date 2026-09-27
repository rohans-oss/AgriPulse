"use client";

import { AlertTriangle, CloudSun, Info, RefreshCw } from "lucide-react";
import { useMemo, useState } from "react";
import { SourceStatusBadge, WeatherCard } from "@/components/data";
import { WeatherHistoryPanels, waitForRun } from "@/components/weather";
import { Button, Card, EmptyState, ErrorState, Notice, PageHeader, Select, Skeleton } from "@/components/ui";
import { api, ApiError, qs, useApi } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { ago, fmtIST } from "@/lib/format";
import type { Run, SourceStatus, WeatherNow } from "@/lib/types";

export default function WeatherPage() {
  const { can } = useAuth();
  const [regionId, setRegionId] = useState("");
  const all = useApi<WeatherNow[]>("/weather/current");
  const filtered = useApi<WeatherNow[]>(regionId ? `/weather/current${qs({ region_id: regionId })}` : null);
  const now = regionId ? filtered : all;
  const regions = useMemo(() => {
    const m = new Map<string, string>();
    for (const w of all.data ?? []) m.set(w.region.id, w.region.name);
    return [...m].sort((a, b) => a[1].localeCompare(b[1]));
  }, [all.data]);
  const sources = useApi<SourceStatus[]>("/data/sources");
  const src = sources.data?.find((s) => s.key === "open_meteo_weather");
  const [selected, setSelected] = useState("");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<Run | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const withCoords = (all.data ?? []).filter((w) => w.latitude !== null);
  const warehouseId = selected || withCoords[0]?.warehouse.id || "";

  async function refresh() {
    setRunning(true);
    setErr(null);
    setResult(null);
    try {
      const run = await api<Run>("/data/sources/open_meteo_weather/runs", { method: "POST" });
      const done = await waitForRun(run.id);
      setResult(done);
      all.reload();
      if (regionId) filtered.reload();
      sources.reload();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }

  return (
    <div>
      <PageHeader
        icon={CloudSun}
        eyebrow="Market intelligence"
        title="Weather at your warehouses"
        description={
          <>
            Current conditions, disruption indicators and completed-day history for each warehouse&apos;s coordinates.
            {src?.last_success_at && <span className="text-ink-3"> Last successful update {ago(src.last_success_at)}.</span>}
            {src && (
              <span className="ml-2 inline-flex align-middle">
                <SourceStatusBadge status={src.status} detail={src.status_detail} />
              </span>
            )}
          </>
        }
        actions={
          can("data.ingest") && (
            <Button icon={RefreshCw} loading={running} onClick={refresh}>
              {running ? "Fetching…" : "Fetch latest"}
            </Button>
          )
        }
      />

      <div className="space-y-6">
        <Notice icon={Info}>
          Source: <strong className="font-medium text-ink">Open-Meteo</strong> — model-based estimates from national weather services for each
          location. These are not IMD station readings. Every reading shows its own timestamp; nothing here is streamed live. Indicators are
          simple published thresholds (IMD rainfall categories, heat and gust limits) applied to observed readings or, where marked, to the
          provider&apos;s forecast — hover one to see its rule.
        </Notice>

        {src?.status === "FAILING" && !result && (
          <div className="flex items-start gap-2.5 rounded-xl border border-red-200 bg-red-50/70 px-4 py-3 text-sm" role="alert">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-bad" />
            <div>
              <div className="font-medium text-bad">Latest weather update failed</div>
              <div className="text-ink-2">{src.last_failure_message}</div>
              <div className="mt-0.5 text-xs text-ink-3">
                {src.last_success_at ? `Readings below are from the last successful update (${fmtIST(src.last_success_at)}).` : "No verified readings yet."}
              </div>
            </div>
          </div>
        )}

        {regions.length > 1 && (
          <div className="flex items-center justify-end gap-2 text-xs font-medium text-ink-2">
            Region
            <Select value={regionId} onChange={(e) => setRegionId(e.target.value)} aria-label="Filter by region">
              <option value="">All in my scope</option>
              {regions.map(([id, name]) => (
                <option key={id} value={id}>
                  {name}
                </option>
              ))}
            </Select>
          </div>
        )}

        {err && <ErrorState title="Unable to fetch weather" message={err} />}
        {result && result.status === "FAILED" && (
          <ErrorState
            title="Weather fetch failed"
            message={result.error_message ?? "The external source did not respond."}
            footnote={src?.last_success_at ? `Last successful update ${ago(src.last_success_at)} — older readings are still shown below.` : "No successful update yet."}
          />
        )}
        {result && result.status !== "FAILED" && (
          <Notice icon={RefreshCw}>
            Fetched {result.params.locations as number} location(s): {result.rows_inserted} new, {result.rows_updated} updated, {result.rows_unchanged} unchanged
            observations{result.params.forecast_days_stored ? `, plus ${result.params.forecast_days_stored as number} forecast days (stored separately)` : ""}.
            {result.rows_rejected > 0 && ` ${result.rows_rejected} rejected — see the run details.`}
          </Notice>
        )}

        {now.loading && !now.data ? (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-56 rounded-xl" />
            ))}
          </div>
        ) : now.error ? (
          <ErrorState title="Unable to load weather" message={now.error.message} onRetry={now.reload} />
        ) : !now.data?.length ? (
          <Card>
            <EmptyState art icon={CloudSun} title="No warehouses in your scope" body="Weather is shown for warehouses you have access to." />
          </Card>
        ) : (
          <div className="stagger grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {now.data.map((w, i) => (
              <WeatherCard key={w.warehouse.id} w={w} style={{ "--i": i } as React.CSSProperties} />
            ))}
          </div>
        )}

        {withCoords.length > 0 && (
          <section className="animate-fade-up space-y-3">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <h2 className="text-[15px] font-semibold tracking-tight">Recent history</h2>
                <p className="text-xs text-ink-3">Daily totals for completed days at the selected warehouse</p>
              </div>
              <Select className="w-64" value={warehouseId} onChange={(e) => setSelected(e.target.value)} aria-label="Warehouse">
                {withCoords.map((w) => (
                  <option key={w.warehouse.id} value={w.warehouse.id}>
                    {w.warehouse.name}
                  </option>
                ))}
              </Select>
            </div>
            {warehouseId && <WeatherHistoryPanels key={`${warehouseId}-${result?.id ?? ""}`} warehouseId={warehouseId} />}
          </section>
        )}
      </div>
    </div>
  );
}
