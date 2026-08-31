"use client";

import { useMemo, useState } from "react";
import { useAllAssessments } from "@/lib/query/hooks";
import { TableSkeleton, ErrorState, EmptyState, Button } from "@/components/ui/Primitives";
import { VerdictChip } from "@/components/ui/VerdictChip";
import { ConfidenceMeter } from "@/components/ui/ConfidenceMeter";
import { formatDate, formatKwp, VERDICT_LABEL } from "@/lib/utils";
import type { Verdict } from "@/lib/types";
import { ClipboardList } from "lucide-react";

const PAGE_SIZE = 20;

export function AssessmentsListClient() {
  const [q, setQ] = useState("");
  const [verdict, setVerdict] = useState("");
  const [page, setPage] = useState(1);
  const assessments = useAllAssessments({ pageSize: 2000 });

  const filtered = useMemo(() => {
    let list = assessments.data?.items ?? [];
    if (q) {
      const needle = q.toLowerCase();
      list = list.filter((row) => row.siteName.toLowerCase().includes(needle) || row.siteId.toLowerCase().includes(needle) || row.district.toLowerCase().includes(needle));
    }
    if (verdict) list = list.filter((row) => row.assessment.verdict === verdict);
    return list;
  }, [assessments.data, q, verdict]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const pageItems = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor="assessment-search" className="sr-only">
          Search assessments
        </label>
        <input
          id="assessment-search"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setPage(1);
          }}
          placeholder="Search by site name, ID, or district…"
          className="min-w-[220px] flex-1 rounded-[var(--radius-app)] border border-line bg-paper px-3 py-1.5 text-sm text-ink outline-none focus:border-slate"
        />
        <select
          value={verdict}
          onChange={(e) => {
            setVerdict(e.target.value);
            setPage(1);
          }}
          className="rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
        >
          <option value="">All verdicts</option>
          {(Object.keys(VERDICT_LABEL) as Verdict[]).map((v) => (
            <option key={v} value={v}>
              {VERDICT_LABEL[v]}
            </option>
          ))}
        </select>
      </div>

      {assessments.isLoading && <TableSkeleton />}
      {assessments.isError && <ErrorState description="Could not load assessments." onRetry={() => assessments.refetch()} />}
      {assessments.data && filtered.length === 0 && (
        <EmptyState icon={<ClipboardList size={28} strokeWidth={1.5} />} title="No assessments match these filters" description="Try clearing filters." />
      )}
      {assessments.data && filtered.length > 0 && (
        <div className="space-y-3">
          <div className="overflow-x-auto scrollbar-thin">
            <table className="w-full min-w-[900px] text-sm">
              <caption className="sr-only">All platform assessments</caption>
              <thead>
                <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-ink-faint">
                  <th scope="col" className="py-2 pr-3 font-medium">Site</th>
                  <th scope="col" className="py-2 pr-3 font-medium">District / State</th>
                  <th scope="col" className="py-2 pr-3 font-medium">Verdict</th>
                  <th scope="col" className="py-2 pr-3 font-medium text-right">Capacity</th>
                  <th scope="col" className="py-2 pr-3 font-medium">Confidence</th>
                  <th scope="col" className="py-2 pr-3 font-medium">Assessed</th>
                </tr>
              </thead>
              <tbody>
                {pageItems.map((row, i) => (
                  <tr key={row.siteId} className={i % 2 === 1 ? "bg-surface" : undefined}>
                    <td className="py-2.5 pr-3">
                      <span className="font-medium text-ink">{row.siteName}</span>
                      <p className="font-mono tabular text-xs text-ink-faint">{row.siteId}</p>
                    </td>
                    <td className="py-2.5 pr-3 text-ink-soft">{row.district}, {row.state}</td>
                    <td className="py-2.5 pr-3">
                      <VerdictChip verdict={row.assessment.verdict} size="sm" />
                    </td>
                    <td className="py-2.5 pr-3 text-right font-mono tabular text-ink">
                      {row.assessment.capacityKwp > 0 ? formatKwp(row.assessment.capacityKwp) : "—"}
                    </td>
                    <td className="py-2.5 pr-3">
                      <ConfidenceMeter tier={row.assessment.confidence} />
                    </td>
                    <td className="py-2.5 pr-3 font-mono tabular text-xs text-ink-soft">{formatDate(row.assessment.assessedAt)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex items-center justify-between gap-2 text-sm text-ink-soft">
            <span>
              Page {page} of {totalPages} · {filtered.length} assessments
            </span>
            <div className="flex gap-2">
              <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                Previous
              </Button>
              <Button variant="secondary" size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
                Next
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
