"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { fmt, fmtDay } from "@/lib/format";

const SERIES = ["var(--color-series-1)", "var(--color-series-2)", "var(--color-series-3)"];

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [w, setW] = useState(0);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setW(Math.floor(e.contentRect.width)));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, w] as const;
}

function niceTicks(min: number, max: number, count = 4): number[] {
  if (min === max) {
    const pad = Math.abs(min) * 0.1 || 1;
    min -= pad;
    max += pad;
  }
  const span = max - min;
  const step0 = span / count;
  const mag = Math.pow(10, Math.floor(Math.log10(step0)));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= step0) ?? step0;
  const start = Math.floor(min / step) * step;
  const ticks = [];
  for (let v = start; v <= max + step * 0.5; v += step) ticks.push(+v.toFixed(6));
  return ticks;
}

export function NotEnoughData({ message = "Not enough data available", sub }: { message?: string; sub?: string }) {
  return (
    <div className="grid h-48 place-items-center rounded-lg border border-dashed border-line-strong bg-sunken/60 text-center">
      <div>
        <div className="text-sm font-medium text-ink-2">{message}</div>
        {sub && <div className="mt-1 max-w-sm text-xs text-ink-3">{sub}</div>}
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- line chart

export type LineSeries = { label: string; points: { date: string; value: number; note?: string }[] };

export function LineChart({
  series,
  height = 240,
  valueFormat = (v: number) => fmt(v),
  unit = "",
}: {
  series: LineSeries[];
  height?: number;
  valueFormat?: (v: number) => string;
  unit?: string;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<string | null>(null);
  const [drawn, setDrawn] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => setDrawn(true));
    return () => cancelAnimationFrame(id);
  }, []);

  const m = { top: 12, right: 16, bottom: 26, left: 56 };
  const dates = useMemo(() => [...new Set(series.flatMap((s) => s.points.map((p) => p.date)))].sort(), [series]);
  const values = series.flatMap((s) => s.points.map((p) => p.value));
  const ticks = niceTicks(Math.min(...values), Math.max(...values));
  const [y0, y1] = [ticks[0], ticks[ticks.length - 1]];
  const t = (d: string) => new Date(d + "T00:00:00").getTime();
  const [t0, t1] = [t(dates[0]), t(dates[dates.length - 1])];
  const iw = Math.max(width - m.left - m.right, 10);
  const ih = height - m.top - m.bottom;
  const x = (d: string) => m.left + (t1 === t0 ? iw / 2 : ((t(d) - t0) / (t1 - t0)) * iw);
  const y = (v: number) => m.top + ih - ((v - y0) / (y1 - y0 || 1)) * ih;
  const xLabels = dates.length <= 2 ? dates : [dates[0], dates[Math.floor(dates.length / 2)], dates[dates.length - 1]];

  function onMove(e: React.MouseEvent<SVGSVGElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = e.clientX - rect.left;
    let best = dates[0];
    for (const d of dates) if (Math.abs(x(d) - px) < Math.abs(x(best) - px)) best = d;
    setHover(best);
  }

  const hoverX = hover ? x(hover) : 0;
  const tipLeft = hover ? Math.min(Math.max(hoverX - 90, 0), Math.max(width - 180, 0)) : 0;

  return (
    <div>
      {series.length > 1 && (
        <div className="mb-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
          {series.map((s, i) => (
            <span key={s.label} className="inline-flex items-center gap-1.5">
              <span className="h-0.5 w-4 rounded-full" style={{ background: SERIES[i] }} />
              {s.label}
            </span>
          ))}
        </div>
      )}
      <div ref={ref} className="relative w-full">
        {width > 0 && (
          <svg width={width} height={height} onMouseMove={onMove} onMouseLeave={() => setHover(null)} className="block touch-none select-none">
            {ticks.map((v) => (
              <g key={v}>
                <line x1={m.left} x2={width - m.right} y1={y(v)} y2={y(v)} stroke="var(--color-line)" strokeDasharray={v === y0 ? "" : "3 4"} />
                <text x={m.left - 8} y={y(v)} dy="0.32em" textAnchor="end" className="fill-ink-3 text-[11px] tabular">
                  {valueFormat(v)}
                </text>
              </g>
            ))}
            {xLabels.map((d, i) => (
              <text
                key={d}
                x={x(d)}
                y={height - 6}
                textAnchor={i === 0 && xLabels.length > 1 ? "start" : i === xLabels.length - 1 && xLabels.length > 1 ? "end" : "middle"}
                className="fill-ink-3 text-[11px]"
              >
                {fmtDay(d)}
              </text>
            ))}
            {series.map((s, i) => {
              const pts = [...s.points].sort((a, b) => a.date.localeCompare(b.date));
              const d = pts.map((p, k) => `${k ? "L" : "M"}${x(p.date).toFixed(1)},${y(p.value).toFixed(1)}`).join("");
              return (
                <g key={s.label}>
                  {pts.length > 1 && (
                    <path
                      d={d}
                      fill="none"
                      stroke={SERIES[i]}
                      strokeWidth={2}
                      strokeLinejoin="round"
                      strokeLinecap="round"
                      pathLength={1}
                      strokeDasharray={1}
                      strokeDashoffset={drawn ? 0 : 1}
                      style={{ transition: "stroke-dashoffset 900ms cubic-bezier(0.2,0.7,0.2,1)" }}
                    />
                  )}
                  {(pts.length <= 12 || hover) &&
                    pts
                      .filter((p) => pts.length <= 12 || p.date === hover)
                      .map((p) => (
                        <circle key={p.date} cx={x(p.date)} cy={y(p.value)} r={p.date === hover ? 5 : 3.5} fill={SERIES[i]} stroke="var(--color-surface)" strokeWidth={2} />
                      ))}
                </g>
              );
            })}
            {hover && <line x1={hoverX} x2={hoverX} y1={m.top} y2={m.top + ih} stroke="var(--color-ink-3)" strokeDasharray="2 3" />}
          </svg>
        )}
        {hover && (
          <div
            className="pointer-events-none absolute top-1 z-10 w-[180px] animate-fade-in rounded-lg border border-line bg-surface/95 px-3 py-2 text-xs shadow-lift backdrop-blur"
            style={{ left: tipLeft }}
          >
            <div className="mb-1 font-semibold text-ink">{fmtDay(hover)}</div>
            {series.map((s, i) => {
              const p = s.points.find((q) => q.date === hover);
              return (
                <div key={s.label} className="flex items-center justify-between gap-2">
                  <span className="flex min-w-0 items-center gap-1.5 text-ink-2">
                    <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: SERIES[i] }} />
                    <span className="truncate">{series.length > 1 ? s.label : "Value"}</span>
                  </span>
                  <span className="tabular font-medium text-ink">{p ? `${valueFormat(p.value)}${unit}` : "—"}</span>
                </div>
              );
            })}
            {series.length === 1 && series[0].points.find((q) => q.date === hover)?.note && (
              <div className="mt-1 text-ink-3">{series[0].points.find((q) => q.date === hover)?.note}</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- bars (single series)

export function ColumnChart({
  rows,
  height = 170,
  unit = "",
  color = "var(--color-series-1)",
  valueFormat = (v: number) => fmt(v),
}: {
  rows: { label: string; value: number | null; sub?: string }[];
  height?: number;
  unit?: string;
  color?: string;
  valueFormat?: (v: number) => string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const max = Math.max(...rows.map((r) => r.value ?? 0), 0) || 1;
  const active = hover !== null ? rows[hover] : null;
  const peak = rows.reduce<(typeof rows)[number] | null>((a, r) => (r.value !== null && (!a || r.value > (a.value ?? -1)) ? r : a), null);
  return (
    <div>
      <div className="mb-1 h-5 text-xs text-ink-2" aria-live="polite">
        {active ? (
          <>
            <span className="font-medium text-ink">{active.label}</span> —{" "}
            {active.value === null ? "no data" : `${valueFormat(active.value)}${unit}`}
          </>
        ) : (
          <span className="text-ink-3">
            {peak && peak.value ? `Peak ${valueFormat(peak.value)}${unit} on ${peak.label} · hover a bar` : "Hover a bar for its value"}
          </span>
        )}
      </div>
      <div className="flex items-end gap-1.5 border-b border-line" style={{ height }} onMouseLeave={() => setHover(null)}>
        {rows.map((r, i) => (
          <div
            key={r.label}
            className={`flex h-full flex-1 items-end justify-center rounded-t-md transition-colors ${hover === i ? "bg-black/[0.03]" : ""}`}
            onMouseEnter={() => setHover(i)}
            aria-label={`${r.label}: ${r.value === null ? "no data" : valueFormat(r.value) + unit}`}
          >
            <span
              className="w-full max-w-7 origin-bottom animate-[grow_600ms_cubic-bezier(0.2,0.7,0.2,1)_both] rounded-t-[4px]"
              style={{
                height: r.value ? `${Math.max((r.value / max) * 100, 1.5)}%` : "2px",
                background: r.value ? color : "var(--color-line-strong)",
                animationDelay: `${i * 30}ms`,
              }}
            />
          </div>
        ))}
      </div>
      <div className="mt-1.5 flex gap-1.5 text-center text-[10.5px] text-ink-3">
        {rows.map((r) => (
          <span key={r.label} className="flex-1 truncate">
            {r.sub ?? r.label}
          </span>
        ))}
      </div>
      <style>{`@keyframes grow{from{transform:scaleY(0)}to{transform:scaleY(1)}}`}</style>
    </div>
  );
}

/** Daily min–max temperature as floating range bars on one °C axis. */
export function RangeChart({ rows, height = 170 }: { rows: { label: string; sub: string; lo: number | null; hi: number | null }[]; height?: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const vals = rows.flatMap((r) => [r.lo, r.hi]).filter((v): v is number => v !== null);
  const lo = Math.floor(Math.min(...vals) - 1);
  const hi = Math.ceil(Math.max(...vals) + 1);
  const pos = (v: number) => ((v - lo) / (hi - lo || 1)) * 100;
  const active = hover !== null ? rows[hover] : null;
  return (
    <div>
      <div className="mb-1 h-5 text-xs text-ink-2" aria-live="polite">
        {active ? (
          <>
            <span className="font-medium text-ink">{active.label}</span> — {active.lo ?? "—"}°C to {active.hi ?? "—"}°C
          </>
        ) : (
          <span className="text-ink-3">
            Range {lo}–{hi}°C · hover a day
          </span>
        )}
      </div>
      <div className="flex gap-1.5 border-b border-line" style={{ height }} onMouseLeave={() => setHover(null)}>
        {rows.map((r, i) => (
          <div
            key={r.label}
            className={`relative h-full flex-1 rounded-t-md transition-colors ${hover === i ? "bg-black/[0.03]" : ""}`}
            onMouseEnter={() => setHover(i)}
            aria-label={`${r.label}: ${r.lo}°C to ${r.hi}°C`}
          >
            {r.lo !== null && r.hi !== null && (
              <span
                className="absolute left-1/2 w-full max-w-3 -translate-x-1/2 animate-fade-in rounded-full"
                style={{
                  bottom: `${pos(r.lo)}%`,
                  height: `${Math.max(pos(r.hi) - pos(r.lo), 2)}%`,
                  background: "linear-gradient(to top, var(--color-series-1), var(--color-series-2))",
                  animationDelay: `${i * 30}ms`,
                }}
              />
            )}
          </div>
        ))}
      </div>
      <div className="mt-1.5 flex gap-1.5 text-center text-[10.5px] text-ink-3">
        {rows.map((r) => (
          <span key={r.label} className="flex-1 truncate">
            {r.sub}
          </span>
        ))}
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- existing V1 charts (restyled)

/** Single-series horizontal bars (magnitude). One hue; values in text ink beside each bar. */
export function HBars({ rows, unit = "t" }: { rows: { key: string; label: string; value: number; sub?: string }[]; unit?: string }) {
  const max = Math.max(...rows.map((r) => r.value), 0) || 1;
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => setReady(true));
    return () => cancelAnimationFrame(id);
  }, []);
  return (
    <ul className="space-y-3">
      {rows.map((r) => (
        <li key={r.key} className="grid grid-cols-[minmax(6rem,9rem)_1fr_auto] items-center gap-3 text-sm">
          <span className="truncate text-ink" title={r.label}>
            <span className="font-medium">{r.label}</span>
            {r.sub && <span className="block text-xs text-ink-3">{r.sub}</span>}
          </span>
          <span className="h-2.5 w-full rounded-full bg-black/[0.04]" title={`${r.label}: ${fmt(r.value)} ${unit}`}>
            <span
              className="block h-full rounded-full bg-series-1 transition-[width] duration-700 ease-out"
              style={{ width: ready ? `${Math.max((r.value / max) * 100, r.value > 0 ? 1 : 0)}%` : "0%" }}
            />
          </span>
          <span className="tabular w-20 text-right font-medium text-ink-2">
            {fmt(r.value)} {unit}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** Two-series daily inbound/outbound bars with legend, hover readout and a table view. */
export function DailyMovementChart({ rows }: { rows: { day: string; inbound_tonnes: number; outbound_tonnes: number }[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const [asTable, setAsTable] = useState(false);
  const max = Math.max(...rows.flatMap((r) => [r.inbound_tonnes, r.outbound_tonnes]), 0) || 1;
  const active = hover !== null ? rows[hover] : null;

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-xs text-ink-2">
        <div className="flex items-center gap-4">
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm bg-series-1" /> Inbound (t)
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm bg-series-2" /> Outbound (t)
          </span>
        </div>
        <button className="font-medium text-brand hover:underline" onClick={() => setAsTable((t) => !t)}>
          {asTable ? "Show chart" : "Show table"}
        </button>
      </div>

      {asTable ? (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-ink-3">
              <th className="py-1 text-left font-medium">Day</th>
              <th className="py-1 text-right font-medium">Inbound (t)</th>
              <th className="py-1 text-right font-medium">Outbound (t)</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.day} className="border-t border-line">
                <td className="py-1">{fmtDay(r.day)}</td>
                <td className="tabular py-1 text-right">{fmt(r.inbound_tonnes)}</td>
                <td className="tabular py-1 text-right">{fmt(r.outbound_tonnes)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <>
          <div className="h-5 text-xs text-ink-2" aria-live="polite">
            {active ? (
              `${fmtDay(active.day)} — inbound ${fmt(active.inbound_tonnes)} t · outbound ${fmt(active.outbound_tonnes)} t`
            ) : (
              <span className="text-ink-3">Hover a day for values</span>
            )}
          </div>
          <div className="flex h-40 items-end gap-1 border-b border-line" onMouseLeave={() => setHover(null)}>
            {rows.map((r, i) => (
              <div
                key={r.day}
                className={`flex h-full flex-1 cursor-default items-end justify-center gap-[2px] rounded-t ${hover === i ? "bg-black/[0.03]" : ""}`}
                onMouseEnter={() => setHover(i)}
                aria-label={`${fmtDay(r.day)}: inbound ${fmt(r.inbound_tonnes)} t, outbound ${fmt(r.outbound_tonnes)} t`}
              >
                <span
                  className="w-full max-w-3 origin-bottom animate-[grow_600ms_cubic-bezier(0.2,0.7,0.2,1)_both] rounded-t-[4px] bg-series-1"
                  style={{ height: `${(r.inbound_tonnes / max) * 100}%`, animationDelay: `${i * 25}ms` }}
                />
                <span
                  className="w-full max-w-3 origin-bottom animate-[grow_600ms_cubic-bezier(0.2,0.7,0.2,1)_both] rounded-t-[4px] bg-series-2"
                  style={{ height: `${(r.outbound_tonnes / max) * 100}%`, animationDelay: `${i * 25}ms` }}
                />
              </div>
            ))}
          </div>
          <div className="mt-1 flex justify-between text-[11px] text-ink-3">
            <span>{rows.length ? fmtDay(rows[0].day) : ""}</span>
            <span>{rows.length ? fmtDay(rows[rows.length - 1].day) : ""}</span>
          </div>
          <style>{`@keyframes grow{from{transform:scaleY(0)}to{transform:scaleY(1)}}`}</style>
        </>
      )}
    </div>
  );
}
