"use client";

import { useState } from "react";
import { fmt, fmtDay } from "@/lib/format";

/** Single-series horizontal bars (magnitude). One hue; values in text ink beside each bar. */
export function HBars({
  rows,
  unit = "t",
}: {
  rows: { key: string; label: string; value: number; sub?: string }[];
  unit?: string;
}) {
  const max = Math.max(...rows.map((r) => r.value), 0) || 1;
  return (
    <ul className="space-y-2.5">
      {rows.map((r) => (
        <li key={r.key} className="grid grid-cols-[minmax(6rem,9rem)_1fr_auto] items-center gap-3 text-sm">
          <span className="truncate text-ink" title={r.label}>
            {r.label}
            {r.sub && <span className="block text-xs text-ink-3">{r.sub}</span>}
          </span>
          <span className="h-3 w-full" title={`${r.label}: ${fmt(r.value)} ${unit}`}>
            <span
              className="block h-full rounded-r-[4px] bg-series-1"
              style={{ width: `${Math.max((r.value / max) * 100, r.value > 0 ? 1 : 0)}%` }}
            />
          </span>
          <span className="tabular w-20 text-right text-ink-2">
            {fmt(r.value)} {unit}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** Two-series daily inbound/outbound bars with legend, hover readout and a table view. */
export function DailyMovementChart({
  rows,
}: {
  rows: { day: string; inbound_tonnes: number; outbound_tonnes: number }[];
}) {
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
            {active
              ? `${fmtDay(active.day)} — inbound ${fmt(active.inbound_tonnes)} t · outbound ${fmt(active.outbound_tonnes)} t`
              : "Hover a day for values"}
          </div>
          <div className="flex h-40 items-end gap-1 border-b border-line" onMouseLeave={() => setHover(null)}>
            {rows.map((r, i) => (
              <div
                key={r.day}
                className={`flex h-full flex-1 cursor-default items-end justify-center gap-[2px] rounded-t ${hover === i ? "bg-canvas" : ""}`}
                onMouseEnter={() => setHover(i)}
                aria-label={`${fmtDay(r.day)}: inbound ${fmt(r.inbound_tonnes)} t, outbound ${fmt(r.outbound_tonnes)} t`}
              >
                <span
                  className="w-full max-w-3 rounded-t-[4px] bg-series-1"
                  style={{ height: `${(r.inbound_tonnes / max) * 100}%` }}
                />
                <span
                  className="w-full max-w-3 rounded-t-[4px] bg-series-2"
                  style={{ height: `${(r.outbound_tonnes / max) * 100}%` }}
                />
              </div>
            ))}
          </div>
          <div className="mt-1 flex justify-between text-[11px] text-ink-3">
            <span>{rows.length ? fmtDay(rows[0].day) : ""}</span>
            <span>{rows.length ? fmtDay(rows[rows.length - 1].day) : ""}</span>
          </div>
        </>
      )}
    </div>
  );
}
