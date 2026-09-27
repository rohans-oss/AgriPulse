"use client";

import { Settings as SettingsIcon, Building2, ScrollText } from "lucide-react";
import { useState } from "react";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  Field,
  FormError,
  Input,
  Loading,
  PageHeader,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { api, ApiError, useApi } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate } from "@/lib/format";
import type { AuditEntry } from "@/lib/types";

export default function SettingsPage() {
  const { me, can, refresh } = useAuth();
  const [name, setName] = useState(me?.organization.name ?? "");
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const audit = useApi<AuditEntry[]>(can("audit.read") ? "/audit-logs?limit=100" : null);

  if (!can("settings.manage")) {
    return (
      <div>
        <PageHeader icon={SettingsIcon} eyebrow="Administration" title="Settings" />
        <ErrorState title="No access" message="Your role cannot change organization settings. Ask an organization admin if you need a change." />
      </div>
    );
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setMsg(null);
    try {
      await api("/organizations/current", { method: "PATCH", json: { name } });
      await refresh();
      audit.reload();
      setMsg("Saved");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <PageHeader icon={SettingsIcon} eyebrow="Administration" title="Settings" description="Organization details and the audit trail of important actions." />

      <Card title="Organization" subtitle="Name and workspace identifier" icon={Building2}>
        <form onSubmit={save} className="max-w-md space-y-4">
          <Field label="Organization name">
            <Input required maxLength={160} value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label="Workspace ID">
            <Input disabled value={me?.organization.slug ?? ""} />
          </Field>
          <FormError message={error} />
          <div className="flex items-center gap-3">
            <Button type="submit" disabled={busy || name === me?.organization.name}>
              {busy ? "Saving…" : "Save changes"}
            </Button>
            {msg && <span className="text-sm text-good">{msg}</span>}
          </div>
        </form>
      </Card>

      {can("audit.read") && (
        <Card title="Audit log" subtitle="Latest 100 important actions in this organization" icon={ScrollText} flush className="mt-6">
          {audit.loading && !audit.data ? (
            <div className="px-4">
              <Loading />
            </div>
          ) : audit.error ? (
            <div className="p-4">
              <ErrorState message={audit.error.message} onRetry={audit.reload} />
            </div>
          ) : !audit.data?.length ? (
            <EmptyState icon={ScrollText} title="No audit entries yet" />
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>When</Th>
                  <Th>Action</Th>
                  <Th>Actor</Th>
                  <Th>Details</Th>
                </tr>
              </thead>
              <tbody>
                {audit.data.map((a) => (
                  <tr key={a.id}>
                    <Td className="whitespace-nowrap text-ink-2">{fmtDate(a.created_at)}</Td>
                    <Td>
                      <code className="font-mono text-xs">{a.action}</code>
                    </Td>
                    <Td className="text-ink-2">{a.actor_email ?? "—"}</Td>
                    <Td className="max-w-md truncate font-mono text-[11px] text-ink-3" >
                      <span title={JSON.stringify(a.details)}>
                        {Object.keys(a.details).length ? JSON.stringify(a.details) : "—"}
                      </span>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>
      )}
    </div>
  );
}
