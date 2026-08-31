"use client";

import { useState } from "react";
import Link from "next/link";
import type { AdminVendorSummary } from "@/lib/types";
import { EmptyState } from "@/components/ui/Primitives";
import { formatDate } from "@/lib/utils";
import { ArrowDown, ArrowUp, Users } from "lucide-react";

const STATUS_TONE: Record<AdminVendorSummary["verificationStatus"], { color: string; bg: string }> = {
  verified: { color: "var(--good)", bg: "var(--good-bg)" },
  pending: { color: "var(--warn)", bg: "var(--warn-bg)" },
  rejected: { color: "var(--bad)", bg: "var(--bad-bg)" },
  suspended: { color: "var(--bad)", bg: "var(--bad-bg)" },
};

type SortKey = "accuracyScore" | "slaCompliancePct" | "activeJobs";

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

  function SortHeader({ label, sortk }: { label: string; sortk: SortKey }) {
    const active = sortKey === sortk;
    return (
      <th scope="col" className="py-2 pr-3 font-medium text-right">
        <button
          type="button"
          onClick={() => toggleSort(sortk)}
          className="inline-flex items-center gap-1 hover:text-ink"
        >
          {label}
          {active ? (sortDir === "asc" ? <ArrowUp size={12} strokeWidth={2} /> : <ArrowDown size={12} strokeWidth={2} />) : null}
        </button>
      </th>
    );
  }

  return (
    <div className="overflow-x-auto scrollbar-thin">
      <table className="w-full min-w-[900px] text-sm">
        <caption className="sr-only">Vendor list sortable by accuracy, SLA compliance, and active jobs</caption>
        <thead>
          <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-ink-faint">
            <th scope="col" className="py-2 pr-3 font-medium">Vendor</th>
            <th scope="col" className="py-2 pr-3 font-medium">Verification</th>
            <th scope="col" className="py-2 pr-3 font-medium">Service area</th>
            <SortHeader label="Accuracy" sortk="accuracyScore" />
            <SortHeader label="SLA %" sortk="slaCompliancePct" />
            <SortHeader label="Active jobs" sortk="activeJobs" />
            <th scope="col" className="py-2 pr-3 font-medium">Joined</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((v, i) => (
            <tr key={v.id} className={i % 2 === 1 ? "bg-surface" : undefined}>
              <td className="py-2.5 pr-3">
                <Link href={`/admin/vendors/${v.id}`} className="font-medium text-ink hover:text-slate">
                  {v.name}
                </Link>
                <p className="font-mono tabular text-xs text-ink-faint">{v.id}</p>
              </td>
              <td className="py-2.5 pr-3">
                <span
                  className="inline-flex items-center rounded-[3px] px-1.5 py-0.5 text-[11px] font-medium capitalize"
                  style={{ color: STATUS_TONE[v.verificationStatus].color, background: STATUS_TONE[v.verificationStatus].bg }}
                >
                  {v.verificationStatus}
                </span>
              </td>
              <td className="py-2.5 pr-3 text-ink-soft">{v.serviceArea}</td>
              <td className="py-2.5 pr-3 text-right font-mono tabular text-ink">{v.accuracyScore || "—"}</td>
              <td className="py-2.5 pr-3 text-right font-mono tabular text-ink">{v.slaCompliancePct || "—"}</td>
              <td className="py-2.5 pr-3 text-right font-mono tabular text-ink">{v.activeJobs}</td>
              <td className="py-2.5 pr-3 font-mono tabular text-xs text-ink-soft">{formatDate(v.joinedAt)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
