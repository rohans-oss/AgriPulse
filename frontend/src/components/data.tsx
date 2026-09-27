"use client";

import {
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  CheckCircle2,
  Cloud,
  CloudDrizzle,
  CloudFog,
  CloudLightning,
  CloudRain,
  CloudSun,
  Droplets,
  Loader2,
  Snowflake,
  Sun,
  Umbrella,
  Wind,
  XCircle,
  AlertTriangle,
  CircleDashed,
  Gauge,
  Thermometer,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Badge, DataClassBadge, FreshnessBadge, Modal, SourceTag } from "./ui";
import { api, ApiError } from "@/lib/api";
import { ago, fmtDateOnly, fmtINR, fmtIST, fmtTimeIST } from "@/lib/format";
import type { DataEnvironment, ForecastDay, Indicator, LatestPrice, PriceDetail, Run, SourceStatus, WeatherNow } from "@/lib/types";

// --------------------------------------------------------------------------- market

export function PriceCard({ p, style }: { p: LatestPrice; style?: React.CSSProperties }) {
  const up = p.change_pct !== null && p.change_pct > 0;
  const down = p.change_pct !== null && p.change_pct < 0;
  const Trend = up ? ArrowUpRight : down ? ArrowDownRight : ArrowRight;
  return (
    <Link
      href={`/market?commodity=${encodeURIComponent(p.commodity)}`}
      className="group flex flex-col rounded-xl border border-line bg-surface p-4 shadow-card transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lift"
      style={style}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-[15px] font-semibold text-ink">{p.commodity}</div>
          <div className="text-xs text-ink-3">
            {p.latest_date ? `${p.markets_reporting} market${p.markets_reporting === 1 ? "" : "s"} · ${fmtDateOnly(p.latest_date)}` : "No reports yet"}
          </div>
        </div>
        <FreshnessBadge freshness={p.freshness} />
      </div>
      {p.avg_modal !== null ? (
        <>
          <div className="mt-3 flex items-baseline gap-1.5">
            <span className="tabular text-2xl font-semibold tracking-tight">{fmtINR(p.avg_modal)}</span>
            <span className="text-xs text-ink-3">/ quintal</span>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
            {p.change_pct !== null ? (
              <span className="inline-flex items-center gap-0.5 font-medium text-ink-2">
                <Trend className="h-3.5 w-3.5" />
                {p.change_abs !== null && `${p.change_abs > 0 ? "+" : ""}${fmtINR(p.change_abs)} · `}
                {p.change_pct > 0 ? "+" : ""}
                {p.change_pct}% vs {p.previous_date ? fmtDateOnly(p.previous_date) : "previous"}
              </span>
            ) : (
              <span className="text-ink-3">No earlier report to compare</span>
            )}
            {p.min_modal !== null && p.max_modal !== null && p.markets_reporting > 1 && (
              <span className="text-ink-3">
                Range {fmtINR(p.min_modal)}–{fmtINR(p.max_modal)}
              </span>
            )}
          </div>
        </>
      ) : (
        <p className="mt-3 text-sm text-ink-3">{p.freshness.detail}</p>
      )}
      <div className="mt-auto pt-3">
        <div className="border-t border-line pt-2.5">
          {p.source ? <SourceTag source={p.source} /> : <DataClassBadge value={p.data_class} label="No verified price" />}
        </div>
      </div>
    </Link>
  );
}

// --------------------------------------------------------------------------- weather

export function weatherIcon(code: number | null | undefined): LucideIcon {
  if (code === null || code === undefined) return Cloud;
  if (code <= 1) return Sun;
  if (code === 2) return CloudSun;
  if (code === 3) return Cloud;
  if (code === 45 || code === 48) return CloudFog;
  if (code >= 51 && code <= 57) return CloudDrizzle;
  if ((code >= 61 && code <= 67) || (code >= 80 && code <= 82)) return CloudRain;
  if ((code >= 71 && code <= 77) || code === 85 || code === 86) return Snowflake;
  if (code >= 95) return CloudLightning;
  return Cloud;
}

export function WeatherCard({ w, style, compact = false }: { w: WeatherNow; style?: React.CSSProperties; compact?: boolean }) {
  const r = w.reading;
  const Icon = weatherIcon(r?.weather_code);
  return (
    <div className="flex min-w-0 flex-col rounded-xl border border-line bg-surface p-4 shadow-card" style={style}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-[15px] font-semibold">{w.warehouse.name}</div>
          <div className="text-xs text-ink-3">{w.region.name}</div>
        </div>
        <FreshnessBadge freshness={w.freshness} />
      </div>
      {r ? (
        <>
          <div className="mt-3 flex items-center gap-3">
            <span className="grid h-12 w-12 place-items-center rounded-xl bg-gradient-to-br from-sky-50 to-amber-50 text-[#b27a17] ring-1 ring-inset ring-line">
              <Icon className="h-6 w-6" strokeWidth={1.7} />
            </span>
            <div>
              <div className="tabular text-2xl font-semibold tracking-tight">{r.temperature_c !== null ? `${r.temperature_c}°C` : "—"}</div>
              <div className="text-xs text-ink-2">{r.condition ?? "Condition unavailable"}</div>
            </div>
          </div>
          {!compact && (
            <dl className="mt-3 grid grid-cols-2 gap-1.5 text-xs sm:grid-cols-4">
              <Stat icon={Droplets} label="Humidity" value={r.humidity_pct !== null ? `${r.humidity_pct}%` : "—"} />
              <Stat icon={Umbrella} label="Rain" value={r.precipitation_mm !== null ? `${r.precipitation_mm} mm` : "—"} />
              <Stat icon={Wind} label="Wind" value={r.wind_kmh !== null ? `${r.wind_kmh} km/h` : "—"} />
              <Stat icon={Gauge} label="Gusts" value={r.wind_gust_kmh !== null ? `${r.wind_gust_kmh} km/h` : "—"} />
            </dl>
          )}
          {w.stale && (
            <p className="mt-2 flex items-start gap-1.5 text-xs text-warn">
              <AlertTriangle className="mt-px h-3.5 w-3.5 shrink-0" /> This reading is old and may not reflect current conditions.
            </p>
          )}
          {!compact && <IndicatorList items={w.indicators} note={w.indicators_note} />}
          {!compact && w.forecast.length > 0 && <ForecastStrip days={w.forecast} />}
          <div className="mt-auto border-t border-line pt-2.5 text-[11px] text-ink-3" style={{ marginTop: 12 }}>
            Observed {fmtTimeIST(r.observed_at)} · fetched {ago(r.fetched_at)}
            {r.run_id && (
              <>
                {" · "}
                <Link href={`/data/runs/${r.run_id}`} className="underline decoration-line-strong underline-offset-2 hover:text-ink">
                  run
                </Link>
              </>
            )}
            {w.source && (
              <div className="mt-1 flex flex-wrap items-center gap-1.5">
                <DataClassBadge value={w.data_class} />
                <SourceTag source={w.source} />
              </div>
            )}
          </div>
        </>
      ) : (
        <p className="mt-3 text-sm text-ink-3">{w.freshness.detail}</p>
      )}
    </div>
  );
}

function Stat({ icon: Icon, label, value }: { icon: LucideIcon; label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-lg bg-sunken px-2 py-1.5">
      <dt className="flex items-center gap-1 truncate text-ink-3">
        <Icon className="h-3 w-3" /> {label}
      </dt>
      <dd className="tabular mt-0.5 truncate font-semibold text-ink">{value}</dd>
    </div>
  );
}

// --------------------------------------------------------------------------- runs & sources

const RUN: Record<Run["status"], { tone: "good" | "warn" | "bad" | "info"; icon: LucideIcon; text: string }> = {
  SUCCESS: { tone: "good", icon: CheckCircle2, text: "Succeeded" },
  PARTIAL: { tone: "warn", icon: AlertTriangle, text: "Partial" },
  FAILED: { tone: "bad", icon: XCircle, text: "Failed" },
  RUNNING: { tone: "info", icon: Loader2, text: "Running" },
};

export function RunStatusBadge({ status }: { status: Run["status"] }) {
  const s = RUN[status];
  return (
    <span className={status === "RUNNING" ? "[&_svg]:animate-spin" : ""}>
      <Badge tone={s.tone} icon={s.icon}>
        {s.text}
      </Badge>
    </span>
  );
}

const STATUS: Record<SourceStatus["status"], { tone: "good" | "warn" | "bad" | "neutral"; text: string; icon: LucideIcon }> = {
  CONNECTED: { tone: "good", text: "Connected", icon: CheckCircle2 },
  DEGRADED: { tone: "warn", text: "Degraded", icon: AlertTriangle },
  FAILING: { tone: "bad", text: "Failing", icon: XCircle },
  NOT_CONFIGURED: { tone: "neutral", text: "Not configured", icon: CircleDashed },
  NOT_CONNECTED: { tone: "neutral", text: "Waiting for first fetch", icon: CircleDashed },
  UPLOAD_ONLY: { tone: "neutral", text: "Upload only", icon: CircleDashed },
  DISABLED: { tone: "neutral", text: "Disabled", icon: CircleDashed },
};

/** Connection health, from the backend's ingestion history — never assumed. */
export function SourceStatusBadge({ status, detail }: { status: SourceStatus["status"]; detail?: string }) {
  const s = STATUS[status] ?? STATUS.NOT_CONNECTED;
  return (
    <span title={detail} className="inline-flex">
      <Badge tone={s.tone} icon={s.icon}>
        {s.text}
      </Badge>
    </span>
  );
}

export function SourceHealthRow({ s }: { s: SourceStatus }) {
  const upload = s.origin === "USER_UPLOAD";
  const health = upload
    ? { tone: "neutral" as const, text: s.last_success_at ? "Uploaded" : "No uploads yet" }
    : null;
  return (
    <Link href="/data" className="flex items-center justify-between gap-3 rounded-lg px-2 py-2.5 transition-colors hover:bg-sunken">
      <div className="min-w-0">
        <div className="truncate text-sm font-medium">{s.name}</div>
        <div className="truncate text-xs text-ink-3">
          {s.last_success_at
            ? `${upload ? "Last upload" : "Last successful update"} ${ago(s.last_success_at)}`
            : s.config_message ?? (upload ? "Upload a CSV from the Import page" : "No successful update yet")}
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        {health ? <Badge tone={health.tone}>{health.text}</Badge> : <SourceStatusBadge status={s.status} detail={s.status_detail} />}
        {!upload && s.freshness && s.freshness.label !== "UNAVAILABLE" && <FreshnessBadge freshness={s.freshness} />}
      </div>
    </Link>
  );
}

// --------------------------------------------------------------------------- V3: indicators & forecast

const LEVEL = { WARNING: "border-red-200 bg-red-50/70 text-bad", WATCH: "border-amber-200 bg-amber-50/70 text-warn" } as const;
const IND_ICON: Record<Indicator["key"], LucideIcon> = {
  RAIN: CloudRain,
  HEAT: Thermometer,
  WIND: Wind,
  STORM: CloudLightning,
  HUMIDITY: Droplets,
};

/** Transparent threshold rules. Each one says whether it used an observation or a forecast. */
export function IndicatorList({ items, note }: { items: Indicator[]; note?: string | null }) {
  if (!items.length) {
    return (
      <p className="mt-3 flex items-center gap-1.5 rounded-lg bg-sunken px-2.5 py-2 text-xs text-ink-3">
        <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-good" />
        No weather disruption indicators{note ? ` · ${note}` : ""}
      </p>
    );
  }
  return (
    <ul className="mt-3 space-y-1.5">
      {items.map((i, n) => {
        const Icon = IND_ICON[i.key] ?? AlertTriangle;
        return (
          <li key={n} className={`rounded-lg border px-2.5 py-2 text-xs ${LEVEL[i.level]}`} title={`Rule: ${i.rule}`}>
            <div className="flex flex-wrap items-center gap-1.5 font-semibold">
              <Icon className="h-3.5 w-3.5 shrink-0" />
              <span className="min-w-0">{i.title}</span>
              <span className="ml-auto">
                <DataClassBadge value={i.data_class} label={i.basis === "FORECAST" ? "Forecast" : "Observed"} />
              </span>
            </div>
            <p className="mt-0.5 text-ink-2">{i.message}</p>
          </li>
        );
      })}
    </ul>
  );
}

export function ForecastStrip({ days }: { days: ForecastDay[] }) {
  return (
    <div className="mt-3">
      <div className="mb-1.5 flex items-center justify-between gap-2 text-[11px] text-ink-3">
        <span className="font-semibold uppercase tracking-[0.06em]">Provider forecast</span>
        <DataClassBadge value="MODEL_PREDICTION" label="Model prediction" />
      </div>
      <div className="grid grid-cols-3 gap-1.5">
        {days.map((d) => {
          const Icon = weatherIcon(d.weather_code);
          return (
            <div key={d.date} className="min-w-0 rounded-lg border border-dashed border-line-strong/70 px-2 py-1.5 text-xs" title={d.condition ?? undefined}>
              <div className="flex items-center justify-between gap-1 text-ink-3">
                <span className="truncate">{new Date(d.date + "T00:00:00").toLocaleDateString("en-IN", { weekday: "short", day: "numeric" })}</span>
                <Icon className="h-3.5 w-3.5 shrink-0" />
              </div>
              <div className="tabular mt-0.5 truncate font-semibold text-ink">
                {d.temp_max_c !== null ? `${Math.round(d.temp_max_c)}°` : "—"}
                <span className="font-normal text-ink-3"> / {d.temp_min_c !== null ? `${Math.round(d.temp_min_c)}°` : "—"}</span>
              </div>
              <div className="tabular truncate text-ink-3">
                {d.precipitation_mm !== null ? `${d.precipitation_mm} mm` : "—"}
                {d.precipitation_probability !== null && ` · ${Math.round(d.precipitation_probability)}%`}
              </div>
            </div>
          );
        })}
      </div>
      <p className="mt-1 text-[11px] text-ink-3">Issued {ago(days[0].issued_at)} by the provider. Not an observation.</p>
    </div>
  );
}

// --------------------------------------------------------------------------- V3: data environment

const ENV_DOT = { ok: "bg-good", warn: "bg-warn", bad: "bg-bad", none: "bg-line-strong" } as const;

/** What every dashboard section is built on. */
export function EnvironmentPanel({ env }: { env: DataEnvironment }) {
  return (
    <div>
      <ul className="divide-y divide-line">
        {env.items.map((i) => (
          <li key={i.key} className="flex flex-col gap-1 py-2.5 sm:flex-row sm:items-center sm:gap-3">
            <div className="flex min-w-0 items-center gap-2 sm:w-44 sm:shrink-0">
              <span className={`h-2 w-2 shrink-0 rounded-full ${ENV_DOT[i.status]}`} aria-hidden />
              <span className="truncate text-sm font-medium">{i.label}</span>
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-1.5">
                <DataClassBadge value={i.data_class} />
                <span className="text-sm text-ink-2">{i.summary}</span>
              </div>
              <p className="mt-0.5 text-xs text-ink-3">{i.detail}</p>
            </div>
          </li>
        ))}
      </ul>
      <p className="mt-2 border-t border-line pt-2.5 text-xs text-ink-3">
        Last successful sync: {env.last_successful_sync ? `${fmtIST(env.last_successful_sync)} (${ago(env.last_successful_sync)})` : "none yet"}
      </p>
    </div>
  );
}

// --------------------------------------------------------------------------- V3: price provenance

export function PriceDetailModal({ id, onClose }: { id: string | null; onClose: () => void }) {
  const [data, setData] = useState<PriceDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setData(null);
    setErr(null);
    api<PriceDetail>(`/market/prices/${id}`)
      .then((d) => !cancelled && setData(d))
      .catch((e) => !cancelled && setErr(e instanceof ApiError ? e.message : String(e)));
    return () => {
      cancelled = true;
    };
  }, [id]);
  return (
    <Modal open={Boolean(id)} onClose={onClose} title="Where this price comes from" description={data ? `${data.commodity} · ${data.market}` : undefined} wide>
      {err ? (
        <p className="text-sm text-bad">{err}</p>
      ) : !data ? (
        <p className="text-sm text-ink-3">Loading…</p>
      ) : (
        <div className="space-y-4 text-sm">
          <div className="flex flex-wrap items-center gap-1.5">
            <DataClassBadge value={data.data_class} />
            <SourceTag source={data.source} />
            {data.validation_status === "ACCEPTED_WITH_WARNING" && (
              <Badge tone="warn" icon={AlertTriangle}>
                Accepted with warning
              </Badge>
            )}
          </div>
          {data.validation_notes && <p className="rounded-lg border border-amber-200 bg-amber-50/70 px-3 py-2 text-xs text-warn">{data.validation_notes}</p>}
          <dl className="grid grid-cols-1 gap-x-6 gap-y-2.5 sm:grid-cols-2">
            <Prov label="Modal price">{fmtINR(data.modal_price)} / quintal</Prov>
            <Prov label="Range">{data.min_price !== null && data.max_price !== null ? `${fmtINR(data.min_price)} – ${fmtINR(data.max_price)}` : "—"}</Prov>
            <Prov label="Market">{[data.market, data.district, data.state].filter(Boolean).join(", ")}</Prov>
            <Prov label="Variety / grade">{[data.variety, data.grade].filter(Boolean).join(" · ") || "—"}</Prov>
            <Prov label="Reported for">{fmtDateOnly(data.arrival_date)}</Prov>
            <Prov label="Fetched">{fmtIST(data.fetched_at)}</Prov>
            <Prov label="Publisher">{data.publisher}</Prov>
            <Prov label="Dataset">{data.source_dataset ?? "—"}</Prov>
            <Prov label="Endpoint" mono>{data.source_endpoint ?? "—"}</Prov>
            <Prov label="Source record ID" mono>{data.source_record_id ?? "—"}</Prov>
            <Prov label="Ingestion run">
              {data.run ? (
                <Link href={`/data/runs/${data.run.id}`} className="text-brand hover:underline">
                  {fmtIST(data.run.started_at)} · {data.run.trigger.toLowerCase()}
                </Link>
              ) : (
                "—"
              )}
            </Prov>
          </dl>
          {data.raw_reference && (
            <details className="rounded-lg border border-line bg-sunken">
              <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-ink-2">Original record as received</summary>
              <pre className="max-h-64 overflow-auto px-3 pb-3 font-mono text-[11px] leading-5 text-ink-2">{JSON.stringify(data.raw_reference, null, 2)}</pre>
            </details>
          )}
        </div>
      )}
    </Modal>
  );
}

function Prov({ label, children, mono = false }: { label: string; children: React.ReactNode; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-3">{label}</dt>
      <dd className={`mt-0.5 break-words ${mono ? "font-mono text-xs" : ""}`}>{children}</dd>
    </div>
  );
}

