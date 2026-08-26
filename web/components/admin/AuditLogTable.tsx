import type { AuditLogEntry } from "@/lib/types";
import { EmptyState } from "@/components/ui/Primitives";
import { formatDateTime } from "@/lib/utils";
import { ScrollText } from "lucide-react";

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
            <th scope="col" className="py-2 pr-3 font-medium">Timestamp</th>
            <th scope="col" className="py-2 pr-3 font-medium">Actor</th>
            <th scope="col" className="py-2 pr-3 font-medium">Action</th>
            <th scope="col" className="py-2 pr-3 font-medium">Target</th>
            <th scope="col" className="py-2 pr-3 font-medium">Details</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((e, i) => (
            <tr key={e.id} className={i % 2 === 1 ? "bg-surface" : undefined}>
              <td className="py-2.5 pr-3 font-mono tabular text-xs text-ink-soft whitespace-nowrap">{formatDateTime(e.timestamp)}</td>
              <td className="py-2.5 pr-3 text-ink-soft whitespace-nowrap">{e.actor}</td>
              <td className="py-2.5 pr-3">
                <code className="rounded-[3px] bg-surface-2 px-1.5 py-0.5 font-mono text-xs text-slate">{e.action}</code>
              </td>
              <td className="py-2.5 pr-3 text-ink whitespace-nowrap">{e.target}</td>
              <td className="py-2.5 pr-3 text-ink-soft max-w-md">{e.details}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
