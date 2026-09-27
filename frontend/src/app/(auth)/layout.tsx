import { BarChart3, CloudSun, ShieldCheck } from "lucide-react";
import { Logo } from "@/components/AppShell";

const POINTS = [
  { icon: BarChart3, title: "Stock you can trust", body: "Inventory, capacity and every movement across your warehouses." },
  { icon: CloudSun, title: "Real public data, clearly sourced", body: "Mandi prices and weather with their source and timestamp on every figure." },
  { icon: ShieldCheck, title: "Right data for each role", body: "Access follows each person's role and locations, enforced on the server." },
];

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid min-h-screen lg:grid-cols-[1.05fr_1fr]">
      <aside className="relative hidden overflow-hidden bg-forest-900 lg:block">
        <div aria-hidden className="absolute inset-0 bg-[url(/art/fields.svg)] bg-cover bg-center" />
        <div aria-hidden className="absolute inset-0 bg-gradient-to-br from-forest-950/95 via-forest-900/82 to-forest-900/45" />
        <div className="relative flex h-full flex-col justify-between p-12 text-white">
          <div className="flex items-center gap-3">
            <Logo />
            <div>
              <div className="font-semibold tracking-tight">AgriFlow AI</div>
              <div className="text-xs text-white/60">Agricultural supply-chain intelligence</div>
            </div>
          </div>
          <div className="max-w-md animate-fade-up">
            <h2 className="font-display text-[40px] font-medium leading-[1.1] tracking-tight">
              From field to market, <span className="italic text-harvest">one clear picture.</span>
            </h2>
            <ul className="mt-10 space-y-5">
              {POINTS.map(({ icon: Icon, title, body }) => (
                <li key={title} className="flex gap-3.5">
                  <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-white/15 bg-white/[0.07] backdrop-blur">
                    <Icon className="h-[18px] w-[18px] text-harvest" strokeWidth={1.8} />
                  </span>
                  <div>
                    <div className="text-sm font-semibold">{title}</div>
                    <div className="text-sm text-white/65">{body}</div>
                  </div>
                </li>
              ))}
            </ul>
          </div>
          <div className="text-xs text-white/40">Illustration: aerial farmland (original artwork)</div>
        </div>
      </aside>

      <main className="flex items-center justify-center px-5 py-10 sm:px-8">
        <div className="w-full max-w-[400px] animate-fade-up">
          <div className="mb-8 flex items-center gap-2.5 lg:hidden">
            <Logo />
            <div>
              <div className="font-semibold tracking-tight">AgriFlow AI</div>
              <div className="text-xs text-ink-2">Agricultural supply-chain intelligence</div>
            </div>
          </div>
          {children}
        </div>
      </main>
    </div>
  );
}
