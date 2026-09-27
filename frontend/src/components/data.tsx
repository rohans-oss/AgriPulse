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
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { Badge, FreshnessBadge, SourceTag } from "./ui";
import { ago, fmtDateOnly, fmtINR, fmtTimeIST } from "@/lib/format";
import type { LatestPrice, Run, SourceStatus, WeatherNow } from "@/lib/types";

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
          {p.source ? <SourceTag source={p.source} /> : <span className="text-xs text-ink-3">Awaiting first fetch</span>}
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
            <dl className="mt-3 grid grid-cols-3 gap-1.5 text-xs">
              <Stat icon={Droplets} label="Humidity" value={r.humidity_pct !== null ? `${r.humidity_pct}%` : "—"} />
              <Stat icon={Umbrella} label="Rain" value={r.precipitation_mm !== null ? `${r.precipitation_mm} mm` : "—"} />
              <Stat icon={Wind} label="Wind" value={r.wind_kmh !== null ? `${r.wind_kmh} km/h` : "—"} />
            </dl>
          )}
          <div className="mt-auto border-t border-line pt-2.5 text-[11px] text-ink-3" style={{ marginTop: 12 }}>
            Reading at {fmtTimeIST(r.observed_at)} · fetched {ago(r.fetched_at)}
            {w.source && (
              <div className="mt-1">
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

export function SourceHealthRow({ s }: { s: SourceStatus }) {
  const upload = s.origin === "USER_UPLOAD";
  const health = !s.configured
    ? { tone: "neutral" as const, text: "Not configured" }
    : upload
      ? { tone: "neutral" as const, text: s.last_success_at ? "Uploaded" : "No uploads yet" }
    : s.last_run?.status === "FAILED"
      ? { tone: "bad" as const, text: "Last fetch failed" }
      : s.last_success_at || s.record_count
        ? { tone: "good" as const, text: "Working" }
        : { tone: "neutral" as const, text: "Not fetched yet" };
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
        <Badge tone={health.tone}>{health.text}</Badge>
        {!upload && s.freshness && s.freshness.label !== "UNAVAILABLE" && <FreshnessBadge freshness={s.freshness} />}
      </div>
    </Link>
  );
}
