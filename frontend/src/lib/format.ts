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
