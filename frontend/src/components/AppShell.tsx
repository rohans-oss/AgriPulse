"use client";

import {
  Boxes,
  CloudSun,
  Database,
  FileUp,
  LayoutDashboard,
  LogOut,
  MapPin,
  Menu,
  Settings,
  Sprout,
  TrendingUp,
  Users,
  Warehouse,
  X,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { ROLE_LABELS, useAuth } from "@/lib/auth";
import { PageSkeleton, SyntheticBanner } from "./ui";

type NavItem = { href: string; label: string; icon: LucideIcon; permission?: string | string[] };

const NAV: { heading: string | null; items: NavItem[] }[] = [
  { heading: null, items: [{ href: "/dashboard", label: "Dashboard", icon: LayoutDashboard }] },
  {
    heading: "Operations",
    items: [
      { href: "/inventory", label: "Inventory", icon: Boxes, permission: "inventory.read" },
      { href: "/warehouses", label: "Warehouses", icon: Warehouse, permission: "warehouse.read" },
      { href: "/commodities", label: "Commodities", icon: Sprout, permission: "commodity.read" },
      { href: "/regions", label: "Regions", icon: MapPin, permission: "region.read" },
    ],
  },
  {
    heading: "Market intelligence",
    items: [
      { href: "/market", label: "Market prices", icon: TrendingUp, permission: "data.read" },
      { href: "/weather", label: "Weather", icon: CloudSun, permission: ["data.read", "warehouse.read"] },
    ],
  },
  {
    heading: "Data platform",
    items: [
      { href: "/data", label: "Data sources", icon: Database, permission: "data.read" },
      { href: "/data/import", label: "Import CSV", icon: FileUp, permission: ["data.import|inventory.update"] },
    ],
  },
  {
    heading: "Administration",
    items: [
      { href: "/users", label: "Users & roles", icon: Users, permission: "users.read" },
      { href: "/settings", label: "Settings", icon: Settings, permission: "settings.manage" },
    ],
  },
];

function allowed(item: NavItem, can: (p: string) => boolean) {
  if (!item.permission) return true;
  const perms = Array.isArray(item.permission) ? item.permission : [item.permission];
  // "a|b" means either permission is enough.
  return perms.every((p) => p.split("|").some(can));
}

function isActive(pathname: string, href: string) {
  if (href === "/data") return pathname === "/data" || pathname.startsWith("/data/runs");
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { me, loading, can, logout } = useAuth();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  useEffect(() => setOpen(false), [pathname]);

  if (loading || !me) {
    return (
      <div className="min-h-screen lg:pl-64">
        <div className="fixed inset-y-0 left-0 hidden w-64 bg-forest-900 lg:block" />
        <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
          <PageSkeleton />
        </div>
      </div>
    );
  }

  const sections = NAV.map((s) => ({ ...s, items: s.items.filter((i) => allowed(i, can)) })).filter((s) => s.items.length);
  const role = me.primary_role ? ROLE_LABELS[me.primary_role] : "No role";
  const scope = me.scope.org_wide
    ? "All locations"
    : [...me.scope.regions, ...me.scope.warehouses].map((r) => r.name).join(", ") || "No locations assigned";
  const initials = me.user.full_name
    .split(/\s+/)
    .map((p) => p[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  const sidebar = (
    <div className="relative flex h-full flex-col overflow-hidden bg-forest-900 text-white">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 bottom-0 h-72 bg-[url(/art/fields.svg)] bg-cover bg-bottom opacity-[0.16] [mask-image:linear-gradient(to_top,black,transparent)]"
      />
      <div className="relative px-5 pb-4 pt-5">
        <Link href="/dashboard" className="flex items-center gap-2.5">
          <Logo />
          <div className="leading-tight">
            <div className="text-[15px] font-semibold tracking-tight">AgriFlow AI</div>
            <div className="text-[11px] text-white/50">Supply-chain intelligence</div>
          </div>
        </Link>
        <div className="mt-4 rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2">
          <div className="text-[10px] font-semibold uppercase tracking-[0.1em] text-white/40">Workspace</div>
          <div className="truncate text-[13px] font-medium text-white/90" title={me.organization.name}>
            {me.organization.name}
          </div>
        </div>
      </div>

      <nav className="relative flex-1 space-y-5 overflow-y-auto px-3 pb-4">
        {sections.map((s) => (
          <div key={s.heading ?? "top"}>
            {s.heading && (
              <div className="mb-1 px-3 text-[10px] font-semibold uppercase tracking-[0.12em] text-white/35">{s.heading}</div>
            )}
            <div className="space-y-0.5">
              {s.items.map((n) => {
                const active = isActive(pathname, n.href);
                const Icon = n.icon;
                return (
                  <Link
                    key={n.href}
                    href={n.href}
                    aria-current={active ? "page" : undefined}
                    className={`group relative flex items-center gap-3 rounded-lg px-3 py-2 text-[13.5px] font-medium transition-colors duration-150 ${
                      active ? "bg-white/[0.09] text-white" : "text-white/65 hover:bg-white/[0.05] hover:text-white"
                    }`}
                  >
                    <span
                      className={`absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-harvest transition-all duration-200 ${
                        active ? "opacity-100" : "scale-y-0 opacity-0"
                      }`}
                    />
                    <Icon
                      className={`h-[18px] w-[18px] shrink-0 transition-colors ${active ? "text-harvest" : "text-white/45 group-hover:text-white/80"}`}
                      strokeWidth={1.8}
                    />
                    {n.label}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      <div className="relative border-t border-white/10 px-4 py-3.5">
        <div className="flex items-center gap-3">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-harvest/90 text-[13px] font-semibold text-forest-950">
            {initials}
          </span>
          <div className="min-w-0 flex-1">
            <div className="truncate text-[13px] font-medium">{me.user.full_name}</div>
            <div className="truncate text-[11px] text-white/55">{role}</div>
          </div>
          <button
            onClick={logout}
            className="rounded-lg p-2 text-white/55 transition-colors hover:bg-white/10 hover:text-white"
            aria-label="Sign out"
            title="Sign out"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
        <div className="mt-2 flex items-center gap-1.5 truncate text-[11px] text-white/45" title={scope}>
          <MapPin className="h-3 w-3 shrink-0" />
          {scope}
        </div>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 lg:block">{sidebar}</aside>

      {/* Mobile drawer */}
      <div
        className={`fixed inset-0 z-40 bg-forest-950/50 backdrop-blur-[2px] transition-opacity duration-200 lg:hidden ${
          open ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
        onClick={() => setOpen(false)}
        aria-hidden
      />
      <aside
        className={`fixed inset-y-0 left-0 z-50 w-72 max-w-[85vw] transition-transform duration-250 ease-out lg:hidden ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
        aria-hidden={!open}
      >
        {sidebar}
        <button
          onClick={() => setOpen(false)}
          className="absolute right-3 top-4 rounded-lg p-2 text-white/70 hover:bg-white/10"
          aria-label="Close menu"
        >
          <X className="h-5 w-5" />
        </button>
      </aside>

      <div className="lg:pl-64">
        {me.organization.is_demo && <SyntheticBanner />}
        <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-line bg-surface/85 px-4 backdrop-blur-md lg:hidden">
          <div className="flex items-center gap-2">
            <Logo small />
            <span className="text-sm font-semibold">AgriFlow AI</span>
          </div>
          <button
            className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-sm font-medium"
            onClick={() => setOpen(true)}
            aria-expanded={open}
          >
            <Menu className="h-4 w-4" /> Menu
          </button>
        </header>
        <main key={pathname} className="mx-auto max-w-7xl animate-fade-in px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          {children}
        </main>
      </div>
    </div>
  );
}

export function Logo({ small = false }: { small?: boolean }) {
  const s = small ? "h-7 w-7" : "h-9 w-9";
  return (
    <span className={`grid ${s} shrink-0 place-items-center rounded-xl bg-gradient-to-br from-harvest to-[#b27a17] shadow-[inset_0_1px_0_rgb(255_255_255/0.3)]`}>
      <Sprout className={small ? "h-4 w-4 text-forest-950" : "h-5 w-5 text-forest-950"} strokeWidth={2.2} />
    </span>
  );
}
