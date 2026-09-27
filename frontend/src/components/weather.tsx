"use client";

import { CloudRain, Thermometer } from "lucide-react";
import { ColumnChart, NotEnoughData, RangeChart } from "./charts";
import { Card, ErrorState, FreshnessBadge, SourceTag } from "./ui";
import { api, useApi } from "@/lib/api";
import { fmtDay } from "@/lib/format";
import type { Run, WeatherHistory } from "@/lib/types";

/** Poll an ingestion run until it leaves RUNNING (or ~90 s pass). */
export async function waitForRun(id: string, onTick?: (r: Run) => void): Promise<Run> {
  const started = Date.now();
  for (;;) {
    const run = await api<Run>(`/data/runs/${id}`);
    onTick?.(run);
    if (run.status !== "RUNNING" || Date.now() - started > 90_000) return run;
    await new Promise((r) => setTimeout(r, 1200));
  }
}

export function WeatherHistoryPanels({ warehouseId, days = 14 }: { warehouseId: string; days?: number }) {
  const { data, error, loading } = useApi<WeatherHistory>(`/weather/daily?warehouse_id=${warehouseId}&days=${days}`);
  if (loading && !data)
    return (
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="skeleton h-64 rounded-xl" />
        <div className="skeleton h-64 rounded-xl" />
      </div>
    );
  if (error) return <ErrorState title="Unable to load weather history" message={error.message} />;
  if (!data) return null;
  const rows = data.days;
  const enough = rows.length >= 2;
  const footer = data.source ? (
    <span className="flex flex-wrap items-center gap-2">
      <SourceTag source={data.source} /> <span>· completed days only; today is never shown until it has ended</span>
    </span>
  ) : undefined;
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card title="Daily rainfall" subtitle={`Last ${days} days · mm per day`} icon={CloudRain} action={<FreshnessBadge freshness={data.freshness} />} footer={footer}>
        {enough ? (
          <ColumnChart unit=" mm" rows={rows.map((d) => ({ label: fmtDay(d.date), sub: fmtDay(d.date).split(" ")[0], value: d.precipitation_mm }))} />
        ) : (
          <NotEnoughData sub="Daily values appear after weather has been fetched for this warehouse." />
        )}
      </Card>
      <Card title="Daily temperature range" subtitle={`Last ${days} days · °C min to max`} icon={Thermometer} action={<FreshnessBadge freshness={data.freshness} />} footer={footer}>
        {enough ? (
          <RangeChart rows={rows.map((d) => ({ label: fmtDay(d.date), sub: fmtDay(d.date).split(" ")[0], lo: d.temp_min_c, hi: d.temp_max_c }))} />
        ) : (
          <NotEnoughData sub="Daily values appear after weather has been fetched for this warehouse." />
        )}
      </Card>
    </div>
  );
}
