"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button, Field, FormError, Input } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

export default function RegisterPage() {
  const router = useRouter();
  const [form, setForm] = useState({ organization_name: "", full_name: "", email: "", password: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/auth/register", { method: "POST", json: form });
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the server");
      setBusy(false);
    }
  }

  return (
    <>
      <h1 className="text-lg font-semibold">Create a workspace</h1>
      <p className="mt-1 text-sm text-ink-2">You will be the organization admin and can invite your team.</p>
      <form onSubmit={submit} className="mt-5 space-y-4">
        <Field label="Organization name">
          <Input required maxLength={160} value={form.organization_name} onChange={set("organization_name")} />
        </Field>
        <Field label="Your name">
          <Input required maxLength={120} autoComplete="name" value={form.full_name} onChange={set("full_name")} />
        </Field>
        <Field label="Work email">
          <Input type="email" required autoComplete="email" value={form.email} onChange={set("email")} />
        </Field>
        <Field label="Password" hint="At least 8 characters.">
          <Input
            type="password"
            required
            minLength={8}
            autoComplete="new-password"
            value={form.password}
            onChange={set("password")}
          />
        </Field>
        <FormError message={error} />
        <Button type="submit" className="w-full" disabled={busy}>
          {busy ? "Creating…" : "Create workspace"}
        </Button>
      </form>
      <p className="mt-4 text-sm text-ink-2">
        Already have an account?{" "}
        <Link href="/login" className="font-medium text-brand hover:underline">
          Sign in
        </Link>
      </p>
    </>
  );
}
