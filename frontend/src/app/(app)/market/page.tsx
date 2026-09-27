"use client";

import { AlertTriangle, BarChart3, ChevronLeft, ChevronRight, FileSearch, Info, LineChart as LineIcon, Table2, TrendingUp } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { HBars, LineChart, NotEnoughData } from "@/components/charts";
import { PriceCard, PriceDetailModal } from "@/components/data";
import {
  Badge,
  Button,
  Card,
  DataClassBadge,
  EmptyState,
  ErrorState,
  FreshnessBadge,
  Input,
  Loading,
  Notice,
  PageHeader,
  Select,
  Skeleton,
  SourceTag,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { qs, useApi } from "@/lib/api";
import { ago, fmtDateOnly, fmtINR } from "@/lib/format";
import type { Compare, LatestPrice, MarketFilters, Price, SourceStatus, Trend } from "@/lib/types";

type PricePageT = { total: number; rows: Price[] };

const RANGES = [
  [30, "30 days"],
  [90, "90 days"],
  [180, "6 months"],
  [365, "1 year"],
] as const;
const PAGE = 25;

function MarketInner() {
  const params = useSearchParams();
  const latest = useApi<LatestPrice[]>("/market/latest");
  const filters = useApi<MarketFilters>("/market/filters");
  const sources = useApi<SourceStatus[]>("/data/sources");
  const official = sources.data?.find((s) => s.key === "ogd_mandi_prices");

  const withData = latest.data?.filter((l) => l.avg_modal !== null) ?? [];
  const defaultCommodity = params.get("commodity") || withData[0]?.commodity || filters.data?.commodities[0]?.name || "";
  const [commodity, setCommodity] = useState("");
  const trendCommodity = commodity || defaultCommodity;
  const [days, setDays] = useState<number>(90);
  const [markets, setMarkets] = useState<string[]>([]);

  const trend = useApi<Trend>(
    trendCommodity
      ? `/market/trend?commodity=${encodeURIComponent(trendCommodity)}&days=${days}${markets.map((m) => `&market=${encodeURIComponent(m)}`).join("")}`
      : null,
  );

  // table filters
  const [f, setF] = useState({
    commodity: params.get("commodity") ?? "",
    state: "",
    district: "",
    market: "",
    source: "",
    validation: "",
    date_from: "",
    date_to: "",
  });
  const [detailId, setDetailId] = useState<string | null>(null);
  const [by, setBy] = useState<"market" | "district" | "state">("market");
  const [cmpDays, setCmpDays] = useState(7);
  const cmp = useApi<Compare>(trendCommodity ? `/market/compare${qs({ commodity: trendCommodity, by, days: String(cmpDays) })}` : null);
  const [offset, setOffset] = useState(0);
  const table = useApi<PricePageT>(`/market/prices${qs({ ...f, limit: String(PAGE), offset: String(offset) })}`);
  const setFilter = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    setOffset(0);
    setF((x) => ({ ...x, [k]: e.target.value }));
  };

  const points = trend.data?.series.reduce((n, s) => n + s.points.length, 0) ?? 0;

  return (
    <div className="space-y-6">
      <PageHeader
        icon={TrendingUp}
        eyebrow="Market intelligence"
        title="Market prices"
        description="Wholesale mandi prices in ₹ per quintal — official AGMARKNET data via data.gov.in, plus price files your team uploaded."
      />

      {official && !official.configured && (
        <Notice tone="warn" icon={Info}>
          <strong className="font-medium text-ink">Official mandi prices are not connected yet.</strong> Add a free data.gov.in API key as{" "}
          <code className="rounded bg-black/5 px-1 font-mono text-xs">DATA_GOV_IN_API_KEY</code> in the backend settings, then fetch from{" "}
          <Link href="/data" className="font-medium text-brand hover:underline">
            Data sources
          </Link>
          . Until then only uploaded files appear here — no prices are ever estimated or invented.
        </Notice>
      )}
      {official?.configured && official.status === "FAILING" && (
        <ErrorState
          title="Latest mandi price fetch failed"
          message={official.last_failure_message ?? "The external source did not respond."}
          footnote={
            official.last_success_at
              ? `Last successful update ${ago(official.last_success_at)}. Prices below are from then and are marked “Update failed”.`
              : "No successful update yet — no official prices are shown, and none are estimated."
          }
        />
      )}

      {/* Latest */}
      <section>
        <div className="mb-3">
          <h2 className="text-[15px] font-semibold tracking-tight">Your commodities today</h2>
          <p className="text-xs text-ink-3">Average modal price across markets on the latest reported date</p>
        </div>
        {latest.loading && !latest.data ? (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-44 rounded-xl" />
            ))}
          </div>
        ) : latest.error ? (
          <ErrorState title="Unable to load market data" message={latest.error.message} onRetry={latest.reload} />
        ) : !latest.data?.length ? (
          <Card>
            <EmptyState icon={TrendingUp} title="No commodities in your catalog" body="Add commodities to track their mandi prices." />
          </Card>
        ) : (
          <div className="stagger grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {latest.data.map((p, i) => (
              <PriceCard key={`${p.commodity}-${p.source?.key ?? "none"}`} p={p} style={{ "--i": i } as React.CSSProperties} />
            ))}
          </div>
        )}
      </section>

      {/* Trend */}
      <Card
        title="Price trend"
        subtitle="Daily average modal price, ₹ per quintal. Only dates with reports are plotted."
        icon={LineIcon}
        action={trend.data && <FreshnessBadge freshness={trend.data.freshness} />}
        footer={
          trend.data?.source ? (
            <span className="flex flex-wrap items-center gap-2">
              <SourceTag source={trend.data.source} /> · {points} data point{points === 1 ? "" : "s"}
            </span>
          ) : undefined
        }
      >
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <Select className="w-56" value={trendCommodity} onChange={(e) => { setCommodity(e.target.value); setMarkets([]); }} aria-label="Commodity">
            {!filters.data?.commodities.length && <option value="">No commodities with data</option>}
            {filters.data?.commodities.map((c) => (
              <option key={c.name} value={c.name}>
                {c.name} ({c.rows})
              </option>
            ))}
          </Select>
          <Select
            className="w-56"
            value=""
            onChange={(e) => e.target.value && setMarkets((m) => (m.includes(e.target.value) || m.length >= 3 ? m : [...m, e.target.value]))}
            aria-label="Compare markets"
          >
            <option value="">{markets.length >= 3 ? "Up to 3 markets" : "Compare a market…"}</option>
            {filters.data?.markets.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </Select>
          {markets.map((m) => (
            <button key={m} onClick={() => setMarkets((x) => x.filter((y) => y !== m))} className="rounded-full border border-line bg-sunken px-2.5 py-1 text-xs hover:border-line-strong">
              {m} ✕
            </button>
          ))}
          <div className="ml-auto inline-flex rounded-lg border border-line bg-sunken p-0.5">
            {RANGES.map(([d, label]) => (
              <button
                key={d}
                onClick={() => setDays(d)}
                className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${days === d ? "bg-surface text-ink shadow-card" : "text-ink-3 hover:text-ink"}`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        {!trendCommodity ? (
          <NotEnoughData message="No market data available" sub="Fetch official prices or upload a price file to see trends." />
        ) : trend.loading && !trend.data ? (
          <Skeleton className="h-60" />
        ) : trend.error ? (
          <ErrorState title="Unable to load price trend" message={trend.error.message} />
        ) : !trend.data || trend.data.series.every((s) => s.points.length < 2) ? (
          <NotEnoughData
            sub={
              trend.data?.series.some((s) => s.points.length === 1)
                ? "Only one reported date so far. A trend appears once there are reports on two or more dates."
                : "No reports for this selection in the chosen period."
            }
          />
        ) : (
          <div key={`${trendCommodity}-${days}-${markets.join()}`} className="animate-fade-in">
            <LineChart
              series={trend.data.series.map((s) => ({ label: s.label, points: s.points.map((p) => ({ date: p.date, value: p.modal, note: `${p.markets} market(s) reporting` })) }))}
              valueFormat={(v) => fmtINR(v)}
            />
          </div>
        )}
      </Card>

      {/* Comparison */}
      <Card
        title={trendCommodity ? `${trendCommodity}: compare the latest report` : "Compare markets"}
        subtitle={`Latest reported modal price per ${by} within the last ${cmpDays} days of data · ₹ per quintal · nothing is interpolated`}
        icon={BarChart3}
        action={cmp.data && <FreshnessBadge freshness={cmp.data.freshness} />}
        footer={cmp.data?.source ? <SourceTag source={cmp.data.source} /> : undefined}
      >
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <div className="inline-flex rounded-lg border border-line bg-sunken p-0.5" role="group" aria-label="Compare by">
            {(["market", "district", "state"] as const).map((b) => (
              <button
                key={b}
                onClick={() => setBy(b)}
                aria-pressed={by === b}
                className={`rounded-md px-2.5 py-1 text-xs font-medium capitalize transition-colors ${by === b ? "bg-surface text-ink shadow-card" : "text-ink-3 hover:text-ink"}`}
              >
                By {b}
              </button>
            ))}
          </div>
          <div className="inline-flex rounded-lg border border-line bg-sunken p-0.5" role="group" aria-label="Window">
            {[7, 30].map((d) => (
              <button
                key={d}
                onClick={() => setCmpDays(d)}
                aria-pressed={cmpDays === d}
                className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${cmpDays === d ? "bg-surface text-ink shadow-card" : "text-ink-3 hover:text-ink"}`}
              >
                {d} days
              </button>
            ))}
          </div>
        </div>
        {!trendCommodity ? (
          <NotEnoughData message="No market data available" sub="Fetch official prices or upload a price file to compare markets." />
        ) : cmp.loading && !cmp.data ? (
          <Skeleton className="h-32" />
        ) : cmp.error ? (
          <ErrorState title="Unable to load comparison" message={cmp.error.message} />
        ) : !cmp.data?.rows.length ? (
          <NotEnoughData sub="No reports for this commodity in the chosen window." />
        ) : cmp.data.rows.length < 2 ? (
          <NotEnoughData
            message={`Only one ${by} reporting`}
            sub={`${cmp.data.rows[0].name}: ${fmtINR(cmp.data.rows[0].modal)} on ${fmtDateOnly(cmp.data.rows[0].latest_date)}. A comparison needs at least two.`}
          />
        ) : (
          <HBars
            key={`${trendCommodity}-${by}-${cmpDays}`}
            format={(n) => fmtINR(n)}
            rows={cmp.data.rows.slice(0, 12).map((r) => ({
              key: r.name,
              label: r.name,
              sub: `${fmtDateOnly(r.latest_date)} · ${r.reports} report${r.reports === 1 ? "" : "s"}`,
              value: r.modal,
            }))}
          />
        )}
        {cmp.data && cmp.data.rows.length > 12 && <p className="mt-3 text-xs text-ink-3">Showing the 12 highest of {cmp.data.rows.length}.</p>}
      </Card>

      {/* Table */}
      <Card title="Market reports" subtitle="Every stored report, newest first" icon={Table2} flush>
        <div className="grid gap-2 border-b border-line p-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-8">
          <Select value={f.commodity} onChange={setFilter("commodity")} aria-label="Commodity">
            <option value="">All commodities</option>
            {filters.data?.commodities.map((c) => (
              <option key={c.name} value={c.name}>
                {c.name}
              </option>
            ))}
          </Select>
          <Select value={f.state} onChange={setFilter("state")} aria-label="State">
            <option value="">All states</option>
            {filters.data?.states.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </Select>
          <Select value={f.district} onChange={setFilter("district")} aria-label="District">
            <option value="">All districts</option>
            {filters.data?.districts.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </Select>
          <Select value={f.market} onChange={setFilter("market")} aria-label="Market">
            <option value="">All markets</option>
            {filters.data?.markets.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </Select>
          <Select value={f.source} onChange={setFilter("source")} aria-label="Source">
            <option value="">All sources</option>
            {filters.data?.sources.map((s) => (
              <option key={s.key} value={s.key}>
                {s.name}
              </option>
            ))}
          </Select>
          <Select value={f.validation} onChange={setFilter("validation")} aria-label="Validation">
            <option value="">All validation</option>
            <option value="ACCEPTED">Accepted</option>
            <option value="ACCEPTED_WITH_WARNING">Accepted with warning</option>
          </Select>
          <Input type="date" value={f.date_from} onChange={setFilter("date_from")} aria-label="From date" />
          <Input type="date" value={f.date_to} onChange={setFilter("date_to")} aria-label="To date" />
        </div>
        {table.loading && !table.data ? (
          <div className="px-5">
            <Loading />
          </div>
        ) : table.error ? (
          <div className="p-4">
            <ErrorState title="Unable to load market data" message={table.error.message} onRetry={table.reload} />
          </div>
        ) : !table.data?.rows.length ? (
          <EmptyState
            art
            icon={TrendingUp}
            title="No market data available"
            body="No source has provided observations for these filters. Try changing the filters or check the source status."
            action={
              <Link href="/data" className="text-sm font-medium text-brand hover:underline">
                Check data sources →
              </Link>
            }
          />
        ) : (
          <>
            <Table>
              <thead>
                <tr>
                  <Th>Arrival date</Th>
                  <Th>Commodity</Th>
                  <Th>Market</Th>
                  <Th right>Min</Th>
                  <Th right>Max</Th>
                  <Th right>Modal</Th>
                  <Th>Source</Th>
                  <Th>
                    <span className="sr-only">Provenance</span>
                  </Th>
                </tr>
              </thead>
              <tbody>
                {table.data.rows.map((r) => (
                  <tr key={r.id}>
                    <Td className="whitespace-nowrap">{fmtDateOnly(r.arrival_date)}</Td>
                    <Td>
                      <div className="font-medium">{r.commodity}</div>
                      <div className="text-xs text-ink-3">{[r.variety, r.grade].filter(Boolean).join(" · ") || "—"}</div>
                    </Td>
                    <Td>
                      <div>{r.market}</div>
                      <div className="text-xs text-ink-3">{[r.district, r.state].filter(Boolean).join(", ")}</div>
                    </Td>
                    <Td right className="text-ink-2">{r.min_price !== null ? fmtINR(r.min_price) : "—"}</Td>
                    <Td right className="text-ink-2">{r.max_price !== null ? fmtINR(r.max_price) : "—"}</Td>
                    <Td right className="font-semibold">
                      {fmtINR(r.modal_price)}
                      {r.validation_status === "ACCEPTED_WITH_WARNING" && (
                        <div className="mt-0.5" title={r.validation_notes ?? undefined}>
                          <Badge tone="warn" icon={AlertTriangle}>
                            Warning
                          </Badge>
                        </div>
                      )}
                    </Td>
                    <Td>
                      <div className="flex flex-wrap items-center gap-1">
                        <DataClassBadge value={r.data_class} />
                      </div>
                      <div className="mt-0.5 max-w-[14rem] truncate text-[11px] text-ink-3" title={r.source.name}>
                        {r.source.name} · fetched {ago(r.fetched_at)}
                      </div>
                    </Td>
                    <Td>
                      <Button size="sm" variant="ghost" icon={FileSearch} onClick={() => setDetailId(r.id)} aria-label={`Provenance for ${r.commodity} at ${r.market}`}>
                        Source
                      </Button>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
            <div className="flex items-center justify-between gap-3 px-5 py-3 text-xs text-ink-3">
              <span>
                {offset + 1}–{Math.min(offset + PAGE, table.data.total)} of {table.data.total.toLocaleString("en-IN")} reports · prices in ₹ per quintal
              </span>
              <div className="flex gap-1">
                <Button size="sm" variant="secondary" icon={ChevronLeft} disabled={offset === 0} onClick={() => setOffset((o) => Math.max(o - PAGE, 0))}>
                  Previous
                </Button>
                <Button size="sm" variant="secondary" disabled={offset + PAGE >= table.data.total} onClick={() => setOffset((o) => o + PAGE)}>
                  Next <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
          </>
        )}
      </Card>
      <PriceDetailModal id={detailId} onClose={() => setDetailId(null)} />
    </div>
  );
}

export default function MarketPage() {
  return (
    <Suspense>
      <MarketInner />
    </Suspense>
  );
}
