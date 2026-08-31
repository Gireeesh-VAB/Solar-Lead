"use client";

import { useMemo, useState } from "react";
import { useAdminVendors } from "@/lib/query/hooks";
import { TableSkeleton, ErrorState, EmptyState } from "@/components/ui/Primitives";
import { VendorTable } from "@/components/admin/VendorTable";
import { Users } from "lucide-react";

const STATUSES = ["verified", "pending", "rejected", "suspended"];

export function VendorsListClient() {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const vendors = useAdminVendors();

  const items = useMemo(() => {
    let list = vendors.data ?? [];
    if (q) {
      const needle = q.toLowerCase();
      list = list.filter((v) => v.name.toLowerCase().includes(needle) || v.serviceArea.toLowerCase().includes(needle));
    }
    if (status) list = list.filter((v) => v.verificationStatus === status);
    return list;
  }, [vendors.data, q, status]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor="vendor-search" className="sr-only">
          Search vendors
        </label>
        <input
          id="vendor-search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search by name or service area…"
          className="min-w-[220px] flex-1 rounded-[var(--radius-app)] border border-line bg-paper px-3 py-1.5 text-sm text-ink outline-none focus:border-slate"
        />
        <select value={status} onChange={(e) => setStatus(e.target.value)} className="rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink">
          <option value="">All statuses</option>
          {STATUSES.map((s) => (
            <option key={s} value={s} className="capitalize">
              {s}
            </option>
          ))}
        </select>
      </div>

      {vendors.isLoading && <TableSkeleton />}
      {vendors.isError && <ErrorState description="Could not load vendors." onRetry={() => vendors.refetch()} />}
      {vendors.data && items.length === 0 && (
        <EmptyState icon={<Users size={28} strokeWidth={1.5} />} title="No vendors match these filters" description="Try clearing filters." />
      )}
      {vendors.data && items.length > 0 && <VendorTable vendors={items} />}
    </div>
  );
}
