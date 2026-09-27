"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Button, Field, FormError, Input } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

const DEMO_ACCOUNTS = [
  ["admin", "Organization Admin"],
  ["ops", "Operations Manager"],
  ["procurement", "Procurement Manager"],
  ["ravi", "Warehouse Manager (Bengaluru only)"],
  ["logistics", "Logistics Manager"],
  ["analyst", "Analyst"],
  ["viewer", "Viewer (Mysuru only)"],
];

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/auth/login", { method: "POST", json: { email, password } });
      const next = params.get("next");
      router.replace(next && next.startsWith("/") && !next.startsWith("//") ? next : "/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the server");
      setBusy(false);
    }
  }

  return (
    <>
      <h1 className="text-lg font-semibold">Sign in</h1>
      <p className="mt-1 text-sm text-ink-2">Use your organization account.</p>
      <form onSubmit={submit} className="mt-5 space-y-4">
        <Field label="Email">
          <Input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field label="Password">
          <Input
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>
        <FormError message={error} />
        <Button type="submit" className="w-full" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </Button>
      </form>
      <p className="mt-4 text-sm text-ink-2">
        New organization?{" "}
        <Link href="/register" className="font-medium text-brand hover:underline">
          Create a workspace
        </Link>
      </p>

      <details className="mt-5 border-t border-line pt-4 text-sm">
        <summary className="cursor-pointer font-medium text-ink-2">Synthetic demo accounts</summary>
        <p className="mt-2 text-xs text-ink-3">
          Available after running the seed script. Password for all: <code className="font-mono">Demo@1234</code>
        </p>
        <ul className="mt-2 space-y-1">
          {DEMO_ACCOUNTS.map(([local, label]) => (
            <li key={local}>
              <button
                type="button"
                className="text-left text-xs text-brand hover:underline"
                onClick={() => {
                  setEmail(`${local}@agriflow.demo`);
                  setPassword("Demo@1234");
                }}
              >
                {local}@agriflow.demo
              </button>
              <span className="text-xs text-ink-3"> — {label}</span>
            </li>
          ))}
        </ul>
      </details>
    </>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
