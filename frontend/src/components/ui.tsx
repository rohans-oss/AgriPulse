"use client";

import {
  AlertTriangle,
  Building2,
  CheckCircle2,
  CircleDashed,
  Clock,
  Database,
  ExternalLink,
  FlaskConical,
  Globe2,
  Info,
  Layers,
  Loader2,
  RefreshCw,
  Sparkles,
  X,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

// --------------------------------------------------------------------------- buttons

type Btn = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger" | "ghost";
  size?: "sm" | "md";
  icon?: LucideIcon;
  loading?: boolean;
};

export function Button({ variant = "primary", size = "md", className = "", icon: Icon, loading, children, disabled, ...props }: Btn) {
  const base =
    "inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition-all duration-150 active:translate-y-px disabled:opacity-50 disabled:cursor-not-allowed disabled:active:translate-y-0 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand whitespace-nowrap";
  const sizes = { sm: "h-8 px-3 text-[13px]", md: "h-9 px-4 text-sm" };
  const variants = {
    primary: "bg-brand text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.12),0_1px_2px_rgb(16_41_28/0.25)] hover:bg-brand-hover",
    secondary: "bg-surface text-ink border border-line-strong/70 shadow-card hover:bg-sunken hover:border-line-strong",
    danger: "bg-surface text-bad border border-line-strong/70 hover:bg-red-50 hover:border-red-200",
    ghost: "text-ink-2 hover:bg-black/[0.04] hover:text-ink",
  };
  return (
    <button className={`${base} ${sizes[size]} ${variants[variant]} ${className}`} disabled={disabled || loading} {...props}>
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : Icon ? <Icon className="h-4 w-4" strokeWidth={2} /> : null}
      {children}
    </button>
  );
}

// --------------------------------------------------------------------------- layout

export function Card({
  title,
  subtitle,
  icon: Icon,
  action,
  children,
  className = "",
  flush = false,
  footer,
}: {
  title?: React.ReactNode;
  subtitle?: React.ReactNode;
  icon?: LucideIcon;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  flush?: boolean;
  footer?: React.ReactNode;
}) {
  return (
    <section className={`min-w-0 overflow-hidden rounded-xl border border-line bg-surface shadow-card ${className}`}>
      {(title || action) && (
        <header className="flex items-start justify-between gap-3 border-b border-line px-5 py-3.5">
          <div className="flex min-w-0 items-start gap-2.5">
            {Icon && (
              <span className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-brand-soft text-brand">
                <Icon className="h-4 w-4" strokeWidth={2} />
              </span>
            )}
            <div className="min-w-0">
              <h2 className="text-[15px] font-semibold leading-6 tracking-tight text-ink">{title}</h2>
              {subtitle && <p className="text-xs leading-5 text-ink-3">{subtitle}</p>}
            </div>
          </div>
          {action && <div className="shrink-0">{action}</div>}
        </header>
      )}
      <div className={flush ? "" : "p-5"}>{children}</div>
      {footer && <footer className="border-t border-line bg-sunken px-5 py-2.5 text-xs text-ink-3">{footer}</footer>}
    </section>
  );
}

export function PageHeader({
  title,
  description,
  actions,
  icon: Icon,
  eyebrow,
}: {
  title: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  icon?: LucideIcon;
  eyebrow?: string;
}) {
  return (
    <div className="mb-6 flex animate-fade-up flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="flex min-w-0 items-start gap-3.5">
        {Icon && (
          <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl border border-line bg-surface text-brand shadow-card">
            <Icon className="h-5 w-5" strokeWidth={1.8} />
          </span>
        )}
        <div className="min-w-0">
          {eyebrow && <div className="mb-0.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-brand">{eyebrow}</div>}
          <h1 className="text-2xl font-semibold tracking-tight text-ink">{title}</h1>
          {description && <div className="mt-1 text-sm text-ink-2">{description}</div>}
        </div>
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

// --------------------------------------------------------------------------- badges & tags

type Tone = "neutral" | "good" | "warn" | "bad" | "brand" | "info";

const BADGE_TONES: Record<Tone, string> = {
  neutral: "bg-sunken text-ink-2 ring-line-strong/70",
  good: "bg-green-50 text-good ring-green-200",
  warn: "bg-amber-50 text-warn ring-amber-200",
  bad: "bg-red-50 text-bad ring-red-200",
  brand: "bg-brand-soft text-brand ring-green-200",
  info: "bg-sky-50 text-sky-800 ring-sky-200",
};

export function Badge({ children, tone = "neutral", icon: Icon }: { children: React.ReactNode; tone?: Tone; icon?: LucideIcon }) {
  return (
    <span className={`inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-md px-1.5 py-0.5 text-[11px] font-medium ring-1 ring-inset ${BADGE_TONES[tone]}`}>
      {Icon && <Icon className="h-3 w-3" strokeWidth={2.2} />}
      {children}
    </span>
  );
}

export interface FreshnessInfo {
  label: string;
  tone: string;
  detail: string;
}

const FRESHNESS: Record<string, { tone: Tone; icon: LucideIcon; text: string }> = {
  CURRENT: { tone: "good", icon: CheckCircle2, text: "Current" },
  RECENT: { tone: "info", icon: Clock, text: "Recent" },
  DAILY: { tone: "brand", icon: Clock, text: "Daily" },
  HISTORICAL: { tone: "warn", icon: Clock, text: "Historical" },
  UNAVAILABLE: { tone: "neutral", icon: CircleDashed, text: "Data unavailable" },
  ERROR: { tone: "bad", icon: AlertTriangle, text: "Update failed" },
};

/** Honest freshness label computed by the backend. Never shows "LIVE". */
export function FreshnessBadge({ freshness, showDetail = false }: { freshness: FreshnessInfo | null | undefined; showDetail?: boolean }) {
  if (!freshness) return null;
  const f = FRESHNESS[freshness.label] ?? FRESHNESS.UNAVAILABLE;
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5" title={freshness.detail}>
      <Badge tone={f.tone} icon={f.icon}>
        {f.text}
      </Badge>
      {showDetail && <span className="text-xs text-ink-3">{freshness.detail}</span>}
    </span>
  );
}

const ORIGIN: Record<string, { label: string; tone: Tone; icon: LucideIcon }> = {
  OFFICIAL_API: { label: "Official data", tone: "brand", icon: Database },
  PUBLIC_API: { label: "Public API", tone: "info", icon: Database },
  USER_UPLOAD: { label: "Uploaded file", tone: "neutral", icon: Database },
};

export function SourceTag({ source, link }: { source: { key: string; name: string; origin: string } | null | undefined; link?: boolean }) {
  if (!source) return null;
  const o = ORIGIN[source.origin] ?? ORIGIN.USER_UPLOAD;
  const inner = (
    <span className="inline-flex min-w-0 max-w-full items-center gap-1.5 text-xs text-ink-3">
      <Badge tone={o.tone} icon={o.icon}>
        {o.label}
      </Badge>
      <span className="truncate">{source.name}</span>
      {link && <ExternalLink className="h-3 w-3" />}
    </span>
  );
  return link ? (
    <a href="/data" className="hover:text-ink">
      {inner}
    </a>
  ) : (
    inner
  );
}

const DATA_CLASS: Record<string, { label: string; tone: Tone; icon: LucideIcon; title: string }> = {
  REAL_EXTERNAL: { label: "Real external", tone: "brand", icon: Globe2, title: "Fetched from a named public source" },
  REAL_ORGANIZATION: { label: "Organization data", tone: "info", icon: Building2, title: "Entered or imported by your team" },
  SYNTHETIC_DEMO: { label: "Synthetic demo", tone: "warn", icon: FlaskConical, title: "Created by the demo seed — not real" },
  MIXED: { label: "Mixed data", tone: "warn", icon: Layers, title: "Part synthetic demo data, part organization data" },
  MODEL_PREDICTION: { label: "Forecast", tone: "neutral", icon: Sparkles, title: "A model prediction, not an observation" },
  UNAVAILABLE: { label: "No data", tone: "neutral", icon: CircleDashed, title: "No verified data available" },
};

/** What kind of data a figure is built on. Every card and table shows one. */
export function DataClassBadge({ value, label }: { value: string | null | undefined; label?: string }) {
  if (!value) return null;
  const d = DATA_CLASS[value] ?? DATA_CLASS.UNAVAILABLE;
  return (
    <span title={d.title} className="inline-flex">
      <Badge tone={d.tone} icon={d.icon}>
        {label ?? d.label}
      </Badge>
    </span>
  );
}

export function SyntheticTag() {
  return (
    <Badge tone="warn" icon={FlaskConical}>
      Synthetic demo data
    </Badge>
  );
}

// --------------------------------------------------------------------------- numbers

export function useCountUp(target: number, duration = 650): number {
  const [value, setValue] = useState(0);
  const from = useRef(0);
  useEffect(() => {
    const reduce = typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce || !Number.isFinite(target)) {
      setValue(target);
      return;
    }
    const start = performance.now();
    const origin = from.current;
    let raf = 0;
    const tick = (now: number) => {
      const t = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - t, 3);
      setValue(origin + (target - origin) * eased);
      if (t < 1) raf = requestAnimationFrame(tick);
      else from.current = target;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, duration]);
  return value;
}

const TONE_TEXT = { good: "text-good", warn: "text-warn", bad: "text-bad", neutral: "text-ink-2" } as const;
const TONE_LABEL = { good: "Healthy", warn: "Watch", bad: "Critical", neutral: "" } as const;

export function StatTile({
  label,
  value,
  unit,
  hint,
  tone = "neutral",
  icon: Icon,
  format,
  style,
  statusText,
}: {
  statusText?: string;
  label: string;
  value: number | string;
  unit?: string | null;
  hint?: string | null;
  tone?: "neutral" | "good" | "warn" | "bad";
  icon?: LucideIcon;
  format?: (n: number) => string;
  style?: React.CSSProperties;
}) {
  const animated = useCountUp(typeof value === "number" ? value : 0);
  const shown = typeof value === "number" ? (format ? format(animated) : Math.round(animated).toLocaleString("en-IN")) : value;
  return (
    <div
      className="group relative overflow-hidden rounded-xl border border-line bg-surface px-4 py-3.5 shadow-card transition-shadow duration-200 hover:shadow-lift"
      style={style}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-[13px] font-medium text-ink-2">{label}</span>
        {Icon && <Icon className="h-4 w-4 text-ink-3 transition-colors group-hover:text-brand" strokeWidth={1.8} />}
      </div>
      <div className="mt-1.5 flex items-baseline gap-1">
        <span className="tabular text-[26px] font-semibold leading-8 tracking-tight text-ink">{shown}</span>
        {unit && <span className="text-sm font-medium text-ink-3">{unit}</span>}
      </div>
      {(hint || tone !== "neutral") && (
        <div className="mt-1 text-xs text-ink-3">
          {tone !== "neutral" && (
            <span className={`mr-1.5 inline-flex items-center gap-1 font-medium ${TONE_TEXT[tone]}`}>
              <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden /> {statusText ?? TONE_LABEL[tone]}
            </span>
          )}
          {hint}
        </div>
      )}
    </div>
  );
}

export function utilTone(pct: number): "good" | "warn" | "bad" {
  return pct >= 95 ? "bad" : pct >= 85 ? "warn" : "good";
}

/** Capacity meter: fill colour carries status, but the % always travels with it. */
export function CapacityBar({ pct, showLabel = true }: { pct: number; showLabel?: boolean }) {
  const tone = utilTone(pct);
  const fill = { good: "bg-good", warn: "bg-warn", bad: "bg-bad" }[tone];
  const [w, setW] = useState(0);
  useEffect(() => {
    const id = requestAnimationFrame(() => setW(Math.min(pct, 100)));
    return () => cancelAnimationFrame(id);
  }, [pct]);
  return (
    <div className="flex items-center gap-2" title={`${pct}% of capacity used`}>
      <div
        className="h-1.5 w-full min-w-16 overflow-hidden rounded-full bg-black/[0.06]"
        role="meter"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Capacity used"
      >
        <div className={`h-full rounded-full ${fill} transition-[width] duration-700 ease-out`} style={{ width: `${w}%` }} />
      </div>
      {showLabel && <span className={`tabular w-12 shrink-0 text-right text-xs font-semibold ${TONE_TEXT[tone]}`}>{pct}%</span>}
    </div>
  );
}

// --------------------------------------------------------------------------- states

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skeleton ${className}`} aria-hidden />;
}

export function Loading({ label = "Loading…", rows = 5 }: { label?: string; rows?: number }) {
  return (
    <div className="space-y-3 py-4" role="status" aria-label={label}>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-4">
          <Skeleton className="h-4 w-1/4" />
          <Skeleton className="h-4 flex-1" />
          <Skeleton className="h-4 w-20" />
        </div>
      ))}
      <span className="sr-only">{label}</span>
    </div>
  );
}

export function PageSkeleton() {
  return (
    <div className="space-y-6" role="status" aria-label="Loading">
      <div className="flex items-center gap-3">
        <Skeleton className="h-11 w-11 rounded-xl" />
        <div className="space-y-2">
          <Skeleton className="h-6 w-56" />
          <Skeleton className="h-4 w-80" />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-[92px] rounded-xl" />
        ))}
      </div>
      <Skeleton className="h-64 rounded-xl" />
    </div>
  );
}

export function ErrorState({
  message,
  title = "Something went wrong",
  onRetry,
  footnote,
}: {
  message: string;
  title?: string;
  onRetry?: () => void;
  footnote?: React.ReactNode;
}) {
  return (
    <div className="flex animate-fade-in items-start gap-3 rounded-xl border border-red-200 bg-red-50/70 px-4 py-3.5 text-sm" role="alert">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-bad" />
      <div className="min-w-0 flex-1">
        <div className="font-medium text-bad">{title}</div>
        <div className="mt-0.5 text-ink-2">{message}</div>
        {footnote && <div className="mt-1 text-xs text-ink-3">{footnote}</div>}
      </div>
      {onRetry && (
        <Button size="sm" variant="secondary" icon={RefreshCw} onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}

export function Notice({ children, tone = "info", icon: Icon = Info }: { children: React.ReactNode; tone?: "info" | "warn"; icon?: LucideIcon }) {
  const cls = tone === "warn" ? "border-amber-200 bg-amber-50/70 text-warn" : "border-sky-200 bg-sky-50/60 text-sky-900";
  return (
    <div className={`flex items-start gap-2.5 rounded-xl border px-4 py-3 text-sm ${cls}`}>
      <Icon className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="min-w-0 text-ink-2">{children}</div>
    </div>
  );
}

export function EmptyState({
  title,
  body,
  action,
  icon: Icon = CircleDashed,
  art = false,
}: {
  title: string;
  body?: React.ReactNode;
  action?: React.ReactNode;
  icon?: LucideIcon;
  art?: boolean;
}) {
  return (
    <div className="relative flex animate-fade-in flex-col items-center justify-center overflow-hidden px-6 py-12 text-center">
      {art && (
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 bg-[url(/art/fields.svg)] bg-cover bg-center opacity-[0.07] [mask-image:radial-gradient(ellipse_at_center,black_20%,transparent_70%)]"
        />
      )}
      <span className="relative grid h-12 w-12 place-items-center rounded-2xl border border-line bg-surface text-ink-3 shadow-card">
        <Icon className="h-5 w-5" strokeWidth={1.8} />
      </span>
      <div className="relative mt-3 text-sm font-semibold text-ink">{title}</div>
      {body && <div className="relative mt-1 max-w-md text-sm text-ink-2">{body}</div>}
      {action && <div className="relative mt-4">{action}</div>}
    </div>
  );
}

// --------------------------------------------------------------------------- tables

export function Table({ children, compact = false }: { children: React.ReactNode; compact?: boolean }) {
  return (
    <div className="relative overflow-x-auto">
      <table className={`row-hover w-full text-left text-sm ${compact ? "min-w-[360px]" : "min-w-[560px]"}`}>{children}</table>
    </div>
  );
}

export function Th({ children, right = false }: { children?: React.ReactNode; right?: boolean }) {
  return (
    <th
      className={`border-b border-line bg-sunken px-5 py-2.5 text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-3 ${right ? "text-right" : ""}`}
    >
      {children}
    </th>
  );
}

export function Td({ children, right = false, className = "" }: { children?: React.ReactNode; right?: boolean; className?: string }) {
  return (
    <td className={`border-b border-line/80 px-5 py-3 align-middle ${right ? "tabular text-right" : ""} ${className}`}>{children}</td>
  );
}

// --------------------------------------------------------------------------- forms

export function Modal({
  open,
  title,
  description,
  onClose,
  children,
  wide = false,
}: {
  open: boolean;
  title: string;
  description?: string;
  onClose: () => void;
  children: React.ReactNode;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  return (
    <dialog
      ref={ref}
      onClose={onClose}
      className={`m-auto w-[calc(100%-2rem)] ${wide ? "max-w-2xl" : "max-w-lg"} rounded-2xl border border-line bg-surface p-0 text-ink shadow-2xl backdrop:bg-forest-950/40 backdrop:backdrop-blur-[2px]`}
    >
      {open && (
        <div>
          <header className="flex items-start justify-between gap-4 border-b border-line px-6 py-4">
            <div>
              <h2 className="text-base font-semibold tracking-tight">{title}</h2>
              {description && <p className="mt-0.5 text-sm text-ink-2">{description}</p>}
            </div>
            <button onClick={onClose} className="rounded-lg p-1.5 text-ink-3 transition-colors hover:bg-black/[0.05] hover:text-ink" aria-label="Close">
              <X className="h-4 w-4" />
            </button>
          </header>
          <div className="px-6 py-5">{children}</div>
        </div>
      )}
    </dialog>
  );
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[13px] font-medium text-ink">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-ink-3">{hint}</span>}
    </label>
  );
}

const inputCls =
  "block h-10 rounded-lg border border-line-strong/80 bg-surface px-3 text-sm text-ink shadow-[inset_0_1px_1px_rgb(22_32_26/0.03)] transition-[border-color,box-shadow] duration-150 placeholder:text-ink-3 hover:border-line-strong focus:border-brand focus:outline-none focus:ring-4 focus:ring-brand/12 disabled:bg-sunken disabled:text-ink-3";

// Full width unless the caller sets its own width.
const widthOf = (cls?: string) => (cls && /(^|\s)(w-|min-w-|max-w-)/.test(cls) ? "" : "w-full");

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`${inputCls} ${widthOf(props.className)} ${props.className ?? ""}`} />;
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={`${inputCls} pr-8 ${widthOf(props.className)} ${props.className ?? ""}`} />;
}

export function FormError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p className="flex animate-fade-in items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-bad" role="alert">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      {message}
    </p>
  );
}

export function SyntheticBanner() {
  return (
    <div className="flex items-center justify-center gap-2 border-b border-amber-200/80 bg-harvest-soft px-4 py-1.5 text-center text-xs text-warn">
      <FlaskConical className="h-3.5 w-3.5 shrink-0" />
      <span>
        <strong className="font-semibold">Synthetic demo data.</strong> Organization figures in this workspace are invented for testing.
        Market and weather data are labelled with their real public source.
      </span>
    </div>
  );
}
