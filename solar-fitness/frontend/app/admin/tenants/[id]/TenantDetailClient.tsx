"use client";

import { useState } from "react";
import { useTenant, useTenantStatusAction, useUpdateTenantTier } from "@/lib/query/hooks";
import { Card, CardSkeleton, ErrorState, Button } from "@/components/ui/Primitives";
import { ConfirmDialog } from "@/components/admin/ConfirmDialog";
import { formatDate } from "@/lib/utils";
import type { TenantTier } from "@/lib/types";
import { Ban, CheckCircle2 } from "lucide-react";

const TIERS: TenantTier[] = ["starter", "growth", "enterprise"];

export function TenantDetailClient({ tenantId }: { tenantId: string }) {
  const tenant = useTenant(tenantId);
  const updateTier = useUpdateTenantTier(tenantId);
  const statusAction = useTenantStatusAction(tenantId);
  const [pendingTier, setPendingTier] = useState<TenantTier | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);

  if (tenant.isLoading) {
    return (
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <CardSkeleton />
        <CardSkeleton />
      </div>
    );
  }
  if (tenant.isError || !tenant.data) {
    return <ErrorState description="Could not load tenant." onRetry={() => tenant.refetch()} />;
  }

  const t = tenant.data;
  const willSuspend = t.status !== "suspended";

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card className="p-4 space-y-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">Billing &amp; tier</h2>
          <div>
            <p className="text-xs text-ink-faint">Billing contact</p>
            <p className="font-mono tabular text-sm text-ink">{t.billingContactEmail}</p>
          </div>
          <div>
            <p className="text-xs text-ink-faint">Seats</p>
            <p className="font-mono tabular text-sm text-ink">{t.seatCount}</p>
          </div>
          <div>
            <p className="mb-1 text-xs text-ink-faint">Tier</p>
            <div className="flex items-center gap-2">
              <select
                value={pendingTier ?? t.tier}
                onChange={(e) => setPendingTier(e.target.value as TenantTier)}
                className="rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink capitalize"
              >
                {TIERS.map((tier) => (
                  <option key={tier} value={tier} className="capitalize">
                    {tier}
                  </option>
                ))}
              </select>
              <Button
                size="sm"
                disabled={!pendingTier || pendingTier === t.tier || updateTier.isPending}
                onClick={() => pendingTier && updateTier.mutate(pendingTier, { onSuccess: () => setPendingTier(null) })}
              >
                {updateTier.isPending ? "Saving…" : "Save"}
              </Button>
            </div>
          </div>
          <div>
            <p className="text-xs text-ink-faint">Status</p>
            <p className="text-sm capitalize text-ink">{t.status}</p>
          </div>
          <div className="pt-2">
            {willSuspend ? (
              <Button variant="danger" size="sm" onClick={() => setConfirmOpen(true)} disabled={statusAction.isPending}>
                <Ban size={14} strokeWidth={1.75} /> Suspend tenant
              </Button>
            ) : (
              <Button variant="secondary" size="sm" onClick={() => setConfirmOpen(true)} disabled={statusAction.isPending}>
                <CheckCircle2 size={14} strokeWidth={1.75} /> Reinstate tenant
              </Button>
            )}
          </div>
        </Card>

        <Card className="p-4 space-y-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">Usage this month</h2>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <p className="text-xs text-ink-faint">Sites assessed</p>
              <p className="font-mono tabular text-xl text-ink">{t.sitesAssessedThisMonth.toLocaleString("en-IN")}</p>
            </div>
            <div>
              <p className="text-xs text-ink-faint">API calls</p>
              <p className="font-mono tabular text-xl text-ink">{t.apiCallsThisMonth.toLocaleString("en-IN")}</p>
            </div>
          </div>
        </Card>
      </div>

      <Card className="p-4">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-ink-faint">Users</h2>
        <ul className="divide-y divide-line">
          {t.users.map((u) => (
            <li key={u.email} className="flex items-center justify-between gap-3 py-2 text-sm">
              <div>
                <p className="text-ink">{u.name}</p>
                <p className="font-mono tabular text-xs text-ink-faint">{u.email}</p>
              </div>
              <span className="text-xs text-ink-soft">{u.role}</span>
            </li>
          ))}
        </ul>
      </Card>

      <p className="text-xs text-ink-faint">Tenant created {formatDate(t.createdAt)}</p>

      <ConfirmDialog
        open={confirmOpen}
        title={willSuspend ? `Suspend ${t.name}?` : `Reinstate ${t.name}?`}
        description={
          willSuspend
            ? "This immediately blocks all seats on this tenant from accessing the platform. This action can be reversed by reinstating the tenant."
            : "This restores platform access for all seats on this tenant."
        }
        confirmLabel={willSuspend ? "Suspend tenant" : "Reinstate tenant"}
        tone={willSuspend ? "danger" : "primary"}
        pending={statusAction.isPending}
        onCancel={() => setConfirmOpen(false)}
        onConfirm={() =>
          statusAction.mutate(willSuspend ? "suspend" : "reinstate", {
            onSuccess: () => setConfirmOpen(false),
          })
        }
      />
    </div>
  );
}
