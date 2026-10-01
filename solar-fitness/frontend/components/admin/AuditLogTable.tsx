"use client";

import { useState } from "react";
import type { AuditLogEntry } from "@/lib/types";
import { EmptyState } from "@/components/ui/Primitives";
import { formatDateTime } from "@/lib/utils";
import { ChevronDown, ChevronRight, ScrollText } from "lucide-react";

function hasExpandableDetail(e: AuditLogEntry): boolean {
  return Boolean(
    e.previousValue ||
      e.newValue ||
      e.reason ||
      e.entityType ||
      e.projectId ||
      e.surveyId ||
      e.customerId ||
      e.vendorId ||
      e.ipAddress ||
      e.userAgent
  );
}

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  if (!value) return null;
  return (
    <div className="flex gap-1.5">
      <span className="text-ink-faint">{label}:</span>
      <span className="text-ink-soft">{value}</span>
    </div>
  );
}

function ValueDiff({ previous, next }: { previous?: Record<string, unknown> | null; next?: Record<string, unknown> | null }) {
  if (!previous && !next) return null;
  const keys = Array.from(new Set([...Object.keys(previous ?? {}), ...Object.keys(next ?? {})]));
  if (keys.length === 0) return null;
  return (
    <table className="text-xs">
      <thead>
        <tr className="text-left text-ink-faint">
          <th className="pr-3 font-medium">Field</th>
          <th className="pr-3 font-medium">Previous</th>
          <th className="pr-3 font-medium">New</th>
        </tr>
      </thead>
      <tbody>
        {keys.map((k) => {
          const before = previous?.[k];
          const after = next?.[k];
          const changed = JSON.stringify(before) !== JSON.stringify(after);
          return (
            <tr key={k}>
              <td className="pr-3 py-0.5 font-mono text-ink-soft">{k}</td>
              <td className={`pr-3 py-0.5 font-mono ${changed ? "text-bad line-through" : "text-ink-faint"}`}>
                {before === undefined ? "—" : String(before)}
              </td>
              <td className={`pr-3 py-0.5 font-mono ${changed ? "text-good" : "text-ink-faint"}`}>
                {after === undefined ? "—" : String(after)}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function AuditLogRow({ entry, alt }: { entry: AuditLogEntry; alt: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const expandable = hasExpandableDetail(entry);

  return (
    <>
      <tr className={alt ? "bg-surface" : undefined}>
        <td className="py-2.5 pr-2 align-top">
          {expandable && (
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              aria-expanded={expanded}
              aria-label={expanded ? "Hide details" : "Show details"}
              className="text-ink-faint hover:text-ink"
            >
              {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            </button>
          )}
        </td>
        <td className="py-2.5 pr-3 font-mono tabular text-xs text-ink-soft whitespace-nowrap">{formatDateTime(entry.timestamp)}</td>
        <td className="py-2.5 pr-3 text-ink-soft whitespace-nowrap">
          {entry.actor}
          {entry.actorRole && <span className="ml-1 text-[10px] uppercase text-ink-faint">({entry.actorRole})</span>}
        </td>
        <td className="py-2.5 pr-3">
          <code className="rounded-[3px] bg-surface-2 px-1.5 py-0.5 font-mono text-xs text-slate">{entry.action}</code>
        </td>
        <td className="py-2.5 pr-3 text-ink whitespace-nowrap">{entry.target}</td>
        <td className="py-2.5 pr-3 text-ink-soft max-w-md">{entry.details}</td>
      </tr>
      {expanded && expandable && (
        <tr className={alt ? "bg-surface" : undefined}>
          <td />
          <td colSpan={5} className="pb-3 pr-3 text-xs">
            <div className="space-y-2 rounded-[var(--radius-app)] border border-line bg-paper p-3">
              <div className="grid grid-cols-2 gap-x-6 gap-y-1 sm:grid-cols-3">
                <Field label="Entity type" value={entry.entityType} />
                <Field label="Entity ID" value={entry.entityId} />
                <Field label="Project / site ID" value={entry.projectId} />
                <Field label="Survey ID" value={entry.surveyId} />
                <Field label="Customer ID" value={entry.customerId} />
                <Field label="Vendor ID" value={entry.vendorId} />
                <Field label="IP address" value={entry.ipAddress} />
                <Field label="User agent" value={entry.userAgent} />
              </div>
              {entry.reason && (
                <div>
                  <span className="text-ink-faint">Reason: </span>
                  <span className="text-ink-soft">{entry.reason}</span>
                </div>
              )}
              <ValueDiff previous={entry.previousValue} next={entry.newValue} />
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export function AuditLogTable({ entries }: { entries: AuditLogEntry[] }) {
  if (entries.length === 0) {
    return <EmptyState icon={<ScrollText size={28} strokeWidth={1.5} />} title="No audit events match these filters" description="Try widening your search or date range." />;
  }
  return (
    <div className="overflow-x-auto scrollbar-thin">
      <table className="w-full min-w-[900px] text-sm">
        <caption className="sr-only">Append-only audit log of platform actions</caption>
        <thead>
          <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-ink-faint">
            <th scope="col" className="py-2 pr-2 font-medium" aria-hidden />
            <th scope="col" className="py-2 pr-3 font-medium">Timestamp</th>
            <th scope="col" className="py-2 pr-3 font-medium">Actor</th>
            <th scope="col" className="py-2 pr-3 font-medium">Action</th>
            <th scope="col" className="py-2 pr-3 font-medium">Target</th>
            <th scope="col" className="py-2 pr-3 font-medium">Details</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((e, i) => (
            <AuditLogRow key={e.id} entry={e} alt={i % 2 === 1} />
          ))}
        </tbody>
      </table>
    </div>
  );
}
