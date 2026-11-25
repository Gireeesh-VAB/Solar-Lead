"use client";

import { useState } from "react";
import Link from "next/link";
import { HardHat } from "lucide-react";
import { useAdminInstallations } from "@/lib/query/hooks";
import { Badge, EmptyState, ErrorState, TableSkeleton } from "@/components/ui/Primitives";
import { stageLabel } from "@/components/installations/StageProgress";
import { INSTALLATION_STAGES } from "@/lib/types";
import { formatDate } from "@/lib/utils";

export function InstallationsListClient() {
  const [status, setStatus] = useState("");
  const projects = useAdminInstallations({ status: status || undefined });

  return (
    <div className="space-y-4">
      <select
        value={status}
        onChange={(e) => setStatus(e.target.value)}
        aria-label="Filter by stage"
        className="rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink outline-none focus:border-teal"
      >
        <option value="">All stages</option>
        {INSTALLATION_STAGES.map((s) => (
          <option key={s} value={s}>
            {stageLabel(s)}
          </option>
        ))}
      </select>

      {projects.isLoading && <TableSkeleton rows={6} cols={5} />}
      {projects.isError && (
        <ErrorState
          description="Could not load installation projects."
          onRetry={() => projects.refetch()}
        />
      )}
      {projects.data && projects.data.length === 0 && (
        <EmptyState
          icon={<HardHat size={28} strokeWidth={1.5} />}
          title="No installation projects"
          description="A project appears here the moment a customer accepts a quotation on an approved assessment."
        />
      )}
      {projects.data && projects.data.length > 0 && (
        <div className="overflow-x-auto rounded-[var(--radius-app)] border border-line">
          <table className="w-full min-w-[42rem] text-left text-sm">
            <thead className="bg-surface-2 text-xs uppercase tracking-wide text-ink-faint">
              <tr>
                <th className="px-3 py-2 font-medium">Project</th>
                <th className="px-3 py-2 font-medium">Stage</th>
                <th className="px-3 py-2 font-medium">Progress</th>
                <th className="px-3 py-2 font-medium">Capacity</th>
                <th className="px-3 py-2 font-medium">Opened</th>
              </tr>
            </thead>
            <tbody>
              {projects.data.map((p) => (
                <tr key={p.id} className="border-t border-line hover:bg-surface-2">
                  <td className="px-3 py-2">
                    <Link
                      href={`/admin/installations/${p.id}`}
                      className="font-medium text-teal hover:underline"
                    >
                      {p.id.slice(0, 8)}
                    </Link>
                    <span className="block text-xs text-ink-faint">site {p.siteId.slice(0, 8)}</span>
                  </td>
                  <td className="px-3 py-2">
                    <Badge tone={p.status === "completed" ? "blue" : "neutral"}>
                      {stageLabel(p.status)}
                    </Badge>
                  </td>
                  <td className="px-3 py-2 tabular-nums text-ink-soft">
                    {Math.max(0, p.stageIndex)} / {p.stages.length - 1}
                  </td>
                  <td className="px-3 py-2 tabular-nums text-ink-soft">
                    {p.approvedCapacityKwp} kWp
                  </td>
                  <td className="px-3 py-2 text-ink-soft">{formatDate(p.createdAt)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
