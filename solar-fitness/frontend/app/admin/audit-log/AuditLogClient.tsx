"use client";

import { useMemo, useState } from "react";
import { useAuditLog } from "@/lib/query/hooks";
import { TableSkeleton, ErrorState, EmptyState } from "@/components/ui/Primitives";
import { AuditLogTable } from "@/components/admin/AuditLogTable";
import type { AuditLogListParams } from "@/lib/api/client";
import { ScrollText } from "lucide-react";

const ENTITY_TYPES = [
  "assessment",
  "vendor_job",
  "installation_project",
  "vendor",
  "vendor_user",
  "user",
  "obstacle",
  "feature_flag",
  "service_api_key",
  "jurisdiction_pack",
  "financial_config",
  "analysis_cache",
];

const ACTOR_ROLES = ["admin", "vendor", "customer"];

function fieldClass() {
  return "rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink outline-none focus:border-slate";
}

export function AuditLogClient() {
  const [q, setQ] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  // Structured filters (spec section 8) — sent as server-side query
  // params, unlike q/from/to which stay client-side substring/date
  // filters over whatever page the server already returned.
  const [entityType, setEntityType] = useState("");
  const [actorRole, setActorRole] = useState("");
  const [projectId, setProjectId] = useState("");
  const [customerId, setCustomerId] = useState("");
  const [vendorId, setVendorId] = useState("");

  const serverParams = useMemo<AuditLogListParams>(
    () => ({
      entityType: entityType || undefined,
      actorRole: actorRole || undefined,
      projectId: projectId || undefined,
      customerId: customerId || undefined,
      vendorId: vendorId || undefined,
    }),
    [entityType, actorRole, projectId, customerId, vendorId]
  );

  const auditLog = useAuditLog(serverParams);

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

  const hasStructuredFilters = entityType || actorRole || projectId || customerId || vendorId;

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
            className={fieldClass()}
          />
        </div>
        <div>
          <label htmlFor="audit-to" className="mb-1 block text-[11px] text-ink-faint">
            To
          </label>
          <input id="audit-to" type="date" value={to} onChange={(e) => setTo(e.target.value)} className={fieldClass()} />
        </div>
      </div>

      <div className="flex flex-wrap items-end gap-2">
        <div>
          <label htmlFor="audit-entity-type" className="mb-1 block text-[11px] text-ink-faint">
            Entity type
          </label>
          <select
            id="audit-entity-type"
            value={entityType}
            onChange={(e) => setEntityType(e.target.value)}
            className={fieldClass()}
          >
            <option value="">All</option>
            {ENTITY_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="audit-actor-role" className="mb-1 block text-[11px] text-ink-faint">
            Actor role
          </label>
          <select
            id="audit-actor-role"
            value={actorRole}
            onChange={(e) => setActorRole(e.target.value)}
            className={fieldClass()}
          >
            <option value="">All</option>
            {ACTOR_ROLES.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="audit-project-id" className="mb-1 block text-[11px] text-ink-faint">
            Project / site ID
          </label>
          <input
            id="audit-project-id"
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
            placeholder="site id"
            className={`${fieldClass()} w-40`}
          />
        </div>
        <div>
          <label htmlFor="audit-customer-id" className="mb-1 block text-[11px] text-ink-faint">
            Customer ID
          </label>
          <input
            id="audit-customer-id"
            value={customerId}
            onChange={(e) => setCustomerId(e.target.value)}
            placeholder="customer id / org"
            className={`${fieldClass()} w-40`}
          />
        </div>
        <div>
          <label htmlFor="audit-vendor-id" className="mb-1 block text-[11px] text-ink-faint">
            Vendor ID
          </label>
          <input
            id="audit-vendor-id"
            value={vendorId}
            onChange={(e) => setVendorId(e.target.value)}
            placeholder="vendor id"
            className={`${fieldClass()} w-40`}
          />
        </div>
        {hasStructuredFilters && (
          <button
            type="button"
            onClick={() => {
              setEntityType("");
              setActorRole("");
              setProjectId("");
              setCustomerId("");
              setVendorId("");
            }}
            className="rounded-[var(--radius-app)] border border-line px-3 py-1.5 text-xs text-ink-soft hover:border-slate hover:text-ink"
          >
            Clear filters
          </button>
        )}
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
