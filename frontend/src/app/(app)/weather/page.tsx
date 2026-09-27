"use client";

import { CloudSun, Info, RefreshCw } from "lucide-react";
import { useState } from "react";
import { WeatherCard } from "@/components/data";
import { WeatherHistoryPanels, waitForRun } from "@/components/weather";
import { Button, Card, EmptyState, ErrorState, Notice, PageHeader, Select, Skeleton } from "@/components/ui";
import { api, ApiError, useApi } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { ago } from "@/lib/format";
import type { Run, SourceStatus, WeatherNow } from "@/lib/types";

export default function WeatherPage() {
  const { can } = useAuth();
  const now = useApi<WeatherNow[]>("/weather/current");
  const sources = useApi<SourceStatus[]>("/data/sources");
  const src = sources.data?.find((s) => s.key === "open_meteo_weather");
  const [selected, setSelected] = useState("");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<Run | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const withCoords = (now.data ?? []).filter((w) => w.latitude !== null);
  const warehouseId = selected || withCoords[0]?.warehouse.id || "";

  async function refresh() {
    setRunning(true);
    setErr(null);
    setResult(null);
    try {
      const run = await api<Run>("/data/sources/open_meteo_weather/runs", { method: "POST" });
      const done = await waitForRun(run.id);
      setResult(done);
      now.reload();
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
            Current conditions and completed-day history for each warehouse&apos;s coordinates.
            {src?.last_success_at && <span className="text-ink-3"> Last successful update {ago(src.last_success_at)}.</span>}
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
          location. These are not IMD station readings. Every reading shows its own timestamp; nothing here is streamed live.
        </Notice>

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
            Fetched {result.params.locations as number} location(s): {result.rows_inserted} new, {result.rows_updated} updated, {result.rows_unchanged} unchanged readings.
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
