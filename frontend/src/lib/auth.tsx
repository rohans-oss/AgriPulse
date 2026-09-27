"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api } from "./api";
import type { Me, RoleCode } from "./types";

interface AuthState {
  me: Me | null;
  loading: boolean;
  /** UI convenience only — the backend enforces every permission independently. */
  can: (permission: string) => boolean;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      setMe(await api<Me>("/auth/me"));
    } catch {
      setMe(null);
      window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const logout = useCallback(async () => {
    try {
      await api("/auth/logout", { method: "POST" });
    } finally {
      window.location.href = "/login";
    }
  }, []);

  const can = useCallback((p: string) => Boolean(me?.permissions.includes(p)), [me]);

  return <AuthContext.Provider value={{ me, loading, can, refresh, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

export const ROLE_LABELS: Record<RoleCode, string> = {
  ORGANIZATION_ADMIN: "Organization Admin",
  OPERATIONS_MANAGER: "Operations Manager",
  PROCUREMENT_MANAGER: "Procurement Manager",
  WAREHOUSE_MANAGER: "Warehouse Manager",
  LOGISTICS_MANAGER: "Logistics Manager",
  ANALYST: "Analyst",
  VIEWER: "Viewer",
};
