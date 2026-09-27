"use client";

import { ArrowRight, FlaskConical } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Button, Field, FormError, Input } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

const DEMO_ACCOUNTS = [
  ["admin", "Organization Admin", "All locations"],
  ["ops", "Operations Manager", "All locations"],
  ["procurement", "Procurement Manager", "All locations"],
  ["ravi", "Warehouse Manager", "Bengaluru Central only"],
  ["logistics", "Logistics Manager", "All locations"],
  ["analyst", "Analyst", "All locations"],
  ["viewer", "Viewer", "Mysuru region only"],
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
      <h1 className="text-[28px] font-semibold tracking-tight">Welcome back</h1>
      <p className="mt-1.5 text-sm text-ink-2">Sign in to your organization&apos;s workspace.</p>
      <form onSubmit={submit} className="mt-7 space-y-4">
        <Field label="Email">
          <Input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" />
        </Field>
        <Field label="Password">
          <Input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <FormError message={error} />
        <Button type="submit" className="h-10 w-full" loading={busy}>
          {busy ? "Signing in…" : "Sign in"}
          {!busy && <ArrowRight className="h-4 w-4" />}
        </Button>
      </form>
      <p className="mt-5 text-sm text-ink-2">
        New to AgriFlow?{" "}
        <Link href="/register" className="font-medium text-brand hover:underline">
          Create a workspace
        </Link>
      </p>

      <details className="group mt-8 rounded-xl border border-line bg-surface shadow-card">
        <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-sm font-medium text-ink-2 [&::-webkit-details-marker]:hidden">
          <FlaskConical className="h-4 w-4 text-harvest" />
          Try a synthetic demo account
          <span className="ml-auto text-xs text-ink-3 transition-transform group-open:rotate-90">›</span>
        </summary>
        <div className="border-t border-line px-2 py-2">
          <p className="px-2 pb-2 text-xs text-ink-3">
            Available after running the seed script. Organization data in the demo is invented; market and weather data come from
            real public sources.
          </p>
          <ul>
            {DEMO_ACCOUNTS.map(([local, label, scope]) => (
              <li key={local}>
                <button
                  type="button"
                  className="flex w-full items-center justify-between gap-3 rounded-lg px-2 py-1.5 text-left transition-colors hover:bg-sunken"
                  onClick={() => {
                    setEmail(`${local}@agriflow.demo`);
                    setPassword("Demo@1234");
                  }}
                >
                  <span className="text-[13px] font-medium text-ink">{label}</span>
                  <span className="text-xs text-ink-3">{scope}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
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
