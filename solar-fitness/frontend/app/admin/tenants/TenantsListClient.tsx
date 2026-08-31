"use client";

import { useMemo, useState } from "react";
import { useTenants } from "@/lib/query/hooks";
import { TableSkeleton, ErrorState, EmptyState } from "@/components/ui/Primitives";
import { TenantTable } from "@/components/admin/TenantTable";
import { Building2 } from "lucide-react";

const TIERS = ["starter", "growth", "enterprise"];
const STATUSES = ["active", "trial", "suspended", "churned"];

export function TenantsListClient() {
  const [q, setQ] = useState("");
  const [tier, setTier] = useState("");
  const [status, setStatus] = useState("");
  const tenants = useTenants();

  const items = useMemo(() => {
    let list = tenants.data ?? [];
    if (q) {
      const needle = q.toLowerCase();
      list = list.filter((t) => t.name.toLowerCase().includes(needle) || t.id.toLowerCase().includes(needle));
    }
    if (tier) list = list.filter((t) => t.tier === tier);
    if (status) list = list.filter((t) => t.status === status);
    return list;
  }, [tenants.data, q, tier, status]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor="tenant-search" className="sr-only">
          Search tenants
        </label>
        <input
          id="tenant-search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search by name or ID…"
          className="min-w-[220px] flex-1 rounded-[var(--radius-app)] border border-line bg-paper px-3 py-1.5 text-sm text-ink outline-none focus:border-slate"
        />
        <select value={tier} onChange={(e) => setTier(e.target.value)} className="rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink">
          <option value="">All tiers</option>
          {TIERS.map((t) => (
            <option key={t} value={t} className="capitalize">
              {t}
            </option>
          ))}
        </select>
        <select value={status} onChange={(e) => setStatus(e.target.value)} className="rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink">
          <option value="">All statuses</option>
          {STATUSES.map((s) => (
            <option key={s} value={s} className="capitalize">
              {s}
            </option>
          ))}
        </select>
      </div>

      {tenants.isLoading && <TableSkeleton />}
      {tenants.isError && <ErrorState description="Could not load tenants." onRetry={() => tenants.refetch()} />}
      {tenants.data && items.length === 0 && (
        <EmptyState icon={<Building2 size={28} strokeWidth={1.5} />} title="No tenants match these filters" description="Try clearing filters." />
      )}
      {tenants.data && items.length > 0 && <TenantTable tenants={items} />}
    </div>
  );
}
