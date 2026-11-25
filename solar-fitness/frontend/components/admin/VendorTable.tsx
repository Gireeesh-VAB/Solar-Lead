"use client";

import { useState } from "react";
import Link from "next/link";
import type { AdminVendorSummary } from "@/lib/types";
import { Badge, EmptyState } from "@/components/ui/Primitives";
import { formatDate, formatPercent } from "@/lib/utils";
import { ArrowDown, ArrowUp, Users } from "lucide-react";

/** Status colors go through the shared Badge tone vocabulary rather than
 *  hand-rolled inline styles, so a token change only has to happen once
 *  in Primitives.tsx. */
const STATUS_TONE: Record<AdminVendorSummary["verificationStatus"], "green" | "amber" | "red"> = {
  verified: "green",
  pending: "amber",
  rejected: "red",
  suspended: "red",
};

type SortKey = "accuracyScore" | "slaCompliancePct" | "activeJobs";

function SortHeader({
  label,
  sortk,
  sortKey,
  sortDir,
  onToggle,
}: {
  label: string;
  sortk: SortKey;
  sortKey: SortKey | null;
  sortDir: "asc" | "desc";
  onToggle: (key: SortKey) => void;
}) {
  const active = sortKey === sortk;
  return (
    <th scope="col" className="py-2 pr-3 font-medium text-right">
      <button
        type="button"
        onClick={() => onToggle(sortk)}
        className="inline-flex items-center gap-1 hover:text-ink"
      >
        {label}
        {active ? (sortDir === "asc" ? <ArrowUp size={12} strokeWidth={2} /> : <ArrowDown size={12} strokeWidth={2} />) : null}
      </button>
    </th>
  );
}

export function VendorTable({ vendors }: { vendors: AdminVendorSummary[] }) {
  const [sortKey, setSortKey] = useState<SortKey | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  if (vendors.length === 0) {
    return <EmptyState icon={<Users size={28} strokeWidth={1.5} />} title="No vendors match these filters" description="Try widening your search or filters." />;
  }

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  const sorted = sortKey
    ? [...vendors].sort((a, b) => (sortDir === "asc" ? a[sortKey] - b[sortKey] : b[sortKey] - a[sortKey]))
    : vendors;

  return (
    <div className="overflow-x-auto scrollbar-thin">
      <table className="w-full min-w-[900px] text-sm">
        <caption className="sr-only">Vendor list sortable by accuracy, SLA compliance, and active jobs</caption>
        <thead>
          <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-ink-faint">
            <th scope="col" className="py-2 pr-3 font-medium">Vendor</th>
            <th scope="col" className="py-2 pr-3 font-medium">Verification</th>
            <th scope="col" className="py-2 pr-3 font-medium">Service area</th>
            <SortHeader label="Accuracy" sortk="accuracyScore" sortKey={sortKey} sortDir={sortDir} onToggle={toggleSort} />
            <SortHeader label="SLA %" sortk="slaCompliancePct" sortKey={sortKey} sortDir={sortDir} onToggle={toggleSort} />
            <SortHeader label="Active jobs" sortk="activeJobs" sortKey={sortKey} sortDir={sortDir} onToggle={toggleSort} />
            <th scope="col" className="py-2 pr-3 font-medium">Joined</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((v, i) => (
            <tr key={v.id} className={i % 2 === 1 ? "bg-surface" : undefined}>
              <td className="py-2.5 pr-3">
                <Link href={`/admin/vendors/${v.id}`} className="font-medium text-ink hover:text-brand">
                  {v.name}
                </Link>
                <p className="font-mono tabular text-xs text-ink-faint">{v.id}</p>
              </td>
              <td className="py-2.5 pr-3">
                <Badge tone={STATUS_TONE[v.verificationStatus]} className="capitalize">
                  {v.verificationStatus}
                </Badge>
              </td>
              <td className="py-2.5 pr-3 text-ink-soft">{v.serviceArea}</td>
              <td className="py-2.5 pr-3 text-right font-mono tabular text-ink">{v.accuracyScore || "—"}</td>
              <td className="py-2.5 pr-3 text-right font-mono tabular text-ink">{v.slaCompliancePct ? formatPercent(v.slaCompliancePct) : "—"}</td>
              <td className="py-2.5 pr-3 text-right font-mono tabular text-ink">{v.activeJobs}</td>
              <td className="py-2.5 pr-3 font-mono tabular text-xs text-ink-soft">{formatDate(v.joinedAt)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
