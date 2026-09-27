const NUM = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 1 });
const NUM3 = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 3 });

export const fmt = (n: number) => NUM.format(n);
export const fmtQty = (n: number) => NUM3.format(n);

export const UNIT_SHORT: Record<string, string> = { TONNE: "t", QUINTAL: "q", KG: "kg" };

export function title(s: string): string {
  return s
    .toLowerCase()
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

export function fmtDate(iso: string): string {
  return new Date(iso).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
}

export function fmtDay(iso: string): string {
  return new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}

const INR = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });
export const fmtINR = (n: number) => INR.format(n);

/** Timestamp in IST, labelled, e.g. "27 Sept 2026, 10:30 am IST". */
export function fmtIST(iso: string): string {
  return (
    new Date(iso).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium", timeStyle: "short" }) + " IST"
  );
}

export function fmtTimeIST(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour: "numeric", minute: "2-digit" }) + " IST";
}

export function ago(iso: string | null | undefined): string {
  if (!iso) return "never";
  const s = Math.max((Date.now() - new Date(iso).getTime()) / 1000, 0);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 172800) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)} days ago`;
}

export function fmtDateOnly(d: string): string {
  return new Date(d + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}
