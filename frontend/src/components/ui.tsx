"use client";

import { useEffect, useRef } from "react";

type Btn = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger" | "ghost";
  size?: "sm" | "md";
};

export function Button({ variant = "primary", size = "md", className = "", ...props }: Btn) {
  const base =
    "inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand";
  const sizes = { sm: "h-8 px-3 text-sm", md: "h-9 px-4 text-sm" };
  const variants = {
    primary: "bg-brand text-white hover:bg-brand-hover",
    secondary: "bg-surface text-ink border border-line hover:bg-canvas",
    danger: "bg-surface text-bad border border-line hover:bg-red-50",
    ghost: "text-ink-2 hover:bg-canvas hover:text-ink",
  };
  return <button className={`${base} ${sizes[size]} ${variants[variant]} ${className}`} {...props} />;
}

export function Card({
  title,
  action,
  children,
  className = "",
  flush = false,
}: {
  title?: React.ReactNode;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  flush?: boolean;
}) {
  return (
    <section className={`min-w-0 overflow-hidden rounded-lg border border-line bg-surface ${className}`}>
      {(title || action) && (
        <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
          <h2 className="text-sm font-semibold text-ink">{title}</h2>
          {action}
        </header>
      )}
      <div className={flush ? "" : "p-4"}>{children}</div>
    </section>
  );
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-ink">{title}</h1>
        {description && <p className="mt-1 text-sm text-ink-2">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

const TONE_TEXT = { good: "text-good", warn: "text-warn", bad: "text-bad", neutral: "text-ink-2" } as const;
const TONE_LABEL = { good: "Healthy", warn: "Watch", bad: "Critical", neutral: "" } as const;

export function Badge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: "neutral" | "good" | "warn" | "bad" | "brand";
}) {
  const tones = {
    neutral: "bg-canvas text-ink-2 border-line",
    good: "bg-green-50 text-good border-green-200",
    warn: "bg-amber-50 text-warn border-amber-200",
    bad: "bg-red-50 text-bad border-red-200",
    brand: "bg-brand-soft text-brand border-green-200",
  };
  return (
    <span className={`inline-flex items-center rounded border px-1.5 py-0.5 text-xs font-medium ${tones[tone]}`}>
      {children}
    </span>
  );
}

export function StatTile({
  label,
  value,
  unit,
  hint,
  tone = "neutral",
}: {
  label: string;
  value: string;
  unit?: string | null;
  hint?: string | null;
  tone?: "neutral" | "good" | "warn" | "bad";
}) {
  return (
    <div className="rounded-lg border border-line bg-surface px-4 py-3">
      <div className="text-xs font-medium text-ink-2">{label}</div>
      <div className="mt-1 flex items-baseline gap-1">
        <span className="tabular text-2xl font-semibold text-ink">{value}</span>
        {unit && <span className="text-sm text-ink-2">{unit}</span>}
      </div>
      {(hint || tone !== "neutral") && (
        <div className="mt-0.5 text-xs text-ink-3">
          {tone !== "neutral" && (
            <span className={`mr-1.5 font-medium ${TONE_TEXT[tone]}`}>
              <span aria-hidden>●</span> {TONE_LABEL[tone]}
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

/** Capacity meter: fill color carries status, but the % and label always travel with it. */
export function CapacityBar({ pct, showLabel = true }: { pct: number; showLabel?: boolean }) {
  const tone = utilTone(pct);
  const fill = { good: "bg-good", warn: "bg-warn", bad: "bg-bad" }[tone];
  return (
    <div className="flex items-center gap-2" title={`${pct}% of capacity used`}>
      <div
        className="h-1.5 w-full min-w-16 overflow-hidden rounded-full bg-canvas ring-1 ring-line"
        role="meter"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Capacity used"
      >
        <div className={`h-full rounded-full ${fill}`} style={{ width: `${Math.min(pct, 100)}%` }} />
      </div>
      {showLabel && (
        <span className={`tabular w-12 shrink-0 text-right text-xs font-medium ${TONE_TEXT[tone]}`}>{pct}%</span>
      )}
    </div>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-10 text-sm text-ink-2" role="status">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-line border-t-brand" />
      {label}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-bad" role="alert">
      <div className="flex items-center justify-between gap-3">
        <span>{message}</span>
        {onRetry && (
          <Button size="sm" variant="secondary" onClick={onRetry}>
            Retry
          </Button>
        )}
      </div>
    </div>
  );
}

export function EmptyState({ title, body, action }: { title: string; body?: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-12 text-center">
      <div className="text-sm font-medium text-ink">{title}</div>
      {body && <p className="mt-1 max-w-sm text-sm text-ink-2">{body}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Table({ children, compact = false }: { children: React.ReactNode; compact?: boolean }) {
  return (
    <div className="overflow-x-auto">
      <table className={`w-full text-left text-sm ${compact ? "min-w-[360px]" : "min-w-[560px]"}`}>{children}</table>
    </div>
  );
}

export function Th({ children, right = false }: { children?: React.ReactNode; right?: boolean }) {
  return (
    <th
      className={`border-b border-line bg-canvas/60 px-4 py-2 text-xs font-medium uppercase tracking-wide text-ink-3 ${right ? "text-right" : ""}`}
    >
      {children}
    </th>
  );
}

export function Td({
  children,
  right = false,
  className = "",
}: {
  children?: React.ReactNode;
  right?: boolean;
  className?: string;
}) {
  return (
    <td className={`border-b border-line px-4 py-2.5 align-middle ${right ? "tabular text-right" : ""} ${className}`}>
      {children}
    </td>
  );
}

export function Modal({
  open,
  title,
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: React.ReactNode;
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
      className="m-auto w-[calc(100%-2rem)] max-w-lg rounded-lg border border-line bg-surface p-0 text-ink shadow-xl backdrop:bg-black/30"
    >
      {open && (
        <div>
          <header className="flex items-center justify-between border-b border-line px-5 py-3">
            <h2 className="text-base font-semibold">{title}</h2>
            <button onClick={onClose} className="rounded p-1 text-ink-3 hover:bg-canvas hover:text-ink" aria-label="Close">
              ✕
            </button>
          </header>
          <div className="px-5 py-4">{children}</div>
        </div>
      )}
    </dialog>
  );
}

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-medium text-ink">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-ink-3">{hint}</span>}
    </label>
  );
}

const inputCls =
  "block h-9 w-full rounded-md border border-line bg-surface px-3 text-sm text-ink placeholder:text-ink-3 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20 disabled:bg-canvas";

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`${inputCls} ${props.className ?? ""}`} />;
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={`${inputCls} pr-8 ${props.className ?? ""}`} />;
}

export function FormError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-bad" role="alert">
      {message}
    </p>
  );
}

export function SyntheticBanner() {
  return (
    <div className="border-b border-amber-200 bg-amber-50 px-4 py-1.5 text-center text-xs text-warn">
      <strong className="font-semibold">Synthetic demo data.</strong> All figures in this workspace are invented for
      testing and do not describe real agricultural operations.
    </div>
  );
}
