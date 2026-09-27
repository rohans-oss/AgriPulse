"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { ROLE_LABELS, useAuth } from "@/lib/auth";
import { Loading, SyntheticBanner } from "./ui";

const NAV: { href: string; label: string; permission?: string }[] = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/inventory", label: "Inventory", permission: "inventory.read" },
  { href: "/warehouses", label: "Warehouses", permission: "warehouse.read" },
  { href: "/commodities", label: "Commodities", permission: "commodity.read" },
  { href: "/regions", label: "Regions", permission: "region.read" },
  { href: "/users", label: "Users", permission: "users.read" },
  { href: "/settings", label: "Settings", permission: "settings.manage" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const { me, loading, can, logout } = useAuth();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  if (loading || !me) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Loading label="Loading workspace…" />
      </div>
    );
  }

  const items = NAV.filter((n) => !n.permission || can(n.permission));
  const role = me.primary_role ? ROLE_LABELS[me.primary_role] : "No role";
  const scope = me.scope.org_wide
    ? "All locations"
    : [...me.scope.regions, ...me.scope.warehouses].map((r) => r.name).join(", ") || "No locations assigned";

  const nav = (
    <nav className="flex flex-col gap-0.5">
      {items.map((n) => {
        const active = pathname === n.href || pathname.startsWith(`${n.href}/`);
        return (
          <Link
            key={n.href}
            href={n.href}
            onClick={() => setOpen(false)}
            className={`rounded-md px-3 py-2 text-sm font-medium ${
              active ? "bg-brand-soft text-brand" : "text-ink-2 hover:bg-canvas hover:text-ink"
            }`}
          >
            {n.label}
          </Link>
        );
      })}
    </nav>
  );

  return (
    <div className="min-h-screen">
      {me.organization.is_demo && <SyntheticBanner />}
      <div className="flex">
        <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-line bg-surface lg:flex">
          <Brand org={me.organization.name} />
          <div className="flex-1 overflow-y-auto px-3 py-4">{nav}</div>
          <UserBlock name={me.user.full_name} role={role} scope={scope} onLogout={logout} />
        </aside>

        <div className="min-w-0 flex-1">
          <header className="sticky top-0 z-10 flex h-14 items-center justify-between border-b border-line bg-surface px-4 lg:hidden">
            <span className="text-sm font-semibold">AgriFlow AI</span>
            <button
              className="rounded-md border border-line px-3 py-1.5 text-sm"
              onClick={() => setOpen((o) => !o)}
              aria-expanded={open}
            >
              Menu
            </button>
          </header>
          {open && (
            <div className="border-b border-line bg-surface px-3 py-3 lg:hidden">
              {nav}
              <div className="mt-3 border-t border-line pt-3">
                <UserBlock name={me.user.full_name} role={role} scope={scope} onLogout={logout} />
              </div>
            </div>
          )}
          <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">{children}</main>
        </div>
      </div>
    </div>
  );
}

function Brand({ org }: { org: string }) {
  return (
    <div className="border-b border-line px-5 py-4">
      <div className="flex items-center gap-2">
        <span className="grid h-7 w-7 place-items-center rounded-md bg-brand text-xs font-bold text-white">AF</span>
        <span className="text-sm font-semibold">AgriFlow AI</span>
      </div>
      <div className="mt-2 truncate text-xs text-ink-2" title={org}>
        {org}
      </div>
    </div>
  );
}

function UserBlock({
  name,
  role,
  scope,
  onLogout,
}: {
  name: string;
  role: string;
  scope: string;
  onLogout: () => void;
}) {
  return (
    <div className="border-t border-line px-4 py-3 lg:border-t">
      <div className="truncate text-sm font-medium">{name}</div>
      <div className="text-xs text-ink-2">{role}</div>
      <div className="mt-0.5 truncate text-xs text-ink-3" title={scope}>
        {scope}
      </div>
      <button onClick={onLogout} className="mt-2 text-xs font-medium text-ink-2 hover:text-bad">
        Sign out
      </button>
    </div>
  );
}
