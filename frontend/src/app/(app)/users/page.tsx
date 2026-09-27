"use client";

import { useState } from "react";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Field,
  FormError,
  Input,
  Loading,
  Modal,
  PageHeader,
  Select,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { api, ApiError, useApi } from "@/lib/api";
import { ROLE_LABELS, useAuth } from "@/lib/auth";
import { fmtDate } from "@/lib/format";
import type { Region, Role, RoleCode, User, Warehouse } from "@/lib/types";

export default function UsersPage() {
  const { can, me } = useAuth();
  const manage = can("users.manage");
  const users = useApi<User[]>("/users");
  const roles = useApi<Role[]>("/roles");
  const regions = useApi<Region[]>("/regions");
  const warehouses = useApi<Warehouse[]>("/warehouses");
  const [editing, setEditing] = useState<User | "new" | null>(null);

  const regionName = (id: string) => regions.data?.find((r) => r.id === id)?.name ?? "Unknown region";
  const whName = (id: string) => warehouses.data?.find((w) => w.id === id)?.name ?? "Unknown warehouse";

  function scopeText(u: User) {
    if (u.org_wide_access) return "All locations";
    const parts = [...u.region_ids.map((id) => `${regionName(id)} (region)`), ...u.warehouse_ids.map(whName)];
    return parts.length ? parts.join(", ") : "None — sees no warehouses";
  }

  return (
    <div>
      <PageHeader
        title="Users"
        description="Everyone in your organization, their role and the locations they can access."
        actions={manage && <Button onClick={() => setEditing("new")}>Add user</Button>}
      />
      <Card flush>
        {users.loading && !users.data ? (
          <div className="px-4">
            <Loading />
          </div>
        ) : users.error ? (
          <div className="p-4">
            <ErrorState message={users.error.message} onRetry={users.reload} />
          </div>
        ) : !users.data?.length ? (
          <EmptyState title="No users" />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Name</Th>
                <Th>Role</Th>
                <Th>Location scope</Th>
                <Th>Status</Th>
                <Th>Last sign-in</Th>
                {manage && <Th />}
              </tr>
            </thead>
            <tbody>
              {users.data.map((u) => (
                <tr key={u.id}>
                  <Td>
                    <div className="font-medium">
                      {u.full_name}
                      {u.id === me?.user.id && <span className="ml-1.5 text-xs text-ink-3">(you)</span>}
                    </div>
                    <div className="text-xs text-ink-3">{u.email}</div>
                  </Td>
                  <Td>{u.roles.map((r) => ROLE_LABELS[r] ?? r).join(", ")}</Td>
                  <Td className="max-w-64 text-ink-2">{scopeText(u)}</Td>
                  <Td>
                    <Badge tone={u.is_active ? "good" : "neutral"}>{u.is_active ? "Active" : "Deactivated"}</Badge>
                  </Td>
                  <Td className="whitespace-nowrap text-ink-2">{u.last_login_at ? fmtDate(u.last_login_at) : "Never"}</Td>
                  {manage && (
                    <Td right>
                      <Button size="sm" variant="ghost" onClick={() => setEditing(u)}>
                        Edit
                      </Button>
                    </Td>
                  )}
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      {roles.data && (
        <Card title="Roles and permissions" className="mt-6" flush>
          <Table>
            <thead>
              <tr>
                <Th>Role</Th>
                <Th>Permissions</Th>
              </tr>
            </thead>
            <tbody>
              {roles.data.map((r) => (
                <tr key={r.id}>
                  <Td className="align-top">
                    <div className="font-medium">{r.name}</div>
                    <div className="text-xs text-ink-3">{r.description}</div>
                  </Td>
                  <Td>
                    <div className="flex flex-wrap gap-1">
                      {r.permissions.map((p) => (
                        <code key={p} className="rounded bg-canvas px-1.5 py-0.5 font-mono text-[11px] text-ink-2">
                          {p}
                        </code>
                      ))}
                    </div>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Card>
      )}

      {manage && (
        <UserModal
          user={editing}
          roles={roles.data ?? []}
          regions={regions.data ?? []}
          warehouses={warehouses.data ?? []}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            users.reload();
          }}
        />
      )}
    </div>
  );
}

type Form = {
  full_name: string;
  email: string;
  password: string;
  role: RoleCode;
  is_active: boolean;
  org_wide_access: boolean;
  region_ids: string[];
  warehouse_ids: string[];
};

function UserModal({
  user,
  roles,
  regions,
  warehouses,
  onClose,
  onSaved,
}: {
  user: User | "new" | null;
  roles: Role[];
  regions: Region[];
  warehouses: Warehouse[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const isNew = user === "new";
  const [form, setForm] = useState<Form | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loadedFor, setLoadedFor] = useState<unknown>(null);

  if (user !== loadedFor) {
    setLoadedFor(user);
    setError(null);
    setForm(
      user === null
        ? null
        : user === "new"
          ? {
              full_name: "",
              email: "",
              password: "",
              role: "VIEWER",
              is_active: true,
              org_wide_access: false,
              region_ids: [],
              warehouse_ids: [],
            }
          : {
              full_name: user.full_name,
              email: user.email,
              password: "",
              role: user.roles[0] ?? "VIEWER",
              is_active: user.is_active,
              org_wide_access: user.org_wide_access,
              region_ids: user.region_ids,
              warehouse_ids: user.warehouse_ids,
            },
    );
  }

  if (!form) return <Modal open={false} title="" onClose={onClose}>{null}</Modal>;
  const isAdminRole = form.role === "ORGANIZATION_ADMIN";
  const toggle = (key: "region_ids" | "warehouse_ids", id: string) =>
    setForm({ ...form, [key]: form[key].includes(id) ? form[key].filter((x) => x !== id) : [...form[key], id] });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!form || !user) return;
    setBusy(true);
    setError(null);
    try {
      if (isNew) {
        const { is_active: _ignored, ...body } = form;
        void _ignored;
        await api("/users", { method: "POST", json: body });
      } else {
        const { email: _e, password, ...rest } = form;
        void _e;
        await api(`/users/${user.id}`, { method: "PATCH", json: password ? { ...rest, password } : rest });
      }
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open={user !== null} title={isNew ? "Add user" : "Edit user"} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Full name">
            <Input required maxLength={120} value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
          </Field>
          <Field label="Email">
            <Input
              required
              type="email"
              disabled={!isNew}
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
          </Field>
        </div>
        <Field
          label={isNew ? "Initial password" : "Reset password"}
          hint={isNew ? "At least 8 characters. Share it securely." : "Leave blank to keep. Resetting signs the user out."}
        >
          <Input
            type="password"
            required={isNew}
            minLength={8}
            autoComplete="new-password"
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
          />
        </Field>
        <Field label="Role">
          <Select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as RoleCode })}>
            {roles.map((r) => (
              <option key={r.code} value={r.code}>
                {r.name}
              </option>
            ))}
          </Select>
        </Field>

        <fieldset className="rounded-md border border-line p-3">
          <legend className="px-1 text-sm font-medium">Location scope</legend>
          {isAdminRole ? (
            <p className="text-sm text-ink-2">Organization admins always have access to every location.</p>
          ) : (
            <>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={form.org_wide_access}
                  onChange={(e) => setForm({ ...form, org_wide_access: e.target.checked })}
                />
                All locations in the organization
              </label>
              {!form.org_wide_access && (
                <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div>
                    <div className="mb-1 text-xs font-medium text-ink-2">Whole regions</div>
                    <div className="max-h-36 space-y-1 overflow-y-auto">
                      {regions.map((r) => (
                        <label key={r.id} className="flex items-center gap-2 text-sm">
                          <input type="checkbox" checked={form.region_ids.includes(r.id)} onChange={() => toggle("region_ids", r.id)} />
                          {r.name}
                        </label>
                      ))}
                    </div>
                  </div>
                  <div>
                    <div className="mb-1 text-xs font-medium text-ink-2">Individual warehouses</div>
                    <div className="max-h-36 space-y-1 overflow-y-auto">
                      {warehouses.map((w) => (
                        <label key={w.id} className="flex items-center gap-2 text-sm">
                          <input
                            type="checkbox"
                            checked={form.warehouse_ids.includes(w.id)}
                            onChange={() => toggle("warehouse_ids", w.id)}
                          />
                          {w.name}
                        </label>
                      ))}
                    </div>
                  </div>
                  {!form.region_ids.length && !form.warehouse_ids.length && (
                    <p className="text-xs text-warn sm:col-span-2">
                      With no locations selected this user will not see any warehouse or inventory data.
                    </p>
                  )}
                </div>
              )}
            </>
          )}
        </fieldset>

        {!isNew && (
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
            Account active
          </label>
        )}
        <FormError message={error} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={busy}>
            {busy ? "Saving…" : "Save"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
