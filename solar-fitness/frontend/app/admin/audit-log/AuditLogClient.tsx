"use client";

import { useMemo, useState } from "react";
import { useAuditLog } from "@/lib/query/hooks";
import { TableSkeleton, ErrorState, EmptyState } from "@/components/ui/Primitives";
import { AuditLogTable } from "@/components/admin/AuditLogTable";
import { ScrollText } from "lucide-react";

export function AuditLogClient() {
  const [q, setQ] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const auditLog = useAuditLog();

  const items = useMemo(() => {
    let list = auditLog.data ?? [];
    if (q) {
      const needle = q.toLowerCase();
      list = list.filter(
        (e) =>
          e.actor.toLowerCase().includes(needle) ||
          e.action.toLowerCase().includes(needle) ||
          e.target.toLowerCase().includes(needle) ||
          e.details.toLowerCase().includes(needle)
      );
    }
    if (from) list = list.filter((e) => new Date(e.timestamp) >= new Date(from));
    if (to) list = list.filter((e) => new Date(e.timestamp) <= new Date(`${to}T23:59:59`));
    return list;
  }, [auditLog.data, q, from, to]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-2">
        <div className="min-w-[220px] flex-1">
          <label htmlFor="audit-search" className="sr-only">
            Search audit log
          </label>
          <input
            id="audit-search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search by actor, action, or target…"
            className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-3 py-1.5 text-sm text-ink outline-none focus:border-slate"
          />
        </div>
        <div>
          <label htmlFor="audit-from" className="mb-1 block text-[11px] text-ink-faint">
            From
          </label>
          <input
            id="audit-from"
            type="date"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
            className="rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
          />
        </div>
        <div>
          <label htmlFor="audit-to" className="mb-1 block text-[11px] text-ink-faint">
            To
          </label>
          <input
            id="audit-to"
            type="date"
            value={to}
            onChange={(e) => setTo(e.target.value)}
            className="rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
          />
        </div>
      </div>

      {auditLog.isLoading && <TableSkeleton />}
      {auditLog.isError && <ErrorState description="Could not load audit log." onRetry={() => auditLog.refetch()} />}
      {auditLog.data && items.length === 0 && (
        <EmptyState icon={<ScrollText size={28} strokeWidth={1.5} />} title="No audit events match these filters" description="Try clearing filters." />
      )}
      {auditLog.data && items.length > 0 && <AuditLogTable entries={items} />}
    </div>
  );
}
